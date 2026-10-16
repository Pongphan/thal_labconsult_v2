"""Learning visuals and top navigation never create or overwrite clinical results."""
from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest

from ui.home_visuals import collection_counts
from ui.navigation import navigation_key
from ui.wbc_learning import CASES, balance_chart, case_result
from utils.module_registry import load_modules, navigation_pages

ROOT = Path(__file__).resolve().parents[1]


class HomeVisualTests(unittest.TestCase):
    def test_wbc_lesson_preserves_absolute_values_and_incomplete_data(self):
        for case, expected in (("balanced", 4), ("exceeds", 6), ("partial", 1)):
            with self.subTest(case=case):
                result = case_result(case)
                total = result.calculated["absolute_total"]
                self.assertEqual(total["known_total_10e9_l"], expected)
                self.assertFalse(total["complete"])
                chart = balance_chart(total)
                # Remainder is explicitly named, never treated as a measured cell count.
                known = sum(trace.x[0] for trace in chart.data if trace.name != "ส่วนที่ยังอธิบายไม่ได้")
                self.assertEqual(known, expected)
                self.assertEqual(chart.layout.shapes[0].x0, 4)
                self.assertGreater(chart.layout.xaxis.range[1], max(expected, 4))
                if case == "exceeds":
                    self.assertEqual(result.status, "invalid")
                if case == "partial":
                    self.assertEqual(chart.data[-1].name, "ส่วนที่ยังอธิบายไม่ได้")
                    self.assertEqual(chart.data[-1].x[0], 3)

    def test_wbc_lesson_is_isolated_from_saved_results(self):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
        app.session_state["white_cells_result"] = {"sentinel": "submitted"}
        app.session_state["cbc_result"] = {"sentinel": "cbc"}
        for case in CASES:
            app.selectbox(key="home_wbc_case").set_value(case).run()
            self.assertFalse(app.exception, [item.message for item in app.exception])
            self.assertEqual(app.session_state["white_cells_result"], {"sentinel": "submitted"})
            self.assertEqual(app.session_state["cbc_result"], {"sentinel": "cbc"})
            self.assertFalse(app.get("download_button"))
            if case == "exceeds":
                self.assertTrue(any("ผลรวม 6 เกิน WBC 4" in item.value for item in app.error))
            if case == "partial":
                self.assertTrue(any("ทราบเพียง 1 จาก WBC 4" in item.value for item in app.info))

    def test_exploring_every_topic_preserves_workspace_and_chart_labels(self):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
        app.session_state["screening_single_result"] = {"sentinel": "existing result"}
        app.session_state["cbc_input_hb_g_dl"] = 12.3
        for module in load_modules():
            with self.subTest(module=module.id):
                app.selectbox(key="home_explorer_module").set_value(module.id).run()
                self.assertFalse(app.exception, [item.message for item in app.exception])
                self.assertEqual(app.session_state["screening_single_result"], {"sentinel": "existing result"})
                self.assertEqual(app.session_state["cbc_input_hb_g_dl"], 12.3)
                self.assertEqual(len(app.get("plotly_chart")), 3)
                self.assertFalse(app.get("download_button"))
                self.assertTrue(any("ไม่ใช่จำนวนผู้ป่วย" in caption.value for caption in app.caption))
                labels = {item.proto.label for item in app.get("page_link")}
                self.assertTrue(all(f"เปิด {route.title}" in labels for route in module.routes))
        self.assertEqual(int(app.metric[3].value), sum(collection_counts().values()))

    def test_top_navigation_reaches_all_pages_and_preserves_submitted_cbc(self):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
        cbc_path = "pages/3_CBC_Anemia.py"
        app.button(key=f"top_{navigation_key(cbc_path)}").click().run()
        app.switch_page(cbc_path)
        app.radio(key="cbc_source").set_value("demo").run()
        app.button(key="cbc_submit").click().run()
        snapshot = app.session_state["cbc_result"]
        for page in navigation_pages():
            with self.subTest(page=page.path):
                app.button(key=f"top_{navigation_key(page.path)}").click().run()
                self.assertFalse(app.exception, [item.message for item in app.exception])
                self.assertEqual(app.session_state["_platform_current_page"], page.path)
                self.assertEqual(app.session_state["cbc_result"], snapshot)
                app.switch_page(page.path)


if __name__ == "__main__":
    unittest.main()
