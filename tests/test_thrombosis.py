"""Guard context and unit requirements; the tool never independently excludes VTE."""
import json
import unittest

from logic.hematology_common import load_domain_rules
from logic.thrombosis import analyze_thrombosis


class ThrombosisTests(unittest.TestCase):
    def setUp(self):
        self.base = dict(load_domain_rules("thrombosis")["examples"][0]["data"])

    def test_valid_low_pretest_only_supports_review_not_exclusion(self):
        result = analyze_thrombosis(self.base)
        self.assertEqual(result.calculated["ddimer_to_cutoff_ratio"], 0.4)
        self.assertEqual(result.calculated["ddimer_interpretation"], "below_cutoff_requires_pathway_review")
        self.assertFalse(result.calculated["vte_excluded_by_tool"])
        self.assertEqual(result.thresholds_used["ddimer_basis"], "feu")

    def test_unknown_units_or_factors_cannot_be_negative(self):
        for field in ("ddimer_value", "ddimer_cutoff", "ddimer_unit", "cutoff_unit", "ddimer_basis", "cutoff_basis", "cutoff_validated"):
            with self.subTest(field=field):
                result = analyze_thrombosis({**self.base, field: None})
                self.assertEqual(result.calculated["ddimer_interpretation"], "not_interpretable")
                self.assertNotIn("ddimer_to_cutoff_ratio", result.calculated)

    def test_unit_and_feu_ddu_mismatch_are_not_automatically_converted(self):
        for changes in ({"cutoff_unit": "ug_l"}, {"cutoff_unit": "mg_l"}, {"cutoff_basis": "ddu"}):
            result = analyze_thrombosis({**self.base, **changes})
            self.assertIn("DDIMER_UNIT_BASIS_GATE", result.rules_used)
            self.assertEqual(result.calculated["ddimer_interpretation"], "not_interpretable")

    def test_high_intermediate_or_unknown_pretest_blocks_low_result_pathway(self):
        for probability in ("high", "intermediate", "unknown"):
            result = analyze_thrombosis({**self.base, "pretest_probability": probability})
            self.assertEqual(result.calculated["ddimer_interpretation"], "not_used_for_exclusion")
            self.assertFalse(result.calculated["vte_excluded_by_tool"])

    def test_low_result_requires_population_and_context(self):
        for changes in ({"age": 17}, {"age": None}, {"pregnant": "yes"}, {"pregnant": "unknown"}, {"suspected_site": "other"}, {"recurrent_vte": "yes"}, {"anticoagulant_use": "yes"}, {"anticoagulant_use": "unknown"}, {"high_sensitivity_assay": "unknown"}, {"symptoms_current": "unknown"}):
            with self.subTest(changes=changes):
                result = analyze_thrombosis({**self.base, **changes})
                self.assertEqual(result.calculated["ddimer_interpretation"], "not_used_for_exclusion")

    def test_above_cutoff_and_equal_cutoff_not_diagnostic(self):
        for value in (500, 1000):
            result = analyze_thrombosis({**self.base, "ddimer_value": value})
            self.assertEqual(result.calculated["ddimer_interpretation"], "at_or_above_cutoff")
            self.assertIn("DDIMER_ABOVE_NOT_DIAGNOSTIC", result.rules_used)

    def test_imaging_discordance_and_interference_paths(self):
        result = analyze_thrombosis({**self.base, "pretest_probability": "high", "imaging_status": "negative"})
        self.assertIn("VTE_DISCORDANT_IMAGING_REVIEW", result.rules_used)
        result = analyze_thrombosis({"thrombophilia_requested": "yes", "acute_event": "yes", "anticoagulant_use": "yes"})
        self.assertIn("THROMBOPHILIA_INTERFERENCE_GATE", result.rules_used)

    def test_urgent_clinical_evidence_survives_numeric_error(self):
        result = analyze_thrombosis({**self.base, "unstable": "yes", "imaging_status": "positive", "ddimer_cutoff": 0})
        self.assertEqual(result.status, "invalid")
        self.assertEqual(len(result.alerts), 2)
        self.assertFalse(result.calculated["vte_excluded_by_tool"])

    def test_blank_and_examples_have_strict_serializable_snapshots(self):
        self.assertEqual(analyze_thrombosis({}).status, "incomplete")
        for example in load_domain_rules("thrombosis")["examples"]:
            result = analyze_thrombosis(example["data"])
            self.assertFalse(result.validation_errors)
            json.dumps(result.to_dict(), ensure_ascii=False, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
