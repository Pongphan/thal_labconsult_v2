"""Reference evaluation measures supplied-label agreement, never grants approval."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from logic.hematology_common import DOMAIN_IDS
from scripts import evaluate_reference_cases as evaluator


def dataset_with_case(module="screening", inputs=None, expected=None):
    dataset = evaluator.demo_dataset()
    dataset["cases"] = [{"case_id": "CASE-001", "module": module, "inputs": inputs or {},
                         "expected": expected or {"validation_valid": False}}]
    return dataset


def test_synthetic_demo_has_expected_agreement_without_clinical_approval():
    dataset = evaluator.demo_dataset()
    original = deepcopy(dataset)
    report = evaluator.evaluate_reference_cases(dataset)
    assert dataset == original
    assert report["summary"] == {"total_cases": 3, "exact_match_cases": 3, "mismatch_cases": 0, "evaluation_error_cases": 0}
    assert report["dataset_provenance"]["kind"] == "synthetic"
    assert report["clinical_approval"] is False
    assert report["provenance_verified"] is False
    assert report["acceptance_policy"] is None
    assert report["evaluation_scope"] == "agreement_with_supplied_labels_only"
    assert len(report["dataset_sha256"]) == len(report["evaluator_sha256"]) == 64
    assert len(report["rulesets"]) == 3
    assert all(len(value["ruleset_sha256"]) == 64 for value in report["rulesets"].values())
    assert all(case["build_id"] in report["builds"] and case["ruleset_key"] in report["rulesets"] for case in report["cases"])
    assert all(value["clinical_approval"] is False for value in report["builds"].values())
    json.dumps(report, allow_nan=False)


def test_output_never_includes_raw_measurements_identifiers_or_free_text_findings():
    dataset = dataset_with_case(inputs={"sample_id": "PRIVATE-PATIENT-XYZ", "hb_g_dl": 12.345678, "mcv_fl": "PRIVATE-MEASUREMENT", "mch_pg": 22})
    report = evaluator.evaluate_reference_cases(dataset)
    serialized = json.dumps(report)
    assert "PRIVATE" not in serialized
    assert "12.345678" not in serialized
    assert '"inputs"' not in serialized
    assert '"normalized"' not in serialized
    assert '"findings"' not in serialized
    assert report["cases"][0]["exact_match"]


def test_confusion_counts_preserve_mismatch_and_only_count_explicitly_expected_endpoints():
    dataset = evaluator.demo_dataset()
    dataset["cases"] = [dataset["cases"][1], deepcopy(dataset["cases"][1])]
    dataset["cases"][0]["expected"] = {"pattern_code": "normo"}
    dataset["cases"][1]["case_id"] = "OTHER-CASE"
    dataset["cases"][1]["expected"] = {"pattern_code": "micro"}
    report = evaluator.evaluate_reference_cases(dataset)
    assert report["summary"] == {"total_cases": 2, "exact_match_cases": 1, "mismatch_cases": 1, "evaluation_error_cases": 0}
    assert len(report["endpoint_counts"]) == 1
    counts = report["endpoint_counts"][0]
    assert (counts["total"], counts["matched"], counts["mismatched"], counts["evaluation_errors"]) == (2, 1, 1, 0)
    assert counts["confusion"] == [
        {"expected": "micro", "observed": "normo", "evaluation_status": "evaluated", "count": 1},
        {"expected": "normo", "observed": "normo", "evaluation_status": "evaluated", "count": 1},
    ]
    assert report["clinical_approval"] is False


def test_null_primary_rule_is_an_explicit_label_not_a_missing_expected_case():
    report = evaluator.evaluate_reference_cases(dataset_with_case(expected={"primary_rule_id": None, "validation_valid": False}))
    assert report["summary"]["exact_match_cases"] == 1
    assert len(report["cases"][0]["checks"]) == 2
    assert report["cases"][0]["checks"][0]["observed"] is None


@pytest.mark.parametrize("module", DOMAIN_IDS)
def test_all_six_domain_endpoint_contracts_are_supported(module):
    report = evaluator.evaluate_reference_cases(dataset_with_case(module, expected={"status": "incomplete", "urgent_alert_present": False, "validation_valid": True}))
    assert report["cases"][0]["exact_match"]
    assert report["cases"][0]["module"] == module


def test_valid_independent_reference_assertion_is_recorded_but_never_certified():
    dataset = evaluator.demo_dataset()
    dataset["provenance"] = {"kind": "independent_reference", "reference_standard": "LOCALLY-LABELLED-PROTOCOL-V1", "labels_independent_of_engine": True}
    report = evaluator.evaluate_reference_cases(dataset)
    assert report["dataset_provenance"] == dataset["provenance"]
    assert report["provenance_verified"] is False
    assert report["clinical_approval"] is False
    dataset["provenance"]["reference_standard"] = "CHANGED"
    assert report["dataset_provenance"]["reference_standard"] == "LOCALLY-LABELLED-PROTOCOL-V1"


@pytest.mark.parametrize("provenance", [None, {}, {"kind": "approved"}, {"kind": "independent_reference", "reference_standard": "protocol", "labels_independent_of_engine": False}, {"kind": "synthetic", "reference_standard": "", "labels_independent_of_engine": False}, {"kind": "synthetic", "reference_standard": "protocol", "labels_independent_of_engine": 1}])
def test_invalid_or_unasserted_provenance_is_rejected(provenance):
    dataset = evaluator.demo_dataset()
    dataset["provenance"] = provenance
    with pytest.raises(evaluator.DatasetError):
        evaluator.evaluate_reference_cases(dataset)


@pytest.mark.parametrize("expected", [{}, {"severe_anemia_flag": 1}, {"validation_valid": "true"}, {"primary_rule_id": "unknown_rule"}, {"primary_rule_id": []}, {"hb_g_dl": 12}, {"status": "normal"}])
def test_expected_labels_are_strict_module_specific_categorical_contracts(expected):
    dataset = evaluator.demo_dataset()
    dataset["cases"][0]["expected"] = expected
    with pytest.raises(evaluator.DatasetError):
        evaluator.evaluate_reference_cases(dataset)


@pytest.mark.parametrize("mutation", [
    lambda data: data.update(schema_version=True),
    lambda data: data.update(schema_version=2),
    lambda data: data.update(patient_name="PRIVATE"),
    lambda data: data.update(dataset_id="not an opaque id"),
    lambda data: data.update(cases=[]),
    lambda data: data["cases"].append(deepcopy(data["cases"][0])),
    lambda data: data["cases"][0].update(module="pcr"),
    lambda data: data["cases"][0].update(case_id="PRIVATE WITH SPACES"),
    lambda data: data["cases"][0].update(inputs=[]),
    lambda data: data["cases"][0]["inputs"].update(patient_name="PRIVATE"),
    lambda data: data["cases"][0]["inputs"].update(hb_g_dl=float("inf")),
])
def test_invalid_case_schema_is_rejected_without_echoing_source_values(mutation):
    dataset = evaluator.demo_dataset()
    mutation(dataset)
    with pytest.raises(evaluator.DatasetError) as error:
        evaluator.evaluate_reference_cases(dataset)
    assert "PRIVATE" not in str(error.value)


def test_dataset_case_budget_is_bounded():
    dataset = evaluator.demo_dataset()
    dataset["cases"] = [dataset["cases"][0]] * (evaluator.MAX_CASES + 1)
    with pytest.raises(evaluator.DatasetError, match="10000"):
        evaluator.evaluate_reference_cases(dataset)


@pytest.mark.parametrize("payload", [b'{"schema_version":1,"schema_version":2}', b'{"value":NaN}', b'{"value":Infinity}', b'{"value":-Infinity}', b'not-json', b'\xff'])
def test_json_loader_rejects_duplicate_nonfinite_or_invalid_encoding(payload, tmp_path):
    path = tmp_path / "data.json"
    path.write_bytes(payload)
    with pytest.raises(evaluator.DatasetError):
        evaluator.load_dataset(path)


def test_json_loader_and_direct_api_reject_oversized_datasets(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluator, "MAX_DATASET_BYTES", 100)
    path = tmp_path / "large.json"
    path.write_bytes(b"x" * 101)
    with pytest.raises(evaluator.DatasetError, match="10 MB"):
        evaluator.load_dataset(path)
    with pytest.raises(evaluator.DatasetError, match="10 MB"):
        evaluator.evaluate_reference_cases(evaluator.demo_dataset())


def test_execution_error_is_counted_separately_never_agrees_with_expected_null(monkeypatch):
    def failure(*args):
        raise RuntimeError("PRIVATE-RAW-INPUT")
    monkeypatch.setattr(evaluator, "_run_case", failure)
    report = evaluator.evaluate_reference_cases(dataset_with_case(expected={"primary_rule_id": None}))
    assert report["summary"] == {"total_cases": 1, "exact_match_cases": 0, "mismatch_cases": 0, "evaluation_error_cases": 1}
    counts = report["endpoint_counts"][0]
    assert counts["evaluation_errors"] == 1
    assert counts["matched"] == counts["mismatched"] == 0
    assert not report["cases"][0]["exact_match"]
    assert report["cases"][0]["build_id"] is None
    assert "PRIVATE" not in json.dumps(report)


def test_cli_demo_and_evaluation_run_outside_project_working_directory(tmp_path):
    script = Path(evaluator.__file__).resolve()
    dataset, output = tmp_path / "synthetic.json", tmp_path / "evaluation.json"
    demo = subprocess.run([sys.executable, str(script), "--write-demo", str(dataset)], cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert demo.returncode == 0, demo.stderr
    evaluation = subprocess.run([sys.executable, str(script), str(dataset), "--output", str(output)], cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert evaluation.returncode == 0, evaluation.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["summary"]["exact_match_cases"] == 3
    assert report["clinical_approval"] is False
    assert "Clinical approval: false" in evaluation.stdout


def test_cli_mismatch_is_not_an_invented_clinical_acceptance_threshold(tmp_path, capsys):
    dataset = evaluator.demo_dataset()
    dataset["cases"][0]["expected"]["validation_valid"] = False
    source, output = tmp_path / "cases.json", tmp_path / "result.json"
    source.write_text(json.dumps(dataset), encoding="utf-8")
    assert evaluator.main([str(source), "--output", str(output)]) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["summary"]["mismatch_cases"] == 1
    assert report["acceptance_policy"] is None
    assert "1 mismatches" in capsys.readouterr().out


def test_cli_rejects_overwriting_input_and_existing_demo_file(tmp_path):
    source = tmp_path / "cases.json"
    original = json.dumps(evaluator.demo_dataset())
    source.write_text(original, encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        evaluator.main([str(source), "--output", str(source)])
    assert error.value.code == 2
    with pytest.raises(SystemExit) as error:
        evaluator.main(["--write-demo", str(source)])
    assert error.value.code == 2
    assert source.read_text(encoding="utf-8") == original


def test_cli_bad_schema_writes_no_report_or_input_contents(tmp_path, capsys):
    source, output = tmp_path / "cases.json", tmp_path / "result.json"
    source.write_text('{"patient":"PRIVATE"}', encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        evaluator.main([str(source), "--output", str(output)])
    assert error.value.code == 2
    assert not output.exists()
    assert "PRIVATE" not in capsys.readouterr().err
