"""Population-specific observations, specimen gates, and real count arithmetic."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from logic.hematology_common import load_domain_rules
from logic.morphology_quality import analyze_morphology_quality


class MorphologyQualityTests(unittest.TestCase):
    def row(self, **updates):
        return {**load_domain_rules("morphology_quality")["examples"][1]["data"], **updates}

    def test_complete_manual_count_and_nrbc_use_distinct_denominators(self):
        result = analyze_morphology_quality(self.row())
        calculated = result.calculated
        self.assertEqual(calculated["manual_differential_total"], 100)
        self.assertEqual(calculated["manual_differential_percent"]["neutrophils"], 55)
        self.assertEqual(sum(calculated["manual_differential_percent"].values()), 100)
        self.assertEqual(calculated["nrbc_per_100_wbc_counted"], 2)
        self.assertFalse(calculated["report_authorized"])

    def test_missing_count_is_not_zero_and_total_can_be_inferred_only_when_complete(self):
        result = analyze_morphology_quality(self.row(diff_basophils=None))
        self.assertEqual(result.calculated["manual_differential_percent"], {})
        self.assertIsNone(result.calculated["manual_differential_total"])
        complete = analyze_morphology_quality(self.row(diff_total_reported=None))
        self.assertEqual(complete.calculated["manual_differential_total"], 100)

    def test_zero_fractional_and_mismatched_counts_cannot_produce_percentages(self):
        fields = load_domain_rules("morphology_quality")["thresholds"]["differential_fields"]
        for changes in ({**{field: 0 for field in fields}, "diff_total_reported": None},
                        {"diff_neutrophils": 55.5}, {"diff_total_reported": 200}):
            with self.subTest(changes=changes):
                result = analyze_morphology_quality(self.row(**changes))
                self.assertEqual(result.status, "invalid")
                self.assertEqual(result.calculated["manual_differential_percent"], {})
                self.assertNotEqual(result.calculated["quality_gate"], "eligible_for_professional_review")

    def test_schistocyte_boundary_and_population_scope(self):
        for population in ("adult", "term_neonate"):
            at_limit = analyze_morphology_quality(self.row(population=population, schistocyte_percent=1))
            above = analyze_morphology_quality(self.row(population=population, schistocyte_percent=1.01))
            self.assertFalse(at_limit.alerts)
            self.assertTrue(above.alerts)
            self.assertEqual(above.thresholds_used["schistocyte_percent_upper"], 1)
        preterm = analyze_morphology_quality(self.row(population="preterm_neonate", schistocyte_percent=2))
        self.assertFalse(preterm.alerts)
        self.assertEqual(preterm.thresholds_used["schistocyte_percent_upper"], 5)
        for population in ("unknown", "other_child"):
            result = analyze_morphology_quality(self.row(population=population, schistocyte_percent=2))
            self.assertNotIn("schistocyte_percent_upper", result.thresholds_used)
            self.assertTrue(result.validation_warnings)

    def test_local_stability_boundary_and_unvalidated_limit(self):
        at_limit = analyze_morphology_quality(self.row(sample_age_hours=6))
        self.assertEqual(at_limit.calculated["quality_gate"], "eligible_for_professional_review")
        beyond = analyze_morphology_quality(self.row(sample_age_hours=6.01))
        self.assertEqual(beyond.calculated["quality_gate"], "hold_for_review")
        unknown = analyze_morphology_quality(self.row(timing_limit_validated="unknown", sample_age_hours=100))
        self.assertNotIn("local_max_age_hours", unknown.thresholds_used)
        self.assertEqual(unknown.calculated["quality_gate"], "incomplete")

    def test_each_specimen_problem_holds_affected_results(self):
        for key, value in (("specimen_clot", "yes"), ("specimen_hemolysis", "yes"),
                           ("edta_fill_status", "outside"), ("smear_quality", "unacceptable"), ("platelet_clumps", "yes")):
            with self.subTest(key=key):
                result = analyze_morphology_quality(self.row(**{key: value}))
                self.assertEqual(result.calculated["quality_gate"], "hold_for_review")
                self.assertIn(key, result.calculated["quality_holds"])
                self.assertFalse(result.calculated["report_authorized"])

    def test_blast_alert_survives_quality_failure_and_input_errors(self):
        result = analyze_morphology_quality(self.row(blast_observation="suspected", specimen_clot="yes"))
        self.assertTrue(result.alerts)
        self.assertEqual(result.status, "urgent")
        invalid = analyze_morphology_quality(self.row(blast_observation="not_seen", diff_blasts=1))
        self.assertEqual(invalid.status, "invalid")
        self.assertTrue(invalid.alerts)

    def test_observations_require_consistent_manual_review(self):
        conflict = analyze_morphology_quality(self.row(rbc_morphology=["none", "spherocytes"]))
        self.assertEqual(conflict.status, "invalid")
        not_reviewed = analyze_morphology_quality(self.row(smear_reviewed="no"))
        self.assertEqual(not_reviewed.status, "invalid")

    def test_blank_invalid_ranges_and_privacy(self):
        blank = analyze_morphology_quality({"patient_name": "not stored"})
        self.assertEqual(blank.status, "incomplete")
        self.assertEqual(blank.calculated["quality_gate"], "incomplete")
        self.assertNotIn("patient_name", blank.normalized)
        for value in (-1, 101, float("inf"), "bad"):
            self.assertEqual(analyze_morphology_quality({"schistocyte_percent": value}).status, "invalid")
        json.dumps(blank.to_dict(), allow_nan=False)

    def test_malformed_differential_schema_cannot_silently_change_denominators(self):
        original = load_domain_rules("morphology_quality")["thresholds"]["differential_fields"]
        for fields in (original[:-1], [*original[:-1], original[0]], [*original, "nrbc_count"], "diff_neutrophils"):
            with self.subTest(fields=fields), tempfile.TemporaryDirectory() as directory:
                rules = load_domain_rules("morphology_quality")
                rules["thresholds"]["differential_fields"] = fields
                path = Path(directory) / "morphology_quality_rules.json"
                path.write_text(json.dumps(rules), encoding="utf-8")
                with patch("logic.hematology_common.DATA_DIR", Path(directory)):
                    with self.assertRaises(ValueError):
                        analyze_morphology_quality({"diff_neutrophils": 55, "nrbc_count": 2})

    def test_malformed_population_thresholds_fail_before_any_assessment(self):
        for value in (-1, 0, 101, True, "1", float("nan")):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                rules = load_domain_rules("morphology_quality")
                rules["thresholds"]["schistocyte_percent_upper"]["adult"] = value
                path = Path(directory) / "morphology_quality_rules.json"
                path.write_text(json.dumps(rules), encoding="utf-8")
                with patch("logic.hematology_common.DATA_DIR", Path(directory)):
                    with self.assertRaises(ValueError):
                        analyze_morphology_quality({"population": "adult", "schistocyte_percent": 2})


if __name__ == "__main__":
    unittest.main()
