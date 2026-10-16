"""Guard platform navigation and preserve existing routes as modules expand."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from utils.module_registry import CATALOG_PATH, ROOT, load_modules, navigation_groups, navigation_pages, presentation_specs
from logic.hematology_common import DOMAIN_IDS


class PlatformRegistryTests(unittest.TestCase):
    def test_presentation_catalog_covers_routes_and_preserves_four_groups(self):
        from ui.palette import CARD_TONES, resolve_tone
        groups = navigation_groups()
        self.assertEqual([group.id for group in groups], ["home", "red_cells", "white_cells", "other"])
        self.assertEqual([[module.id for module in group.modules] for group in groups], [
            [], ["cbc_anemia", "thalassemia"], ["white_cells", "marrow_malignancies"],
            ["platelets_bleeding", "thrombosis", "transfusion", "morphology_quality"],
        ])
        for module in load_modules():
            self.assertIn(module.presentation.tone, CARD_TONES)
            self.assertEqual(resolve_tone(module.id), module.presentation.tone)
            self.assertEqual(presentation_specs()[module.id], module.presentation)
        self.assertEqual(len(navigation_pages()), 11)

    def test_group_assignment_and_chart_labels_follow_catalog_metadata(self):
        from ui.home_visuals import example_chart
        modules = load_modules()
        changed = replace(modules[0], presentation=replace(
            modules[0].presentation, group="other", short_name="Catalog label", tone="mint",
        ))
        replacement = (changed, *modules[1:])
        with patch("utils.module_registry.load_modules", return_value=replacement):
            groups = navigation_groups()
            self.assertEqual([module.id for module in groups[1].modules], ["thalassemia"])
            self.assertEqual(groups[3].modules[0].id, "cbc_anemia")
        with patch("ui.home_visuals.load_modules", return_value=replacement):
            figure = example_chart({module.id: 1 for module in replacement}, "cbc_anemia")
            self.assertEqual(figure.data[0].y[0], "Catalog label")

    def test_registry_rejects_missing_or_malformed_presentation(self):
        original = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        invalid_values = [None, {}, {"group": "other"}]
        for key, value in (("group", "fifth_group"), ("icon", "javascript:alert(1)"), ("tone", "x; color:red"), ("short_name", "")):
            metadata = dict(original["modules"][0]["presentation"])
            metadata[key] = value
            invalid_values.append(metadata)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "modules.json"
            for metadata in invalid_values:
                with self.subTest(metadata=metadata):
                    payload = deepcopy(original)
                    payload["modules"][0]["presentation"] = metadata
                    path.write_text(json.dumps(payload), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_modules(path)

    def test_only_implemented_modules_have_routes_and_old_routes_exist(self):
        modules = load_modules()
        self.assertEqual({m.id for m in modules if m.status == "draft"}, {"cbc_anemia", "thalassemia", *DOMAIN_IDS})
        self.assertEqual(len(modules), 8)
        for module in modules:
            if module.status == "planned":
                self.assertFalse(module.routes)
        paths = {page.path for page in navigation_pages()}
        self.assertTrue({"app.py", "pages/1_Laboratory_Screening_Test.py",
                         "pages/2_PCR_Allele_Matching.py", "pages/3_CBC_Anemia.py"} <= paths)
        for path in paths:
            self.assertTrue((ROOT / path).is_file(), path)

    def test_registry_rejects_duplicate_unsafe_or_planned_routes(self):
        original = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        invalid = []
        duplicate = deepcopy(original)
        duplicate["modules"].append(duplicate["modules"][0])
        invalid.append(duplicate)
        planned_route = deepcopy(original)
        planned_route["modules"][0]["status"] = "planned"
        invalid.append(planned_route)
        for path in ("../app.py", "https://example.com/app.py", "pages/../app.py", "pages\\bad.py", "pages/10_Reporting.py"):
            payload = deepcopy(original)
            payload["modules"][0]["routes"][0]["path"] = path
            invalid.append(payload)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "modules.json"
            for payload in invalid:
                with self.subTest(payload=payload):
                    path.write_text(json.dumps(payload), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_modules(path)


if __name__ == "__main__":
    unittest.main()
