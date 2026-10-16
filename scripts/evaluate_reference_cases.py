"""Offline agreement evaluation against supplied labels, never clinical approval.

Usage: python scripts/evaluate_reference_cases.py cases.json --output evaluation.json
       python scripts/evaluate_reference_cases.py --write-demo synthetic-cases.json

Dataset provenance and label independence are caller assertions, not verified by
this tool. Case IDs must be de-identified. Outputs contain allowed categorical
endpoints and provenance, never measurements, free-text findings or input rows.
No acceptance threshold, calibration claim or clinical release is implemented.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from logic.cbc import NUMERIC_FIELDS, analyze_cbc
from logic.engine import analyze_screening
from logic.hematology import analyze_domain
from logic.hematology_common import DOMAIN_IDS, STATUS_LABELS, load_domain_rules
from logic.rules import load_rules
from logic.units import CANONICAL_UNITS, MEASUREMENT_ALIASES
from logic.validation import SCREENING_COLUMNS
from utils.build_provenance import capture_build_provenance

MAX_DATASET_BYTES = 10 * 1024 * 1024
MAX_CASES = 10000
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")
_BOOLEAN_ENDPOINTS = {"validation_valid", "severe_anemia_flag", "urgent_alert_present"}
_CBC_ENDPOINTS = {
    "pattern_code": {"micro", "normo", "macro", "invalid", "unavailable"},
    "support_code": {"supported", "incomplete", "out_of_scope", "invalid"},
    "validation_valid": {True, False},
}


class DatasetError(ValueError):
    """Safe schema error that does not echo source values or patient identifiers."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DatasetError(message)


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in output, "Duplicate JSON keys are not allowed")
        output[key] = value
    return output


def _reject_constant(value: str) -> None:
    raise DatasetError("Nonfinite JSON numbers are not allowed")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":"))


def load_dataset(path: str | Path) -> dict[str, Any]:
    """Bound reads and reject duplicate keys, invalid encoding and nonfinite JSON."""
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(MAX_DATASET_BYTES + 1)
        _require(len(raw) <= MAX_DATASET_BYTES, "Dataset exceeds the 10 MB input limit")
        return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError):
        raise DatasetError("Cannot read a valid UTF-8 JSON dataset") from None


def _validate_dataset(dataset: Any) -> None:
    _require(isinstance(dataset, dict), "Dataset must be a JSON object")
    _require(set(dataset) == {"schema_version", "dataset_id", "provenance", "cases"}, "Dataset fields do not match schema version 1")
    _require(type(dataset["schema_version"]) is int and dataset["schema_version"] == 1, "Unsupported dataset schema version")
    _require(isinstance(dataset["dataset_id"], str) and _ID.fullmatch(dataset["dataset_id"]) is not None, "Dataset ID must be an opaque ASCII identifier")
    provenance = dataset["provenance"]
    _require(isinstance(provenance, dict) and set(provenance) == {"kind", "reference_standard", "labels_independent_of_engine"}, "Provenance fields are incomplete or unsupported")
    _require(provenance["kind"] in ("synthetic", "independent_reference"), "Dataset provenance must be explicitly classified")
    _require(isinstance(provenance["reference_standard"], str) and 0 < len(provenance["reference_standard"].strip()) <= 200, "A reference protocol or label-source description is required")
    _require(type(provenance["labels_independent_of_engine"]) is bool, "Label independence must be an explicit boolean assertion")
    _require(provenance["kind"] != "independent_reference" or provenance["labels_independent_of_engine"] is True, "Independent-reference data require an explicit independent-label assertion")
    cases = dataset["cases"]
    _require(isinstance(cases, list) and 1 <= len(cases) <= MAX_CASES, "Dataset must contain 1 to 10000 cases")
    screening_fields = set(SCREENING_COLUMNS) | set(MEASUREMENT_ALIASES)
    input_fields = {
        "screening": screening_fields | {key + "_unit" for key in set(CANONICAL_UNITS) | set(MEASUREMENT_ALIASES)} | {"units"},
        "cbc": set(NUMERIC_FIELDS) | {"sex", "pregnant", "units"} | {key + "_unit" for key in NUMERIC_FIELDS},
    }
    endpoints = {
        "screening": {"primary_rule_id": {None, *(rule["id"] for rule in load_rules()["rules"])}, "severe_anemia_flag": {True, False}, "validation_valid": {True, False}},
        "cbc": _CBC_ENDPOINTS,
    }
    for module in DOMAIN_IDS:
        fields = load_domain_rules(module)["fields"]
        input_fields[module] = {item["key"] for item in fields} | {item["key"] + "_unit" for item in fields if item["type"] == "number"} | {"units"}
        endpoints[module] = {"status": set(STATUS_LABELS), "urgent_alert_present": {True, False}, "validation_valid": {True, False}}
    seen: set[str] = set()
    for case in cases:
        _require(isinstance(case, dict) and set(case) == {"case_id", "module", "inputs", "expected"}, "Case fields are incomplete or unsupported")
        case_id = case["case_id"]
        _require(isinstance(case_id, str) and _ID.fullmatch(case_id) is not None and case_id not in seen, "Case IDs must be unique opaque ASCII identifiers")
        seen.add(case_id)
        module = case["module"]
        _require(isinstance(module, str) and module in endpoints, "Unsupported evaluation module")
        _require(isinstance(case["inputs"], dict) and set(case["inputs"]) <= input_fields[module], "Inputs contain fields outside the selected module schema")
        expected = case["expected"]
        _require(isinstance(expected, dict) and bool(expected) and set(expected) <= set(endpoints[module]), "Expected labels must use a nonempty subset of supported module endpoints")
        for endpoint, value in expected.items():
            scalar_type = type(value) is bool if endpoint in _BOOLEAN_ENDPOINTS else value is None or type(value) is str
            _require(scalar_type and value in endpoints[module][endpoint], "Expected label type or value is not supported")
    try:
        serialized = _json(dataset)
    except (TypeError, ValueError, OverflowError, RecursionError):
        raise DatasetError("Dataset must contain finite, serializable JSON values") from None
    _require(len(serialized.encode("utf-8")) <= MAX_DATASET_BYTES, "Dataset exceeds the 10 MB input limit")


def _run_case(module: str, inputs: Mapping[str, Any]) -> tuple[dict[str, Any], Any]:
    if module == "screening":
        result = analyze_screening(inputs)
        observed = {"primary_rule_id": result.rule_ids[0] if result.rule_ids else None,
                    "severe_anemia_flag": bool(result.severe_anemia_flag)}
    elif module == "cbc":
        result = analyze_cbc(inputs)
        observed = {"pattern_code": result.pattern_code, "support_code": result.support_code}
    else:
        result = analyze_domain(module, inputs)
        observed = {"status": result.status, "urgent_alert_present": bool(result.alerts)}
    observed["validation_valid"] = not bool(result.validation_errors)
    return observed, result


def evaluate_reference_cases(dataset: Mapping[str, Any]) -> dict[str, Any]:
    """Compare only explicitly labelled endpoints; missing labels are not negatives."""
    _validate_dataset(dataset)
    evaluator_build = capture_build_provenance()
    builds = {evaluator_build["build_id"]: evaluator_build}
    rulesets: dict[str, dict[str, Any]] = {}
    per_case: list[dict[str, Any]] = []
    aggregate: dict[str, dict[str, Any]] = {}
    for case in dataset["cases"]:
        module = case["module"]
        outcome: dict[str, Any] = {"case_id": case["case_id"], "module": module, "checks": []}
        observed: dict[str, Any] = {}
        try:
            observed, result = _run_case(module, case["inputs"])
            build = result.build_provenance
            builds[build["build_id"]] = deepcopy(build)
            rule_key = module + ":" + result.ruleset_hash
            rulesets[rule_key] = {"module": module, "ruleset_version": result.ruleset_version, "ruleset_sha256": result.ruleset_hash}
            outcome.update({"evaluation_status": "evaluated", "build_id": build["build_id"], "ruleset_key": rule_key})
        except Exception:
            # Never expose an analyzer exception containing an input value.
            # Count execution errors separately; they cannot become agreements.
            outcome.update({"evaluation_status": "error", "build_id": None, "ruleset_key": None})
        for endpoint, expected in case["expected"].items():
            evaluated = outcome["evaluation_status"] == "evaluated"
            actual = observed.get(endpoint) if evaluated else None
            matched = evaluated and type(actual) is type(expected) and actual == expected
            outcome["checks"].append({"endpoint": endpoint, "expected": expected, "observed": actual, "matched": matched})
            key = module + "." + endpoint
            bucket = aggregate.setdefault(key, {"module": module, "endpoint": endpoint, "total": 0, "matched": 0, "mismatched": 0, "evaluation_errors": 0, "confusion": Counter()})
            bucket["total"] += 1
            bucket["matched" if matched else "mismatched" if evaluated else "evaluation_errors"] += 1
            bucket["confusion"][(_json(expected), _json(actual), outcome["evaluation_status"])] += 1
        outcome["exact_match"] = all(check["matched"] for check in outcome["checks"])
        per_case.append(outcome)
    endpoint_counts = []
    for key in sorted(aggregate):
        bucket = aggregate[key]
        counts = bucket.pop("confusion")
        bucket["confusion"] = [{"expected": json.loads(expected), "observed": json.loads(observed), "evaluation_status": status, "count": count}
                               for (expected, observed, status), count in sorted(counts.items())]
        endpoint_counts.append(bucket)
    exact = sum(case["exact_match"] for case in per_case)
    errors = sum(case["evaluation_status"] == "error" for case in per_case)
    return {
        "schema_version": 1,
        "artifact_type": "reference_label_agreement_evaluation",
        "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset_id": dataset["dataset_id"],
        "dataset_sha256": sha256(_json(dataset).encode("utf-8")).hexdigest(),
        "dataset_provenance": deepcopy(dataset["provenance"]),
        "provenance_verified": False,
        "clinical_approval": False,
        "evaluation_scope": "agreement_with_supplied_labels_only",
        "acceptance_policy": None,
        "evaluator_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "builds": builds,
        "rulesets": rulesets,
        "summary": {"total_cases": len(per_case), "exact_match_cases": exact,
                    "mismatch_cases": len(per_case) - exact - errors, "evaluation_error_cases": errors},
        "endpoint_counts": endpoint_counts,
        "cases": per_case,
    }


def demo_dataset() -> dict[str, Any]:
    """Hand-authored synthetic demonstration; not independent clinical evidence."""
    return {
        "schema_version": 1,
        "dataset_id": "SYNTHETIC-DEMO-001",
        "provenance": {"kind": "synthetic", "reference_standard": "Hand-authored demonstration expectations; not clinical reference evidence", "labels_independent_of_engine": False},
        "cases": [
            {"case_id": "SYN-001", "module": "screening", "inputs": {"age": 30, "sex": "Male", "hb_g_dl": 12, "mcv_fl": 70, "mch_pg": 22, "hba2_percent": 5, "hb_method": "HPLC", "transfusion_recent": False},
             "expected": {"primary_rule_id": "beta_trait", "severe_anemia_flag": False, "validation_valid": True}},
            {"case_id": "SYN-002", "module": "cbc", "inputs": {"age": 30, "sex": "Male", "pregnant": False, "hb_g_dl": 14, "mcv_fl": 90},
             "expected": {"pattern_code": "normo", "support_code": "supported", "validation_valid": True}},
            {"case_id": "SYN-003", "module": "white_cells", "inputs": {"age": 30, "anc_10e9_l": 0.2, "temperature_c": 39, "fever_38_for_hour": "no"},
             "expected": {"status": "urgent", "urgent_alert_present": True, "validation_valid": True}},
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", nargs="?", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--write-demo", type=Path)
    args = parser.parse_args(argv)
    if args.write_demo is not None:
        if args.dataset is not None or args.output is not None:
            parser.error("--write-demo cannot be combined with dataset or --output")
        try:
            with args.write_demo.open("x", encoding="utf-8") as stream:
                json.dump(demo_dataset(), stream, ensure_ascii=False, allow_nan=False, indent=2)
        except OSError:
            parser.error("Cannot create demo file; choose a writable path that does not exist")
        print("Synthetic demonstration dataset written; not clinical validation evidence.")
        return 0
    if args.dataset is None or args.output is None:
        parser.error("Provide dataset.json and --output evaluation.json, or use --write-demo")
    if args.dataset.resolve() == args.output.resolve():
        parser.error("Output must not overwrite the input dataset")
    try:
        report = evaluate_reference_cases(load_dataset(args.dataset))
        args.output.write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")
    except (DatasetError, OSError):
        parser.error("Cannot evaluate dataset or write output; check schema, size and file access")
    summary = report["summary"]
    print(f"Evaluated {summary['total_cases']} cases: {summary['exact_match_cases']} exact matches, {summary['mismatch_cases']} mismatches, {summary['evaluation_error_cases']} execution errors. Clinical approval: false.")
    return 1 if summary["evaluation_error_cases"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
