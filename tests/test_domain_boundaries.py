"""Boundary contracts for domain review engines; no clinical cutoff is changed.

Numeric schema limits are technical validation bounds, not reference intervals.
NaN follows the established missing-value convention; infinities are invalid.
Transfusion has categorical safety gates rather than numeric thresholds.
"""
from copy import deepcopy
import itertools
import json
import math

import pandas as pd
import pytest

from logic.hematology import analyze_domain
from logic.hematology_common import DOMAIN_IDS, load_domain_rules, validate_domain_inputs
from thalab.genetics import match_pcr_bands


RULES = {module: load_domain_rules(module) for module in DOMAIN_IDS}
NUMERIC_FIELDS = [
    pytest.param(module, item, id=f"{module}-{item['key']}")
    for module, rules in RULES.items() for item in rules["fields"] if item["type"] == "number"
]


@pytest.mark.parametrize("module,item", NUMERIC_FIELDS)
@pytest.mark.parametrize("edge,offset", list(itertools.product(("min", "max"), (-1, 0, 1))))
def test_every_numeric_field_validates_both_range_edges(module, item, edge, offset):
    """Check every field, including local limits/divisors, before interpretation."""
    bound = item[edge]
    # Integer count fields retain meaningful whole-cell neighbors.
    step = 1 if item["key"].startswith("diff_") or item["key"] == "nrbc_count" else min(
        0.01, (item["max"] - item["min"]) / 1000, abs(bound) / 10 if bound else 0.01,
    )
    value = bound + offset * step
    normalized, errors, _ = validate_domain_inputs({item["key"]: value}, RULES[module])
    allowed = item["min"] <= value <= item["max"]
    assert bool(errors) is not allowed
    assert normalized[item["key"]] == (float(value) if allowed else None)
    if not allowed:
        result = analyze_domain(module, {item["key"]: value})
        assert result.status == "invalid"
        assert result.validation_errors
        assert result.normalized[item["key"]] is None


@pytest.mark.parametrize("module,item", NUMERIC_FIELDS)
@pytest.mark.parametrize("missing", [None, "", float("nan")], ids=["null", "blank", "nan-is-missing"])
def test_every_numeric_field_missing_is_not_zero_or_normal(module, item, missing):
    result = analyze_domain(module, {item["key"]: missing})
    assert result.normalized[item["key"]] is None
    assert result.status == "incomplete"
    assert not result.alerts
    json.dumps(result.to_dict(), allow_nan=False)


@pytest.mark.parametrize("module,item", NUMERIC_FIELDS)
@pytest.mark.parametrize("invalid", [math.inf, -math.inf, True, "1 g/L"], ids=["inf", "negative-inf", "boolean", "unit-bearing-text"])
def test_every_numeric_field_rejects_nonfinite_boolean_or_unit_text(module, item, invalid):
    result = analyze_domain(module, {item["key"]: invalid})
    assert result.status == "invalid"
    assert result.validation_errors
    assert result.normalized[item["key"]] is None
    json.dumps(result.to_dict(), allow_nan=False)


@pytest.mark.parametrize("module", DOMAIN_IDS)
def test_all_six_engines_without_inputs_remain_incomplete(module):
    result = analyze_domain(module, {})
    assert result.status == "incomplete"
    assert not result.alerts
    assert result.calculated.get("release_authorized", False) is False
    assert result.calculated.get("report_authorized", False) is False
    assert result.calculated.get("vte_excluded_by_tool", False) is False


@pytest.mark.parametrize("anc", [0.499, 0.5, 0.501])
@pytest.mark.parametrize("temperature", [38.299, 38.3, 38.301])
@pytest.mark.parametrize("age", [17.99, 18, 18.01])
def test_wbc_anc_fever_and_adult_scope_boundaries_interact(anc, temperature, age):
    result = analyze_domain("white_cells", {"age": age, "anc_10e9_l": anc,
                                            "temperature_c": temperature, "fever_38_for_hour": "no"})
    assert ("WBC_FEVER_LOW_ANC_ALERT" in result.rules_used) is (anc < 0.5 and temperature >= 38.3)
    assert ("WBC_ADULT_SEVERE_ANC_REVIEW" in result.rules_used) is (age >= 18 and anc < 0.5)
    assert result.calculated["fever_criterion_present"] is (temperature >= 38.3)


@pytest.mark.parametrize("total,consistent", [(98.99, False), (99, True), (99.01, True),
                                               (100.99, True), (101, True), (101.01, False)])
def test_complete_wbc_differential_tolerance_is_inclusive_at_both_edges(total, consistent):
    row = {"neutrophils_percent": total - 40, "lymphocytes_percent": 30,
           "monocytes_percent": 6, "eosinophils_percent": 3, "basophils_percent": 1,
           "immature_granulocytes_percent": 0, "blasts_percent": 0}
    result = analyze_domain("white_cells", row)
    assert result.calculated["differential"]["complete"]
    assert result.calculated["differential"]["consistent"] is consistent
    assert ("WBC_DIFFERENTIAL_INCONSISTENT" in result.rules_used) is not consistent


@pytest.mark.parametrize("measured,wbc,percent,conflict", [
    (5, 10, 39.99, True), (5, 10, 40, False), (5, 10, 40.01, False),
    (0.1, 1, 19.99, False), (0.1, 1, 20, False), (0.1, 1, 20.01, True),
])
def test_wbc_measured_derived_conflict_relative_and_absolute_tolerance(measured, wbc, percent, conflict):
    result = analyze_domain("white_cells", {"anc_10e9_l": measured, "wbc_10e9_l": wbc,
                                            "neutrophils_percent": percent})
    absolute = result.calculated["absolute_counts"]["anc"]
    assert absolute["conflict"] is conflict
    assert absolute["effective"] == measured
    assert absolute["source"] == "measured"


@pytest.mark.parametrize("short", ["wbc", "anc", "alc", "amc", "aec", "abc"])
@pytest.mark.parametrize("value,direction", [(3.99, "LOW"), (4, "WITHIN"), (4.01, "WITHIN"),
                                           (9.99, "WITHIN"), (10, "WITHIN"), (10.01, "HIGH")])
def test_each_wbc_population_uses_local_reference_boundaries(short, value, direction):
    field = "wbc_10e9_l" if short == "wbc" else short + "_10e9_l"
    result = analyze_domain("white_cells", {field: value, short + "_low": 4, short + "_high": 10})
    assert f"WBC_LOCAL_RANGE_{short.upper()}_{direction}" in result.rules_used


@pytest.mark.parametrize("field", ["pb_blasts_percent", "bm_blasts_percent"])
@pytest.mark.parametrize("value,high", [(19.99, False), (20, True), (20.01, True)])
def test_marrow_high_blast_alert_boundary_does_not_assign_diagnosis(field, value, high):
    result = analyze_domain("marrow_malignancies", {field: value})
    assert ("MARROW_HIGH_BLAST_REVIEW_ALERT" in result.rules_used) is high
    groups = {item["group_id"] for item in result.calculated["hypothesis_groups"]}
    assert groups == ({"unassigned_blast_path"} if high or field == "pb_blasts_percent" else set())
    assert "diagnosis" not in result.to_dict()


@pytest.mark.parametrize("value,above", [(3.99, False), (4, False), (4.01, True)])
def test_marrow_local_blast_upper_boundary_is_strict(value, above):
    result = analyze_domain("marrow_malignancies", {"bm_blasts_percent": value, "bm_blasts_high": 4})
    assert ("MARROW_BLASTS_ABOVE_LOCAL_BOUND" in result.rules_used) is above
    assert bool(result.calculated["hypothesis_groups"]) is above
    assert not result.alerts


@pytest.mark.parametrize("field,limit,threshold", [("hb_g_dl", "hb_low", 12),
                                                  ("anc_10e9_l", "anc_low", 1.5),
                                                  ("platelets_10e9_l", "platelets_low", 150)])
@pytest.mark.parametrize("offset", [-0.01, 0, 0.01])
def test_each_marrow_cytopenia_requires_value_below_its_local_limit(field, limit, threshold, offset):
    result = analyze_domain("marrow_malignancies", {field: threshold + offset, limit: threshold})
    assert result.calculated["cytopenias"]["local_count"] == int(offset < 0)


@pytest.mark.parametrize("lineages", [1, 2, 3])
def test_marrow_multiple_cytopenia_threshold_counts_distinct_lineages(lineages):
    measurements = [("hb_g_dl", 10, "hb_low", 12), ("anc_10e9_l", 1, "anc_low", 1.5),
                    ("platelets_10e9_l", 100, "platelets_low", 150)]
    row = {key: number for field, measured, limit, cutoff in measurements[:lineages]
           for key, number in ((field, measured), (limit, cutoff))}
    result = analyze_domain("marrow_malignancies", row)
    assert result.calculated["cytopenias"]["local_count"] == lineages
    assert ("MARROW_MULTIPLE_CYTOPENIA_PATH" in result.rules_used) is (lineages >= 2)


@pytest.mark.parametrize("value,expected", [(149.99, "LOW"), (150, "WITHIN"), (150.01, "WITHIN"),
                                         (449.99, "WITHIN"), (450, "WITHIN"), (450.01, "HIGH")])
def test_platelet_local_reference_boundary_after_quality_gate(value, expected):
    result = analyze_domain("platelets_bleeding", {"platelets_10e9_l": value,
        "platelet_ref_low": 150, "platelet_ref_high": 450,
        "cbc_sample_quality": "acceptable", "platelet_clumps": "no"})
    assert "PLATELET_LOCAL_REFERENCE_" + expected in result.rules_used


@pytest.mark.parametrize("value,alert", [(19.99, True), (20, False), (20.01, False)])
@pytest.mark.parametrize("quality", ["acceptable", "unknown", "clotted"])
def test_local_critical_platelet_boundary_survives_specimen_quality_gate(value, alert, quality):
    result = analyze_domain("platelets_bleeding", {"platelets_10e9_l": value,
        "platelet_critical_low": 20, "cbc_sample_quality": quality})
    assert ("PLATELET_LOCAL_CRITICAL_VERIFY" in result.rules_used) is alert
    assert bool(result.alerts) is alert


@pytest.mark.parametrize("pt_offset,aptt_offset", list(itertools.product((-0.01, 0, 0.01), repeat=2)))
def test_pt_aptt_at_or_either_side_of_local_upper_limits(pt_offset, aptt_offset):
    result = analyze_domain("platelets_bleeding", {"coag_sample_quality": "acceptable",
        "pt_seconds": 14 + pt_offset, "pt_uln_seconds": 14,
        "aptt_seconds": 35 + aptt_offset, "aptt_uln_seconds": 35})
    expected = ("both_prolonged" if pt_offset > 0 and aptt_offset > 0 else
                "isolated_pt" if pt_offset > 0 else "isolated_aptt" if aptt_offset > 0 else "neither_prolonged")
    assert result.calculated["coagulation_pattern"] == expected


@pytest.mark.parametrize("value,low", [(1.99, True), (2, False), (2.01, False)])
def test_fibrinogen_local_lower_limit_is_strict(value, low):
    result = analyze_domain("platelets_bleeding", {"coag_sample_quality": "acceptable",
        "fibrinogen_g_l": value, "fibrinogen_ref_low": 2})
    assert result.calculated["fibrinogen_below_local_lower_limit"] is low
    assert ("FIBRINOGEN_LOCAL_LOW" in result.rules_used) is low


@pytest.mark.parametrize("unit,cutoff", [("ng_ml", 500), ("ug_l", 500), ("mg_l", 0.5)])
@pytest.mark.parametrize("basis", ["feu", "ddu"])
@pytest.mark.parametrize("ratio", [0.999, 1, 1.001])
def test_ddimer_uses_same_assay_unit_and_basis_at_each_cutoff_edge(unit, cutoff, basis, ratio):
    # The supplied cutoff is assay-validated; no FEU/DDU conversion is inferred.
    row = {**RULES["thrombosis"]["examples"][0]["data"], "ddimer_value": cutoff * ratio,
           "ddimer_cutoff": cutoff, "ddimer_unit": unit, "cutoff_unit": unit,
           "ddimer_basis": basis, "cutoff_basis": basis}
    result = analyze_domain("thrombosis", row)
    assert result.calculated["ddimer_to_cutoff_ratio"] == pytest.approx(ratio)
    expected = "at_or_above_cutoff" if ratio >= 1 else "below_cutoff_requires_pathway_review"
    assert result.calculated["ddimer_interpretation"] == expected
    assert result.calculated["vte_excluded_by_tool"] is False


@pytest.mark.parametrize("result_unit,cutoff_unit", list(itertools.permutations(("ng_ml", "ug_l", "mg_l"), 2)))
@pytest.mark.parametrize("result_basis,cutoff_basis", [("feu", "feu"), ("ddu", "ddu"), ("feu", "ddu"), ("ddu", "feu")])
def test_ddimer_units_or_basis_mismatch_cannot_enter_negative_pathway(result_unit, cutoff_unit, result_basis, cutoff_basis):
    row = {**RULES["thrombosis"]["examples"][0]["data"], "ddimer_unit": result_unit,
           "cutoff_unit": cutoff_unit, "ddimer_basis": result_basis, "cutoff_basis": cutoff_basis}
    result = analyze_domain("thrombosis", row)
    assert result.calculated["ddimer_interpretation"] == "not_interpretable"
    assert "ddimer_to_cutoff_ratio" not in result.calculated
    assert result.calculated["vte_excluded_by_tool"] is False


@pytest.mark.parametrize("age,eligible", [(17.99, False), (18, True), (18.01, True)])
def test_vte_low_result_pathway_adult_age_boundary(age, eligible):
    result = analyze_domain("thrombosis", {**RULES["thrombosis"]["examples"][0]["data"], "age": age})
    expected = "below_cutoff_requires_pathway_review" if eligible else "not_used_for_exclusion"
    assert result.calculated["ddimer_interpretation"] == expected
    assert result.calculated["vte_excluded_by_tool"] is False


@pytest.mark.parametrize("population,limit", [("adult", 1), ("term_neonate", 1), ("preterm_neonate", 5)])
@pytest.mark.parametrize("offset", [-0.01, 0, 0.01])
def test_schistocyte_population_boundaries_preserve_neonate_distinction(population, limit, offset):
    result = analyze_domain("morphology_quality", {"population": population, "smear_reviewed": "yes",
                                                   "schistocyte_percent": limit + offset})
    assert result.thresholds_used["schistocyte_percent_upper"] == limit
    assert bool(result.alerts) is (offset > 0 and population != "preterm_neonate")
    assert result.calculated["report_authorized"] is False
    if population == "preterm_neonate" and offset > 0:
        assert len(result.recommendations) > 0


@pytest.mark.parametrize("age,hold", [(5.99, False), (6, False), (6.01, True)])
def test_specimen_stability_local_limit_with_all_quality_controls(age, hold):
    row = deepcopy(RULES["morphology_quality"]["examples"][1]["data"])
    result = analyze_domain("morphology_quality", {**row, "sample_age_hours": age, "local_max_age_hours": 6})
    expected = "hold_for_review" if hold else "eligible_for_professional_review"
    assert result.calculated["quality_gate"] == expected
    assert result.calculated["report_authorized"] is False


@pytest.mark.parametrize("reported,valid", [(99, False), (100, True), (101, False)])
def test_manual_differential_reported_count_must_equal_actual_sum(reported, valid):
    row = deepcopy(RULES["morphology_quality"]["examples"][1]["data"])
    result = analyze_domain("morphology_quality", {**row, "diff_total_reported": reported})
    assert (result.calculated["manual_differential_total"] == 100) is valid
    assert bool(result.calculated["manual_differential_percent"]) is valid
    assert bool(result.validation_errors) is not valid


@pytest.mark.parametrize("component", ["rbc", "plasma"])
@pytest.mark.parametrize("control", ["identity_verified", "specimen_valid", "independent_type_verified"])
@pytest.mark.parametrize("value", [None, "no", "unknown"])
def test_transfusion_categorical_gate_rejects_missing_unknown_and_explicit_failure(component, control, value):
    row = {**RULES["transfusion"]["examples"][0]["data"], "component": component,
           "donor_abo": "A", control: value}
    result = analyze_domain("transfusion", row)
    assert result.calculated["compatibility_review_ready"] is False
    assert result.calculated["abo_table_match"] is None
    assert result.calculated["release_authorized"] is False
    assert "TF_REVIEW_ONLY_NOT_RELEASE" not in result.rules_used


@pytest.mark.parametrize("side", [-1, 1], ids=["below-reference", "above-reference"])
@pytest.mark.parametrize("distance", [24.99, 25, 25.01])
@pytest.mark.parametrize("operator_call", ["Positive", "Negative", "Unknown"])
@pytest.mark.parametrize("controls", ["pass", "fail", "not_confirmed"])
def test_pcr_tolerance_boundary_respects_operator_evidence_and_controls(side, distance, operator_call, controls):
    frame = pd.DataFrame([{"sample_id": "PCR-SYNTHETIC", "target_code": "SEA_DEL",
                           "observed_bp": 730 + side * distance, "result": operator_call}])
    result = match_pcr_bands(frame, tolerance_bp=25, controls_status=controls)
    row = result.iloc[0]
    expected = "unresolved"
    if controls == "pass":
        if operator_call == "Positive" and distance <= 25:
            expected = "detected"
        elif operator_call == "Negative" and distance > 25:
            expected = "not_detected"
    assert row["call"] == expected
    assert bool(row["detected"]) is (expected == "detected")
    assert result.attrs["evaluation"]["tolerance_bp"] == 25
    if distance == 25 and controls == "pass" and operator_call == "Positive":
        # A zero proximity score at the inclusive boundary is still a band match.
        assert row["match_score"] == 0
