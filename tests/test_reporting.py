"""Executable contracts for the synthetic reporting prototype, not clinical limits."""
from __future__ import annotations

from copy import deepcopy
import json
import math

import numpy as np
import pytest

from logic.reporting import PANEL_FIELDS, PANEL_LABELS, TEST_CATALOG, demo_rows, report_input_snapshot, validate_report


def row(code, value, **extra):
    return {"code": code, "result": value, "unit": TEST_CATALOG[code]["unit"], **extra}


def replace(rows, code, **values):
    for item in rows:
        if item["code"] == code:
            item.update(values)
            break
    return rows


def findings(result, rule):
    return [item for item in result["findings"] if item["rule_id"] == rule]


def status(result, rule):
    matches = findings(result, rule)
    assert len(matches) == 1, matches
    return matches[0]["status"]


@pytest.mark.parametrize("panel", PANEL_FIELDS)
def test_every_demo_panel_has_complete_immutable_schema_but_never_releases(panel):
    rows = demo_rows(panel)
    pristine = deepcopy(rows)
    report = validate_report(rows, panel=panel)
    assert rows == pristine
    assert set(PANEL_LABELS) == set(PANEL_FIELDS)
    assert all(isinstance(label, str) and label for label in PANEL_LABELS.values())
    assert tuple(item["code"] for item in rows) == PANEL_FIELDS[panel]
    assert len({item["code"] for item in rows}) == len(rows)
    assert all(set(item) == {"code", "result", "unit", "previous_result", "previous_days"} for item in rows)
    assert report["decision"] == "HOLD"
    assert report["release_eligible"] is False
    assert status(report, "POLICY_NOT_APPROVED") == "HOLD"
    assert status(report, "REQUIRED_TESTS") == "PASS"
    assert status(report, "CLINICAL_POLICY") == "NOT_EVALUATED"
    assert not any(item["status"] == "REJECT" for item in report["findings"])
    assert report["raw_rows"] == rows
    assert json.loads(json.dumps(report, ensure_ascii=False, allow_nan=False)) == report
    rows[0]["result"] = 999
    assert demo_rows(panel) == pristine


def test_user_sample_arithmetic_is_consistent_at_reported_precision_without_invented_limits():
    result = validate_report(demo_rows("cbc"), panel="cbc")
    derived = result["derived"]
    assert derived["mcv_fl"] == pytest.approx(98.38709677419355)
    assert derived["mch_pg"] == pytest.approx(23.225806451612904)
    assert derived["mchc_g_dl"] == pytest.approx(23.60655737704918)
    assert derived["delta_hb_g_dl"] == pytest.approx(-5.6)
    assert derived["delta_hb_percent"] == pytest.approx(-43.75)
    assert derived["previous_days"] == 7
    assert derived["rule_three_difference_percent"] == pytest.approx(8.9)
    for rule in ("INDEX_MCV_FL", "INDEX_MCH_PG", "INDEX_MCHC_G_DL", "DELTA_HB", "RULE_OF_THREE"):
        assert status(result, rule) == "NOT_EVALUATED"
    assert not any(item["rule_id"] in {"MCHC_FAIL", "DELTA_FAIL"} for item in result["findings"])


def test_missing_config_never_turns_derived_formula_agreement_into_a_pass():
    result = validate_report(demo_rows("combined"), panel="combined")
    check_rules = ("DIFFERENTIAL_SUM", "ABSOLUTE_RETIC", "ABSOLUTE_ANC_10E9_L", "ABSOLUTE_ALC_10E9_L",
                   "ABSOLUTE_AMC_10E9_L", "ABSOLUTE_AEC_10E9_L", "ABSOLUTE_ABC_10E9_L")
    for rule in check_rules:
        assert status(result, rule) == "NOT_EVALUATED"


@pytest.mark.parametrize("code,expected", [("mcv_fl", 90.0), ("mch_pg", 30.0), ("mchc_g_dl", 100.0 / 3.0)])
@pytest.mark.parametrize("difference,expected_status", [(0.49, "PASS"), (0.5, "PASS"), (0.51, "HOLD")])
def test_index_comparison_boundaries_are_configured_and_inclusive(code, expected, difference, expected_status):
    rows = [row("hb_g_dl", 12), row("hct_percent", 36), row("rbc_10e12_l", 4), row(code, expected + difference)]
    result = validate_report(rows, panel="cbc", tolerances={"index_abs": {code: 0.5}})
    assert status(result, "INDEX_" + code.upper()) == expected_status
    assert result["derived"][code] == pytest.approx(expected)


@pytest.mark.parametrize("code,dependent", [("rbc_10e12_l", ["INDEX_MCV_FL", "INDEX_MCH_PG"]), ("hct_percent", ["INDEX_MCHC_G_DL"])])
def test_zero_denominator_cannot_be_reported_as_an_arithmetic_pass(code, dependent):
    rows = replace(demo_rows("cbc"), code, result=0)
    result = validate_report(rows, panel="cbc", tolerances={"index_abs": {"mcv_fl": 10000, "mch_pg": 10000, "mchc_g_dl": 10000}})
    assert result["decision"] == "HOLD"
    for rule in dependent:
        assert status(result, rule) == "NOT_EVALUATED"


@pytest.mark.parametrize("value", [True, False, np.bool_(True), "7.2", float("nan"), float("inf"), -float("inf"), -1, [], {}, 1 + 2j])
@pytest.mark.parametrize("field", ["result", "previous_result", "previous_days"])
def test_invalid_scalar_input_is_quarantined_without_boolean_or_nonfinite_coercion(value, field):
    rows = replace(demo_rows("cbc"), "hb_g_dl", **{field: value})
    result = validate_report(rows, panel="cbc")
    assert result["decision"] == "REJECT"
    assert result["release_eligible"] is False
    assert findings(result, "INVALID_VALUE")
    assert not any(item["code"] == "hb_g_dl" for item in result["normalized_rows"])
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("value", [None, "", "  "])
def test_missing_result_is_hold_and_never_assumed_zero_or_normal(value):
    result = validate_report(replace(demo_rows("cbc"), "hb_g_dl", result=value), panel="cbc")
    assert result["decision"] == "HOLD"
    assert status(result, "REQUIRED_TESTS") == "HOLD"
    assert status(result, "INDEX_MCH_PG") == "NOT_EVALUATED"
    assert "mch_pg" not in result["derived"]
    assert "delta_hb_g_dl" not in result["derived"]


@pytest.mark.parametrize("code", ["hct_percent", "retic_percent", "hba2_percent", "neutrophils_percent"])
@pytest.mark.parametrize("value,decision", [(0, "HOLD"), (100, "HOLD"), (100.0001, "REJECT"), (-0.001, "REJECT")])
def test_fraction_domain_is_technical_not_a_clinical_reference_interval(code, value, decision):
    assert validate_report([row(code, value)], panel="combined")["decision"] == decision


def test_rdw_cv_is_not_a_fraction_and_has_no_invented_upper_clinical_limit():
    rows = replace(demo_rows("cbc"), "rdw_percent", result=101, previous_result=102)
    result = validate_report(rows, panel="cbc")
    assert result["decision"] == "HOLD"
    assert not findings(result, "INVALID_VALUE")
    rdw = next(item for item in result["normalized_rows"] if item["code"] == "rdw_percent")
    assert rdw["result"] == 101 and rdw["previous_result"] == 102


@pytest.mark.parametrize("unit", ["g/L", "g/dl", " g/dL", "g/dL ", None, 1, True])
def test_units_are_exact_and_raw_mismatch_survives(unit):
    rows = replace(demo_rows("cbc"), "hb_g_dl", unit=unit)
    result = validate_report(rows, panel="cbc")
    assert result["decision"] == "REJECT"
    assert status(result, "UNIT_MISMATCH") == "REJECT"
    assert result["raw_rows"][0]["unit"] == unit
    assert "mch_pg" not in result["derived"]


def test_ucum_count_units_are_explicit_and_do_not_silently_accept_legacy_display_notation():
    assert TEST_CATALOG["rbc_10e12_l"]["unit"] == "10*12/L"
    assert TEST_CATALOG["wbc_10e9_l"]["unit"] == "10*9/L"
    result = validate_report([row("rbc_10e12_l", 3.1, unit="10^12/L")], panel="cbc")
    assert result["decision"] == "REJECT"


@pytest.mark.parametrize("bad_rows", [None, {}, "cbc", [1], [{"code": "hb_g_dl", "result": 7.2}], [{"code": "hb_g_dl", "result": 7.2, "unit": "g/dL", "patient": "SYNTHETIC"}]])
def test_malformed_row_schema_is_rejected(bad_rows):
    result = validate_report(bad_rows, panel="cbc")
    assert result["decision"] == "REJECT"
    assert findings(result, "ROW_SCHEMA")


@pytest.mark.parametrize("panel", ["", "unknown", None, []])
def test_unknown_panel_is_rejected(panel):
    assert validate_report([], panel=panel)["decision"] == "REJECT"


@pytest.mark.parametrize("code", ["HB", "unknown", None, 1, []])
def test_unknown_code_is_rejected(code):
    result = validate_report([{"code": code, "result": 7.2, "unit": "g/dL"}], panel="cbc")
    assert result["decision"] == "REJECT"
    assert status(result, "UNKNOWN_TEST") == "REJECT"


def test_duplicates_invalidate_all_copies_and_never_choose_first_or_last():
    rows = demo_rows("cbc") + [row("hb_g_dl", 12), row("hb_g_dl", 13)]
    result = validate_report(rows, panel="cbc")
    assert result["decision"] == "REJECT"
    assert len(findings(result, "DUPLICATE_TEST")) == 2
    assert "hb_g_dl" not in {item["code"] for item in result["normalized_rows"]}
    assert "mch_pg" not in result["derived"]
    assert len(result["raw_rows"]) == len(rows)


def test_missing_panel_tests_are_enumerated_and_no_schema_pass_implies_release():
    result = validate_report([], panel="cbc")
    assert status(result, "REQUIRED_TESTS") == "HOLD"
    assert findings(result, "REQUIRED_TESTS")[0]["evidence"]["missing"] == list(PANEL_FIELDS["cbc"])
    assert result["decision"] == "HOLD" and not result["release_eligible"]


@pytest.mark.parametrize("difference,expected", [(0.49, "PASS"), (0.5, "PASS"), (0.51, "HOLD")])
def test_differential_sum_tolerance_boundaries(difference, expected):
    rows = replace(demo_rows("cbc_diff"), "neutrophils_percent", result=60 + difference)
    result = validate_report(rows, panel="cbc_diff", tolerances={"diff_sum_abs": 0.5})
    assert status(result, "DIFFERENTIAL_SUM") == expected
    assert result["derived"]["differential_sum_percent"] == pytest.approx(100 + difference)


def test_partial_differential_is_not_completed_with_zero():
    rows = replace(demo_rows("cbc_diff"), "basophils_percent", result=None)
    result = validate_report(rows, panel="cbc_diff", tolerances={"diff_sum_abs": 100})
    assert status(result, "DIFFERENTIAL_SUM") == "NOT_EVALUATED"
    assert "differential_sum_percent" not in result["derived"]


@pytest.mark.parametrize("difference,expected", [(0.09, "PASS"), (0.1, "PASS"), (0.11, "HOLD")])
def test_absolute_count_tolerance_boundaries(difference, expected):
    rows = replace(demo_rows("cbc_diff"), "anc_10e9_l", result=4.8 + difference)
    result = validate_report(rows, panel="cbc_diff", tolerances={"absolute_count_abs": 0.1})
    assert status(result, "ABSOLUTE_ANC_10E9_L") == expected
    assert result["derived"]["absolute_counts_10e9_l"]["anc_10e9_l"] == pytest.approx(4.8)


def test_retic_absolute_formula_uses_correct_power_of_ten():
    result = validate_report(demo_rows("reticulocyte"), panel="reticulocyte", tolerances={"absolute_count_abs": 0})
    assert result["derived"]["retic_abs_10e9_l"] == pytest.approx(62)
    assert status(result, "ABSOLUTE_RETIC") == "PASS"


def test_zero_absolute_tolerance_does_not_hide_small_nonzero_difference():
    rows = replace(demo_rows("cbc_diff"), "wbc_10e9_l", result=0)
    rows = replace(rows, "anc_10e9_l", result=1e-13)
    result = validate_report(rows, panel="cbc_diff", tolerances={"absolute_count_abs": 0})
    assert status(result, "ABSOLUTE_ANC_10E9_L") == "HOLD"


@pytest.mark.parametrize("absolute,percent,expected_abs,expected_percent", [(5.61, 43.76, "PASS", "PASS"), (5.6, 43.75, "PASS", "PASS"), (5.59, 43.74, "HOLD", "HOLD"), (5.61, 43.74, "PASS", "HOLD")])
def test_delta_thresholds_compare_magnitudes_inclusively_and_independently(absolute, percent, expected_abs, expected_percent):
    result = validate_report(demo_rows("cbc"), panel="cbc", previous_comparable=True,
                             tolerances={"delta_hb_abs": absolute, "delta_hb_percent": percent, "delta_max_days": 7})
    assert status(result, "DELTA_HB_ABS") == expected_abs
    assert status(result, "DELTA_HB_PERCENT") == expected_percent
    assert result["decision"] == "HOLD" and not result["release_eligible"]


@pytest.mark.parametrize("max_days,comparable,changes", [(6.99, True, {}), (7, False, {}), (7, True, {"previous_result": None}), (7, True, {"previous_days": None})])
def test_delta_requires_prior_comparability_and_time_window(max_days, comparable, changes):
    result = validate_report(replace(demo_rows("cbc"), "hb_g_dl", **changes), panel="cbc", previous_comparable=comparable,
                             tolerances={"delta_hb_abs": 10, "delta_hb_percent": 100, "delta_max_days": max_days})
    assert status(result, "DELTA_HB") == "NOT_EVALUATED"


def test_delta_missing_threshold_or_window_is_not_evaluated():
    for config in ({"delta_max_days": 7}, {"delta_hb_abs": 6}):
        result = validate_report(demo_rows("cbc"), panel="cbc", previous_comparable=True, tolerances=config)
        assert status(result, "DELTA_HB") == "NOT_EVALUATED"
    partial = validate_report(demo_rows("cbc"), panel="cbc", previous_comparable=True,
                              tolerances={"delta_hb_abs": 6, "delta_max_days": 7})
    assert status(partial, "DELTA_HB_ABS") == "PASS"
    assert status(partial, "DELTA_HB_PERCENT") == "NOT_EVALUATED"


def test_zero_prior_hb_allows_absolute_difference_but_not_percentage_delta():
    result = validate_report(replace(demo_rows("cbc"), "hb_g_dl", previous_result=0, previous_days=0), panel="cbc", previous_comparable=True,
                             tolerances={"delta_hb_abs": 8, "delta_hb_percent": 100, "delta_max_days": 0})
    assert status(result, "DELTA_HB_ABS") == "PASS"
    assert status(result, "DELTA_HB_PERCENT") == "NOT_EVALUATED"
    assert "delta_hb_percent" not in result["derived"]


@pytest.mark.parametrize("applicable,expected", [(None, "NOT_EVALUATED"), (False, "NOT_APPLICABLE"), (True, "HOLD")])
def test_rule_of_three_needs_explicit_context_and_does_not_override_index_agreement(applicable, expected):
    config = {"rule_three_abs": 0.5, "index_abs": {"mcv_fl": 0.5, "mch_pg": 0.5, "mchc_g_dl": 0.5}}
    if applicable is not None:
        config["rule_three_applicable"] = applicable
    result = validate_report(demo_rows("cbc"), panel="cbc", tolerances=config)
    assert status(result, "RULE_OF_THREE") == expected
    assert status(result, "INDEX_MCHC_G_DL") == "PASS"


@pytest.mark.parametrize("limit,expected", [(8.89, "HOLD"), (8.9, "PASS"), (8.91, "PASS")])
def test_rule_of_three_boundary_is_only_a_configured_demonstration(limit, expected):
    result = validate_report(demo_rows("cbc"), panel="cbc", tolerances={"rule_three_applicable": True, "rule_three_abs": limit})
    assert status(result, "RULE_OF_THREE") == expected


@pytest.mark.parametrize("config", [[], True, {"delta_hb_abs": True}, {"delta_max_days": -1}, {"diff_sum_abs": math.inf}, {"absolute_count_abs": math.nan}, {"rule_three_applicable": "true"}, {"index_abs": True}, {"index_abs": {"mcv": 0.5}}, {"index_abs": {"mcv_fl": -1}}, {"critical_hb": 6}])
def test_malformed_or_unknown_config_holds_without_guessing_a_policy(config):
    result = validate_report(demo_rows("combined"), panel="combined", tolerances=config)
    assert result["decision"] == "HOLD"
    assert findings(result, "CONFIG_INVALID")
    assert not result["release_eligible"]


@pytest.mark.parametrize("comparable", [1, "true", None, np.bool_(True)])
def test_prior_comparability_is_not_truthiness(comparable):
    result = validate_report(demo_rows("cbc"), panel="cbc", previous_comparable=comparable,
                             tolerances={"delta_hb_abs": 100, "delta_max_days": 7})
    assert status(result, "DELTA_HB") == "NOT_EVALUATED"
    assert findings(result, "CONFIG_INVALID")


@pytest.mark.parametrize("flag", ["clotted", "hemolyzed", "insufficient_volume", "unmapped analyzer concern"])
def test_specimen_flags_hold_for_review_without_automatic_specimen_discard(flag):
    result = validate_report(demo_rows("cbc"), panel="cbc", specimen_flags=[flag])
    assert result["decision"] == "HOLD"
    assert status(result, "SPECIMEN_REVIEW") == "HOLD"
    assert findings(result, "SPECIMEN_REVIEW")[0]["evidence"]["flag"] == flag


@pytest.mark.parametrize("flags", [None, "clotted", [None], [""], [True]])
def test_malformed_flag_metadata_rejects_the_record(flags):
    assert validate_report(demo_rows("cbc"), panel="cbc", specimen_flags=flags)["decision"] == "REJECT"


def test_finite_extremes_do_not_export_infinite_derived_results_or_crash():
    rows = replace(demo_rows("cbc"), "hb_g_dl", result=1e308, previous_result=1e-308)
    rows = replace(rows, "rbc_10e12_l", result=1e-308)
    result = validate_report(rows, panel="cbc", tolerances={"index_abs": {"mch_pg": 0.5}})
    assert status(result, "INDEX_MCH_PG") == "NOT_EVALUATED"
    assert "delta_hb_percent" not in result["derived"]
    json.dumps(result, allow_nan=False)


def test_validation_context_and_raw_rows_are_detached_from_mutable_inputs():
    rows = demo_rows("cbc")
    flags = ["hemolyzed"]
    config = {"index_abs": {"mcv_fl": 0.5}}
    result = validate_report(rows, panel="cbc", specimen_flags=flags, tolerances=config, previous_comparable=True)
    expected_rows = report_input_snapshot(rows)
    expected_context = {"specimen_flags": ["hemolyzed"], "tolerances": {"index_abs": {"mcv_fl": 0.5}}, "previous_comparable": True}
    rows[0]["result"] = 99
    flags.append("clotted")
    config["index_abs"]["mcv_fl"] = 100
    assert result["raw_rows"] == expected_rows
    assert result["validation_context"] == expected_context


def test_validation_context_normalizes_only_absent_tolerances_and_preserves_invalid_original_context():
    result = validate_report(demo_rows("cbc"), panel="cbc")
    assert result["validation_context"] == {"specimen_flags": [], "tolerances": {}, "previous_comparable": False}
    invalid = validate_report(demo_rows("cbc"), panel="cbc", specimen_flags="clotted", tolerances={"delta_hb_abs": math.nan}, previous_comparable="true")
    assert invalid["validation_context"] == {"specimen_flags": "clotted", "tolerances": {"delta_hb_abs": {"nonfinite": "nan"}}, "previous_comparable": "true"}
    assert findings(invalid, "CONFIG_INVALID")
    json.dumps(invalid, allow_nan=False)


def test_public_snapshot_has_the_same_nonfinite_encoding_as_validation():
    rows = replace(demo_rows("cbc"), "hb_g_dl", result=math.inf)
    result = validate_report(rows, panel="cbc")
    assert report_input_snapshot(rows) == result["raw_rows"]
    assert result["raw_rows"][0]["result"] == {"nonfinite": "inf"}
