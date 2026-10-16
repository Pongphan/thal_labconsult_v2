"""PCR evidence and Mendelian probability regression checks."""
import unittest
from copy import deepcopy
from datetime import datetime
from unittest.mock import patch

import pandas as pd

from thalab.genetics import ALLELES, match_pcr_bands, prepare_pcr_calls, punnett, read_pcr_csv
from utils.csv_io import CSVInputError


class GeneticsTests(unittest.TestCase):
    def row(self, call="Positive", size=730):
        return pd.DataFrame([dict(sample_id="CASE", target_code="SEA_DEL", result=call, observed_bp=size)])

    def test_controls_gate_every_call(self):
        for status in ("not_confirmed", "fail"):
            result = match_pcr_bands(self.row(), controls_status=status).iloc[0]
            self.assertEqual(result["call"], "unresolved")
            self.assertFalse(result["detected"])
        result = match_pcr_bands(self.row(), controls_status="pass").iloc[0]
        self.assertTrue(result["detected"])

    def test_contradictory_and_unknown_calls_require_review(self):
        for call, size in [("Negative", 730), ("Positive", 900), (None, 730), ("unrecognized", 730), ("Positive", None)]:
            result = match_pcr_bands(self.row(call, size), controls_status="pass").iloc[0]
            self.assertEqual(result["call"], "unresolved")
            self.assertFalse(result["detected"])

    def test_negative_and_unknown_target_remain_distinct(self):
        negative = match_pcr_bands(self.row("Negative", None), controls_status="pass").iloc[0]
        self.assertEqual(negative["call"], "not_detected")
        unknown = self.row()
        unknown["target_code"] = "NOT_IN_PANEL"
        result = match_pcr_bands(unknown, controls_status="pass").iloc[0]
        self.assertEqual(result["call"], "unresolved")

    def test_bad_tolerance_rejected(self):
        for value in (0, -1, float("inf"), "bad"):
            with self.assertRaises(ValueError):
                match_pcr_bands(self.row(), tolerance_bp=value)

    def test_invalid_band_is_not_silently_a_negative(self):
        for value in (0, -1, float("inf"), "bad", 10001):
            with self.subTest(value=value), self.assertRaises(ValueError):
                match_pcr_bands(self.row("Negative", value), controls_status="pass")

    def test_import_removes_identifiers_and_unknown_columns(self):
        frame = pd.concat([self.row(), self.row()], ignore_index=True)
        frame["patient_name"] = "TEST NAME"
        result = prepare_pcr_calls(frame, pseudonymize=True)
        self.assertNotIn("patient_name", result)
        self.assertEqual(result["sample_id"].tolist(), ["PCR-001", "PCR-001"])

    def test_duplicate_csv_results_are_rejected_before_selecting_columns(self):
        for headers in ("result,result", "RESULT, result ", "result,ＲＥＳＵＬＴ"):
            payload = f"sample_id,target_code,{headers}\nPRIVATE,SEA_DEL,Negative,Positive\n".encode()
            with self.subTest(headers=headers), self.assertRaises(CSVInputError):
                read_pcr_csv(payload)

    def test_pcr_csv_requires_schema_and_exact_row_width(self):
        for payload in (
            b"sample_id,result\nPRIVATE,Negative\n",
            b"sample_id,target_code,result\nPRIVATE,SEA_DEL,Negative,Positive\n",
            b"sample_id,target_code,result\nPRIVATE,SEA_DEL\n",
            b"sample_id,target_code,result\n",
        ):
            with self.subTest(payload=payload), self.assertRaises(CSVInputError):
                read_pcr_csv(payload)

    def test_pcr_csv_normalizes_headers_retains_blank_rows_and_drops_identities(self):
        payload = b" SAMPLE_ID ,TARGET_CODE,RESULT,patient_name\nPRIVATE,SEA_DEL,Negative,PRIVATE\n\nPRIVATE,HBE,,PRIVATE\n"
        frame, notes = read_pcr_csv(payload)
        self.assertEqual(len(frame), 3)
        self.assertEqual(frame["sample_id"].tolist(), ["PCR-001", "PCR-002", "PCR-001"])
        self.assertNotIn("PRIVATE", frame.to_csv(index=False))
        self.assertEqual(frame["result"].tolist(), ["Negative", "Unknown", "Unknown"])
        self.assertTrue(notes)
        matched = match_pcr_bands(frame, controls_status="pass")
        self.assertEqual(matched["call"].tolist(), ["not_detected", "unresolved", "unresolved"])

    def test_blank_ids_never_merge_with_a_literal_missing_id(self):
        frame, _ = read_pcr_csv(b"sample_id,target_code\n,SEA_DEL\n__MISSING_ROW_0,HBE\n,CS\n")
        self.assertEqual(frame["sample_id"].nunique(), 3)

    def test_pcr_row_budget_also_applies_to_direct_api_calls(self):
        with self.assertRaisesRegex(CSVInputError, "200"):
            read_pcr_csv(b"sample_id,target_code\n" + b"X,SEA_DEL\n" * 201)
        with self.assertRaisesRegex(CSVInputError, "200"):
            match_pcr_bands(pd.concat([self.row()] * 201, ignore_index=True))
        frame = self.row()
        frame.columns = ["sample_id", "target_code", "result", "result"]
        with self.assertRaises(CSVInputError):
            prepare_pcr_calls(frame)

    def test_pcr_provenance_describes_evaluated_panel_and_survives_reference_change(self):
        with patch("thalab.genetics.load_allele_panel", side_effect=AssertionError("must not reread")):
            result = match_pcr_bands(self.row(), controls_status="pass")
        metadata = dict(result.attrs["evaluation"])
        evaluated_band = result.iloc[0]["expected_bp"]
        self.assertEqual(len(metadata["panel_sha256"]), 64)
        self.assertEqual(datetime.fromisoformat(metadata["evaluated_at"]).utcoffset().total_seconds(), 7 * 3600)
        changed = deepcopy(ALLELES)
        next(item for item in changed if item["target_code"] == "SEA_DEL")["expected_bp"] += 100
        with patch("thalab.genetics.ALLELES", changed):
            new_result = match_pcr_bands(self.row(), controls_status="pass")
        self.assertNotEqual(new_result.attrs["evaluation"]["panel_sha256"], metadata["panel_sha256"])
        self.assertEqual(result.attrs["evaluation"], metadata)
        self.assertEqual(result.iloc[0]["expected_bp"], evaluated_band)
        self.assertEqual(new_result.iloc[0]["expected_bp"], evaluated_band + 100)

    def test_mendelian_probabilities_are_aggregated(self):
        result = punnett(["βA", "βE"], ["βA", "βE"], "beta")
        self.assertEqual(sorted(result["probability"].tolist()), [25, 25, 50])
        self.assertEqual(result["probability"].sum(), 100)
        alpha = punnett(["--SEA", "αα"], ["--SEA", "αα"], "alpha")
        self.assertEqual(alpha.loc[alpha["severity"] == "critical", "probability"].sum(), 25)

    def test_unsupported_genotypes_rejected(self):
        for p1, p2, system in [(["βA"], ["βA", "βA"], "beta"),
                                (["unknown", "αα"], ["αα", "αα"], "alpha"),
                                (["βA", "βA"], ["βA", "βA"], "other")]:
            with self.assertRaises(ValueError):
                punnett(p1, p2, system)


if __name__ == "__main__":
    unittest.main()
