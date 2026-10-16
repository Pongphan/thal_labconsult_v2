"""Top navigation preserves workspace/report state without sidebar controls."""
from copy import deepcopy
from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest
from pandas.testing import assert_frame_equal

from ui.navigation import navigation_key
from utils.module_registry import navigation_pages

ROOT = Path(__file__).resolve().parents[1]


class TopNavigationTests(unittest.TestCase):
    def test_learning_topic_and_demo_toggle_survive_navigation_and_topic_changes(self):
        app = self.open()
        app.selectbox(key="platform_learning_module").set_value("cbc_anemia").run()
        app.toggle(key="platform_learning_demo_cbc_anemia").set_value(True).run()
        self.navigate(app, "pages/3_CBC_Anemia.py")
        self.navigate(app, "app.py")
        self.assertEqual(app.selectbox(key="platform_learning_module").value, "cbc_anemia")
        self.assertTrue(app.toggle(key="platform_learning_demo_cbc_anemia").value)
        app.selectbox(key="platform_learning_module").set_value("thalassemia").run()
        app.toggle(key="platform_show_thal_demo").set_value(True).run()
        app.selectbox(key="platform_learning_module").set_value("cbc_anemia").run()
        self.assertTrue(app.toggle(key="platform_learning_demo_cbc_anemia").value)
        app.selectbox(key="platform_learning_module").set_value("thalassemia").run()
        self.assertTrue(app.toggle(key="platform_show_thal_demo").value)

    def open(self):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
        self.assertFalse(app.exception, [item.message for item in app.exception])
        return app

    def navigate(self, app, path):
        app.button(key=f"top_{navigation_key(path)}").click().run()
        self.assertFalse(app.exception, [item.message for item in app.exception])
        self.assertEqual(app.session_state["_platform_current_page"], path)
        # Synchronize AppTest's next-run hash with the native script switch.
        app.switch_page(path)

    def test_every_route_is_reachable_from_top_without_sidebar_controls(self):
        app = self.open()
        pages = navigation_pages()
        expected = [page.title for page in pages]
        for page in (*pages[1:], pages[0]):
            with self.subTest(page=page.path):
                controls = [button for button in app.button if button.key and button.key.startswith("top_thal_nav_")]
                self.assertEqual([button.label for button in controls], expected)
                self.assertFalse(app.sidebar.button)
                self.assertFalse(app.sidebar.selectbox)
                self.assertFalse(app.sidebar.radio)
                self.assertNotIn("_platform_page", [control.key for control in app.main.selectbox])
                self.navigate(app, page.path)
                active = [button for button in app.button if button.key and button.key.startswith("top_thal_nav_")
                          and button.help == "กำลังใช้งาน"]
                self.assertEqual(len(active), 1)
                self.assertIn("กำลังใช้งาน", app.button(key=f"top_{navigation_key(page.path)}").help)

    def test_top_navigation_roundtrip_keeps_reports_and_domain_inputs(self):
        app = self.open()
        self.navigate(app, "pages/3_CBC_Anemia.py")
        app.radio(key="cbc_source").set_value("demo").run()
        app.button(key="cbc_submit").click().run()
        self.assertFalse(app.exception)
        cbc_result = deepcopy(app.session_state["cbc_result"])
        cbc_metadata = deepcopy(app.session_state["cbc_report_metadata"])
        self.navigate(app, "pages/6_Platelets_Bleeding.py")
        prefix = "domain_platelets_bleeding_"
        app.selectbox(key=prefix + "source").set_value("0").run()
        app.button(key=prefix + "submit").click().run()
        self.assertFalse(app.exception)
        domain_result = deepcopy(app.session_state[prefix + "single_result"])
        before = app.number_input(key=prefix + "input_pt_seconds").value
        self.navigate(app, "app.py")
        self.navigate(app, "pages/6_Platelets_Bleeding.py")
        self.assertEqual(app.number_input(key=prefix + "input_pt_seconds").value, before)
        self.assertEqual(app.selectbox(key=prefix + "source").value, "0")
        self.assertEqual(app.session_state[prefix + "single_result"], domain_result)
        self.navigate(app, "pages/3_CBC_Anemia.py")
        self.assertEqual(app.session_state["cbc_result"], cbc_result)
        self.assertEqual(app.session_state["cbc_report_metadata"], cbc_metadata)
        self.assertEqual(len(app.get("download_button")), 2)
        # Clicking the already selected page is a harmless rerun.
        app.button(key=f"top_{navigation_key('pages/3_CBC_Anemia.py')}").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["cbc_result"], cbc_result)

    def test_cbc_roundtrip_keeps_edited_draft_intervals_and_submitted_snapshot(self):
        app = self.open()
        path = "pages/3_CBC_Anemia.py"
        self.navigate(app, path)
        app.radio(key="cbc_source").set_value("demo").run()
        app.checkbox(key="cbc_use_lab_intervals").check().run()
        app.number_input(key="cbc_input_hb_g_dl").set_value(9.1)
        app.number_input(key="cbc_input_wbc_10e9_l").set_value(3.0)
        app.number_input(key="cbc_interval_wbc_10e9_l_low").set_value(4.0)
        app.number_input(key="cbc_interval_wbc_10e9_l_high").set_value(11.0)
        app.button(key="cbc_submit").click().run()
        saved_result = deepcopy(app.session_state["cbc_result"])
        saved_metadata = deepcopy(app.session_state["cbc_report_metadata"])
        self.assertEqual(saved_result.normalized["hb_g_dl"], 9.1)
        self.assertEqual(saved_metadata["input_origin"], "demo")

        # Draft changes are received immediately but don't reevaluate the result.
        self.assertEqual(len(app.get("form")), 0)
        app.number_input(key="cbc_input_hb_g_dl").set_value(8.2).run()
        app.selectbox(key="cbc_input_sex").set_value("Male").run()
        app.selectbox(key="cbc_input_pregnant").set_value("Unknown").run()
        app.number_input(key="cbc_interval_wbc_10e9_l_low").set_value(4.5).run()
        app.checkbox(key="cbc_use_lab_intervals").uncheck().run()
        self.assertEqual(app.session_state["cbc_result"], saved_result)
        self.navigate(app, "app.py")
        self.navigate(app, path)
        self.assertEqual(app.radio(key="cbc_source").value, "demo")
        self.assertEqual(app.number_input(key="cbc_input_hb_g_dl").value, 8.2)
        self.assertEqual(app.selectbox(key="cbc_input_sex").value, "Male")
        self.assertEqual(app.selectbox(key="cbc_input_pregnant").value, "Unknown")
        self.assertFalse(app.checkbox(key="cbc_use_lab_intervals").value)
        app.checkbox(key="cbc_use_lab_intervals").check().run()
        self.assertEqual(app.number_input(key="cbc_interval_wbc_10e9_l_low").value, 4.5)
        self.assertEqual(app.number_input(key="cbc_interval_wbc_10e9_l_high").value, 11.0)
        self.assertEqual(app.session_state["cbc_result"], saved_result)
        self.assertEqual(app.session_state["cbc_report_metadata"], saved_metadata)
        self.assertTrue(any("แก้ไขแล้วยังไม่ได้ประเมิน" in item.value for item in app.warning))
        app.button(key="cbc_submit").click().run()
        self.assertEqual(app.session_state["cbc_result"].normalized["hb_g_dl"], 8.2)
        self.assertFalse(any("แก้ไขแล้วยังไม่ได้ประเมิน" in item.value for item in app.warning))
        self.assertFalse(app.exception, [item.message for item in app.exception])

    def test_domain_draft_survives_mode_and_page_switch_without_reassessment(self):
        app = self.open()
        path = "pages/6_Platelets_Bleeding.py"
        prefix = "domain_platelets_bleeding_"
        self.navigate(app, path)
        app.selectbox(key=prefix + "source").set_value("0").run()
        app.button(key=prefix + "submit").click().run()
        snapshot = deepcopy(app.session_state[prefix + "single_result"])
        self.assertEqual(len(app.get("form")), 0)
        app.number_input(key=prefix + "input_pt_seconds").set_value(18.5).run()
        app.radio(key=prefix + "mode").set_value("batch").run()
        self.navigate(app, "app.py")
        self.navigate(app, path)
        self.assertEqual(app.radio(key=prefix + "mode").value, "batch")
        app.radio(key=prefix + "mode").set_value("single").run()
        self.assertEqual(app.number_input(key=prefix + "input_pt_seconds").value, 18.5)
        self.assertEqual(app.session_state[prefix + "single_result"], snapshot)
        self.assertTrue(any("แก้ไขแล้วยังไม่ได้ประเมิน" in item.value for item in app.warning))
        app.button(key=prefix + "submit").click().run()
        self.assertEqual(app.session_state[prefix + "single_result"].normalized["pt_seconds"], 18.5)
        self.assertFalse(any("แก้ไขแล้วยังไม่ได้ประเมิน" in item.value for item in app.warning))
        self.assertFalse(app.exception, [item.message for item in app.exception])

    def test_pcr_roundtrip_keeps_controls_tolerance_editor_rows_and_genotypes(self):
        from thalab.genetics import BETA_GENOTYPES
        from ui.pcr_visuals import CALL_LABELS

        app = self.open()
        path = "pages/2_PCR_Allele_Matching.py"
        self.navigate(app, path)
        app.button(key="pcr_load_demo").click().run()
        app.selectbox(key="pcr_run_controls").set_value("pass").run()
        app.number_input(key="pcr_tolerance").set_value(41.0).run()
        carrier = list(BETA_GENOTYPES)[1]
        app.selectbox(key="beta_parent1_genotype").set_value(carrier).run()
        app.selectbox(key="beta_parent2_genotype").set_value(carrier).run()
        app.selectbox(key="couple_evidence_basis").set_value("ผลยืนยันทางห้องปฏิบัติการ").run()
        app.text_input(key="pcr_database_search").set_value("SEA").run()
        editor_key = f"pcr_rows_{app.session_state['pcr_editor_epoch']}"
        before = app.session_state["pcr_call_sheet"].copy(deep=True)
        # AppTest has no data_editor setter. Supply its documented delta-shaped
        # session state to exercise the real editor's transformation and storage.
        app.session_state[editor_key] = {
            "edited_rows": {0: {"observed_bp": 731.0}},
            "deleted_rows": [1],
            "added_rows": [{"sample_id": "PCR-011", "target_code": "SEA_DEL",
                            "observed_bp": 730.0, "result": CALL_LABELS["Positive"]}],
        }
        app.run()
        snapshot = app.session_state["pcr_call_sheet"].copy(deep=True)
        self.assertEqual(len(snapshot), len(before))
        self.assertEqual(snapshot.iloc[0]["observed_bp"], 731.0)
        self.assertEqual(snapshot.iloc[-1]["sample_id"], "PCR-011")
        self.assertEqual(app.session_state["pcr_input_origin"], "demo")
        app.run()
        assert_frame_equal(app.session_state["pcr_call_sheet"], snapshot)
        self.navigate(app, "app.py")
        self.navigate(app, path)
        self.assertEqual(app.selectbox(key="pcr_run_controls").value, "pass")
        self.assertEqual(app.number_input(key="pcr_tolerance").value, 41.0)
        self.assertEqual(app.selectbox(key="beta_parent1_genotype").value, carrier)
        self.assertEqual(app.selectbox(key="beta_parent2_genotype").value, carrier)
        self.assertEqual(app.selectbox(key="couple_evidence_basis").value, "ผลยืนยันทางห้องปฏิบัติการ")
        self.assertEqual(app.text_input(key="pcr_database_search").value, "SEA")
        assert_frame_equal(app.session_state["pcr_call_sheet"], snapshot.reset_index(drop=True))
        app.run()
        assert_frame_equal(app.session_state["pcr_call_sheet"], snapshot.reset_index(drop=True))
        app.button(key="pcr_clear").click().run()
        self.assertEqual(len(app.session_state["pcr_call_sheet"]), 1)
        self.assertEqual(app.session_state["pcr_input_origin"], "manual")
        self.assertEqual(app.selectbox(key="pcr_run_controls").value, "not_confirmed")
        self.assertEqual(app.number_input(key="pcr_tolerance").value, 25.0)
        self.assertFalse(app.exception, [item.message for item in app.exception])

    def test_domain_csv_draft_survives_navigation_and_module_reset_clears_it(self):
        from logic.hematology_common import load_domain_rules
        from ui.domain_io import domain_template

        app = self.open()
        path = "pages/4_White_Cells.py"
        prefix = "domain_white_cells_"
        self.navigate(app, path)
        app.radio(key=prefix + "mode").set_value("batch").run()
        draft = domain_template(load_domain_rules("white_cells"), example=True)
        app.session_state[prefix + "batch_csv_bytes"] = draft
        app.run()
        self.navigate(app, "app.py")
        self.navigate(app, path)
        self.assertEqual(app.session_state[prefix + "batch_csv_bytes"], draft)
        self.assertTrue(any("CSV ที่เลือกไว้ยังอยู่" in caption.value for caption in app.caption))
        app.button(key=prefix + "batch_submit").click().run()
        self.assertFalse(app.exception, [item.message for item in app.exception])
        self.assertTrue(app.session_state[prefix + "batch_result"])
        app.button(key=prefix + "reset").click().run()
        self.assertNotIn(prefix + "batch_csv_bytes", app.session_state)

    def test_screening_draft_patient_partner_and_thresholds_survive_navigation(self):
        app = self.open()
        path = "pages/1_Laboratory_Screening_Test.py"
        self.navigate(app, path)
        app.radio(key="screening_single_source").set_value("ใช้ข้อมูลตัวอย่าง").run()
        app.button(key="screening_single_submit").click().run()
        saved = deepcopy(app.session_state["screening_single_result"])
        self.assertEqual(len(app.get("form")), 0)
        app.number_input(key="screening_input_hb_g_dl").set_value(9.1).run()
        app.selectbox(key="screening_partner_oft").set_value("Negative").run()
        app.selectbox(key="screening_partner_dcip").set_value("Negative").run()
        app.checkbox(key="screening_override_indices").check().run()
        app.slider(key="screening_threshold_mcv").set_value(78.5).run()
        self.navigate(app, "app.py")
        self.navigate(app, path)
        self.assertEqual(app.radio(key="screening_single_source").value, "ใช้ข้อมูลตัวอย่าง")
        self.assertEqual(app.number_input(key="screening_input_hb_g_dl").value, 9.1)
        self.assertEqual(app.selectbox(key="screening_partner_oft").value, "Negative")
        self.assertEqual(app.selectbox(key="screening_partner_dcip").value, "Negative")
        self.assertTrue(app.checkbox(key="screening_override_indices").value)
        self.assertEqual(app.slider(key="screening_threshold_mcv").value, 78.5)
        self.assertEqual(app.session_state["screening_single_result"], saved)
        app.button(key="screening_single_submit").click().run()
        self.assertEqual(app.session_state["screening_single_result"].normalized["hb_g_dl"], 9.1)
        self.assertEqual(app.session_state["screening_single_result"].input_origin, "demo")
        self.assertFalse(app.exception, [item.message for item in app.exception])


if __name__ == "__main__":
    unittest.main()
