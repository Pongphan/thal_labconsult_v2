"""Source validation, unit identity and report lineage survive workspace transfers."""
from copy import deepcopy
import csv
from hashlib import sha256
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from logic.cbc import analyze_cbc
from logic.hematology import analyze_domain
from logic.hematology_common import load_domain_rules
from ui import hematology_workbench as workbench
from ui import screening
from utils.domain_reporting import batch_report_csv, report_csv, report_json, report_metadata
from utils.reporting import batch_report_csv as screening_batch_report_csv

ROOT = Path(__file__).resolve().parents[1]


class CBCTransferTests(unittest.TestCase):
    def state(self, **changes):
        row = {"age": 35, "sex": "Male", "hb_g_dl": 13, "mcv_fl": 85,
               "wbc_10e9_l": 4.2, "platelets_10e9_l": 155}
        row.update(changes)
        return {
            "cbc_result": analyze_cbc(row),
            "cbc_report_metadata": {
                "report_id": "CBC-SYNTHETIC", "evaluated_at": "2026-01-02T03:04:05+07:00",
                "input_origin": "demo", "document_status": "ร่างเพื่อทบทวน ยังไม่ลงนาม",
            },
        }

    def test_copy_keeps_identical_numeric_values_and_units_across_destinations(self):
        for module, expected in {
            "white_cells": {"age": 35.0, "wbc_10e9_l": 4.2},
            "marrow_malignancies": {"age": 35.0, "hb_g_dl": 13.0, "wbc_10e9_l": 4.2, "platelets_10e9_l": 155.0},
            "platelets_bleeding": {"platelets_10e9_l": 155.0},
            "thrombosis": {"age": 35.0},
        }.items():
            with self.subTest(module=module):
                state = self.state()
                prefix = f"domain_{module}_"
                with patch.object(workbench.st, "session_state", state):
                    workbench._copy_cbc_values(module)
                snapshot = state[prefix + "source_snapshot"]
                self.assertEqual(snapshot["copied_values"], expected)
                self.assertEqual(snapshot["report_id"], "CBC-SYNTHETIC")
                self.assertEqual(snapshot["input_origin"], "demo")
                self.assertEqual(snapshot["evaluated_at"], state["cbc_report_metadata"]["evaluated_at"])
                self.assertEqual(snapshot["ruleset_hash"], state["cbc_result"].ruleset_hash)
                inputs = {field["key"]: state[prefix + "input_" + field["key"]]
                          for field in load_domain_rules(module)["fields"]}
                result = analyze_domain(module, inputs)
                for field, value in expected.items():
                    self.assertEqual(result.normalized[field], value)
                    self.assertIn(snapshot["copied_units"][field], workbench.CBC_TRANSFER_UNITS[field])

    def test_invalid_cbc_snapshot_cannot_launder_valid_values_or_replace_destination(self):
        # Even a valid WBC is not silently copied from a CBC containing invalid MCV.
        for changes in ({"mcv_fl": 999}, {"wbc_10e9_l": "4 x 10^9/L"}, {"hb_g_dl": -1}):
            with self.subTest(changes=changes):
                state = self.state(**changes)
                state.update({"domain_white_cells_source": "0", "domain_white_cells_input_wbc_10e9_l": 9.0,
                              "domain_white_cells_single_result": "previous-result"})
                with patch.object(workbench.st, "session_state", state):
                    workbench._copy_cbc_values("white_cells")
                self.assertEqual(state["domain_white_cells_source"], "0")
                self.assertEqual(state["domain_white_cells_input_wbc_10e9_l"], 9.0)
                self.assertEqual(state["domain_white_cells_single_result"], "previous-result")
                self.assertIn("ประเมินใหม่", state["domain_white_cells_copy_error"])
                self.assertNotIn("domain_white_cells_source_snapshot", state)

    def test_unit_mismatch_or_corrupt_numeric_snapshot_blocks_entire_copy(self):
        rules = deepcopy(load_domain_rules("white_cells"))
        next(field for field in rules["fields"] if field["key"] == "wbc_10e9_l")["unit"] = "10^12/L"
        state = self.state()
        with patch.object(workbench.st, "session_state", state), patch.object(workbench, "load_domain_rules", return_value=rules):
            workbench._copy_cbc_values("white_cells")
        self.assertIn("หน่วย", state["domain_white_cells_copy_error"])
        self.assertNotIn("domain_white_cells_input_age", state)
        for value in (float("inf"), float("nan"), True, "4.2"):
            with self.subTest(value=value):
                state = self.state()
                state["cbc_result"].normalized["wbc_10e9_l"] = value
                with patch.object(workbench.st, "session_state", state):
                    workbench._copy_cbc_values("white_cells")
                self.assertIn("domain_white_cells_copy_error", state)
                self.assertNotIn("domain_white_cells_source_snapshot", state)

    def test_missing_values_stay_missing_and_no_metadata_is_invented(self):
        state = self.state(wbc_10e9_l=None)
        del state["cbc_report_metadata"]
        with patch.object(workbench.st, "session_state", state):
            workbench._copy_cbc_values("white_cells")
        self.assertIsNone(state["domain_white_cells_input_wbc_10e9_l"])
        snapshot = state["domain_white_cells_source_snapshot"]
        self.assertEqual(snapshot["copied_values"], {"age": 35.0})
        self.assertEqual(snapshot["input_origin"], "unknown")
        self.assertIsNone(snapshot["report_id"])
        self.assertIsNone(snapshot["evaluated_at"])

    def test_exports_freeze_source_lineage_without_changing_existing_origin(self):
        state = self.state()
        with patch.object(workbench.st, "session_state", state):
            workbench._copy_cbc_values("white_cells")
        source = state["domain_white_cells_source_snapshot"]
        origin = state["domain_white_cells_origin"]
        metadata = report_metadata("white_cells", origin, source_snapshot=source)
        result = analyze_domain("white_cells", source["copied_values"])
        source["copied_values"]["wbc_10e9_l"] = 999
        state["cbc_report_metadata"]["input_origin"] = "manual"
        payload = json.loads(report_json(result, metadata))
        frozen = payload["report"]["source_snapshot"]
        self.assertEqual(payload["report"]["input_origin"], origin)
        self.assertEqual(frozen["input_origin"], "demo")
        self.assertEqual(frozen["copied_values"]["wbc_10e9_l"], 4.2)
        single = dict(csv.reader(io.StringIO(report_csv(result, metadata).decode("utf-8-sig"))))
        batch = next(csv.DictReader(io.StringIO(batch_report_csv([result], [metadata]).decode("utf-8-sig"))))
        for exported in (single, batch):
            self.assertEqual(json.loads(exported["ข้อมูลต้นทางที่คัดลอก (JSON)"]), frozen)
        self.assertNotIn("source_snapshot", report_metadata("white_cells"))


class TransferWorkflowTests(unittest.TestCase):
    def open(self, path):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
        app.switch_page(path).run()
        self.assertFalse(app.exception, [error.message for error in app.exception])
        return app

    def test_demo_lineage_remains_visible_after_copy_navigation_and_evaluation(self):
        app = self.open("pages/3_CBC_Anemia.py")
        app.radio(key="cbc_source").set_value("demo").run()
        app.button(key="cbc_submit").click().run()
        source_metadata = deepcopy(app.session_state["cbc_report_metadata"])
        app.switch_page("pages/5_Marrow_Malignancies.py").run()
        prefix = "domain_marrow_malignancies_"
        app.button(key=prefix + "copy_cbc").click().run()
        self.assertTrue(any("CBC เป็นข้อมูลสมมติ" in warning.value for warning in app.warning))
        # A later local correction must not rewrite the original copied snapshot.
        app.number_input(key=prefix + "input_hb_g_dl").set_value(11.0).run()
        app.switch_page("app.py").run()
        app.switch_page("pages/5_Marrow_Malignancies.py").run()
        app.button(key=prefix + "submit").click().run()
        metadata = app.session_state[prefix + "single_metadata"]
        self.assertEqual(metadata["source_snapshot"]["input_origin"], "demo")
        self.assertEqual(metadata["source_snapshot"]["report_id"], source_metadata["report_id"])
        self.assertEqual(metadata["source_snapshot"]["evaluated_at"], source_metadata["evaluated_at"])
        self.assertEqual(metadata["source_snapshot"]["copied_values"]["hb_g_dl"], 10.8)
        self.assertEqual(app.session_state[prefix + "single_result"].normalized["hb_g_dl"], 11.0)
        self.assertTrue(any("ผลนี้เริ่มจากข้อมูลสมมติ" in warning.value for warning in app.warning))
        app.selectbox(key=prefix + "source").set_value("0").run()
        self.assertNotIn(prefix + "source_snapshot", app.session_state)
        self.assertNotIn(prefix + "single_metadata", app.session_state)
        self.assertFalse(app.exception, [error.message for error in app.exception])

    def test_screening_file_change_warns_without_rewriting_evaluated_report(self):
        app = self.open("pages/1_Laboratory_Screening_Test.py")
        app.radio(key="screening_mode").set_value("ประเมินชุดข้อมูล CSV").run()
        original = b"age,sex,hb_g_dl,mcv_fl,mch_pg\n30,Male,12,70,22\n"
        replacement = b"age,sex,hb_g_dl,mcv_fl,mch_pg\n30,Male,10,71,23\n"
        app.session_state["screening_batch_upload_bytes"] = original
        app.button(key="screening_batch_submit").click().run()
        exported = screening_batch_report_csv(app.session_state["screening_batch_results"])
        app.session_state["screening_batch_upload_bytes"] = replacement
        app.run()
        self.assertTrue(any("ไฟล์ CSV ถูกเปลี่ยนหรือนำออกแล้ว" in warning.value for warning in app.warning))
        self.assertEqual(screening_batch_report_csv(app.session_state["screening_batch_results"]), exported)
        app.button(key="screening_batch_submit").click().run()
        self.assertFalse(any("ไฟล์ CSV ถูกเปลี่ยนหรือนำออกแล้ว" in warning.value for warning in app.warning))
        self.assertEqual(app.session_state["screening_batch_results"].iloc[0]["hb_g_dl"], 10)
        del app.session_state["screening_batch_upload_bytes"]
        app.run()
        self.assertTrue(any("ไฟล์ CSV ถูกเปลี่ยนหรือนำออกแล้ว" in warning.value for warning in app.warning))
        self.assertFalse(app.exception, [error.message for error in app.exception])

    def test_uploader_removal_and_replacement_compare_content_not_filename(self):
        original = b"same-content"
        state = {"screening_batch_input_digest": sha256(original).hexdigest(),
                 "screening_batch_upload": io.BytesIO(original)}
        with patch.object(screening.st, "session_state", state):
            screening._capture_batch_upload()
            self.assertFalse(screening._batch_upload_changed())
            state["screening_batch_upload"] = io.BytesIO(b"changed-content")
            screening._capture_batch_upload()
            self.assertTrue(screening._batch_upload_changed())
            state["screening_batch_upload"] = None
            screening._capture_batch_upload()
            self.assertTrue(screening._batch_upload_changed())
            screening._clear_batch_result()
            self.assertFalse(screening._batch_upload_changed())


if __name__ == "__main__":
    unittest.main()
