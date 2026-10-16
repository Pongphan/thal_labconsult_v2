"""Declared units survive every domain input route and cannot change scale silently."""
from __future__ import annotations

import csv
from io import StringIO
import json

import numpy as np
import pandas as pd
import pytest

from logic.hematology import analyze_domain
from logic.hematology_common import DOMAIN_IDS, load_domain_rules
from logic.units import canonical_unit
from ui.data_io import ScreeningCSVError
from ui.domain_io import read_domain_csv
from utils.domain_reporting import report_json, report_metadata


RULES = {module: load_domain_rules(module) for module in DOMAIN_IDS}
STATIC_FIELDS = [
    pytest.param(module, item, id=f"{module}-{item['key']}")
    for module, rules in RULES.items() for item in rules["fields"]
    if item["type"] == "number" and item["key"] not in {"ddimer_value", "ddimer_cutoff"}
]


def csv_payload(headers, values):
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerow(values)
    return output.getvalue().encode("utf-8")


@pytest.mark.parametrize("module,item", STATIC_FIELDS)
@pytest.mark.parametrize("route", ["mapping", "suffix", "csv"])
def test_every_static_domain_number_retains_and_validates_its_declared_unit(module, item, route):
    key, value = item["key"], item["min"]
    for unit, rejected in ((item["unit"], False), ("WRONG_SCALE", True)):
        if route == "csv":
            rows, notes = read_domain_csv(csv_payload([key, key + "_unit"], [value, unit]), RULES[module])
            assert rows[0][key + "_unit"] == unit
            assert not notes
            data = rows[0]
        else:
            data = {key: value}
            data.update({"units": {key: unit}} if route == "mapping" else {key + "_unit": unit})
        result = analyze_domain(module, data)
        assert bool(result.validation_errors) is rejected
        assert result.normalized[key] == (None if rejected else float(value))
        assert result.normalized["declared_units"][key] == (unit if rejected else canonical_unit(unit))
        if rejected:
            assert result.status == "invalid"
        payload = json.loads(report_json(result, report_metadata(module, "demo")))
        assert payload["result"]["normalized"]["declared_units"] == result.normalized["declared_units"]


@pytest.mark.parametrize("module,item", STATIC_FIELDS)
@pytest.mark.parametrize("value", [np.bool_(True), np.bool_(False)])
def test_every_domain_numeric_field_rejects_numpy_boolean(module, item, value):
    result = analyze_domain(module, {item["key"]: value})
    assert result.status == "invalid"
    assert result.validation_errors
    assert result.normalized[item["key"]] is None


def test_numpy_boolean_anc_cannot_create_a_zero_count_fever_alert():
    result = analyze_domain("white_cells", {"age": 30, "anc_10e9_l": np.bool_(False), "temperature_c": 39, "fever_38_for_hour": "no"})
    assert result.status == "invalid"
    assert result.normalized["anc_10e9_l"] is None
    assert "WBC_FEVER_LOW_ANC_ALERT" not in result.rules_used


@pytest.mark.parametrize("missing", [None, "", "  ", float("nan"), pd.NA, pd.NaT])
@pytest.mark.parametrize("form", ["mapping", "mapping_value", "suffix"])
def test_missing_optional_domain_units_preserve_independent_urgent_evidence(missing, form):
    data = {"age": 30, "anc_10e9_l": 0.2, "temperature_c": 39, "fever_38_for_hour": "no"}
    data.update({"units": missing} if form == "mapping" else {"units": {"anc_10e9_l": missing}} if form == "mapping_value" else {"anc_10e9_l_unit": missing})
    result = analyze_domain("white_cells", data)
    assert not result.validation_errors
    assert result.status == "urgent"
    assert "WBC_FEVER_LOW_ANC_ALERT" in result.rules_used


def test_mixed_csv_rows_keep_unit_metadata_on_correct_wrong_and_omitted_rows():
    rows, notes = read_domain_csv(b"age,anc_10e9_l,anc_10e9_l_unit,temperature_c,fever_38_for_hour\n30,0.2,10^9/L,39,no\n30,0.2,,39,no\n30,0.2,10^12/L,39,no\n", RULES["white_cells"])
    assert not notes
    results = [analyze_domain("white_cells", row) for row in rows]
    assert [result.status for result in results] == ["urgent", "urgent", "invalid"]
    assert all("WBC_FEVER_LOW_ANC_ALERT" in result.rules_used for result in results[:2])
    assert "WBC_FEVER_LOW_ANC_ALERT" not in results[2].rules_used
    assert results[2].normalized["declared_units"]["anc_10e9_l"] == "10^12/L"


def test_bad_units_do_not_suppress_valid_independent_bleeding_symptom_alert():
    result = analyze_domain("platelets_bleeding", {"platelets_10e9_l": 5, "platelets_10e9_l_unit": "10^12/L", "bleeding_severity": "major"})
    assert result.status == "invalid"
    assert result.normalized["platelets_10e9_l"] is None
    assert "BLEEDING_URGENT_SYMPTOMS" in result.rules_used
    assert result.alerts


@pytest.mark.parametrize("first", [True, False])
def test_domain_conflicting_map_and_suffix_metadata_cannot_choose_the_valid_unit(first):
    good, bad = "10^9/L", "10^12/L"
    result = analyze_domain("white_cells", {"wbc_10e9_l": 5, "units": {"wbc_10e9_l": good if first else bad}, "wbc_10e9_l_unit": bad if first else good})
    assert result.status == "invalid"
    assert result.normalized["wbc_10e9_l"] is None
    assert result.normalized["declared_units"]["wbc_10e9_l"] == bad


@pytest.mark.parametrize("metadata", ["g/L", [], [None], True, False])
def test_malformed_domain_units_mapping_is_rejected(metadata):
    result = analyze_domain("white_cells", {"wbc_10e9_l": 5, "units": metadata})
    assert result.status == "invalid"
    assert result.normalized["wbc_10e9_l"] is None


@pytest.mark.parametrize("data", [{"wbc_10e9_l_unit": "10^9/L"}, {"units": {"wbc_10e9_l": "10^9/L"}}, {"unknown_value_unit": "g/L"}, {"units": {"unknown_value": "g/L"}}])
def test_domain_orphan_and_unknown_unit_metadata_fail(data):
    result = analyze_domain("white_cells", data)
    assert result.status == "invalid"
    assert result.validation_errors


@pytest.mark.parametrize("header,value", [("anc_10e9_l_unit", "10^9/L"), ("unknown_value_unit", "g/L"), ("units", "g/L")])
def test_domain_csv_rejects_unknown_or_orphan_units_before_dropping_columns(header, value):
    with pytest.raises(ScreeningCSVError, match="หน่วย"):
        read_domain_csv(csv_payload(["wbc_10e9_l", header], [5, value]), RULES["white_cells"])


@pytest.mark.parametrize("key,selector", [("ddimer_value", "ddimer_unit"), ("ddimer_cutoff", "cutoff_unit")])
@pytest.mark.parametrize("selected,unit", [("ng_ml", "ng/mL"), ("ug_l", "µg/L"), ("mg_l", "mg/L")])
@pytest.mark.parametrize("route", ["mapping", "suffix", "csv"])
def test_dynamic_ddimer_declaration_must_match_selected_unit_without_conversion(key, selector, selected, unit, route):
    for declared, rejected in ((unit, False), ("g/L", True)):
        data = {key: 1, selector: selected}
        if route == "mapping":
            data["units"] = {key: declared}
        elif route == "suffix":
            data[key + "_unit"] = declared
        else:
            rows, _ = read_domain_csv(csv_payload([key, selector, key + "_unit"], [1, selected, declared]), RULES["thrombosis"])
            data = rows[0]
        result = analyze_domain("thrombosis", data)
        assert bool(result.validation_errors) is rejected
        assert result.normalized[key] == (None if rejected else 1)
        assert result.normalized["declared_units"][key] == declared


def test_ddimer_explicit_metadata_never_invents_missing_unit_selector_or_basis():
    missing_selector = analyze_domain("thrombosis", {"ddimer_value": 1, "ddimer_value_unit": "mg/L"})
    assert missing_selector.status == "invalid"
    assert missing_selector.normalized["ddimer_unit"] == "unknown"
    assert missing_selector.normalized["ddimer_value"] is None
    unknown_basis = analyze_domain("thrombosis", {"ddimer_value": 1, "ddimer_unit": "mg_l", "ddimer_value_unit": "mg/L", "ddimer_cutoff": 2, "cutoff_unit": "mg_l", "cutoff_validated": "yes"})
    assert not unknown_basis.validation_errors
    assert unknown_basis.calculated["ddimer_interpretation"] == "not_interpretable"
    assert "DDIMER_MISSING_ASSAY_GATE" in unknown_basis.rules_used


@pytest.mark.parametrize("key", ["ddimer_value", "ddimer_cutoff"])
@pytest.mark.parametrize("value", [np.bool_(True), np.bool_(False)])
def test_dynamic_ddimer_numbers_also_reject_numpy_booleans(key, value):
    result = analyze_domain("thrombosis", {key: value})
    assert result.status == "invalid"
    assert result.normalized[key] is None
