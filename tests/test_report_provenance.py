"""Downloaded reports retain the original evaluation time and rule snapshot."""
import csv
from dataclasses import asdict
import io
import json
from pathlib import Path
import unittest

import pandas as pd

from thalab.core import analyze_dataframe, analyze_screening
from utils.reporting import FIELD_LABELS, batch_report_csv, screening_report_csv, screening_report_markdown, to_json_bytes


class ReportProvenanceTests(unittest.TestCase):
    def test_screening_json_keeps_complete_structured_snapshot(self):
        result = analyze_screening({
            "age": 30, "sex": "Male", "hb_g_dl": 12, "mcv_fl": 70, "mch_pg": 22,
            "oft": "Positive", "dcip": "Negative", "partner_oft": "Negative", "partner_dcip": "Negative",
        }, input_origin="demo")
        payload = json.loads(to_json_bytes(result))
        expected = json.loads(to_json_bytes(asdict(result)))
        self.assertEqual({key: payload[key] for key in expected}, expected)
        self.assertEqual(payload["report_schema_version"], 2)
        self.assertIsInstance(payload["thresholds_used"], dict)
        self.assertIsInstance(payload["evidence"], list)
        self.assertTrue(payload["partner_screening"]["complete"])
        self.assertGreater(len(payload["partner_screening"]["recommendations"]), 0)
        self.assertEqual(payload["input_origin"], "demo")
        # The prior top-level input/index aliases remain available to readers.
        self.assertEqual(payload["hb_g_dl"], payload["normalized"]["hb_g_dl"])
        self.assertEqual(payload["mentzer_index"], payload["derived"]["mentzer_index"])
        self.assertIn("ไม่ใช่การวินิจฉัย", payload["disclaimer"])

    def test_batch_csv_retains_partner_recommendations_and_source_on_each_row(self):
        inputs = pd.DataFrame([
            {"age": 30, "hb_g_dl": 12, "mcv_fl": 70, "mch_pg": 22,
             "oft": "Positive", "dcip": "Negative", "partner_oft": "Negative", "partner_dcip": "Negative"},
            {"age": 30, "hb_g_dl": 6, "mcv_fl": 999, "mch_pg": 22},
        ])
        results = analyze_dataframe(inputs, input_origin="csv")
        self.assertFalse(set(results.columns) - set(FIELD_LABELS), "CSV must label every evaluation field")
        records = list(csv.DictReader(io.StringIO(batch_report_csv(results).decode("utf-8-sig"))))
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0][FIELD_LABELS["partner_complete"]], "ใช่")
        self.assertEqual(records[1][FIELD_LABELS["partner_complete"]], "ไม่ใช่")
        for record in records:
            self.assertEqual(record[FIELD_LABELS["input_origin"]], "นำเข้า CSV")
            self.assertTrue(record[FIELD_LABELS["partner_recommendations"]])
        self.assertEqual(records[1][FIELD_LABELS["severe_anemia_flag"]], "ใช่")
        self.assertTrue(records[1][FIELD_LABELS["validation_errors"]])

    def test_input_origin_is_explicit_metadata_and_defaults_to_unknown(self):
        row = {"hb_g_dl": 11, "mcv_fl": 70, "mch_pg": 22, "input_origin": "demo"}
        self.assertEqual(analyze_screening(row).input_origin, "unknown")
        for origin in ("manual", "demo", "csv"):
            result = analyze_screening(row, input_origin=origin)
            self.assertEqual(json.loads(to_json_bytes(result))["input_origin"], origin)
            self.assertIn(FIELD_LABELS["input_origin"], screening_report_markdown(result))
            rows = dict(csv.reader(io.StringIO(screening_report_csv(result).decode("utf-8-sig"))))
            self.assertNotEqual(rows[FIELD_LABELS["input_origin"]], "ไม่ได้บันทึกที่มา")

    def test_domain_batch_rejects_metadata_mismatch_instead_of_dropping_rows(self):
        from logic.white_cells import analyze_white_cells
        from utils.domain_reporting import batch_report_csv as domain_batch_csv
        from utils.domain_reporting import report_json, report_metadata

        result = analyze_white_cells({"age": 30, "wbc_10e9_l": 4})
        meta = report_metadata("white_cells", "demo")
        with self.assertRaises(ValueError):
            domain_batch_csv([result], [])
        with self.assertRaises(ValueError):
            domain_batch_csv([], [meta])
        payload = json.loads(report_json(result, meta))
        self.assertEqual(payload["result"], result.to_dict())
        self.assertEqual(payload["report"], meta)

    def test_all_screening_exports_preserve_evaluation_timestamp(self):
        result = analyze_screening({"hb_g_dl": 11, "mcv_fl": 70, "mch_pg": 22})
        # A historical evaluation must not acquire a fresh timestamp at export.
        result.evaluated_at = "2026-01-02T03:04:05+07:00"
        before = screening_report_csv(result)
        rows = dict(csv.reader(io.StringIO(before.decode("utf-8-sig"))))
        self.assertEqual(rows["เวลาประเมิน (UTC+07:00)"], result.evaluated_at)
        self.assertIn(result.evaluated_at, screening_report_markdown(result))
        self.assertIn(result.evaluated_at, to_json_bytes(result).decode())
        batch = batch_report_csv(pd.DataFrame([result.to_flat_dict()]))
        record = next(csv.DictReader(io.StringIO(batch.decode("utf-8-sig"))))
        self.assertEqual(record["เวลาประเมิน (UTC+07:00)"], result.evaluated_at)
        self.assertEqual(record["ลายนิ้วมือไฟล์กฎ"], result.ruleset_hash)
        self.assertEqual(screening_report_csv(result), before)


class ScreeningReportUITests(unittest.TestCase):
    def test_explicit_upload_removal_forgets_retained_bytes(self):
        from unittest.mock import patch
        from ui import screening

        state = {"screening_batch_upload": io.BytesIO(b"first file")}
        with patch.object(screening.st, "session_state", state):
            screening._capture_batch_upload()
            self.assertEqual(state["screening_batch_upload_bytes"], b"first file")
            state["screening_batch_upload"] = io.BytesIO(b"replacement")
            screening._capture_batch_upload()
            self.assertEqual(state["screening_batch_upload_bytes"], b"replacement")
            state["screening_batch_upload"] = None
            screening._capture_batch_upload()
            self.assertNotIn("screening_batch_upload_bytes", state)

    def open_screening(self):
        from streamlit.testing.v1 import AppTest

        root = Path(__file__).resolve().parents[1]
        app = AppTest.from_file(str(root / "app.py"), default_timeout=30).run()
        app.switch_page("pages/1_Laboratory_Screening_Test.py").run()
        self.assertFalse(app.exception, [error.message for error in app.exception])
        return app

    def test_draft_edits_preserve_snapshot_and_partner_reassessment_preserves_origin(self):
        app = self.open_screening()
        app.radio(key="screening_single_source").set_value("ใช้ข้อมูลตัวอย่าง").run()
        app.button(key="screening_single_submit").click().run()
        self.assertFalse(app.exception, [error.message for error in app.exception])
        original = app.session_state["screening_single_result"]
        self.assertEqual(original.input_origin, "demo")
        exported = to_json_bytes(original)
        app.number_input(key="screening_input_hb_g_dl").set_value(9.1).run()
        self.assertEqual(to_json_bytes(app.session_state["screening_single_result"]), exported)
        self.assertTrue(any("แบบฟอร์มถูกแก้ไขแล้ว" in warning.value for warning in app.warning))
        app.selectbox(key="screening_partner_oft").set_value("Negative").run()
        app.selectbox(key="screening_partner_dcip").set_value("Negative").run()
        self.assertTrue(any("ข้อมูลของคู่ถูกแก้ไขแล้ว" in warning.value for warning in app.warning))
        app.button(key="screening_partner_submit").click().run()
        self.assertFalse(app.exception, [error.message for error in app.exception])
        revised = app.session_state["screening_single_result"]
        self.assertEqual(revised.input_origin, "demo")
        self.assertEqual(revised.normalized["hb_g_dl"], original.normalized["hb_g_dl"])
        self.assertTrue(json.loads(to_json_bytes(revised))["partner_screening"]["complete"])
        self.assertFalse(any("ข้อมูลของคู่ถูกแก้ไขแล้ว" in warning.value for warning in app.warning))
        app.button(key="screening_single_submit").click().run()
        self.assertEqual(app.session_state["screening_single_result"].normalized["hb_g_dl"], 9.1)
        self.assertFalse(any("แบบฟอร์มถูกแก้ไขแล้ว" in warning.value for warning in app.warning))

    def test_uploaded_batch_origin_survives_rerun_and_reset_is_scoped(self):
        app = self.open_screening()
        app.radio(key="screening_mode").set_value("ประเมินชุดข้อมูล CSV").run()
        app.session_state["screening_batch_upload_bytes"] = b"age,sex,hb_g_dl,mcv_fl,mch_pg\n30,Male,12,70,22\n"
        app.run()
        app.button(key="screening_batch_submit").click().run()
        self.assertFalse(app.exception, [error.message for error in app.exception])
        stored = app.session_state["screening_batch_results"]
        self.assertEqual(stored["input_origin"].tolist(), ["csv"])
        report = batch_report_csv(stored)
        app.slider(key="screening_threshold_hba2").set_value(3.7).run()
        self.assertEqual(batch_report_csv(app.session_state["screening_batch_results"]), report)
        app.session_state["cbc_result_sentinel"] = "keep"
        app.session_state["pcr_result_sentinel"] = "keep"
        next(button for button in app.button if button.label == "ล้างข้อมูลคัดกรองหน้านี้").click().run()
        self.assertFalse(app.exception, [error.message for error in app.exception])
        self.assertNotIn("screening_batch_results", app.session_state)
        self.assertNotIn("screening_batch_upload_bytes", app.session_state)
        self.assertEqual(app.session_state["cbc_result_sentinel"], "keep")
        self.assertEqual(app.session_state["pcr_result_sentinel"], "keep")


if __name__ == "__main__":
    unittest.main()
