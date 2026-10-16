"""Executable software contracts; synthetic cases are not clinical validation.

Run with ``python -m pytest tests/test_validation_contracts.py`` or unittest.
VC-01 demographic consistency; VC-02 invalid results; VC-03 existing boundaries;
VC-04 missingness/types/ranges/units; VC-05 preservation of independent alerts.
Expected boundary tables are explicit so tests cannot derive their own answers
from the evaluated engine. No clinical cutoff is introduced or changed here.
"""
from __future__ import annotations

import copy
import math
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from logic.cbc import analyze_cbc, load_cbc_rules
from logic.engine import (
    analyze_dataframe, analyze_screening, anemia_threshold, hct_threshold,
    mch_threshold, mcv_threshold,
)
from logic.rules import load_rules
from logic.validation import validate_screening


BASE = {"age": 30, "sex": "Female", "pregnant": False,
        "hb_g_dl": 14, "mcv_fl": 88, "mch_pg": 29}


def screening(**changes):
    return analyze_screening({**BASE, **changes})


class DemographicContractTests(unittest.TestCase):
    def test_vc01_conflicting_threshold_context_is_invalid_in_both_modules(self):
        for sex in ("Male", "m", "ชาย"):
            for pregnancy in (True, "yes", "Positive", 1, np.bool_(True)):
                # CBC does not support the assay word Positive as a history alias;
                # either its enum error or the demographic conflict must block it.
                row = {**BASE, "sex": sex, "pregnant": pregnancy, "hb_g_dl": 11.5}
                with self.subTest(sex=sex, pregnant=pregnancy):
                    result = analyze_screening(row)
                    cbc = analyze_cbc(row)
                    self.assertTrue(result.validation_errors)
                    self.assertTrue(cbc.validation_errors)
                    self.assertIsNone(result.anemia)
                    self.assertIsNone(result.thresholds_used["anemia_hb"])
                    self.assertIsNone(result.thresholds_used["anemia_hct"])
                    self.assertEqual(cbc.anemia_code, "not_assessed")
                    self.assertEqual(cbc.support_code, "invalid")
                    self.assertFalse(result.rule_ids)

    def test_vc01_missing_sex_never_acquires_a_pregnancy_cutoff(self):
        for sex in (None, "unknown", "Not specified", "ไม่ระบุ"):
            for pregnancy in (True, False, None):
                with self.subTest(sex=sex, pregnant=pregnancy):
                    result = screening(sex=sex, pregnant=pregnancy)
                    cbc = analyze_cbc({**BASE, "sex": sex, "pregnant": pregnancy})
                    self.assertFalse(result.validation_errors)
                    self.assertFalse(cbc.validation_errors)
                    self.assertIsNone(result.anemia)
                    self.assertIsNone(result.thresholds_used["anemia_hb"])
                    self.assertEqual(cbc.anemia_code, "not_assessed")

    def test_vc01_unsupported_sex_is_distinct_from_missing(self):
        for sex in (True, 1, "unrecognized", "Femlae"):
            with self.subTest(sex=sex):
                result = screening(sex=sex)
                cbc = analyze_cbc({**BASE, "sex": sex})
                self.assertTrue(result.validation_errors)
                self.assertTrue(cbc.validation_errors)
                self.assertIsNone(result.anemia)
                self.assertEqual(cbc.pattern_code, "invalid")

    def test_vc01_public_helpers_reject_conflicts_and_invalid_ages(self):
        for helper in (anemia_threshold, hct_threshold):
            for age in (None, True, np.bool_(True), -0.01, 120.01, math.inf, math.nan):
                with self.subTest(helper=helper.__name__, age=age):
                    self.assertTrue(math.isnan(helper(age, "Female", False)))
            for sex in ("Male", None, "unsupported"):
                self.assertTrue(math.isnan(helper(30, sex, True)))

    def test_vc01_unknown_pregnancy_withholds_only_dependent_interpretation(self):
        for pregnancy in (None, "unknown", "Not performed", "Indeterminate"):
            with self.subTest(pregnancy=pregnancy):
                adult = screening(pregnant=pregnancy)
                child = screening(age=4, pregnant=pregnancy)
                male = screening(sex="Male", pregnant=pregnancy)
                self.assertIsNone(adult.anemia)
                self.assertEqual(child.thresholds_used["anemia_hb"], 11)
                self.assertEqual(male.thresholds_used["anemia_hb"], 13)

    def test_vc01_single_and_batch_keep_identical_demographic_decisions(self):
        rows = [{**BASE, "sex": "Male", "pregnant": True},
                {**BASE, "pregnant": None}, {**BASE, "pregnant": False}]
        batch = analyze_dataframe(pd.DataFrame(rows))
        for position, row in enumerate(rows):
            single = analyze_screening(row)
            actual = batch.iloc[position]
            self.assertEqual(actual["top_pattern"], single.top_pattern)
            if single.anemia is None:
                self.assertTrue(pd.isna(actual["anemia"]))
            else:
                self.assertEqual(actual["anemia"], single.anemia)


class InvalidInputContractTests(unittest.TestCase):
    def test_vc02_invalid_optional_input_withholds_all_classification_flags(self):
        for field in ("age", "rbc_10e12_l", "hct_percent", "ferritin_ng_ml", "hba2_percent"):
            with self.subTest(field=field):
                result = screening(**{field: "invalid"})
                self.assertTrue(result.validation_errors)
                self.assertEqual((result.anemia, result.microcytosis, result.hypochromia), (None, None, None))
                self.assertFalse(result.rule_ids)
                self.assertTrue(math.isnan(result.consult_score))
                self.assertEqual(result.consult_risk, "Invalid / incomplete")

    def test_vc04_missing_required_values_cannot_produce_a_screening_classification(self):
        for field in ("hb_g_dl", "mcv_fl", "mch_pg"):
            for value in (None, "", "null", np.nan, pd.NA):
                with self.subTest(field=field, value=value):
                    result = screening(**{field: value})
                    self.assertTrue(result.validation_errors)
                    self.assertFalse(result.rule_ids)
                    self.assertIsNone(result.anemia)
                    self.assertIsNone(result.microcytosis)

    def test_vc04_numeric_types_and_nonfinite_values_fail_closed(self):
        for value in (True, False, np.bool_(True), np.bool_(False), math.inf, -math.inf, "1e999", "bad"):
            for field in ("hb_g_dl", "mcv_fl", "age"):
                with self.subTest(value=value, field=field):
                    result = screening(**{field: value})
                    cbc = analyze_cbc({**BASE, field: value})
                    self.assertTrue(result.validation_errors)
                    self.assertTrue(cbc.validation_errors)
                    self.assertIsNone(result.anemia)
                    self.assertEqual(cbc.anemia_code, "not_assessed")
                    self.assertEqual(cbc.pattern_code, "invalid")

    def test_vc04_cbc_missing_hb_and_mcv_are_incomplete(self):
        for value in (None, "", "null", math.nan, pd.NA):
            result = analyze_cbc({**BASE, "hb_g_dl": value, "mcv_fl": value})
            self.assertIn(result.support_code, {"incomplete", "invalid"})
            self.assertEqual(result.anemia_code, "not_assessed")
            self.assertIn(result.pattern_code, {"unavailable", "invalid"})

    def test_vc04_all_numeric_input_bounds_are_inclusive(self):
        # Bounds are technical filters, never a statement of clinical normality.
        for field, (low, high, _) in load_rules()["validation"]["ranges"].items():
            for value in (low, high):
                with self.subTest(module="screening", field=field, value=value):
                    self.assertFalse(validate_screening({**BASE, field: value}).errors)
            for value in (low - 0.01, high + 0.01):
                self.assertTrue(validate_screening({**BASE, field: value}).errors)
        for field, (low, high, _) in load_cbc_rules()["validation"]["ranges"].items():
            for value in (low, high):
                with self.subTest(module="CBC", field=field, value=value):
                    self.assertFalse(analyze_cbc({**BASE, field: value}).validation_errors)
            for value in (low - 0.01, high + 0.01):
                self.assertTrue(analyze_cbc({**BASE, field: value}).validation_errors)

    def test_vc04_wrong_unit_values_and_unit_suffixes_are_not_converted(self):
        # g/L in a g/dL field; litres in an fL field; unsplit numeric/unit strings.
        # A plausible bare scalar in the wrong unit cannot be detected by range.
        for field, value in (("hb_g_dl", 120), ("mcv_fl", 80e-15),
                             ("hb_g_dl", "12 g/dL"), ("mcv_fl", "80 fL"),
                             ("rbc_10e12_l", "5 x10^6/uL")):
            with self.subTest(field=field, value=value):
                result = screening(**{field: value})
                cbc = analyze_cbc({**BASE, field: value})
                self.assertTrue(result.validation_errors)
                self.assertTrue(cbc.validation_errors)
                self.assertFalse(result.rule_ids)
                self.assertEqual(cbc.pattern_code, "invalid")

    def test_vc04_numpy_boolean_reference_bound_is_rejected(self):
        result = analyze_cbc({**BASE, "wbc_10e9_l": 5}, {"wbc_10e9_l": {"low": np.bool_(True)}})
        self.assertTrue(result.validation_errors)
        self.assertEqual(result.support_code, "invalid")

    def test_vc05_invalid_context_never_hides_independent_low_hb_alert(self):
        for changes in ({"mcv_fl": "invalid"}, {"sex": "Male", "pregnant": True}, {"sex": "unsupported"}):
            with self.subTest(changes=changes):
                result = screening(hb_g_dl=6, **changes)
                cbc = analyze_cbc({**BASE, "hb_g_dl": 6, **changes})
                self.assertTrue(result.validation_errors)
                self.assertTrue(result.severe_anemia_flag)
                self.assertEqual(result.consult_risk, "Critical review")
                self.assertIsNone(result.anemia)
                self.assertTrue(cbc.low_hb_alert)
                self.assertTrue(cbc.findings)


class ExistingThresholdContractTests(unittest.TestCase):
    def test_vc03_hb_hct_thresholds_below_at_above(self):
        for sex, pregnant, hb_limit, hct_limit in (("Male", False, 13, 40),
                                                  ("Female", False, 12, 36), ("Female", True, 11, 33)):
            for offset, expected in ((-0.01, True), (0, False), (0.01, False)):
                with self.subTest(sex=sex, pregnant=pregnant, offset=offset):
                    self.assertEqual(screening(sex=sex, pregnant=pregnant, hb_g_dl=hb_limit + offset).anemia, expected)
                    self.assertEqual(screening(sex=sex, pregnant=pregnant, hct_percent=hct_limit + offset).anemia, expected)
                    if not pregnant:
                        cbc = analyze_cbc({**BASE, "sex": sex, "hb_g_dl": hb_limit + offset})
                        self.assertEqual(cbc.anemia_code, "below_cutoff" if expected else "not_below_cutoff")

    def test_vc03_screening_mcv_mch_and_independent_alert_boundaries(self):
        for field, cutoff, attr in (("mcv_fl", 80, "microcytosis"), ("mch_pg", 26, "hypochromia"),
                                    ("hb_g_dl", 7, "severe_anemia_flag")):
            for offset, expected in ((-0.01, True), (0, False), (0.01, False)):
                with self.subTest(field=field, offset=offset):
                    self.assertEqual(getattr(screening(**{field: cutoff + offset}), attr), expected)
        for value, expected in ((7.99, True), (8, False), (8.01, False)):
            self.assertEqual(analyze_cbc({**BASE, "hb_g_dl": value}).low_hb_alert, expected)

    def test_vc03_cbc_mcv_and_age_scope_boundaries(self):
        for value, expected in ((79.99, "micro"), (80, "normo"), (80.01, "normo"),
                                 (99.99, "normo"), (100, "normo"), (100.01, "macro")):
            self.assertEqual(analyze_cbc({**BASE, "mcv_fl": value}).pattern_code, expected)
        for age, expected in ((17.99, False), (18, True), (18.01, True),
                               (64.99, True), (65, True), (65.01, False)):
            self.assertEqual(analyze_cbc({**BASE, "age": age}).scope_supported, expected)

    def test_vc03_hba2_and_hbf_rule_boundaries(self):
        for value, beta, high in ((3.49, False, False), (3.5, True, False), (3.51, True, False),
                                   (9.99, True, False), (10, True, False), (10.01, False, True)):
            result = screening(hba2_percent=value)
            self.assertEqual("beta_trait" in result.rule_ids, beta)
            self.assertEqual("high_fraction_review" in result.rule_ids, high)
        for value, elevated, review in ((0.99, False, False), (1, False, False), (1.01, True, False),
                                         (4.99, True, False), (5, True, False), (5.01, True, True)):
            result = screening(hbf_percent=value)
            self.assertEqual(result.beta_trait_score, 6 if elevated else 0)
            self.assertEqual("high_fraction_review" in result.rule_ids, review)
        for age, pediatric in ((0.99, True), (1, False), (1.01, False)):
            result = screening(age=age, hba2_percent=5)
            self.assertEqual("pediatric_review" in result.rule_ids, pediatric)
            self.assertEqual("beta_trait" in result.rule_ids, not pediatric)

    def test_vc03_ferritin_hbe_rbc_mentzer_rdw_boundaries(self):
        for value, score, iron in ((14.99, 44, True), (15, 20, False), (15.01, 20, False),
                                    (29.99, 20, False), (30, 0, False), (30.01, 0, False)):
            result = screening(ferritin_ng_ml=value)
            self.assertEqual(result.iron_deficiency_score, score)
            self.assertEqual("iron_deficiency" in result.rule_ids, iron)
        for value, score in ((9.99, 0), (10, 46), (10.01, 46)):
            self.assertEqual(screening(hbe_percent=value).hbe_score, score)
        for value, score in ((4.99, 0), (5, 10), (5.01, 10)):
            self.assertEqual(screening(rbc_10e12_l=value).beta_trait_score, score)
        for mcv, mentzer, score in ((77.94, 12.99, 34), (78, 13, 24), (78.06, 13.01, 24)):
            result = screening(mcv_fl=mcv, rbc_10e12_l=6)
            self.assertEqual(result.derived["mentzer_index"], mentzer)
            self.assertEqual(result.beta_trait_score, score)
        for value, score in ((14.49, 0), (14.5, 0), (14.51, 10)):
            self.assertEqual(screening(rdw_percent=value).iron_deficiency_score, score)

    def test_vc03_fraction_total_and_score_band_boundaries(self):
        for total, invalid in ((101.99, False), (102, False), (102.01, True)):
            self.assertEqual(bool(screening(hba_percent=99, hba2_percent=total - 99).validation_errors), invalid)
        for score, expected in ((44, "Low / inconclusive"), (45, "Moderate"), (46, "Moderate"),
                                 (74, "Moderate"), (75, "High"), (76, "High")):
            config = copy.deepcopy(load_rules())
            config["scores"] = {name: {"family": score if name == "beta_trait_score" else 0}
                                for name in config["scores"]}
            with patch("logic.engine.load_rules", return_value=config):
                self.assertEqual(screening(family_history=True).consult_risk, expected)

    def test_vc03_all_existing_age_profile_transitions(self):
        # (upper age boundary, cutoff immediately below, cutoff at/above).
        cases = {
            mcv_threshold: [(14 / 365, 98, 88), (1 / 12, 88, 91), (1 / 6, 91, 84),
                            (1 / 3, 84, 76), (0.5, 76, 68), (0.75, 68, 70),
                            (1, 70, 71), (2, 71, 75), (6, 75, 77), (12, 77, 80)],
            mch_threshold: [(14 / 365, 31, 30), (1 / 12, 30, 29), (1 / 6, 29, 27),
                            (1 / 3, 27, 25), (0.5, 25, 24), (0.75, 24, 25),
                            (1, 25, 24), (6, 24, 25), (12, 25, 26)],
            anemia_threshold: [(5, 11, 11.5), (12, 11.5, 12), (15, 12, 13)],
            hct_threshold: [(1, 42, 33), (10, 33, 35), (13, 35, 36), (15, 36, 40)],
        }
        for helper, boundaries in cases.items():
            for boundary, before, after in boundaries:
                for delta, expected in ((-1e-8, before), (0, after), (1e-8, after)):
                    with self.subTest(helper=helper.__name__, age=boundary + delta):
                        args = (boundary + delta, "Male", False) if helper in (anemia_threshold, hct_threshold) else (boundary + delta,)
                        self.assertEqual(helper(*args), expected)

    def test_vc03_local_reference_interval_boundaries(self):
        for field, low, high in (("wbc_10e9_l", 4, 10), ("platelets_10e9_l", 150, 400),
                                  ("rdw_percent", 11, 15), ("ferritin_ng_ml", 15, 150),
                                  ("retic_abs_10e9_l", 25, 100)):
            for value, expected in ((low - 0.01, "LOW"), (low, "WITHIN"), (low + 0.01, "WITHIN"),
                                      (high - 0.01, "WITHIN"), (high, "WITHIN"), (high + 0.01, "HIGH")):
                result = analyze_cbc({**BASE, field: value}, {field: {"low": low, "high": high}})
                self.assertIn(f"CBC_LAB_REFERENCE_{field.upper()}_{expected}", result.rules_used)


if __name__ == "__main__":
    unittest.main()
