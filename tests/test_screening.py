"""Regression cases for software behavior, not clinical validation evidence."""
import ast
import copy
import csv
import io
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta

import pandas as pd

from logic.rules import load_rules
from thalab.core import analyze_dataframe, analyze_screening, normalize_call, example_screening_dataframe
from thalab.ml import ml_feature_matrix, phenotype_similarity
from utils.reporting import FIELD_LABELS, batch_report_csv, screening_report_csv, screening_report_markdown, to_json_bytes

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_BETA = dict(age=24, sex="Female", pregnant=False, hb_g_dl=10.2, mcv_fl=68, mch_pg=21, rdw_percent=15, hba2_percent=5.1, hbf_percent=1.5)
EXAMPLE_MICRO = dict(age=24, sex="Female", pregnant=False, hb_g_dl=11, mcv_fl=74, mch_pg=23, hba2_percent=2.2)


class ScreeningTests(unittest.TestCase):
    def test_requested_beta_example(self):
        result = analyze_screening(EXAMPLE_BETA)
        self.assertFalse(result.validation_errors)
        self.assertIn("beta-thalassemia trait", result.top_pattern)
        self.assertIn("HBB", " ".join(result.recommendations))
        self.assertIn("ก่อนมีบุตร", " ".join(result.counseling))
        self.assertIn("beta_trait", result.rule_ids)

    def test_requested_microcytosis_example(self):
        result = analyze_screening(EXAMPLE_MICRO)
        self.assertIn("iron deficiency", result.top_pattern)
        self.assertIn("ยังแยก", result.top_pattern)
        self.assertIn("ferritin", " ".join(result.recommendations))
        self.assertIn("alpha-thal 1 PCR", " ".join(result.recommendations))

    def test_critical_alert_survives_pattern(self):
        result = analyze_screening({**EXAMPLE_BETA, "hb_g_dl": 6})
        self.assertEqual(result.consult_risk, "Critical review")
        self.assertTrue(result.severe_anemia_flag)
        self.assertIn("beta-thalassemia", result.top_pattern)

    def test_infant_does_not_receive_adult_fraction_rule(self):
        result = analyze_screening({**EXAMPLE_BETA, "age": 0.5})
        self.assertNotIn("beta_trait", result.rule_ids)
        self.assertIn("pediatric_review", result.rule_ids)
        self.assertTrue(result.caveats)

    def test_both_fraction_channels_require_review(self):
        result = analyze_screening({**EXAMPLE_BETA, "hba_percent": 50, "hbe_percent": 2,
                                    "hba2e_percent": 40})
        self.assertFalse(result.validation_errors)
        self.assertTrue(any("แยก" in warning and "รวม" in warning for warning in result.validation_warnings))

    def test_combined_peak_never_hides_impossible_resolved_fraction(self):
        for method in ("HPLC", "CZE", "Not specified"):
            row = {**EXAMPLE_BETA, "hba_percent": 90, "hbe_percent": 80,
                   "hba2_percent": None, "hba2e_percent": 10, "hb_method": method}
            with self.subTest(method=method):
                result = analyze_screening(row)
                self.assertTrue(result.validation_errors)
                self.assertFalse(result.rule_ids)
                self.assertTrue(math.isnan(result.hbe_score))
                self.assertEqual(analyze_dataframe(pd.DataFrame([row])).iloc[0]["top_pattern"], result.top_pattern)

    def test_each_fraction_representation_is_checked_without_double_counting(self):
        valid = analyze_screening({**EXAMPLE_BETA, "hba_percent": 70, "hba2_percent": None,
                                   "hbe_percent": 20, "hba2e_percent": 22})
        self.assertFalse(valid.validation_errors)
        self.assertTrue(math.isnan(valid.normalized["hba2_percent"]))
        # A complete resolved pair must not hide an impossible combined representation.
        invalid = analyze_screening({**EXAMPLE_BETA, "hba_percent": 90, "hbe_percent": 2,
                                     "hba2e_percent": 40})
        self.assertTrue(invalid.validation_errors)

    def test_missing_age_does_not_select_adult_or_infant_rules(self):
        result = analyze_screening({**EXAMPLE_BETA, "age": None})
        self.assertFalse(result.validation_errors)
        self.assertNotIn("beta_trait", result.rule_ids)
        self.assertNotIn("pediatric_review", result.rule_ids)
        self.assertIsNone(result.microcytosis)
        self.assertIsNone(result.hypochromia)
        self.assertIsNone(result.anemia)
        self.assertIsNone(result.thresholds_used["anemia_hb"])
        self.assertIsNone(result.thresholds_used["mcv_microcytosis"])
        self.assertTrue(any("ไม่ระบุอายุ" in message for message in result.validation_warnings))
        urgent = analyze_screening({**EXAMPLE_BETA, "age": None, "hb_g_dl": 6})
        self.assertTrue(urgent.severe_anemia_flag)
        self.assertEqual(urgent.consult_risk, "Critical review")

    def test_unknown_sex_does_not_default_to_female_anemia_threshold(self):
        adult = analyze_screening({**EXAMPLE_BETA, "sex": None, "hb_g_dl": 12.5})
        self.assertIsNone(adult.anemia)
        self.assertIsNone(adult.thresholds_used["anemia_hb"])
        self.assertIsNone(adult.thresholds_used["anemia_hct"])
        child = analyze_screening({**EXAMPLE_BETA, "age": 4, "sex": None})
        self.assertTrue(child.anemia)
        self.assertEqual(child.thresholds_used["anemia_hb"], 11)

    def test_invalid_partner_result_preserves_patient_assessment(self):
        result = analyze_screening({**EXAMPLE_BETA, "partner_oft": "Invalid"})
        self.assertFalse(result.validation_errors)
        self.assertIn("beta_trait", result.rule_ids)
        self.assertFalse(result.partner_screening["complete"])

    def test_missing_is_neither_negative_nor_a_carrier_call(self):
        self.assertEqual(normalize_call(None), "Not performed")
        self.assertEqual(normalize_call("nonsense"), "Invalid")
        self.assertEqual(normalize_call("Negative"), "Negative")
        result = analyze_screening({})
        self.assertTrue(result.validation_errors)
        self.assertEqual(result.consult_risk, "Invalid / incomplete")
        self.assertFalse(result.rule_ids)

    def test_invalid_numeric_values_are_rejected(self):
        for key, value in [("hb_g_dl", -1), ("hb_g_dl", True), ("mcv_fl", float("inf")),
                           ("mch_pg", "invalid"), ("rdw_percent", 1000), ("hba2_percent", 101), ("hbf_percent", -2)]:
            with self.subTest(key=key, value=value):
                result = analyze_screening({**EXAMPLE_BETA, key: value})
                self.assertTrue(result.validation_errors)
                self.assertFalse(result.rule_ids)

    def test_fraction_total_and_combined_peak(self):
        invalid = analyze_screening({**EXAMPLE_BETA, "hba_percent": 98, "hbf_percent": 25})
        self.assertTrue(invalid.validation_errors)
        combined = analyze_screening({**EXAMPLE_MICRO, "hba2_percent": None, "hba2e_percent": 5.1, "hb_method": "HPLC"})
        self.assertTrue(math.isnan(combined.normalized["hba2_percent"]))
        self.assertNotIn("beta_trait", combined.rule_ids)
        self.assertFalse(combined.ee_assessment["applicable"])

    def test_threshold_override_and_age_profile(self):
        row = {**EXAMPLE_MICRO, "age": 30, "mcv_fl": 78, "mch_pg": 25}
        custom = analyze_screening(row, {"mcv_microcytosis": 75, "mch_hypochromia": 24})
        self.assertFalse(custom.microcytosis)
        self.assertFalse(custom.hypochromia)
        self.assertEqual(custom.thresholds_used["mcv_microcytosis"], 75)
        child = analyze_screening({**row, "age": 4})
        self.assertEqual(child.thresholds_used["mcv_microcytosis"], 75)
        pregnant = analyze_screening({**row, "pregnant": True, "hb_g_dl": 11.5, "hct_percent": 34})
        self.assertFalse(pregnant.anemia)

    def test_single_and_batch_match_including_duplicates(self):
        rows = [{**EXAMPLE_BETA, "sample_id": "DUP"}, {**EXAMPLE_MICRO, "sample_id": "DUP"}]
        result = analyze_dataframe(pd.DataFrame(rows, index=[7, 7]))
        self.assertEqual(len(result), 2)
        for i, row in enumerate(rows):
            single = analyze_screening(row)
            self.assertEqual(result.iloc[i]["top_pattern"], single.top_pattern)
            self.assertEqual(result.iloc[i]["ruleset_hash"], single.ruleset_hash)
        self.assertIn("top_pattern", analyze_dataframe(pd.DataFrame()).columns)

    def test_batch_uses_one_rules_snapshot_and_enforces_resource_bounds(self):
        config = load_rules()
        with patch("logic.engine.load_rules", return_value=config) as loader:
            results = analyze_dataframe(pd.DataFrame([EXAMPLE_BETA, EXAMPLE_MICRO] * 100))
        loader.assert_called_once_with()
        self.assertEqual(len(results), 200)
        self.assertEqual(results["ruleset_hash"].nunique(), 1)
        with self.assertRaisesRegex(ValueError, "200"):
            analyze_dataframe(pd.DataFrame([EXAMPLE_BETA] * 201))
        with self.assertRaises(ValueError):
            analyze_dataframe(pd.DataFrame([[10, 20]], columns=["hb_g_dl", "hb_g_dl"]))

    def test_timestamp_is_a_result_snapshot_and_missing_thresholds_export_as_null(self):
        result = analyze_screening({**EXAMPLE_BETA, "age": None, "sex": None})
        timestamp = datetime.fromisoformat(result.evaluated_at)
        self.assertEqual(timestamp.utcoffset(), timedelta(hours=7))
        exported = json.loads(to_json_bytes(result))
        self.assertEqual(exported["evaluated_at"], result.evaluated_at)
        self.assertIsNone(exported["thresholds_used"]["anemia_hb"])
        self.assertNotIn("NaN", to_json_bytes(result).decode())
        self.assertEqual(to_json_bytes(result), to_json_bytes(result))

    def test_unavailable_demographic_assessments_are_not_reported_as_negative(self):
        result = analyze_screening({**EXAMPLE_BETA, "age": None, "sex": None})
        payload = json.loads(to_json_bytes(result))
        rows = dict(csv.reader(io.StringIO(screening_report_csv(result).decode("utf-8-sig"))))
        # Mixed known/unknown booleans must survive DataFrame construction and CSV export.
        batch = pd.DataFrame([result.to_flat_dict(), analyze_screening(EXAMPLE_BETA).to_flat_dict()])
        records = list(csv.DictReader(io.StringIO(batch_report_csv(batch).decode("utf-8-sig"))))
        for key in ("anemia", "microcytosis", "hypochromia"):
            self.assertIsNone(payload[key])
            self.assertEqual(rows[FIELD_LABELS[key]], "ไม่ได้ตรวจ/ไม่ทราบ")
            self.assertEqual(records[0][FIELD_LABELS[key]], "ไม่ได้ตรวจ/ไม่ทราบ")
            self.assertEqual(records[1][FIELD_LABELS[key]], "ใช่")

    def test_privacy_allowlist(self):
        result = analyze_screening({**EXAMPLE_BETA, "patient_name": "TEST PATIENT", "HN": "1234567"})
        self.assertNotIn("patient_name", result.normalized)
        self.assertNotIn("TEST PATIENT", to_json_bytes(result).decode())

    def test_exports_have_thai_bom_and_strict_json(self):
        result = analyze_screening(EXAMPLE_BETA)
        report = screening_report_csv(result)
        self.assertTrue(report.startswith(b"\xef\xbb\xbf"))
        self.assertIn(result.top_pattern, report.decode("utf-8-sig"))
        self.assertIn("ไม่ใช่การวินิจฉัย", report.decode("utf-8-sig"))
        self.assertIn(result.top_pattern, screening_report_markdown(result))
        self.assertNotIn("NaN", to_json_bytes(result).decode())
        self.assertIsNone(json.loads(to_json_bytes(result))["rbc_10e12_l"])
        data = analyze_dataframe(pd.DataFrame([EXAMPLE_BETA]))
        self.assertIn(result.top_pattern, batch_report_csv(data).decode("utf-8-sig"))

    def test_csv_formula_text_is_escaped(self):
        result = analyze_screening({**EXAMPLE_BETA, "sample_id": "=1+1"})
        rows = list(csv.reader(io.StringIO(screening_report_csv(result).decode("utf-8-sig"))))
        self.assertIn(["รหัสตัวอย่างสมมติ", "'=1+1"], rows)

    def test_empty_ml_and_combined_fraction(self):
        result = phenotype_similarity(pd.DataFrame([{}]))
        self.assertIn("ไม่เพียงพอ", result.iloc[0]["ml_prototype_pattern"])
        features = ml_feature_matrix(pd.DataFrame([{"hba2e_percent": 25}]))
        self.assertTrue(math.isnan(features.iloc[0]["hba2_percent"]))
        self.assertTrue(phenotype_similarity(pd.DataFrame()).empty)

    def test_ruleset_malformed_fails_closed(self):
        config = copy.deepcopy(load_rules())
        config["thresholds"]["hba2_beta_trait"] = -1
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rules.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_rules(path)

    def test_ruleset_rejects_ambiguous_json_and_boolean_thresholds(self):
        mutations = []
        for section, key in (("risk", "high_score"), ("validation", "fraction_sum_max")):
            config = copy.deepcopy(load_rules())
            config[section][key] = True
            mutations.append(json.dumps(config))
        config = copy.deepcopy(load_rules())
        config["age_thresholds"]["mcv_fl"][0][1] = True
        mutations.append(json.dumps(config))
        config = copy.deepcopy(load_rules())
        config["rules"][0]["score_floor"] = True
        mutations.append(json.dumps(config))
        original = json.dumps(load_rules())
        mutations.extend([original.replace('"severe_hb": 7', '"severe_hb": 7, "severe_hb": 5'),
                          original.replace('"severe_hb": 7', '"severe_hb": NaN')])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rules.json"
            for content in mutations:
                with self.subTest(content=content[:40]):
                    path.write_text(content, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_rules(path)

    def test_demo_cases_and_python310_syntax(self):
        result = analyze_dataframe(example_screening_dataframe())
        self.assertEqual(len(result), 6)
        self.assertTrue((result["validation_errors"] == "").all())
        paths = [ROOT / "app.py"]
        for folder in ("logic", "ui", "utils", "thalab", "pages"):
            paths.extend((ROOT / folder).glob("*.py"))
        for path in paths:
            ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path), feature_version=(3, 10))


if __name__ == "__main__":
    unittest.main()
