"""Cross-domain input, schema, batch, provenance and reporting contracts."""
from copy import deepcopy
import csv
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from logic.hematology import analyze_domain
from logic.hematology_common import DOMAIN_IDS, load_domain_rules, start_review
from ui.data_io import ScreeningCSVError
from ui.domain_io import domain_template, read_domain_csv
from utils.domain_reporting import batch_report_csv, report_csv, report_json, report_metadata


class HematologyContractTests(unittest.TestCase):
    def test_all_domains_have_real_rules_examples_and_incomplete_blank_results(self):
        for module_id in DOMAIN_IDS:
            with self.subTest(module=module_id):
                rules = load_domain_rules(module_id)
                blank = analyze_domain(module_id, {})
                self.assertEqual(blank.status, "incomplete")
                self.assertFalse(blank.alerts)
                self.assertTrue(rules["examples"])
                for example in rules["examples"]:
                    result = analyze_domain(module_id, example["data"])
                    self.assertFalse(result.validation_errors, example["name"])
                    self.assertIn(result.status, {"review", "urgent", "incomplete"})
                    self.assertTrue(result.findings or result.recommendations)
                    json.dumps(result.to_dict(), allow_nan=False)

    def test_all_domains_drop_unknown_fields_and_reject_invalid_selections(self):
        for module_id in DOMAIN_IDS:
            rules = load_domain_rules(module_id)
            with self.subTest(module=module_id):
                result = analyze_domain(module_id, {"patient_name": "PRIVATE", "HN": "PRIVATE"})
                self.assertNotIn("PRIVATE", json.dumps(result.to_dict()))
                field = next(item for item in rules["fields"] if item["type"] == "select")
                invalid = analyze_domain(module_id, {field["key"]: "not-an-option"})
                self.assertEqual(invalid.status, "invalid")
                self.assertTrue(invalid.validation_errors)

    def test_numeric_values_stay_missing_or_valid_and_do_not_coerce_boolean(self):
        for module_id in DOMAIN_IDS:
            rules = load_domain_rules(module_id)
            fields = [item for item in rules["fields"] if item["type"] == "number"]
            if not fields:
                continue
            key = fields[0]["key"]
            for raw in [True, "wrong-unit", float("inf"), -1e10]:
                with self.subTest(module=module_id, value=raw):
                    result, _ = start_review(module_id, {key: raw})
                    self.assertTrue(result.validation_errors)
                    self.assertIsNone(result.normalized[key])
            result, _ = start_review(module_id, {key: float("nan")})
            self.assertIsNone(result.normalized[key])
            self.assertFalse(result.validation_errors)

    def test_example_csv_roundtrips_to_equivalent_assessment(self):
        for module_id in DOMAIN_IDS:
            with self.subTest(module=module_id):
                rules = load_domain_rules(module_id)
                rows, _ = read_domain_csv(domain_template(rules, example=True), rules)
                actual = analyze_domain(module_id, rows[0])
                expected = analyze_domain(module_id, rules["examples"][0]["data"])
                self.assertEqual(actual.to_dict(), expected.to_dict())

    def test_csv_preserves_blank_rows_and_rejects_malformed_or_large_inputs(self):
        rules = load_domain_rules("white_cells")
        rows, _ = read_domain_csv(b"wbc_10e9_l,patient_name\n4,PRIVATE\n,PRIVATE\n", rules)
        self.assertEqual(len(rows), 2)
        self.assertNotIn("PRIVATE", json.dumps(rows))
        self.assertEqual(analyze_domain("white_cells", rows[1]).status, "incomplete")
        for payload in [b"wbc_10e9_l,wbc_10e9_l\n1,2", b"wbc_10e9_l\n1,2", b"wbc_10e9_l", b"x" * (2 * 1024 * 1024 + 1), b"wbc_10e9_l\n" + b"4\n" * 201]:
            with self.assertRaises(ScreeningCSVError):
                read_domain_csv(payload, rules)

    def test_reports_capture_inputs_thresholds_sources_and_thai_csv(self):
        for module_id in DOMAIN_IDS:
            with self.subTest(module=module_id):
                rules = load_domain_rules(module_id)
                result = analyze_domain(module_id, rules["examples"][0]["data"])
                metadata = report_metadata(module_id, "ข้อมูลสมมติ")
                payload = json.loads(report_json(result, metadata))
                self.assertEqual(payload["result"], result.to_dict())
                self.assertEqual(payload["report"], metadata)
                self.assertEqual(len(payload["result"]["ruleset_hash"]), 64)
                csv = report_csv(result, metadata)
                self.assertTrue(csv.startswith(b"\xef\xbb\xbf"))
                self.assertIn("เกณฑ์และขอบเขตที่ใช้จริง", csv.decode("utf-8-sig"))
                self.assertIn(result.disclaimer, csv.decode("utf-8-sig"))

    def test_explicit_none_and_valid_urgent_symptoms_survive_normalization(self):
        result = analyze_domain("platelets_bleeding", {"anticoagulant": "none", "bleeding_severity": "none"})
        self.assertEqual(result.normalized["anticoagulant"], "none")
        self.assertEqual(result.normalized["bleeding_severity"], "none")
        result = analyze_domain("transfusion", {"reaction_symptoms": ["dyspnea", "PRIVATE-invalid"]})
        self.assertEqual(result.normalized["reaction_symptoms"], ["dyspnea"])
        self.assertEqual(result.status, "invalid")
        self.assertTrue(result.alerts)
        self.assertNotIn("PRIVATE-invalid", json.dumps(result.to_dict()))

    def test_units_are_preserved_in_form_and_report_labels(self):
        result = analyze_domain("platelets_bleeding", {})
        rules = load_domain_rules("platelets_bleeding")
        for item in rules["fields"]:
            if item.get("unit"):
                self.assertIn(item["unit"], result.field_labels[item["key"]])

    def test_batch_csv_preserves_calculations_and_full_provenance(self):
        module_id = "morphology_quality"
        rules = load_domain_rules(module_id)
        result = analyze_domain(module_id, rules["examples"][0]["data"])
        metadata = report_metadata(module_id, "ข้อมูลสมมติ")
        rows = list(csv.DictReader(StringIO(batch_report_csv([result], [metadata]).decode("utf-8-sig"))))
        self.assertEqual(len(rows), 1)
        self.assertEqual(json.loads(rows[0]["ค่าคำนวณและสรุปหลักฐาน"]), result.calculated)
        self.assertEqual(json.loads(rows[0]["ข้อมูลที่ใช้ (JSON)"]), result.normalized)
        self.assertEqual(rows[0]["เวลาประเมิน (UTC+07:00)"], metadata["evaluated_at"])
        self.assertEqual(rows[0]["ขอบเขตการใช้ผล"], result.scope)

    def test_schema_rejects_duplicates_unsafe_templates_and_bad_defaults(self):
        module_id = "white_cells"
        original = load_domain_rules(module_id)
        invalid = []
        duplicate = deepcopy(original)
        duplicate["fields"].append(duplicate["fields"][0])
        invalid.append(duplicate)
        bounds = deepcopy(original)
        number = next(item for item in bounds["fields"] if item["type"] == "number")
        number["min"], number["max"] = 5, 1
        invalid.append(bounds)
        template = deepcopy(original)
        template["messages"]["unsafe"] = "{value.__class__}"
        invalid.append(template)
        unknown = deepcopy(original)
        select = next(item for item in unknown["fields"] if item["type"] == "select")
        select["options"].reverse()
        invalid.append(unknown)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rules.json"
            for value in invalid:
                path.write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_domain_rules(module_id, path)
            path.write_text('{"metadata":{},"metadata":{}}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_domain_rules(module_id, path)

    def test_each_domain_requires_its_complete_threshold_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rules.json"
            for module_id in DOMAIN_IDS:
                rules = load_domain_rules(module_id)
                for thresholds in ({}, {**rules["thresholds"], "unrecognized_threshold": 1}):
                    with self.subTest(module=module_id, thresholds=thresholds):
                        modified = deepcopy(rules)
                        modified["thresholds"] = thresholds
                        path.write_text(json.dumps(modified), encoding="utf-8")
                        with self.assertRaises(ValueError):
                            load_domain_rules(module_id, path)

    def test_domain_threshold_types_and_semantics_fail_closed(self):
        invalid = [
            ("white_cells", "adult_min_age", True),
            ("white_cells", "absolute_conflict_relative", 2),
            ("white_cells", "differential_total", 99),
            ("marrow_malignancies", "multiple_cytopenia_lineages", 2.5),
            ("marrow_malignancies", "high_blast_review_percent", 101),
            ("platelets_bleeding", "prolonged_ratio", True),
            ("thrombosis", "adult_min_years", 10),
            ("transfusion", "abo_compatibility", {"rbc": {"O": ["O"]}}),
            ("morphology_quality", "schistocyte_percent_upper", {"adult": -1, "term_neonate": 1, "preterm_neonate": 5}),
            ("morphology_quality", "differential_fields", ["diff_neutrophils"]),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rules.json"
            for module_id, key, value in invalid:
                with self.subTest(module=module_id, key=key):
                    rules = load_domain_rules(module_id)
                    rules["thresholds"][key] = value
                    path.write_text(json.dumps(rules), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_domain_rules(module_id, path)

    def test_abo_tables_require_all_components_and_unique_known_groups(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rules.json"
            for choices in ([], ["O", "O"], ["invalid"], "O", [True]):
                with self.subTest(choices=choices):
                    rules = load_domain_rules("transfusion")
                    rules["thresholds"]["abo_compatibility"]["rbc"]["O"] = choices
                    path.write_text(json.dumps(rules), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_domain_rules("transfusion", path)


if __name__ == "__main__":
    unittest.main()
