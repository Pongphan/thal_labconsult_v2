"""Missing demographics must not acquire an implicit anemia cutoff."""
import math
import unittest

from logic.engine import analyze_screening, anemia_threshold, hct_threshold


class ScreeningDemographicsTests(unittest.TestCase):
    def test_adult_female_unknown_pregnancy_withholds_both_anemia_cutoffs(self):
        for pregnancy in (None, "unknown", "Not performed", "Indeterminate"):
            with self.subTest(pregnancy=pregnancy):
                result = analyze_screening({"age": 30, "sex": "Female", "pregnant": pregnancy,
                                            "hb_g_dl": 11.5, "hct_percent": 34, "mcv_fl": 88, "mch_pg": 29})
                self.assertFalse(result.validation_errors)
                self.assertIsNone(result.anemia)
                self.assertIsNone(result.thresholds_used["anemia_hb"])
                self.assertIsNone(result.thresholds_used["anemia_hct"])
                self.assertTrue(any("ไม่ทราบสถานะการตั้งครรภ์" in item for item in result.validation_warnings))

    def test_explicit_pregnancy_status_preserves_existing_cutoffs(self):
        for pregnancy, hb_limit, hct_limit, anemia in ((False, 12, 36, True), (True, 11, 33, False)):
            result = analyze_screening({"age": 30, "sex": "Female", "pregnant": pregnancy,
                                        "hb_g_dl": 11.5, "hct_percent": 34, "mcv_fl": 88, "mch_pg": 29})
            self.assertEqual(result.anemia, anemia)
            self.assertEqual(result.thresholds_used["anemia_hb"], hb_limit)
            self.assertEqual(result.thresholds_used["anemia_hct"], hct_limit)

    def test_unknown_pregnancy_does_not_hide_independent_low_hb_alert(self):
        result = analyze_screening({"age": 30, "sex": "Female", "hb_g_dl": 6,
                                    "mcv_fl": 68, "mch_pg": 21})
        self.assertIsNone(result.anemia)
        self.assertTrue(result.severe_anemia_flag)
        self.assertEqual(result.consult_risk, "Critical review")
        self.assertTrue(result.evidence)
        self.assertTrue(result.recommendations)

    def test_age_only_child_cutoffs_and_male_cutoffs_do_not_require_pregnancy(self):
        for age, sex, hb_limit, hct_limit in ((4, "Female", 11, 33), (14.99, "Female", 12, 36),
                                            (30, "Male", 13, 40)):
            result = analyze_screening({"age": age, "sex": sex, "hb_g_dl": 10,
                                        "mcv_fl": 88, "mch_pg": 29})
            self.assertTrue(result.anemia)
            self.assertEqual(result.thresholds_used["anemia_hb"], hb_limit)
            self.assertEqual(result.thresholds_used["anemia_hct"], hct_limit)
        boundary = analyze_screening({"age": 15, "sex": "Female", "hb_g_dl": 10,
                                       "mcv_fl": 88, "mch_pg": 29})
        self.assertIsNone(boundary.anemia)

    def test_public_cutoff_helpers_do_not_assume_nonpregnancy(self):
        for helper in (anemia_threshold, hct_threshold):
            self.assertTrue(math.isnan(helper(30, "Female")))
            self.assertTrue(math.isfinite(helper(30, "Female", False)))
            self.assertTrue(math.isfinite(helper(30, "Female", True)))


if __name__ == "__main__":
    unittest.main()
