"""Learning catalog, engine safeguards and isolation from actual workspaces."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from logic.cbc import CBCResult
from logic.hematology_common import DOMAIN_IDS
from utils.learning import LEARNING_PATH, build_learning_demo, load_learning_modules
from utils.module_registry import load_modules


ROOT = Path(__file__).resolve().parents[1]
MODULE_IDS = {"cbc_anemia", "thalassemia", "white_cells", "marrow_malignancies",
              "platelets_bleeding", "thrombosis", "transfusion", "morphology_quality"}
DEMO_IDS = ("cbc_anemia", *DOMAIN_IDS)


class LearningTests(unittest.TestCase):
    def test_catalog_covers_exactly_eight_modules_with_reviewed_content(self):
        catalog = load_learning_modules()
        self.assertEqual(set(catalog), MODULE_IDS)
        self.assertEqual(set(catalog), {module.id for module in load_modules()})
        for module_id, topic in catalog.items():
            with self.subTest(module=module_id):
                self.assertEqual(len(topic["pathway"]), 3)
                self.assertEqual(len(topic["focus"]), 3)
                self.assertEqual(len(topic["limitations"]), 2)
                self.assertTrue(topic["reviewed_on"])
                self.assertTrue(topic["intro"] and topic["example_question"] and topic["sources"])

    def test_incomplete_duplicate_and_unsafe_catalogs_fail_with_thai_message(self):
        original = json.loads(LEARNING_PATH.read_text(encoding="utf-8"))
        invalid = []
        missing = deepcopy(original)
        missing["modules"].pop()
        invalid.append(("missing module", missing))
        duplicate = deepcopy(original)
        duplicate["modules"].append(deepcopy(duplicate["modules"][0]))
        invalid.append(("duplicate module", duplicate))
        unknown = deepcopy(original)
        unknown["modules"][0]["id"] = "not-a-module"
        invalid.append(("unknown module", unknown))
        incomplete = deepcopy(original)
        incomplete["modules"][0]["pathway"].pop()
        invalid.append(("incomplete pathway", incomplete))
        no_sources = deepcopy(original)
        no_sources["modules"][0]["sources"] = []
        invalid.append(("missing sources", no_sources))
        for url in ("javascript:alert(1)", "http://example.org/source", "file:///tmp/source",
                    "https:///missing-host", "https://user:password@example.org/source"):
            unsafe = deepcopy(original)
            unsafe["modules"][0]["sources"][0]["url"] = url
            invalid.append((url, unsafe))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "learning.json"
            for label, payload in invalid:
                with self.subTest(case=label):
                    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "ข้อมูลการเรียนรู้ไม่ครบหรือรูปแบบไม่ถูกต้อง"):
                        load_learning_modules(path)

    def test_seven_engine_demos_are_valid_and_return_independent_snapshots(self):
        for module_id in DEMO_IDS:
            with self.subTest(module=module_id):
                first = build_learning_demo(module_id)
                second = build_learning_demo(module_id)
                self.assertTrue(first.name and first.input_rows and first.result.findings)
                self.assertFalse(first.result.validation_errors)
                self.assertEqual(first.result.to_dict(), second.result.to_dict())
                self.assertEqual(len(first.result.ruleset_hash), 64)
                json.dumps(first.result.to_dict(), ensure_ascii=False, allow_nan=False)
                first.result.findings.append("LOCAL MUTATION")
                first.result.normalized["test_only"] = True
                first.input_rows.clear()
                fresh = build_learning_demo(module_id)
                self.assertEqual(fresh.result.to_dict(), second.result.to_dict())
                self.assertTrue(fresh.input_rows)

    def test_demos_preserve_clinical_guardrails(self):
        cbc = build_learning_demo("cbc_anemia").result
        self.assertIsInstance(cbc, CBCResult)
        self.assertEqual((cbc.support_code, cbc.pattern_code, cbc.anemia_code),
                         ("supported", "micro", "below_cutoff"))
        self.assertFalse(cbc.low_hb_alert)
        wbc = build_learning_demo("white_cells").result
        self.assertAlmostEqual(wbc.calculated["absolute_counts"]["anc"]["effective"], 3.6)
        self.assertTrue(wbc.validation_warnings)
        marrow = build_learning_demo("marrow_malignancies").result
        self.assertEqual(marrow.status, "urgent")
        self.assertTrue(marrow.alerts)
        self.assertEqual(marrow.normalized["pml_rara"], "unknown")
        self.assertFalse(build_learning_demo("thrombosis").result.calculated["vte_excluded_by_tool"])
        transfusion = build_learning_demo("transfusion").result
        self.assertTrue(transfusion.calculated["compatibility_review_ready"])
        self.assertFalse(transfusion.calculated["release_authorized"])
        morphology = build_learning_demo("morphology_quality").result
        self.assertEqual(morphology.calculated["quality_gate"], "hold_for_review")
        self.assertFalse(morphology.calculated["report_authorized"])

    def test_non_engine_and_unknown_demo_ids_are_rejected(self):
        for module_id in ("thalassemia", "unknown", "../cbc"):
            with self.subTest(module=module_id):
                with self.assertRaisesRegex(ValueError, "ไม่พบตัวอย่างการเรียนรู้"):
                    build_learning_demo(module_id)

    def test_spectrum_does_not_assign_fixed_severity_to_genotypes(self):
        from thalab.viz import thalassemia_spectrum_chart

        for theme in ("light", "dark"):
            with self.subTest(theme=theme), patch("thalab.viz.current_theme_type", return_value=theme):
                figure = thalassemia_spectrum_chart()
                self.assertFalse(figure.layout.xaxis.visible)
                self.assertFalse(figure.layout.yaxis.visible)
                self.assertFalse(figure.layout.shapes)
                cues = {}
                for trace in figure.data:
                    self.assertNotIn("risk", trace.name.lower())
                    self.assertNotIn("lines", trace.mode)
                    cues.update({label: values[1] for label, values in zip(trace.text, trace.customdata)})
                self.assertEqual(len(cues), 13)
                self.assertIn("ซีดเล็กน้อย", cues["Homozygous HbE"])
                self.assertIn("แปรผัน", cues["HbE/β0-thal"])
                self.assertIn("ไม่ระบุความรุนแรง", cues["Homozygous β-thal"])
                self.assertTrue(figure.to_json())


class LearningAppTests(unittest.TestCase):
    def open_home(self):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
        self.assertFalse(app.exception, [error.message for error in app.exception])
        return app

    def workspace_state(self, app):
        prefixes = ("cbc_", "screening_", "domain_", "pcr_", "genetics_")
        return {key: app.session_state[key] for key in app.session_state if key.startswith(prefixes)}

    def test_home_selection_has_all_topics_three_tabs_and_correct_workspace_links(self):
        with patch("ui.learning.build_learning_demo", wraps=build_learning_demo) as factory:
            app = self.open_home()
            modules = load_modules()
            self.assertEqual(app.selectbox(key="platform_learning_module").options, [module.title for module in modules])
            self.assertEqual(app.selectbox(key="platform_learning_module").value, "thalassemia")
            for module in modules:
                with self.subTest(module=module.id):
                    # Workspace cards were removed; the independent explorer still
                    # provides the catalog-backed destination for each learning link.
                    app.selectbox(key="home_explorer_module").set_value(module.id)
                    app.selectbox(key="platform_learning_module").set_value(module.id).run()
                    self.assertFalse(app.exception, [error.message for error in app.exception])
                    destinations = {link.proto.label: link.proto.page_script_hash for link in app.get("page_link")}
                    self.assertEqual([tab.label for tab in app.tabs],
                                     ["ภาพรวมและลำดับการทบทวน", "ตัวอย่างจำลอง", "ขอบเขตและแหล่งเรียนรู้"])
                    links = list(app.get("page_link"))[-len(module.routes):]
                    self.assertEqual([link.proto.label for link in links], [route.title for route in module.routes])
                    for link, route in zip(links, module.routes):
                        self.assertEqual(link.proto.page_script_hash, destinations[f"เปิด {route.title}"])
                    self.assertFalse(app.get("download_button"))
                    self.assertFalse(self.workspace_state(app))
            factory.assert_not_called()

    def test_all_engine_toggles_render_synthetic_cautions_without_workspace_changes(self):
        app = self.open_home()
        sentinels = {
            "cbc_result": build_learning_demo("cbc_anemia").result,
            "cbc_input_hb_g_dl": 12.3,
            "screening_single_result": {"source": "WORKSPACE SENTINEL"},
            "domain_white_cells_single_result": build_learning_demo("white_cells").result,
            "domain_platelets_bleeding_input_pt_seconds": 13.2,
            "pcr_control_status": "not_confirmed",
            "genetics_evidence_basis": "confirmed",
        }
        for key, value in sentinels.items():
            app.session_state[key] = deepcopy(value)
        before = deepcopy(self.workspace_state(app))
        for module_id in DEMO_IDS:
            with self.subTest(module=module_id):
                app.selectbox(key="platform_learning_module").set_value(module_id).run()
                app.toggle(key=f"platform_learning_demo_{module_id}").set_value(True).run()
                self.assertFalse(app.exception, [error.message for error in app.exception])
                result = build_learning_demo(module_id).result
                rendered_text = "\n".join(element.value for element in app.markdown)
                self.assertIn("กรณีสมมติ", rendered_text)
                self.assertIn("ไม่ใช่ผลผู้ป่วย", rendered_text)
                for finding in result.findings:
                    self.assertIn(finding, rendered_text)
                for warning in result.validation_warnings:
                    self.assertTrue(any(warning in item.value for item in app.warning))
                for alert in getattr(result, "alerts", []):
                    self.assertTrue(any(alert in item.value for item in app.error))
                self.assertEqual(self.workspace_state(app), before)
                self.assertEqual(len(app.get("download_button")), 0)
                self.assertEqual(len(app.get("plotly_chart")), 3)
                self.assertEqual(len(app.dataframe), 1)

    def test_turning_demo_off_removes_result_and_does_not_recompute(self):
        app = self.open_home()
        app.selectbox(key="platform_learning_module").set_value("white_cells").run()
        baseline_warnings = [item.value for item in app.warning]
        with patch("ui.learning.build_learning_demo", wraps=build_learning_demo) as factory:
            app.toggle(key="platform_learning_demo_white_cells").set_value(True).run()
            self.assertEqual(factory.call_count, 1)
            self.assertTrue(any("ข้อควรทบทวนในตัวอย่าง" in item.value for item in app.warning))
            self.assertEqual(len(app.dataframe), 1)
            app.toggle(key="platform_learning_demo_white_cells").set_value(False).run()
            self.assertFalse(app.exception, [error.message for error in app.exception])
            self.assertEqual(factory.call_count, 1)
            self.assertEqual([item.value for item in app.warning], baseline_warnings)
            self.assertFalse(app.dataframe)
            self.assertFalse(app.get("download_button"))
            self.assertFalse(self.workspace_state(app))


if __name__ == "__main__":
    unittest.main()
