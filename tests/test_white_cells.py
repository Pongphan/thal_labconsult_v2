"""White-cell calculation, evidence precedence and urgent-review boundaries."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from logic.hematology_common import load_domain_rules
from logic.white_cells import analyze_white_cells


class WhiteCellTests(unittest.TestCase):
    def full_differential(self, **updates):
        return {"age": 35, "wbc_10e9_l": 6, "neutrophils_percent": 60,
                "lymphocytes_percent": 30, "monocytes_percent": 6,
                "eosinophils_percent": 3, "basophils_percent": 1,
                "immature_granulocytes_percent": 0, "blasts_percent": 0, **updates}

    def test_blank_and_age_only_are_incomplete_and_unknown_is_preserved(self):
        for data in ({}, {"age": 35}):
            result = analyze_white_cells(data)
            self.assertEqual(result.status, "incomplete")
            self.assertEqual(result.normalized["smear_blasts"], "unknown")
            self.assertIsNone(result.calculated["fever_criterion_present"])
            self.assertFalse(result.alerts)

    def test_complete_and_partial_differentials(self):
        result = analyze_white_cells(self.full_differential())
        self.assertEqual(result.status, "review")
        self.assertTrue(result.calculated["differential"]["complete"])
        self.assertAlmostEqual(result.calculated["absolute_counts"]["anc"]["effective"], 3.6)
        self.assertEqual(result.calculated["absolute_counts"]["anc"]["source"], "calculated")
        partial = analyze_white_cells({"wbc_10e9_l": 5, "neutrophils_percent": 50})
        self.assertEqual(partial.calculated["differential"]["reported_categories"], 1)
        self.assertFalse(partial.calculated["differential"]["complete"])
        self.assertEqual(partial.calculated["absolute_counts"]["anc"]["effective"], 2.5)
        self.assertNotIn("alc", partial.calculated["absolute_counts"])
        self.assertIsNone(partial.normalized["lymphocytes_percent"])

    def test_inconsistent_total_blocks_derived_counts(self):
        for data in (self.full_differential(neutrophils_percent=50),
                     {"wbc_10e9_l": 5, "neutrophils_percent": 80, "lymphocytes_percent": 30}):
            result = analyze_white_cells(data)
            self.assertEqual(result.status, "invalid")
            self.assertIn("WBC_DIFFERENTIAL_INCONSISTENT", result.rules_used)
            self.assertFalse(result.calculated["absolute_counts"])

    def test_measured_absolute_precedence_and_conflict(self):
        result = analyze_white_cells(self.full_differential(anc_10e9_l=1))
        absolute = result.calculated["absolute_counts"]["anc"]
        self.assertEqual(absolute["effective"], 1)
        self.assertAlmostEqual(absolute["derived"], 3.6)
        self.assertTrue(absolute["conflict"])
        self.assertIn("WBC_MEASURED_DERIVED_CONFLICT", result.rules_used)

    def test_inconsistent_differential_does_not_discard_measured_anc(self):
        result = analyze_white_cells(self.full_differential(neutrophils_percent=50, anc_10e9_l=0.3, temperature_c=38.5))
        self.assertEqual(result.status, "invalid")
        self.assertIsNone(result.calculated["absolute_counts"]["anc"]["derived"])
        self.assertEqual(result.calculated["absolute_counts"]["anc"]["effective"], 0.3)
        self.assertIn("WBC_FEVER_LOW_ANC_ALERT", result.rules_used)
        self.assertTrue(result.alerts)

    def test_absolute_counts_cannot_exceed_total_wbc(self):
        for data in ({"wbc_10e9_l": 2, "anc_10e9_l": 3},
                     {"wbc_10e9_l": 2, "anc_10e9_l": 1.5, "alc_10e9_l": 1}):
            self.assertEqual(analyze_white_cells(data).status, "invalid")

    def test_mixed_measured_and_derived_counts_cannot_exceed_wbc(self):
        result = analyze_white_cells({"age": 35, "wbc_10e9_l": 4, "anc_10e9_l": 3,
                                      "lymphocytes_percent": 75})
        self.assertEqual(result.status, "invalid")
        self.assertIn("WBC_ABSOLUTE_TOTAL_INCONSISTENT", result.rules_used)
        total = result.calculated["absolute_total"]
        self.assertEqual(total["known_total_10e9_l"], 6)
        self.assertFalse(total["consistent"])
        self.assertEqual(total["components"]["anc"]["source"], "measured")
        self.assertEqual(total["components"]["alc"]["source"], "calculated")

    def test_absolute_total_counts_each_population_once_and_keeps_missing_unknown(self):
        result = analyze_white_cells(self.full_differential(anc_10e9_l=3.6))
        self.assertFalse(result.validation_errors)
        self.assertAlmostEqual(result.calculated["absolute_total"]["known_total_10e9_l"], 6)
        self.assertTrue(result.calculated["absolute_total"]["complete"])
        partial = analyze_white_cells({"wbc_10e9_l": 4, "anc_10e9_l": 2, "lymphocytes_percent": 25})
        self.assertFalse(partial.validation_errors)
        self.assertEqual(partial.calculated["absolute_total"]["known_total_10e9_l"], 3)
        self.assertFalse(partial.calculated["absolute_total"]["complete"])
        self.assertNotIn("amc", partial.calculated["absolute_total"]["components"])
        for data in ({}, {"wbc_10e9_l": 4}, {"anc_10e9_l": 3}):
            missing = analyze_white_cells(data).calculated["absolute_total"]
            self.assertIsNone(missing["consistent"])
        self.assertIsNone(analyze_white_cells({}).calculated["absolute_total"]["known_total_10e9_l"])

    def test_absolute_total_includes_nonoverlapping_ig_and_blasts(self):
        for field, short in (("immature_granulocytes_percent", "ig"), ("blasts_percent", "blasts")):
            with self.subTest(field=field):
                result = analyze_white_cells({"wbc_10e9_l": 4, "anc_10e9_l": 4, field: 5})
                self.assertEqual(result.status, "invalid")
                self.assertAlmostEqual(result.calculated["absolute_total"]["known_total_10e9_l"], 4.2)
                self.assertEqual(result.calculated["absolute_total"]["components"][short]["source"], "calculated")
                if short == "blasts":
                    self.assertIn("WBC_PERIPHERAL_BLAST_REVIEW", result.rules_used)
                    self.assertTrue(result.alerts)

    def test_absolute_total_retains_tolerance_and_independent_urgent_alerts(self):
        for lymphocytes, expected in ((77.5, "review"), (77.51, "invalid")):
            result = analyze_white_cells({"age": 35, "wbc_10e9_l": 4, "anc_10e9_l": 1,
                                          "lymphocytes_percent": lymphocytes})
            self.assertEqual(result.status, expected)
        result = analyze_white_cells({"age": 35, "wbc_10e9_l": 4, "anc_10e9_l": 0.3,
                                      "lymphocytes_percent": 100, "temperature_c": 38.5})
        self.assertEqual(result.status, "invalid")
        self.assertIn("WBC_FEVER_LOW_ANC_ALERT", result.rules_used)
        self.assertTrue(result.alerts)

    def test_complete_absolute_total_requires_both_tolerance_bounds(self):
        for anc, expected in ((1, "invalid"), (3.49, "invalid"), (3.5, "review"),
                              (3.6, "review"), (3.7, "review"), (3.71, "invalid")):
            with self.subTest(anc=anc):
                result = analyze_white_cells(self.full_differential(anc_10e9_l=anc))
                self.assertEqual(result.status, expected)
                total = result.calculated["absolute_total"]
                self.assertTrue(total["complete"])
                self.assertEqual(total["consistent"], expected == "review")
                self.assertAlmostEqual(total["known_total_10e9_l"], anc + 2.4)
                self.assertEqual("WBC_ABSOLUTE_TOTAL_MISMATCH" in result.rules_used, expected == "invalid")

    def test_complete_low_total_keeps_independent_anc_fever_alert(self):
        result = analyze_white_cells(self.full_differential(anc_10e9_l=0.3, temperature_c=38.5))
        self.assertEqual(result.status, "invalid")
        self.assertIn("WBC_ABSOLUTE_TOTAL_MISMATCH", result.rules_used)
        self.assertIn("WBC_FEVER_LOW_ANC_ALERT", result.rules_used)
        self.assertTrue(result.alerts)

    def test_zero_is_observed_and_missing_wbc_cannot_generate_absolute(self):
        result = analyze_white_cells({"age": 30, "anc_10e9_l": 0})
        self.assertEqual(result.calculated["absolute_counts"]["anc"]["effective"], 0)
        result = analyze_white_cells({"neutrophils_percent": 50})
        self.assertFalse(result.calculated["absolute_counts"])
        self.assertTrue(result.validation_warnings)

    def test_local_ranges_are_required_and_boundaries_are_inclusive(self):
        result = analyze_white_cells({"wbc_10e9_l": 20})
        self.assertFalse(result.thresholds_used["local_reference_intervals"])
        self.assertFalse(any(item.startswith("WBC_LOCAL_RANGE") for item in result.rules_used))
        for value, direction in ((3.99, "LOW"), (4, "WITHIN"), (10, "WITHIN"), (10.01, "HIGH")):
            result = analyze_white_cells({"wbc_10e9_l": value, "wbc_low": 4, "wbc_high": 10})
            self.assertIn("WBC_LOCAL_RANGE_WBC_" + direction, result.rules_used)
            self.assertEqual(result.thresholds_used["local_reference_intervals"]["wbc"], {"low": 4, "high": 10, "unit": "10^9/L"})
        self.assertEqual(analyze_white_cells({"wbc_low": 10, "wbc_high": 4}).status, "invalid")

    def test_adult_fever_and_anc_boundaries(self):
        for anc, temperature, expected in ((0.499, 38.3, True), (0.5, 38.3, False), (0.3, 38.29, False)):
            result = analyze_white_cells({"age": 18, "anc_10e9_l": anc, "temperature_c": temperature})
            self.assertEqual(bool(result.alerts), expected)
        sustained = analyze_white_cells({"age": 40, "anc_10e9_l": 0.3, "temperature_c": 38, "fever_38_for_hour": "yes"})
        self.assertEqual(sustained.status, "urgent")
        self.assertTrue(sustained.calculated["fever_criterion_present"])
        missing_duration = analyze_white_cells({"age": 40, "anc_10e9_l": 0.3, "temperature_c": 38})
        self.assertIsNone(missing_duration.calculated["fever_criterion_present"])
        self.assertFalse(missing_duration.alerts)

    def test_unknown_or_child_age_never_gets_adult_severity(self):
        for age in (None, 17.99):
            result = analyze_white_cells({"age": age, "anc_10e9_l": 0.3, "temperature_c": 38.5})
            self.assertNotIn("WBC_ADULT_SEVERE_ANC_REVIEW", result.rules_used)
            self.assertTrue(result.alerts)
            self.assertTrue(result.validation_warnings)

    def test_instrument_flag_needs_review_but_observed_blasts_prompt_alert(self):
        instrument = analyze_white_cells({"instrument_blast_flag": "yes"})
        self.assertEqual(instrument.status, "review")
        self.assertFalse(instrument.alerts)
        self.assertTrue(instrument.recommendations)
        observed = analyze_white_cells({"blasts_percent": 1, "smear_blasts": "no"})
        self.assertEqual(observed.status, "urgent")
        self.assertIn("WBC_PERIPHERAL_BLAST_REVIEW", observed.rules_used)
        self.assertTrue(observed.validation_warnings)

    def test_invalid_inputs_do_not_hide_independent_alerts(self):
        for value in (-1, "bad", float("inf"), True):
            result = analyze_white_cells({"age": 30, "anc_10e9_l": 0.3, "temperature_c": 38.5, "wbc_10e9_l": value})
            self.assertEqual(result.status, "invalid")
            self.assertTrue(result.alerts)
        result = analyze_white_cells({"anc_10e9_l": "bad", "temperature_c": 38.5})
        self.assertFalse(result.alerts)

    def test_examples_and_json_exports_preserve_provenance_and_drop_unknown_fields(self):
        for example in load_domain_rules("white_cells")["examples"]:
            result = analyze_white_cells(example["data"])
            self.assertNotEqual(result.status, "invalid")
            json.dumps(result.to_dict(), ensure_ascii=False, allow_nan=False)
        result = analyze_white_cells({"patient_name": "DO NOT RETAIN", "anc_10e9_l": float("nan")})
        self.assertNotIn("patient_name", result.normalized)
        self.assertNotIn("DO NOT RETAIN", json.dumps(result.to_dict()))
        self.assertEqual(len(result.ruleset_hash), 64)
        self.assertTrue(result.sources)

    def test_config_cannot_change_percentage_units_or_sustained_fever_assertion(self):
        for key, value in (("differential_total", 99), ("fever_sustained_c", 39),
                           ("fever_sustained_hours", 2), ("fever_single_c", 37),
                           ("severe_anc_10e9_l", float("nan")), ("adult_min_age", True)):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                config = load_domain_rules("white_cells")
                config["thresholds"][key] = value
                path = Path(directory) / "white_cells_rules.json"
                path.write_text(json.dumps(config), encoding="utf-8")
                with patch("logic.hematology_common.DATA_DIR", Path(directory)):
                    with self.assertRaises(ValueError):
                        analyze_white_cells({"anc_10e9_l": 0.3})

    def test_malformed_config_missing_threshold_or_reversed_bounds_fails_closed(self):
        for error in ("missing_threshold", "reversed_bounds"):
            with self.subTest(error=error), tempfile.TemporaryDirectory() as directory:
                config = load_domain_rules("white_cells")
                if error == "missing_threshold":
                    del config["thresholds"]["absolute_conflict_floor"]
                else:
                    config["fields"][0]["min"] = 121
                path = Path(directory) / "white_cells_rules.json"
                path.write_text(json.dumps(config), encoding="utf-8")
                with patch("logic.hematology_common.DATA_DIR", Path(directory)):
                    with self.assertRaises(ValueError):
                        analyze_white_cells({})


if __name__ == "__main__":
    unittest.main()
