"""Input files are parsed without persisting or echoing patient identifiers."""
import unittest

from thalab.core import SCREENING_COLUMNS, analyze_dataframe
from ui.data_io import ScreeningCSVError, read_screening_csv
from utils.csv_io import MAX_BYTES, MAX_COLUMNS, MAX_FIELD_CHARS, MAX_ROWS


class InputTests(unittest.TestCase):
    def test_allowlist_and_duplicate_identifiers(self):
        data = b"sample_id,patient_name,hb_g_dl,mcv_fl,mch_pg\nHN123,TEST,10,68,21\nHN123,TEST,11,74,23\n"
        frame, notes = read_screening_csv(data, SCREENING_COLUMNS, "TEST")
        self.assertEqual(len(frame), 2)
        self.assertEqual(frame["sample_id"].nunique(), 2)
        self.assertNotIn("patient_name", frame)
        self.assertNotIn("HN123", str(frame))
        self.assertEqual(len(analyze_dataframe(frame)), 2)
        self.assertTrue(notes)

    def test_bad_csv_rejected(self):
        for data in (b"", b"hb_g_dl,mcv_fl,mch_pg\n", b"hb_g_dl,hb_g_dl\n10,11", b"hb_g_dl,mcv_fl\n10,68,21"):
            with self.subTest(data=data), self.assertRaises(ScreeningCSVError):
                read_screening_csv(data, SCREENING_COLUMNS)

    def test_blank_data_row_is_not_silently_dropped(self):
        frame, _ = read_screening_csv(b"hb_g_dl,mcv_fl,mch_pg\n,,\n", SCREENING_COLUMNS)
        result = analyze_dataframe(frame)
        self.assertEqual(len(result), 1)
        self.assertTrue(result.iloc[0]["validation_errors"])

    def test_hba2_aliases_remain_separate(self):
        frame, _ = read_screening_csv(b"hb_g_dl,mcv_fl,mch_pg,HbA2,HbA2/E\n11,70,22,2.2,25\n", SCREENING_COLUMNS)
        self.assertEqual(float(frame.iloc[0]["hba2_percent"]), 2.2)
        self.assertEqual(float(frame.iloc[0]["hba2e_percent"]), 25)

    def test_header_normalization_cannot_hide_conflicting_values(self):
        for headers in ("HbA2,hba2_percent", "HB_G_DL, hb_g_dl ", "HbA2/E,HBA2E", "patient_name,PATIENT_NAME"):
            with self.subTest(headers=headers), self.assertRaises(ScreeningCSVError):
                read_screening_csv(f"hb_g_dl,{headers}\n11,2,80\n".encode(), SCREENING_COLUMNS)
        frame, _ = read_screening_csv("\ufeff HB_G_DL ,ＭＣＶ＿ＦＬ,MCH_PG\n11,70,22\n".encode(), SCREENING_COLUMNS)
        self.assertEqual(frame.iloc[0]["mcv_fl"], "70")

    def test_row_budget_is_shared_by_screening_including_blank_rows(self):
        header = b"hb_g_dl,mcv_fl,mch_pg\n"
        frame, _ = read_screening_csv(header + b"11,70,22\n" * MAX_ROWS, SCREENING_COLUMNS)
        self.assertEqual(len(frame), MAX_ROWS)
        for rows in (b"11,70,22\n" * (MAX_ROWS + 1), b"\n" * (MAX_ROWS + 1)):
            with self.assertRaisesRegex(ScreeningCSVError, "200"):
                read_screening_csv(header + rows, SCREENING_COLUMNS)

    def test_resource_limits_and_invalid_text_do_not_echo_contents(self):
        payloads = (
            b"P" * (MAX_BYTES + 1),
            (",".join(["hb_g_dl"] + [f"private{i}" for i in range(MAX_COLUMNS)]) + "\n").encode(),
            b"hb_g_dl,private\n11," + b"PRIVATE" * (MAX_FIELD_CHARS // 7 + 1),
            b"hb_g_dl\n11\x00",
            b"hb_g_dl\n\"PRIVATE",
            b"unrecognized\nPRIVATE\n",
        )
        for payload in payloads:
            with self.subTest(size=len(payload)), self.assertRaises(ScreeningCSVError) as error:
                read_screening_csv(payload, SCREENING_COLUMNS)
            self.assertNotIn("PRIVATE", str(error.exception))

    def test_physically_blank_rows_remain_visible_for_validation(self):
        frame, _ = read_screening_csv(b"hb_g_dl,mcv_fl,mch_pg\n11,70,22\n\n12,80,25\n", SCREENING_COLUMNS)
        results = analyze_dataframe(frame)
        self.assertEqual(len(results), 3)
        self.assertTrue(results.iloc[1]["validation_errors"])


if __name__ == "__main__":
    unittest.main()
