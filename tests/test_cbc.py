"""CBC safety boundaries, scope, evidence preservation and configurable rules."""
import json
from pathlib import Path
import tempfile
import unittest

from logic.cbc import analyze_cbc, load_cbc_rules


class CBCTests(unittest.TestCase):
    def row(self, **updates):
        return {"age": 30, "sex": "Female", "pregnant": False, "hb_g_dl": 11.5, "mcv_fl": 85, **updates}

    def test_who_hb_sex_boundaries_and_no_general_normal_claim(self):
        for sex, boundary in [("Male", 13), ("Female", 12)]:
            self.assertEqual(analyze_cbc(self.row(sex=sex, hb_g_dl=boundary)).anemia_code, "not_below_cutoff")
            self.assertEqual(analyze_cbc(self.row(sex=sex, hb_g_dl=boundary - 0.01)).anemia_code, "below_cutoff")
        result = analyze_cbc(self.row(hb_g_dl=13))
        self.assertIn("ไม่ได้หมายความว่า CBC ปกติ", result.anemia_status)

    def test_scope_boundaries_do_not_default_to_adult(self):
        for age in [None, 0, 17.99, 65.01, 90]:
            with self.subTest(age=age):
                result = analyze_cbc(self.row(age=age))
                self.assertEqual(result.anemia_code, "not_assessed")
                self.assertEqual(result.pattern_code, "unavailable")
                self.assertNotIn("hb_anemia_g_dl", result.thresholds_used)
        for age in [18, 65]:
            self.assertTrue(analyze_cbc(self.row(age=age)).scope_supported)

    def test_missing_sex_allows_only_applicable_mcv_pattern(self):
        result = analyze_cbc(self.row(sex=None, mcv_fl=70))
        self.assertEqual(result.anemia_code, "not_assessed")
        self.assertEqual(result.pattern_code, "micro")
        self.assertFalse(result.scope_supported)
        self.assertNotIn("hb_anemia_g_dl", result.thresholds_used)

    def test_pregnancy_handling_is_explicit(self):
        for pregnancy in [True, None]:
            result = analyze_cbc(self.row(pregnant=pregnancy))
            self.assertEqual(result.anemia_code, "not_assessed")
        self.assertTrue(analyze_cbc(self.row(sex="Male", pregnant=None)).scope_supported)
        self.assertTrue(analyze_cbc(self.row(sex="Male", pregnant=True)).validation_errors)

    def test_mcv_boundaries(self):
        for mcv, expected in [(79.99, "micro"), (80, "normo"), (100, "normo"), (100.01, "macro")]:
            with self.subTest(mcv=mcv):
                self.assertEqual(analyze_cbc(self.row(mcv_fl=mcv)).pattern_code, expected)

    def test_missing_hb_never_replaced_by_hct(self):
        result = analyze_cbc(self.row(hb_g_dl=None, hct_percent=20))
        self.assertEqual(result.anemia_code, "not_assessed")
        self.assertEqual(result.support_code, "incomplete")
        self.assertEqual(result.pattern_code, "normo")
        self.assertFalse(result.validation_errors)

    def test_missing_mcv_preserves_hb_assessment(self):
        result = analyze_cbc(self.row(mcv_fl=None))
        self.assertEqual(result.anemia_code, "below_cutoff")
        self.assertEqual(result.pattern_code, "unavailable")
        self.assertEqual(result.support_code, "incomplete")

    def test_invalid_values_never_become_normal_missing_data(self):
        for value in ["abc", float("inf"), -1, True, 31]:
            with self.subTest(value=value):
                result = analyze_cbc(self.row(hb_g_dl=value))
                self.assertTrue(result.validation_errors)
                self.assertEqual(result.anemia_code, "not_assessed")
                self.assertFalse(result.low_hb_alert)
        result = analyze_cbc(self.row(wbc_10e9_l=-1))
        self.assertEqual(result.support_code, "invalid")
        self.assertEqual(result.pattern_code, "invalid")

    def test_low_hb_survives_invalid_other_data(self):
        result = analyze_cbc(self.row(hb_g_dl=7.9, mcv_fl="bad"))
        self.assertTrue(result.low_hb_alert)
        self.assertTrue(result.severe_anemia_flag)
        self.assertEqual(result.support_code, "invalid")
        self.assertTrue(any("7.9" in item for item in result.findings))
        self.assertFalse(analyze_cbc(self.row(hb_g_dl=8)).low_hb_alert)

    def test_out_of_scope_low_hb_is_caution_not_adult_severity(self):
        for fields in [{"age": None}, {"age": 5}, {"pregnant": True}, {"sex": None}]:
            result = analyze_cbc(self.row(hb_g_dl=6, **fields))
            self.assertTrue(result.low_hb_alert)
            self.assertFalse(result.severe_anemia_flag)
            self.assertEqual(result.anemia_code, "not_assessed")
            self.assertTrue(any("ไม่กำหนดระดับความรุนแรง" in item for item in result.findings))

    def test_no_default_reference_flags_for_optional_labs(self):
        result = analyze_cbc(self.row(ferritin_ng_ml=2, wbc_10e9_l=2, platelets_10e9_l=50))
        self.assertFalse(any(rule.startswith("CBC_LAB_REFERENCE") for rule in result.rules_used))
        self.assertFalse(result.reference_intervals_used)
        self.assertTrue(any("Ferritin" in message and "ไม่มีช่วงอ้างอิง" in message for message in result.validation_warnings))

    def test_local_intervals_are_explicit_and_one_sided_supported(self):
        intervals = {"ferritin_ng_ml": {"low": 15, "high": None}, "platelets_10e9_l": {"low": 150, "high": 400}}
        result = analyze_cbc(self.row(ferritin_ng_ml=14, platelets_10e9_l=150), intervals)
        self.assertIn("CBC_LAB_REFERENCE_FERRITIN_NG_ML_LOW", result.rules_used)
        self.assertIn("CBC_LAB_REFERENCE_PLATELETS_10E9_L_WITHIN", result.rules_used)
        self.assertEqual(result.reference_intervals_used, intervals)
        self.assertTrue(any("ไม่ตัดภาวะขาดธาตุเหล็ก" in message for message in result.limitations))
        self.assertNotIn("iron_deficiency", result.to_dict())

    def test_blank_intervals_ignored_and_bad_intervals_rejected(self):
        self.assertFalse(analyze_cbc(self.row(), {"wbc_10e9_l": {"low": None, "high": None}}).validation_errors)
        for bounds in [{"low": 10, "high": 4}, {"low": -1}, {"low": "bad"}, {"high": float("inf")}, {"low": True}]:
            with self.subTest(bounds=bounds):
                result = analyze_cbc(self.row(wbc_10e9_l=5), {"wbc_10e9_l": bounds})
                self.assertTrue(result.validation_errors)
                self.assertEqual(result.support_code, "invalid")

    def test_export_contains_only_whitelisted_inputs_and_json_numbers(self):
        result = analyze_cbc(self.row(patient_name="DO NOT RETAIN", hb_g_dl=float("nan")))
        output = result.to_dict()
        self.assertNotIn("patient_name", output["normalized"])
        self.assertIsNone(output["normalized"]["hb_g_dl"])
        self.assertEqual(len(output["ruleset_hash"]), 64)
        json.dumps(output, ensure_ascii=False, allow_nan=False)

    def test_rules_changes_are_used_and_hashed(self):
        original = analyze_cbc(self.row(hb_g_dl=7.5))
        config = load_cbc_rules()
        config["thresholds"]["severe_hb_g_dl"] = 7
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cbc_rules.json"
            path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
            changed = analyze_cbc(self.row(hb_g_dl=7.5), rules_path=path)
        self.assertTrue(original.low_hb_alert)
        self.assertFalse(changed.low_hb_alert)
        self.assertNotEqual(original.ruleset_hash, changed.ruleset_hash)

    def test_rules_reject_executable_or_unsafe_templates(self):
        config = load_cbc_rules()
        config["messages"]["counseling"] = "{pattern.__class__}"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cbc_rules.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_cbc_rules(path)

    def test_malformed_rulesets_fail_closed(self):
        malformed = []
        missing_message = load_cbc_rules()
        del missing_message["messages"]["anemia_below"]
        malformed.append(missing_message)
        nonfinite = load_cbc_rules()
        nonfinite["thresholds"]["hb_male_g_dl"] = float("nan")
        malformed.append(nonfinite)
        reversed_bounds = load_cbc_rules()
        reversed_bounds["validation"]["ranges"]["hb_g_dl"][:2] = [30, 1]
        malformed.append(reversed_bounds)
        invalid_template = load_cbc_rules()
        invalid_template["messages"]["tests_baseline"] = "{value}"
        malformed.append(invalid_template)
        invalid_numeric_format = load_cbc_rules()
        invalid_numeric_format["messages"]["reference_missing"] = "{label:g}"
        malformed.append(invalid_numeric_format)
        invalid_pattern_format = load_cbc_rules()
        invalid_pattern_format["messages"]["anemia_pattern"] = "{pattern:g}"
        malformed.append(invalid_pattern_format)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cbc_rules.json"
            for index, config in enumerate(malformed):
                with self.subTest(case=index):
                    path.write_text(json.dumps(config), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_cbc_rules(path)

    def test_scope_limitations_follow_edited_profile(self):
        config = load_cbc_rules()
        config["thresholds"]["age_min_years"] = 20
        config["thresholds"]["age_max_years"] = 60
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cbc_rules.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            result = analyze_cbc(self.row(), rules_path=path)
        self.assertIn("20–60", result.scope)
        self.assertTrue(any("20–60" in text for text in result.limitations))


if __name__ == "__main__":
    unittest.main()
