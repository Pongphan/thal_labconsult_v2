"""Evidence integration must not collapse unknown tests into a diagnosis."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from logic.hematology_common import load_domain_rules
from logic.marrow_malignancies import analyze_marrow_malignancies


class MarrowEvidenceTests(unittest.TestCase):
    def groups(self, result):
        return {item["group_id"] for item in result.calculated["hypothesis_groups"]}

    def test_blank_and_age_only_are_incomplete(self):
        for data in ({}, {"age": 35}):
            result = analyze_marrow_malignancies(data)
            self.assertEqual(result.status, "incomplete")
            self.assertFalse(self.groups(result))
            self.assertEqual(result.normalized["pml_rara"], "unknown")
            self.assertTrue(result.calculated["unassessed_tests"])

    def test_apl_is_urgent_without_blast_percentage_gate(self):
        for data in ({"pml_rara": "detected"}, {"apl_morphology": "yes", "pb_blasts_percent": 1}):
            result = analyze_marrow_malignancies(data)
            self.assertEqual(result.status, "urgent")
            self.assertIn("apl_urgent_path", self.groups(result))
            self.assertTrue(result.recommendations)

    def test_negative_pml_does_not_override_suspicious_apl_morphology(self):
        result = analyze_marrow_malignancies({"apl_morphology": "yes", "pml_rara": "not_detected"})
        self.assertEqual(result.status, "urgent")
        self.assertTrue(result.validation_warnings)
        self.assertIn("apl_urgent_path", self.groups(result))

    def test_genetic_evidence_below_twenty_percent_is_not_discarded(self):
        for evidence in ({"npm1": "detected"}, {"aml_rearrangement": "runx1_runx1t1"}):
            result = analyze_marrow_malignancies({"bm_blasts_percent": 5, **evidence})
            self.assertIn("myeloid_genetic_path", self.groups(result))
            self.assertNotIn("MARROW_HIGH_BLAST_REVIEW_ALERT", result.rules_used)
            self.assertNotIn("diagnosis", result.to_dict())

    def test_high_blasts_without_lineage_do_not_become_aml(self):
        result = analyze_marrow_malignancies({"bm_blasts_percent": 20})
        self.assertEqual(result.status, "urgent")
        self.assertEqual(self.groups(result), {"unassigned_blast_path"})
        self.assertTrue(result.calculated["hypothesis_groups"][0]["confirmation_paths"])
        self.assertFalse(analyze_marrow_malignancies({"bm_blasts_percent": 19.99}).alerts)
        self.assertTrue(analyze_marrow_malignancies({"pb_blasts_percent": 0.1}).alerts)

    def test_below_twenty_marrow_blasts_use_provided_local_upper_bound(self):
        result = analyze_marrow_malignancies({"bm_blasts_percent": 12, "bm_blasts_high": 4})
        self.assertIn("unassigned_blast_path", self.groups(result))
        self.assertIn("MARROW_BLASTS_ABOVE_LOCAL_BOUND", result.rules_used)
        self.assertFalse(result.alerts)
        self.assertEqual(result.thresholds_used["marrow_blast_upper_limit"], 4)
        equal = analyze_marrow_malignancies({"bm_blasts_percent": 4, "bm_blasts_high": 4})
        self.assertFalse(self.groups(equal))

    def test_bcr_evidence_does_not_overwrite_lymphoid_lineage(self):
        result = analyze_marrow_malignancies({"bcr_abl1": "detected", "flow_lineage": "b_lymphoblast"})
        self.assertIn("bcr_abl1_path", self.groups(result))
        self.assertIn("lymphoblastic_path", self.groups(result))
        self.assertEqual(result.normalized["prior_myeloid_neoplasm"], "unknown")

    def test_driver_evidence_generates_mpn_review_not_specific_disease_assignment(self):
        result = analyze_marrow_malignancies({"jak2": "detected"})
        self.assertEqual(self.groups(result), {"mpn_clonal_myeloid_path"})
        self.assertTrue(result.calculated["hypothesis_groups"][0]["confirmation_paths"])
        self.assertFalse(result.alerts)

    def test_monoclonal_protein_and_organ_findings_need_attribution(self):
        result = analyze_marrow_malignancies({"monoclonal_protein": "detected", "bm_plasma_cells_percent": 8,
                                             "organ_findings": ["renal_impairment", "hypercalcemia"]})
        self.assertEqual(self.groups(result), {"plasma_cell_path"})
        self.assertEqual(result.status, "review")
        self.assertNotIn("diagnosis", result.to_dict())
        measured_only = analyze_marrow_malignancies({"bm_plasma_cells_percent": 15})
        self.assertNotIn("plasma_cell_path", self.groups(measured_only))
        self.assertTrue(measured_only.calculated["documented_evidence"])

    def test_cytopenias_need_local_limits_or_explicit_clinician_observation(self):
        counts = {"hb_g_dl": 8, "anc_10e9_l": 0.8, "platelets_10e9_l": 70}
        result = analyze_marrow_malignancies(counts)
        self.assertEqual(result.calculated["cytopenias"]["local_count"], 0)
        self.assertFalse(self.groups(result))
        self.assertTrue(result.validation_warnings)
        local = analyze_marrow_malignancies({**counts, "hb_low": 12, "anc_low": 1.5, "platelets_low": 150})
        self.assertEqual(local.calculated["cytopenias"]["local_count"], 3)
        self.assertIn("multiple_cytopenia_path", self.groups(local))
        clinical = analyze_marrow_malignancies({"clinician_cytopenias": "multiple"})
        self.assertIn("multiple_cytopenia_path", self.groups(clinical))

    def test_local_cytopenia_boundary_and_conflict(self):
        equal = analyze_marrow_malignancies({"hb_g_dl": 12, "hb_low": 12})
        self.assertEqual(equal.calculated["cytopenias"]["local_count"], 0)
        result = analyze_marrow_malignancies({"hb_g_dl": 11.9, "hb_low": 12, "clinician_cytopenias": "none"})
        self.assertEqual(result.calculated["cytopenias"]["local_count"], 1)
        self.assertTrue(result.validation_warnings)

    def test_hypocellular_dysplastic_cytopenia_preserves_differential_paths(self):
        result = analyze_marrow_malignancies({"clinician_cytopenias": "multiple", "marrow_cellularity": "hypocellular", "marrow_dysplasia": "yes"})
        self.assertEqual(self.groups(result), {"hypocellular_cytopenia_path", "cytopenia_dysplasia_path"})
        self.assertTrue(result.recommendations)

    def test_mature_lymphoid_and_tissue_paths(self):
        for evidence in ({"flow_lineage": "mature_b", "flow_clonality": "detected"},
                         {"tissue_pathology": "lymphoid_suspicious"}):
            self.assertIn("mature_lymphoid_path", self.groups(analyze_marrow_malignancies(evidence)))
        contradictory = analyze_marrow_malignancies({"flow_lineage": "no_aberrant", "flow_clonality": "detected"})
        self.assertTrue(contradictory.validation_warnings)
        self.assertFalse(self.groups(contradictory))

    def test_negative_tests_are_recorded_without_excluding_all_disease(self):
        result = analyze_marrow_malignancies({"pml_rara": "not_detected", "bcr_abl1": "not_detected"})
        self.assertEqual(result.status, "review")
        self.assertFalse(self.groups(result))
        self.assertEqual(len(result.calculated["documented_evidence"]), 2)
        self.assertEqual(result.normalized["npm1"], "unknown")
        self.assertTrue(result.limitations)

    def test_invalid_measurements_preserve_independent_apl_alert(self):
        for value in (-1, "bad", float("inf"), True, 101):
            result = analyze_marrow_malignancies({"bm_blasts_percent": value, "pml_rara": "detected"})
            self.assertEqual(result.status, "invalid")
            self.assertTrue(result.alerts)
            self.assertIsNone(result.normalized["bm_blasts_percent"])

    def test_examples_and_exports_are_reproducible_and_whitelisted(self):
        for example in load_domain_rules("marrow_malignancies")["examples"]:
            result = analyze_marrow_malignancies(example["data"])
            self.assertNotEqual(result.status, "invalid")
            json.dumps(result.to_dict(), ensure_ascii=False, allow_nan=False)
        result = analyze_marrow_malignancies({"patient_name": "DO NOT RETAIN", "bm_blasts_percent": float("nan")})
        output = result.to_dict()
        self.assertNotIn("patient_name", output["normalized"])
        self.assertNotIn("DO NOT RETAIN", json.dumps(output))
        self.assertEqual(len(output["ruleset_hash"]), 64)
        self.assertTrue(result.sources)

    def test_invalid_rule_thresholds_fail_closed(self):
        for key, value in (("high_blast_review_percent", 101),
                           ("multiple_cytopenia_lineages", 1),
                           ("high_blast_review_percent", float("inf"))):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                config = load_domain_rules("marrow_malignancies")
                config["thresholds"][key] = value
                path = Path(directory) / "marrow_malignancies_rules.json"
                path.write_text(json.dumps(config), encoding="utf-8")
                with patch("logic.hematology_common.DATA_DIR", Path(directory)):
                    with self.assertRaises(ValueError):
                        analyze_marrow_malignancies({})


if __name__ == "__main__":
    unittest.main()
