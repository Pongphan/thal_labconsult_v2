"""ABO direction, required safety gates, and reaction escalation regressions."""

import json
import unittest

from logic.hematology_common import load_domain_rules
from logic.transfusion import analyze_transfusion


class TransfusionTests(unittest.TestCase):
    def row(self, **updates):
        return {**load_domain_rules("transfusion")["examples"][0]["data"], **updates}

    def test_all_abo_pairs_are_component_specific(self):
        expected = {
            "rbc": {"O": {"O"}, "A": {"A", "O"}, "B": {"B", "O"}, "AB": {"O", "A", "B", "AB"}},
            "plasma": {"O": {"O", "A", "B", "AB"}, "A": {"A", "AB"}, "B": {"B", "AB"}, "AB": {"AB"}},
        }
        for component, recipients in expected.items():
            for patient, permitted in recipients.items():
                for donor in ("O", "A", "B", "AB"):
                    with self.subTest(component=component, patient=patient, donor=donor):
                        result = analyze_transfusion(self.row(component=component, forward_abo=patient, reverse_abo=patient, donor_abo=donor))
                        self.assertEqual(result.calculated["abo_table_match"], donor in permitted)
                        self.assertEqual(result.calculated["compatibility_review_ready"], donor in permitted)
                        self.assertFalse(result.calculated["release_authorized"])

    def test_each_unknown_control_blocks_positive_review(self):
        for field in ("identity_verified", "specimen_valid", "independent_type_verified", "component", "abo_basis",
                      "forward_abo", "reverse_abo", "donor_abo", "patient_rhd", "donor_rhd", "antibody_screen",
                      "antibody_history", "crossmatch_result", "crossmatch_method", "crossmatch_process_validated", "reaction_suspected"):
            with self.subTest(field=field):
                result = analyze_transfusion(self.row(**{field: "unknown"}))
                self.assertFalse(result.calculated["compatibility_review_ready"])
                self.assertNotIn("TF_REVIEW_ONLY_NOT_RELEASE", result.rules_used)

    def test_verified_record_is_an_alternative_not_an_unverified_shortcut(self):
        row = self.row(abo_basis="verified_record", forward_abo="unknown", reverse_abo="unknown",
                       verified_patient_abo="A", record_verified="yes")
        self.assertTrue(analyze_transfusion(row).calculated["compatibility_review_ready"])
        self.assertFalse(analyze_transfusion({**row, "record_verified": "unknown"}).calculated["compatibility_review_ready"])
        conflict = analyze_transfusion({**row, "forward_abo": "B"})
        self.assertIn("TF_ABO_DISCREPANCY", conflict.rules_used)
        self.assertTrue(conflict.alerts)
        self.assertIsNone(conflict.calculated["patient_abo_for_review"])
        unverified = analyze_transfusion(self.row(verified_patient_abo="A", record_verified="unknown"))
        self.assertFalse(unverified.calculated["compatibility_review_ready"])

    def test_forward_reverse_discrepancy_cannot_be_overridden_by_record(self):
        result = analyze_transfusion(self.row(forward_abo="A", reverse_abo="B", abo_basis="verified_record",
                                             verified_patient_abo="A", record_verified="yes"))
        self.assertFalse(result.calculated["compatibility_review_ready"])
        self.assertIn("TF_ABO_DISCREPANCY", result.rules_used)

    def test_rhd_applies_to_rbc_but_not_plasma(self):
        self.assertFalse(analyze_transfusion(self.row(patient_rhd="negative", donor_rhd="positive")).calculated["compatibility_review_ready"])
        self.assertTrue(analyze_transfusion(self.row(patient_rhd="positive", donor_rhd="negative")).calculated["compatibility_review_ready"])
        plasma = analyze_transfusion(self.row(component="plasma", donor_abo="AB", patient_rhd="unknown", donor_rhd="unknown",
                                              antibody_screen="unknown", antibody_history="unknown", crossmatch_result="unknown",
                                              crossmatch_method="unknown", crossmatch_process_validated="unknown"))
        self.assertTrue(plasma.calculated["compatibility_review_ready"])
        self.assertNotIn("TF_RBC_CROSSMATCH_GATE", plasma.rules_used)

    def test_historical_positive_requires_antibody_path_even_if_screen_negative(self):
        for method in ("electronic", "immediate_spin"):
            result = analyze_transfusion(self.row(antibody_history="yes", crossmatch_method=method,
                                                 antibody_workup_reviewed="yes", antigen_negative_verified="yes"))
            self.assertFalse(result.calculated["compatibility_review_ready"])
            self.assertIn("TF_ANTIBODY_HISTORY_IAT_GATE", result.rules_used)
        for condition in ({"antibody_history": "yes"}, {"antibody_screen": "positive"}):
            row = self.row(**condition, crossmatch_method="iat", antibody_workup_reviewed="yes", antigen_negative_verified="yes")
            self.assertTrue(analyze_transfusion(row).calculated["compatibility_review_ready"])
            self.assertFalse(analyze_transfusion({**row, "antigen_negative_verified": "unknown"}).calculated["compatibility_review_ready"])

    def test_incompatible_crossmatch_escalates(self):
        result = analyze_transfusion(self.row(crossmatch_result="incompatible"))
        self.assertTrue(result.alerts)
        self.assertEqual(result.status, "urgent")
        self.assertFalse(result.calculated["compatibility_review_ready"])

    def test_reaction_checklist_does_not_wait_for_complete_lab_inputs(self):
        result = analyze_transfusion({"reaction_suspected": "yes"})
        self.assertEqual(result.status, "urgent")
        self.assertIn("TF_REACTION_ESCALATION", result.rules_used)
        self.assertGreaterEqual(len(result.recommendations), 5)
        self.assertFalse(result.calculated["release_authorized"])
        symptoms = analyze_transfusion({"reaction_suspected": "no", "reaction_symptoms": ["dyspnea"]})
        self.assertTrue(symptoms.alerts)
        invalid = analyze_transfusion({"reaction_suspected": "yes", "component": "platelets"})
        self.assertEqual(invalid.status, "invalid")
        self.assertTrue(invalid.alerts)

    def test_blank_and_unknown_data_do_not_authorize_anything(self):
        result = analyze_transfusion({"patient_name": "not stored"})
        self.assertEqual(result.status, "incomplete")
        self.assertFalse(result.calculated["compatibility_review_ready"])
        self.assertNotIn("patient_name", result.normalized)
        json.dumps(result.to_dict(), allow_nan=False)


if __name__ == "__main__":
    unittest.main()
