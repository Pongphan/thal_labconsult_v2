"""The review package must cover each workspace and detect source drift."""
import ast
import csv
import importlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts.generate_rule_inventory import ROOT, OUTPUT, SPECS, build_rows, render_inventory


class RuleInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = build_rows()

    def test_checked_in_inventory_matches_current_code_and_rules(self):
        self.assertEqual((ROOT / OUTPUT).read_bytes(), render_inventory(),
                         "Run python scripts/generate_rule_inventory.py and review its diff")

    def test_all_registered_modules_rule_files_and_pcr_targets_are_present(self):
        modules = json.loads((ROOT / "data/modules.json").read_text(encoding="utf-8"))["modules"]
        self.assertTrue({module["id"] for module in modules} <= {row["module"] for row in self.rows})
        expected_configs = {str(path.relative_to(ROOT)).replace("\\", "/") for path in (ROOT / "data").glob("*rules.json")}
        self.assertTrue(expected_configs <= {row["implementation"] for row in self.rows if row["entry_kind"] == "configuration"})
        panel = json.loads((ROOT / "data/allele_panel.json").read_text(encoding="utf-8"))
        self.assertEqual({"PCR_TARGET:" + allele["target_code"] for allele in panel["alleles"]},
                         {row["rule_id"] for row in self.rows if row["entry_kind"] == "demonstration_target"})
        self.assertTrue(any(row["implementation"].startswith("thalab/genetics.py:") for row in self.rows))

    def test_runtime_rule_ids_from_every_domain_example_have_concrete_rows(self):
        for module in ("white_cells", "marrow_malignancies", "platelets_bleeding", "thrombosis", "transfusion", "morphology_quality"):
            config = json.loads((ROOT / SPECS[module][0]).read_text(encoding="utf-8"))
            analyze = getattr(importlib.import_module("logic." + module), "analyze_" + module)
            listed = {row["rule_id"] for row in self.rows if row["module"] == module and row["entry_kind"] == "emitted_rule"}
            for example in config["examples"]:
                with self.subTest(module=module, example=example.get("id", example.get("title"))):
                    self.assertTrue(set(analyze(example["data"]).rules_used) <= listed)
            self.assertFalse(any("*" in rule_id for rule_id in listed))

    def test_screening_rules_and_grouping_labels_are_independently_complete(self):
        config = json.loads((ROOT / "data/clinical_rules.json").read_text(encoding="utf-8"))
        self.assertEqual({rule["id"] for rule in config["rules"]},
                         {row["rule_id"] for row in self.rows if row["entry_kind"] == "declared_rule"})
        tree = ast.parse((ROOT / "logic/clinical_grouping.py").read_text(encoding="utf-8"))
        labels = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                      and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "GROUP_LABELS")
        self.assertEqual({"GROUP:" + key for key in labels},
                         {row["rule_id"] for row in self.rows if row["entry_kind"] == "clinical_group"})

    def test_no_invented_approval_and_every_source_reference_resolves(self):
        references = {row["rule_id"] for row in self.rows if row["entry_kind"] == "source_reference"}
        for row in self.rows:
            self.assertTrue(row["review_status"].startswith("REVIEW_REQUIRED"))
            self.assertIn("not established", row["source_mapping"])
            if row["source_guideline"].startswith("SOURCE:"):
                self.assertIn(row["source_guideline"], references)
        encoded = render_inventory()
        self.assertEqual(encoded, render_inventory())
        self.assertEqual(len(list(csv.DictReader(io.StringIO(encoded.decode("utf-8-sig"))))), len(self.rows))

    def test_source_change_cannot_leave_review_snapshot_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for config_path, code_paths in SPECS.values():
                for relative in (*code_paths, config_path):
                    if relative:
                        destination = root / relative
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_bytes((ROOT / relative).read_bytes())
            original = render_inventory(root)
            path = root / "logic/white_cells.py"
            path.write_bytes(path.read_bytes() + b"\n# independent inventory drift sentinel\n")
            self.assertNotEqual(original, render_inventory(root))


if __name__ == "__main__":
    unittest.main()
