"""Units must survive ingestion and may not be guessed from plausible numbers."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from logic.cbc import analyze_cbc
from logic.engine import analyze_dataframe, analyze_screening
from logic.units import CANONICAL_UNITS, MEASUREMENT_ALIASES, validate_declared_units
from logic.validation import SCREENING_COLUMNS
from ui.data_io import ScreeningCSVError, read_screening_csv
from utils.reporting import to_json_bytes

BASE = {"age": 30, "sex": "Male", "pregnant": False, "hb_g_dl": 12,
        "hct_percent": 36, "mcv_fl": 88, "mch_pg": 29}


@pytest.mark.parametrize("field,wrong", [("hb_g_dl", "g/L"), ("mcv_fl", "pL"), ("hct_percent", "fraction"), ("mch_pg", "ng")])
@pytest.mark.parametrize("analyzer", [analyze_screening, analyze_cbc])
def test_plausible_value_with_wrong_declared_unit_fails(field, wrong, analyzer):
    result = analyzer({**BASE, "units": {field: wrong}})
    assert result.validation_errors
    value = result.normalized[field]
    assert value is None or value != value
    if analyzer is analyze_screening:
        assert result.clinical_grouping["group_codes"] == ["invalid"]
        assert result.anemia is None
    else:
        assert result.support_code == "invalid"


@pytest.mark.parametrize("field", list(CANONICAL_UNITS))
def test_canonical_units_are_accepted_without_conversion(field):
    errors, invalid, metadata = validate_declared_units({field: None, "units": {field: CANONICAL_UNITS[field]}}, {field: None})
    assert not errors and not invalid
    assert metadata == {field: CANONICAL_UNITS[field]}


@pytest.mark.parametrize("declared", ["g/dL", 1, ["g/dL"], [], [None], True, False])
def test_malformed_units_mapping_does_not_produce_valid_result(declared):
    result = analyze_screening({**BASE, "units": declared})
    assert result.validation_errors
    assert result.clinical_grouping["group_codes"] == ["invalid"]


def test_csv_unit_metadata_is_not_silently_discarded():
    frame, notes = read_screening_csv(
        b"age,sex,hb_g_dl,mcv_fl,mch_pg,mcv_fl_unit\n30,Male,12,88,29,pL\n",
        SCREENING_COLUMNS,
    )
    assert frame.iloc[0]["mcv_fl_unit"] == "pL"
    result = analyze_dataframe(frame).iloc[0]
    assert result["validation_errors"]
    assert json.loads(result["clinical_grouping"])["group_codes"] == ["invalid"]
    assert not any("ไม่รองรับ" in note for note in notes)


def test_conflicting_unit_declarations_fail_even_when_one_is_correct():
    result = analyze_screening({**BASE, "units": {"hb_g_dl": "g/dL"}, "hb_g_dl_unit": "g/L"})
    assert result.validation_errors
    assert not result.severe_anemia_flag  # A mismatched-unit Hb is not usable for urgency.


def test_accepted_unit_metadata_is_retained_in_report():
    result = analyze_screening({**BASE, "units": {"hb_g_dl": "g/dL"}})
    payload = json.loads(to_json_bytes(result))
    assert payload["normalized"]["declared_units"]["hb_g_dl"] == "g/dL"


def test_unknown_declared_field_fails():
    result = analyze_screening({**BASE, "units": {"unknown_measurement": "g/dL"}})
    assert result.validation_errors


@pytest.mark.parametrize("missing", [None, "", "  ", float("nan"), pd.NA, pd.NaT, np.datetime64("NaT", "ns")])
@pytest.mark.parametrize("form", ["mapping", "mapping_value", "suffix"])
@pytest.mark.parametrize("analyzer", [analyze_screening, analyze_cbc])
def test_missing_optional_unit_metadata_preserves_independent_hb_alert(missing, form, analyzer):
    metadata = ({"units": missing} if form == "mapping" else
                {"units": {"hb_g_dl": missing}} if form == "mapping_value" else
                {"hb_g_dl_unit": missing})
    result = analyzer({**BASE, "hb_g_dl": 6, **metadata})
    assert not result.validation_errors
    assert result.normalized["hb_g_dl"] == 6
    if analyzer is analyze_screening:
        assert result.severe_anemia_flag
        assert result.consult_risk == "Critical review"
    else:
        assert result.low_hb_alert


@pytest.mark.parametrize("form", ["mapping", "suffix"])
def test_mixed_dataframe_unit_metadata_never_invalidates_omitted_rows(form):
    # DataFrame fills absent per-row metadata with NaN. The second row must keep
    # the same result and urgent alert as its single-row evaluation.
    correct = {"units": {"hb_g_dl": "g/dL"}} if form == "mapping" else {"hb_g_dl_unit": "g/dL"}
    wrong = {"units": {"hb_g_dl": "g/L"}} if form == "mapping" else {"hb_g_dl_unit": "g/L"}
    urgent = {**BASE, "hb_g_dl": 6}
    frame = pd.DataFrame([{**BASE, **correct}, urgent, {**urgent, **wrong}])
    result = analyze_dataframe(frame)
    single = analyze_screening(urgent)
    assert result.iloc[0]["validation_errors"] == ""
    assert result.iloc[1]["validation_errors"] == ""
    assert result.iloc[1]["top_pattern"] == single.top_pattern
    assert result.iloc[1]["severe_anemia_flag"] == single.severe_anemia_flag
    assert result.iloc[1]["consult_risk"] == "Critical review"
    assert result.iloc[2]["validation_errors"]
    assert not result.iloc[2]["severe_anemia_flag"]


@pytest.mark.parametrize("analyzer", [analyze_screening, analyze_cbc])
@pytest.mark.parametrize("metadata", [
    {"units": {"hb_g_dl": "g/L"}},
    {"units": {"hb_g_dl": "g/L"}, "hb_g_dl_unit": "g/dL"},
    {"units": {"hb_g_dl": "g/dL"}, "hb_g_dl_unit": "g/L"},
])
def test_rejected_string_unit_remains_traceable_without_reusing_measurement(analyzer, metadata):
    result = analyzer({**BASE, "hb_g_dl": 6, **metadata})
    assert result.validation_errors
    assert result.normalized["declared_units"]["hb_g_dl"] == "g/L"
    payload = json.loads(to_json_bytes(result))
    assert payload["normalized"]["declared_units"]["hb_g_dl"] == "g/L"
    assert payload["normalized"]["hb_g_dl"] is None


@pytest.mark.parametrize("alias,target", MEASUREMENT_ALIASES.items())
@pytest.mark.parametrize("form", ["suffix", "mapping"])
def test_alias_value_and_unit_are_validated_together(alias, target, form):
    for unit, rejected in (("%", False), ("1", True)):
        declaration = {alias + "_unit": unit} if form == "suffix" else {"units": {alias: unit}}
        result = analyze_screening({**BASE, alias: 0.05, **declaration})
        assert bool(result.validation_errors) is rejected
        assert result.normalized["declared_units"][target] == unit
        if rejected:
            assert pd.isna(result.normalized[target])
            assert result.clinical_grouping["group_codes"] == ["invalid"]
        else:
            assert result.normalized[target] == 0.05


@pytest.mark.parametrize("alias,target", MEASUREMENT_ALIASES.items())
def test_csv_normalizes_alias_units_without_dropping_or_converting_them(alias, target):
    payload = f"age,sex,hb_g_dl,mcv_fl,mch_pg,{alias},{alias}_unit\n30,Male,12,70,22,0.05,1\n".encode()
    frame, notes = read_screening_csv(payload, SCREENING_COLUMNS)
    assert frame.iloc[0][target + "_unit"] == "1"
    assert not any("ไม่รองรับ" in note for note in notes)
    result = analyze_dataframe(frame).iloc[0]
    assert result["validation_errors"]
    assert pd.isna(result[target])
    assert result["declared_units"][target] == "1"


@pytest.mark.parametrize("alias,target", MEASUREMENT_ALIASES.items())
def test_conflicting_canonical_and_alias_values_are_not_silently_selected(alias, target):
    result = analyze_screening({**BASE, target: 2.5, alias: 5, alias + "_unit": "%"})
    assert result.validation_errors
    assert pd.isna(result.normalized[target])
    assert result.clinical_grouping["group_codes"] == ["invalid"]
    consistent = analyze_screening({**BASE, target: 2.5, alias: "2.5", alias + "_unit": "%"})
    assert not consistent.validation_errors
    assert consistent.normalized[target] == 2.5


@pytest.mark.parametrize("alias,target", MEASUREMENT_ALIASES.items())
@pytest.mark.parametrize("bad_first", [True, False])
def test_alias_and_canonical_units_cannot_override_a_conflicting_declaration(alias, target, bad_first):
    declarations = {target: "%", alias: "1"} if bad_first else {alias: "1", target: "%"}
    result = analyze_screening({**BASE, target: 5, "units": declarations})
    assert result.validation_errors
    assert result.normalized["declared_units"][target] == "1"
    assert pd.isna(result.normalized[target])


@pytest.mark.parametrize("metadata", [{"hba2_unit": "%"}, {"units": {"HbA2": "%"}}, {"unknown_test_unit": "%"}, {"units": {"unknown_test": "%"}}])
def test_direct_orphan_or_unknown_unit_declarations_fail(metadata):
    result = analyze_screening({**BASE, **metadata})
    assert result.validation_errors
    assert result.clinical_grouping["group_codes"] == ["invalid"]


@pytest.mark.parametrize("extra_header,extra_value", [("hba2_unit", "%"), ("unknown_test_unit", "%"), ("units", "g/dL")])
def test_csv_cannot_discard_orphan_or_unknown_unit_metadata(extra_header, extra_value):
    with pytest.raises(ScreeningCSVError, match="หน่วย"):
        read_screening_csv(f"hb_g_dl,mcv_fl,mch_pg,{extra_header}\n12,70,22,{extra_value}\n".encode(), SCREENING_COLUMNS)


def test_duplicate_alias_unit_headers_are_rejected_before_any_value_is_used():
    payload = b"hb_g_dl,mcv_fl,mch_pg,hba2,HbA2_unit,hba2_percent_unit\n12,70,22,5,%,1\n"
    with pytest.raises(ScreeningCSVError, match="ซ้ำ"):
        read_screening_csv(payload, SCREENING_COLUMNS)


@pytest.mark.parametrize("value", [np.bool_(True), np.bool_(False), True, False])
def test_boolean_threshold_override_is_rejected_without_suppressing_valid_low_hb_alert(value):
    result = analyze_screening({**BASE, "hb_g_dl": 6}, {"severe_hb": value})
    assert result.validation_errors
    assert result.thresholds_used["severe_hb"] == 7
    assert result.severe_anemia_flag
    assert result.clinical_grouping["group_codes"] == ["invalid"]
