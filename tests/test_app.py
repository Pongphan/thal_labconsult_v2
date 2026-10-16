"""Headless Streamlit workflow checks against the real multipage entrypoint."""
from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


class AppTests(unittest.TestCase):
    def open_page(self, path=None):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        if path:
            app.switch_page(path).run()
            self.assertFalse(app.exception, [e.message for e in app.exception])
        return app

    def submit(self, app, label):
        next(button for button in app.button if button.label == label).click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])

    def test_platform_home_and_preserved_learning_demo(self):
        app = self.open_page()
        self.assertEqual(int(app.metric[1].value), 8)
        self.assertEqual(int(app.metric[2].value), 9)
        self.assertTrue(any("ภายในเครื่อง" in item.value for item in app.caption))
        self.assertEqual(len(app.get("plotly_chart")), 3)
        app.toggle(key="platform_show_thal_demo").set_value(True).run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(len(app.get("plotly_chart")), 5)

    def test_cbc_blank_demo_report_and_isolated_reset(self):
        from ui.cbc import RESULT_LABELS, cbc_report_csv, cbc_report_payload
        from utils.reporting import to_json_bytes
        import json

        app = self.open_page("pages/3_CBC_Anemia.py")
        self.assertIsNone(app.number_input(key="cbc_input_hb_g_dl").value)
        self.assertNotIn("cbc_result", app.session_state)
        self.assertEqual(len(app.get("download_button")), 0)
        app.radio(key="cbc_source").set_value("demo").run()
        self.assertNotIn("cbc_result", app.session_state)
        app.button(key="cbc_submit").click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        result = app.session_state["cbc_result"]
        self.assertEqual(result.pattern_code, "micro")
        self.assertEqual(result.anemia_code, "below_cutoff")
        self.assertEqual(len(app.get("download_button")), 2)
        metadata = app.session_state["cbc_report_metadata"]
        report = json.loads(to_json_bytes(cbc_report_payload(result, metadata)))
        self.assertEqual(report["normalized"], result.normalized)
        self.assertEqual(report["thresholds_used"], result.thresholds_used)
        self.assertEqual(report["ruleset_hash"], result.ruleset_hash)
        self.assertFalse(set(result.to_dict()) - set(RESULT_LABELS))
        csv = cbc_report_csv(result, metadata)
        self.assertTrue(csv.startswith(b"\xef\xbb\xbf"))
        self.assertIn("รายงานช่วยทบทวน CBC", csv.decode("utf-8-sig"))
        app.session_state["screening_test_sentinel"] = "preserve"
        app.button(key="cbc_reset").click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertNotIn("cbc_result", app.session_state)
        self.assertIsNone(app.number_input(key="cbc_input_hb_g_dl").value)
        self.assertEqual(app.session_state["screening_test_sentinel"], "preserve")

    def test_cbc_scope_invalid_values_and_low_hb_banner(self):
        app = self.open_page("pages/3_CBC_Anemia.py")
        app.radio(key="cbc_source").set_value("demo").run()
        app.number_input(key="cbc_input_age").set_value(5.0)
        app.number_input(key="cbc_input_hb_g_dl").set_value(6.0)
        app.button(key="cbc_submit").click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        result = app.session_state["cbc_result"]
        self.assertEqual(result.support_code, "out_of_scope")
        self.assertEqual(result.anemia_code, "not_assessed")
        self.assertFalse(result.severe_anemia_flag)
        self.assertTrue(result.low_hb_alert)
        self.assertTrue(any("Hb ต่ำ" in error.value for error in app.error))
        app.number_input(key="cbc_input_age").set_value(30.0)
        app.number_input(key="cbc_input_mcv_fl").set_value(999.0)
        app.button(key="cbc_submit").click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        result = app.session_state["cbc_result"]
        self.assertEqual(result.support_code, "invalid")
        self.assertTrue(result.validation_errors)
        self.assertTrue(result.low_hb_alert)

    def test_cbc_lab_intervals_echo_in_report_and_validate(self):
        from ui.cbc import cbc_report_payload
        app = self.open_page("pages/3_CBC_Anemia.py")
        app.radio(key="cbc_source").set_value("demo").run()
        app.checkbox(key="cbc_use_lab_intervals").check().run()
        app.number_input(key="cbc_input_wbc_10e9_l").set_value(3.0)
        app.number_input(key="cbc_interval_wbc_10e9_l_low").set_value(4.0)
        app.number_input(key="cbc_interval_wbc_10e9_l_high").set_value(11.0)
        app.button(key="cbc_submit").click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        result = app.session_state["cbc_result"]
        self.assertIn("CBC_LAB_REFERENCE_WBC_10E9_L_LOW", result.rules_used)
        report = cbc_report_payload(result, app.session_state["cbc_report_metadata"])
        self.assertEqual(report["reference_intervals_used"]["wbc_10e9_l"], {"low": 4.0, "high": 11.0})
        app.number_input(key="cbc_interval_wbc_10e9_l_low").set_value(12.0)
        app.button(key="cbc_submit").click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertTrue(app.session_state["cbc_result"].validation_errors)

    def test_blank_form_then_requested_example(self):
        app = self.open_page("pages/1_Laboratory_Screening_Test.py")
        self.assertIsNone(app.number_input(key="screening_input_hb_g_dl").value)
        self.assertNotIn("screening_single_result", app.session_state)
        values = {"age": 24, "hb_g_dl": 10.2, "mcv_fl": 68, "mch_pg": 21, "rdw_percent": 15,
                  "hba2_percent": 5.1, "hbf_percent": 1.5}
        for field, value in values.items():
            app.number_input(key=f"screening_input_{field}").set_value(float(value))
        self.submit(app, "ประเมินผลคัดกรอง")
        result = app.session_state["screening_single_result"]
        self.assertIn("beta-thalassemia trait", result.top_pattern)
        self.assertFalse(result.validation_errors)
        self.assertEqual(len(app.get("download_button")), 3)

    def test_invalid_input_and_age_profile(self):
        app = self.open_page("pages/1_Laboratory_Screening_Test.py")
        self.submit(app, "ประเมินผลคัดกรอง")
        self.assertTrue(app.session_state["screening_single_result"].validation_errors)
        for field, value in {"hb_g_dl": 11, "mcv_fl": 78, "mch_pg": 25, "age": 4}.items():
            app.number_input(key=f"screening_input_{field}").set_value(float(value))
        self.submit(app, "ประเมินผลคัดกรอง")
        result = app.session_state["screening_single_result"]
        self.assertEqual(result.thresholds_used["mcv_microcytosis"], 75)
        self.assertFalse(result.microcytosis)

    def test_batch_demo_and_experimental_layer(self):
        app = self.open_page("pages/1_Laboratory_Screening_Test.py")
        app.radio(key="screening_mode").set_value("ประเมินชุดข้อมูล CSV").run()
        app.radio(key="screening_batch_source").set_value("ใช้ชุดข้อมูลตัวอย่าง").run()
        self.submit(app, "ประเมินชุดข้อมูล")
        self.assertEqual(len(app.session_state["screening_batch_results"]), 6)
        app.checkbox(key="screening_experimental_ml").check().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])

    def test_molecular_controls_and_couple_workflows(self):
        app = self.open_page("pages/2_PCR_Allele_Matching.py")
        app.button(key="pcr_load_demo").click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        app.selectbox(key="pcr_run_controls").set_value("pass").run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        from thalab.genetics import BETA_GENOTYPES
        carrier = list(BETA_GENOTYPES)[1]
        app.selectbox(key="beta_parent1_genotype").set_value(carrier).run()
        app.selectbox(key="beta_parent2_genotype").set_value(carrier).run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        app.button(key="pcr_clear").click().run()
        self.assertEqual(app.selectbox(key="pcr_run_controls").value, "not_confirmed")
        self.assertFalse(app.exception, [e.message for e in app.exception])


    def test_invalid_partner_can_be_corrected_without_losing_patient(self):
        app = self.open_page("pages/1_Laboratory_Screening_Test.py")
        app.radio(key="screening_single_source").set_value("ใช้ข้อมูลตัวอย่าง").run()
        self.submit(app, "ประเมินผลคัดกรอง")
        app.selectbox(key="screening_partner_oft").set_value("Invalid")
        self.submit(app, "ประเมินข้อมูลคัดกรองของคู่")
        self.assertFalse(app.session_state["screening_single_result"].validation_errors)
        app.selectbox(key="screening_partner_oft").set_value("Negative")
        app.selectbox(key="screening_partner_dcip").set_value("Negative")
        self.submit(app, "ประเมินข้อมูลคัดกรองของคู่")
        self.assertEqual(app.session_state["screening_single_result"].normalized["partner_oft"], "Negative")

    def test_invalid_batch_row_keeps_independent_urgent_banner(self):
        import pandas as pd
        from thalab.core import analyze_dataframe
        app = self.open_page("pages/1_Laboratory_Screening_Test.py")
        app.radio(key="screening_mode").set_value("ประเมินชุดข้อมูล CSV").run()
        app.session_state["screening_batch_results"] = analyze_dataframe(pd.DataFrame([
            {"hb_g_dl": 6, "mcv_fl": 999, "mch_pg": 20}]))
        app.session_state["screening_batch_thresholds"] = {"hba2_beta_trait": 3.5}
        app.run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertTrue(any("Hb ต่ำรุนแรง 1" in error.value for error in app.error))
        self.assertEqual(len(app.get("plotly_chart")), 0)


if __name__ == "__main__":
    unittest.main()
