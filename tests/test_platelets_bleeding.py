"""Verify specimen gates and independent urgent observations for hemostasis."""
import json
import unittest

from logic.hematology_common import load_domain_rules
from logic.platelets_bleeding import analyze_platelets_bleeding


class PlateletsBleedingTests(unittest.TestCase):
    def setUp(self):
        self.base = {
            "bleeding_severity": "minor", "hemodynamic_instability": "no",
            "cbc_sample_quality": "acceptable", "platelet_clumps": "no",
            "platelets_10e9_l": 200, "platelet_ref_low": 150, "platelet_ref_high": 450,
            "coag_sample_quality": "acceptable", "pt_seconds": 12, "pt_uln_seconds": 14,
            "aptt_seconds": 56, "aptt_uln_seconds": 35,
            "anticoagulant": "none", "recent_factor_or_transfusion": "no",
        }

    def test_pt_aptt_pattern_requires_both_results_and_local_limits(self):
        result = analyze_platelets_bleeding(self.base)
        self.assertEqual(result.calculated["coagulation_pattern"], "isolated_aptt")
        self.assertEqual(result.calculated["aptt_to_uln_ratio"], 1.6)
        for field in ("pt_seconds", "pt_uln_seconds", "aptt_uln_seconds"):
            with self.subTest(field=field):
                result = analyze_platelets_bleeding({**self.base, field: None})
                self.assertNotIn("coagulation_pattern", result.calculated)

    def test_clumping_and_unknown_quality_do_not_label_true_low_count(self):
        for changes in ({"platelet_clumps": "yes"}, {"platelet_clumps": "unknown"}, {"cbc_sample_quality": "clotted"}):
            result = analyze_platelets_bleeding({**self.base, "platelets_10e9_l": 15, **changes})
            self.assertIn("PLATELET_ARTIFACT_GATE", result.rules_used)
            self.assertNotIn("PLATELET_LOCAL_REFERENCE_LOW", result.rules_used)

    def test_coag_quality_gate_blocks_ratios_and_diagnosis_patterns(self):
        for quality in ("unknown", "underfilled", "clotted", "contamination"):
            result = analyze_platelets_bleeding({**self.base, "coag_sample_quality": quality})
            self.assertNotIn("aptt_to_uln_ratio", result.calculated)
            self.assertNotIn("coagulation_pattern", result.calculated)

    def test_interfering_or_unknown_treatment_does_not_direct_mixing_immediately(self):
        config = load_domain_rules("platelets_bleeding")
        for drug in ("unknown", "warfarin", "heparin", "doac"):
            result = analyze_platelets_bleeding({**self.base, "anticoagulant": drug})
            self.assertIn("COAGULATION_INTERFERENCE_GATE", result.rules_used)
            self.assertNotIn(config["messages"]["mixing"], result.recommendations)

    def test_major_bleeding_and_local_critical_alert_survive_invalid_pt(self):
        result = analyze_platelets_bleeding({**self.base, "bleeding_severity": "major", "platelets_10e9_l": 15, "platelet_critical_low": 20, "pt_seconds": -1})
        self.assertEqual(result.status, "invalid")
        self.assertEqual(len(result.alerts), 2)
        self.assertFalse(result.calculated)

    def test_local_ranges_and_boundaries_are_honored(self):
        result = analyze_platelets_bleeding({**self.base, "platelets_10e9_l": 150, "aptt_seconds": 35, "pt_seconds": 14})
        self.assertIn("PLATELET_LOCAL_REFERENCE_WITHIN", result.rules_used)
        self.assertEqual(result.calculated["coagulation_pattern"], "neither_prolonged")
        bad = analyze_platelets_bleeding({**self.base, "platelet_ref_high": 150})
        self.assertTrue(bad.validation_errors)

    def test_combined_abnormalities_do_not_produce_dic_score(self):
        result = analyze_platelets_bleeding({**self.base, "platelets_10e9_l": 70, "pt_seconds": 20, "fibrinogen_g_l": 0.8, "fibrinogen_ref_low": 2, "ddimer_lab_call": "increased"})
        self.assertIn("MULTIPLE_HEMOSTASIS_ABNORMALITIES_NO_DIC_DIAGNOSIS", result.rules_used)
        self.assertFalse(any("score" in key for key in result.calculated))

    def test_blank_inputs_and_export_snapshot(self):
        blank = analyze_platelets_bleeding({})
        self.assertEqual(blank.status, "incomplete")
        self.assertFalse(blank.alerts)
        for example in load_domain_rules("platelets_bleeding")["examples"]:
            result = analyze_platelets_bleeding(example["data"])
            self.assertFalse(result.validation_errors)
            json.dumps(result.to_dict(), ensure_ascii=False, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
