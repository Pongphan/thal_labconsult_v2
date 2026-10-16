"""Conservative grouping/workflow contracts using synthetic screening inputs.

CG-01 covers rule mappings and coexistence; CG-02 incomplete/invalid inputs;
CG-03 independent urgency; CG-04 additive export snapshots; CG-05 rendered UI.
These checks establish software behavior, not clinical validation or approval.
"""
from __future__ import annotations

import copy
import csv
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd

from logic.clinical_grouping import GROUP_LABELS, group_screening_findings
from logic.engine import analyze_dataframe, analyze_screening
from utils.reporting import (
    FIELD_LABELS, batch_report_csv, screening_report_csv,
    screening_report_markdown, to_json_bytes,
)


COMPLETE = {
    "sample_id": "SYNTHETIC-001", "age": 30, "sex": "Female", "pregnant": False,
    "hb_g_dl": 14, "mcv_fl": 88, "mch_pg": 29, "ferritin_ng_ml": 60,
    "hba2_percent": 2.7, "hbf_percent": 0.5, "hbe_percent": 0,
    "hb_method": "CZE", "oft": "Negative", "dcip": "Negative",
    "transfusion_recent": False, "family_history": False,
}


class ClinicalGroupingTests(unittest.TestCase):
    def test_cg01_every_existing_rule_has_the_expected_group(self):
        # Independent expected mapping prevents a missing mapping from becoming
        # a passing test merely because the same production constant is reused.
        expected = {
            "alpha_variant": "suspected_alpha", "beta_trait": "suspected_beta",
            "hbe_pattern": "suspected_hb_variant", "iron_deficiency": "iron_or_mixed",
            "combined_peak": "indeterminate", "high_fraction_review": "indeterminate",
            "micro_unresolved": "indeterminate", "of_screen": "indeterminate",
            "pediatric_review": "indeterminate",
        }
        normalized = analyze_screening(COMPLETE).normalized
        for rule, code in expected.items():
            with self.subTest(rule=rule):
                result = group_screening_findings(
                    normalized, [rule], [], severe=False, anemia=False,
                    microcytosis=False, hypochromia=False,
                )
                self.assertEqual(result["group_codes"], [code])
                self.assertEqual(result["evidence_rule_ids"], [rule])
                self.assertTrue(result["next_actions"][0]["owner"])
                self.assertTrue(result["next_actions"][0]["action"])

    def test_cg01_real_engine_routes_synthetic_cases(self):
        cases = [
            ({"hbh_percent": 1}, "suspected_alpha"),
            ({"hba2_percent": 5}, "suspected_beta"),
            ({"hbe_percent": 25}, "suspected_hb_variant"),
            ({"ferritin_ng_ml": 10}, "iron_or_mixed"),
            ({"hba2_percent": None, "hbe_percent": None, "hba2e_percent": 25}, "indeterminate"),
            ({"hbf_percent": 6}, "indeterminate"),
            ({"mcv_fl": 70}, "indeterminate"),
            ({"oft": "Positive"}, "indeterminate"),
            ({"age": 0.5}, "indeterminate"),
        ]
        for changes, expected in cases:
            with self.subTest(changes=changes):
                result = analyze_screening({**COMPLETE, **changes})
                self.assertFalse(result.validation_errors)
                self.assertIn(expected, result.clinical_grouping["group_codes"])
                self.assertNotIn("no_specific_pattern", result.clinical_grouping["group_codes"])
                self.assertEqual(result.clinical_grouping["evidence_rule_ids"], result.rule_ids)

    def test_cg01_iron_and_beta_findings_are_both_preserved(self):
        result = analyze_screening({**COMPLETE, "hba2_percent": 5, "ferritin_ng_ml": 8})
        self.assertIn("beta_trait", result.rule_ids)
        self.assertIn("iron_deficiency", result.rule_ids)
        self.assertEqual(set(result.clinical_grouping["group_codes"]), {"suspected_beta", "iron_or_mixed"})
        self.assertEqual(len(result.clinical_grouping["next_actions"]), 2)

    def test_cg02_combined_pediatric_and_transfusion_remain_indeterminate(self):
        for changes in ({"hba2e_percent": 25, "hba2_percent": None, "hbe_percent": None},
                        {"age": 0.5, "hba2_percent": 5},
                        {"transfusion_recent": True, "hba2_percent": 5},
                        {"transfusion_recent": None}):
            with self.subTest(changes=changes):
                result = analyze_screening({**COMPLETE, **changes})
                grouping = result.clinical_grouping
                self.assertIn("indeterminate", grouping["group_codes"])
                self.assertNotIn("no_specific_pattern", grouping["group_codes"])
                self.assertEqual(grouping["expert_review_status"], "pending")
                self.assertEqual(grouping["patient_release_status"], "draft_requires_professional_review")

    def test_cg02_incomplete_context_cannot_be_no_specific_pattern(self):
        cases = [{field: None} for field in (
            "age", "sex", "pregnant", "hb_method", "ferritin_ng_ml", "hba2_percent",
            "hbf_percent", "hbe_percent", "oft", "dcip", "family_history",
        )]
        cases.extend([{"age": 4, "sex": None}, {"hb_method": "unverified_method"},
                      {"oft": "Indeterminate"}, {"family_history": True}])
        for changes in cases:
            with self.subTest(changes=changes):
                result = analyze_screening({**COMPLETE, **changes})
                self.assertIn("indeterminate", result.clinical_grouping["group_codes"])
                self.assertNotIn("no_specific_pattern", result.clinical_grouping["group_codes"])
                self.assertTrue(result.clinical_grouping["uncertainty_reasons"])

    def test_cg02_invalid_or_missing_required_inputs_cannot_be_classified(self):
        for row in ({}, {**COMPLETE, "mcv_fl": None}, {**COMPLETE, "hb_g_dl": "bad"},
                    {**COMPLETE, "sex": "Male", "pregnant": True}):
            with self.subTest(row=row):
                result = analyze_screening(row)
                self.assertTrue(result.validation_errors)
                self.assertEqual(result.clinical_grouping["group_codes"], ["invalid"])
                self.assertFalse(result.clinical_grouping["evidence_rule_ids"])
                self.assertIsNone(result.anemia)
                self.assertTrue(result.clinical_grouping["uncertainty_reasons"])

    def test_cg02_complete_unmatched_case_never_rules_out_a_carrier(self):
        result = analyze_screening(COMPLETE)
        grouping = result.clinical_grouping
        self.assertFalse(result.rule_ids)
        self.assertFalse(result.validation_errors)
        self.assertEqual(grouping["group_codes"], ["no_specific_pattern"])
        self.assertFalse(grouping["uncertainty_reasons"])
        self.assertIn("ไม่ได้ตัดพาหะ", grouping["clinician_summary"])
        self.assertIn("ยังไม่ยืนยันหรือปฏิเสธ", grouping["patient_summary"])
        self.assertIn("ไม่ออกข้อความยืนยันว่าไม่เป็นพาหะ", grouping["next_actions"][0]["action"])

    def test_cg02_unknown_rule_ids_fail_to_indeterminate_and_are_traceable(self):
        normalized = analyze_screening(COMPLETE).normalized
        result = group_screening_findings(
            normalized, ["future_unreviewed_rule", "future_unreviewed_rule"], [],
            severe=False, anemia=False, microcytosis=False, hypochromia=False,
        )
        self.assertEqual(result["group_codes"], ["indeterminate"])
        self.assertEqual(result["evidence_rule_ids"], ["future_unreviewed_rule", "future_unreviewed_rule"])
        self.assertNotIn("no_specific_pattern", result["group_codes"])

    def test_cg03_urgent_review_precedes_actions_even_if_other_input_is_invalid(self):
        for changes, expected in (({}, "indeterminate"), ({"mcv_fl": "bad"}, "invalid")):
            result = analyze_screening({**COMPLETE, "hb_g_dl": 6, **changes})
            grouping = result.clinical_grouping
            self.assertTrue(result.severe_anemia_flag)
            self.assertTrue(grouping["urgent_review"])
            self.assertIn(expected, grouping["group_codes"])
            self.assertIn("เร่งด่วน", grouping["next_actions"][0]["action"])
            self.assertIn("ไม่รอ", grouping["next_actions"][0]["action"])

    def test_cg01_grouping_keeps_existing_valid_pattern_and_score(self):
        result = analyze_screening({**COMPLETE, "hb_g_dl": 10, "mcv_fl": 70,
                                    "mch_pg": 22, "rbc_10e12_l": 5.6, "hba2_percent": 5})
        self.assertEqual(result.rule_ids, ["beta_trait"])
        self.assertEqual(result.beta_trait_score, 82)
        self.assertEqual(result.consult_score, 82)
        self.assertEqual(result.consult_risk, "High")
        self.assertTrue(result.anemia)
        self.assertTrue(result.microcytosis)
        self.assertTrue(result.hypochromia)
        self.assertIn("สงสัย beta-thalassemia trait", result.top_pattern)
        self.assertEqual(result.clinical_grouping["group_codes"], ["suspected_beta"])

    def test_cg04_single_json_and_csv_add_structured_grouping_without_removing_legacy_data(self):
        result = analyze_screening({**COMPLETE, "hba2_percent": 5}, input_origin="demo")
        expected = result.clinical_grouping
        payload = json.loads(to_json_bytes(result))
        self.assertEqual(payload["report_schema_version"], 2)
        self.assertEqual(payload["clinical_grouping"], expected)
        self.assertEqual(payload["clinical_group_labels"], " | ".join(expected["group_labels"]))
        for key in ("sample_id", "top_pattern", "rule_ids", "ruleset_version", "ruleset_hash", "evaluated_at"):
            self.assertEqual(payload[key], getattr(result, key))
        self.assertEqual(payload["hb_g_dl"], result.normalized["hb_g_dl"])
        self.assertEqual(payload["thresholds_used"], result.thresholds_used)
        self.assertIsInstance(payload["normalized"], dict)
        self.assertIsInstance(payload["evidence"], list)
        rows = dict(csv.reader(io.StringIO(screening_report_csv(result).decode("utf-8-sig"))))
        self.assertEqual(json.loads(rows[FIELD_LABELS["clinical_grouping"]]), expected)
        self.assertIn(expected["clinician_summary"], screening_report_markdown(result))
        self.assertIn(expected["patient_summary"], screening_report_markdown(result))

    def test_cg04_batch_json_csv_and_single_rows_preserve_the_same_grouping(self):
        inputs = [COMPLETE, {**COMPLETE, "hba2_percent": 5, "ferritin_ng_ml": 8},
                  {**COMPLETE, "hb_g_dl": 6, "mcv_fl": "bad"}]
        batch = analyze_dataframe(pd.DataFrame(inputs), input_origin="csv")
        self.assertFalse(set(batch.columns) - set(FIELD_LABELS))
        records = list(csv.DictReader(io.StringIO(batch_report_csv(batch).decode("utf-8-sig"))))
        json_batch = json.loads(to_json_bytes(batch))
        for position, row in enumerate(inputs):
            expected = analyze_screening(row).clinical_grouping
            self.assertEqual(json.loads(batch.iloc[position]["clinical_grouping"]), expected)
            self.assertEqual(json.loads(records[position][FIELD_LABELS["clinical_grouping"]]), expected)
            self.assertEqual(json.loads(json_batch["clinical_grouping"][str(position)]), expected)
            self.assertEqual(records[position][FIELD_LABELS["ruleset_hash"]], batch.iloc[position]["ruleset_hash"])

    def test_cg04_policy_snapshot_is_strict_json_and_not_recomputed_when_exporting(self):
        result = analyze_screening(COMPLETE)
        grouping = copy.deepcopy(result.clinical_grouping)
        self.assertEqual(len(grouping["policy_hash"]), 64)
        self.assertTrue(grouping["policy_version"])
        self.assertTrue(grouping["sources"])
        json.dumps(grouping, allow_nan=False)
        with patch("logic.engine.group_screening_findings", side_effect=AssertionError("must not recompute")):
            self.assertEqual(json.loads(to_json_bytes(result))["clinical_grouping"], grouping)
            self.assertIn(grouping["policy_hash"], screening_report_csv(result).decode("utf-8-sig"))


class ClinicalGroupingUITests(unittest.TestCase):
    def open_screening(self):
        from streamlit.testing.v1 import AppTest

        root = Path(__file__).resolve().parents[1]
        app = AppTest.from_file(str(root / "app.py"), default_timeout=30).run()
        app.switch_page("pages/1_Laboratory_Screening_Test.py").run()
        self.assertFalse(app.exception, [error.message for error in app.exception])
        return app

    def test_cg05_single_ui_shows_groups_draft_audience_and_independent_urgency(self):
        app = self.open_screening()
        app.button(key="screening_single_submit").click().run()
        self.assertFalse(app.exception, [error.message for error in app.exception])
        self.assertEqual(app.session_state["screening_single_result"].clinical_grouping["group_codes"], ["invalid"])
        self.assertTrue(any(GROUP_LABELS["invalid"] in item.value for item in app.markdown))
        app.radio(key="screening_single_source").set_value("ใช้ข้อมูลตัวอย่าง").run()
        app.button(key="screening_single_submit").click().run()
        self.assertFalse(app.exception, [error.message for error in app.exception])
        result = app.session_state["screening_single_result"]
        grouping = result.clinical_grouping
        rendered = "\n".join(item.value for item in app.markdown)
        for label in grouping["group_labels"]:
            self.assertIn(label, rendered)
        self.assertIn(grouping["clinician_summary"], rendered)
        self.assertIn(grouping["patient_summary"], rendered)
        self.assertIn("ก่อนส่งต่อ", rendered)
        self.assertTrue(any("รอผู้เชี่ยวชาญทบทวน" in item.value for item in app.caption))
        snapshot = to_json_bytes(result)
        app.number_input(key="screening_input_hb_g_dl").set_value(6).run()
        self.assertEqual(to_json_bytes(app.session_state["screening_single_result"]), snapshot)
        app.number_input(key="screening_input_mcv_fl").set_value(999).run()
        app.button(key="screening_single_submit").click().run()
        self.assertFalse(app.exception, [error.message for error in app.exception])
        invalid = app.session_state["screening_single_result"]
        self.assertEqual(invalid.clinical_grouping["group_codes"], ["invalid"])
        self.assertTrue(invalid.clinical_grouping["urgent_review"])
        rendered = "\n".join(item.value for item in app.markdown)
        self.assertIn("Hb ต่ำเร่งด่วน", rendered)
        self.assertIn("โดยไม่รอ", rendered)
        self.assertEqual(len(app.get("download_button")), 3)

    def test_cg05_batch_ui_retains_every_grouping_and_export_row(self):
        app = self.open_screening()
        app.radio(key="screening_mode").set_value("ประเมินชุดข้อมูล CSV").run()
        frame = pd.DataFrame([COMPLETE, {**COMPLETE, "hb_g_dl": 6, "mcv_fl": 999}])
        app.session_state["screening_batch_upload_bytes"] = frame.to_csv(index=False).encode("utf-8")
        app.run()
        app.button(key="screening_batch_submit").click().run()
        self.assertFalse(app.exception, [error.message for error in app.exception])
        results = app.session_state["screening_batch_results"]
        self.assertEqual(len(results), 2)
        self.assertEqual(json.loads(results.iloc[0]["clinical_grouping"])["group_codes"], ["no_specific_pattern"])
        self.assertEqual(json.loads(results.iloc[1]["clinical_grouping"])["group_codes"], ["invalid"])
        records = list(csv.DictReader(io.StringIO(batch_report_csv(results).decode("utf-8-sig"))))
        self.assertEqual(len(records), 2)
        for position, record in enumerate(records):
            self.assertEqual(json.loads(record[FIELD_LABELS["clinical_grouping"]]),
                             json.loads(results.iloc[position]["clinical_grouping"]))
        self.assertTrue(any("Hb ต่ำ" in item.value for item in app.error))
        displayed = [item.value for item in app.dataframe if "กลุ่มผลที่ต้องทบทวน" in item.value.columns]
        self.assertTrue(displayed)
        for table in displayed:
            self.assertNotIn("clinical_grouping", table.columns)
            self.assertNotIn(FIELD_LABELS["clinical_grouping"], table.columns)


if __name__ == "__main__":
    unittest.main()
