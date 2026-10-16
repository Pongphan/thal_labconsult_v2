"""Exercise every new workspace through the real Streamlit entrypoint."""
from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest

from logic.hematology_common import DOMAIN_IDS, load_domain_rules
from utils.module_registry import load_modules

ROOT = Path(__file__).resolve().parents[1]


class DomainAppTests(unittest.TestCase):
    def open(self, module_id):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
        path = next(module.routes[0].path for module in load_modules() if module.id == module_id)
        app.switch_page(path).run()
        self.assertFalse(app.exception, [error.message for error in app.exception])
        return app

    def test_each_form_blank_then_explicit_example_and_reports(self):
        for module_id in DOMAIN_IDS:
            with self.subTest(module=module_id):
                prefix = f"domain_{module_id}_"
                app = self.open(module_id)
                self.assertNotIn(prefix + "single_result", app.session_state)
                self.assertEqual(len(app.get("download_button")), 0)
                for widget in app.number_input:
                    self.assertIsNone(widget.value)
                app.selectbox(key=prefix + "source").set_value("0").run()
                self.assertNotIn(prefix + "single_result", app.session_state)
                app.button(key=prefix + "submit").click().run()
                self.assertFalse(app.exception, [error.message for error in app.exception])
                self.assertFalse(app.session_state[prefix + "single_result"].validation_errors)
                self.assertEqual(len(app.get("download_button")), 2)

    def test_each_batch_preserves_all_examples_and_exports(self):
        for module_id in DOMAIN_IDS:
            with self.subTest(module=module_id):
                prefix = f"domain_{module_id}_"
                app = self.open(module_id)
                app.radio(key=prefix + "mode").set_value("batch").run()
                app.radio(key=prefix + "batch_source").set_value("demo").run()
                app.button(key=prefix + "batch_submit").click().run()
                self.assertFalse(app.exception, [error.message for error in app.exception])
                results = app.session_state[prefix + "batch_result"]
                self.assertEqual(len(results), len(load_domain_rules(module_id)["examples"]))
                self.assertGreaterEqual(len(app.get("download_button")), 4)

    def test_navigation_selection_opens_workspaces_and_reset_is_isolated(self):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
        app.button(key="top_thal_nav_4_White_Cells").click().run()
        self.assertFalse(app.exception, [error.message for error in app.exception])
        prefix = "domain_white_cells_"
        self.assertIsNotNone(app.selectbox(key=prefix + "source"))
        # AppTest does not update its next-run page hash after a script switch;
        # synchronize its public page selector with the page already rendered.
        app.switch_page("pages/4_White_Cells.py")
        app.selectbox(key=prefix + "source").set_value("0").run()
        app.button(key=prefix + "submit").click().run()
        app.session_state["screening_test_sentinel"] = "preserve"
        app.session_state["domain_transfusion_test_sentinel"] = "preserve"
        app.button(key=prefix + "reset").click().run()
        self.assertFalse(app.exception, [error.message for error in app.exception])
        self.assertNotIn(prefix + "single_result", app.session_state)
        self.assertEqual(app.session_state["screening_test_sentinel"], "preserve")
        self.assertEqual(app.session_state["domain_transfusion_test_sentinel"], "preserve")

    def test_inputs_and_origin_persist_across_modes_and_pages(self):
        prefix = "domain_platelets_bleeding_"
        app = self.open("platelets_bleeding")
        app.selectbox(key=prefix + "source").set_value("0").run()
        before = app.number_input(key=prefix + "input_pt_seconds").value
        self.assertIsNotNone(before)
        app.radio(key=prefix + "mode").set_value("batch").run()
        app.radio(key=prefix + "mode").set_value("single").run()
        self.assertFalse(app.exception, [error.message for error in app.exception])
        self.assertEqual(app.number_input(key=prefix + "input_pt_seconds").value, before)
        self.assertEqual(app.selectbox(key=prefix + "source").value, "0")
        app.switch_page("app.py").run()
        app.switch_page("pages/6_Platelets_Bleeding.py").run()
        self.assertFalse(app.exception, [error.message for error in app.exception])
        self.assertEqual(app.number_input(key=prefix + "input_pt_seconds").value, before)
        self.assertEqual(app.selectbox(key=prefix + "source").value, "0")
        self.assertEqual(app.session_state[prefix + "origin"], "ข้อมูลสมมติ")

    def test_copy_from_cbc_resets_unrelated_demo_evidence(self):
        from logic.cbc import analyze_cbc
        app = self.open("white_cells")
        prefix = "domain_white_cells_"
        app.selectbox(key=prefix + "source").set_value("0").run()
        app.session_state["cbc_result"] = analyze_cbc({"age": 30, "sex": "Male", "hb_g_dl": 13, "mcv_fl": 85, "wbc_10e9_l": 4})
        app.run()
        app.button(key=prefix + "copy_cbc").click().run()
        self.assertFalse(app.exception, [error.message for error in app.exception])
        self.assertEqual(app.selectbox(key=prefix + "source").value, "blank")
        self.assertEqual(app.number_input(key=prefix + "input_wbc_10e9_l").value, 4.0)
        self.assertIsNone(app.number_input(key=prefix + "input_temperature_c").value)
        self.assertNotIn(prefix + "single_result", app.session_state)


if __name__ == "__main__":
    unittest.main()
