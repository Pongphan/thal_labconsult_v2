"""Shared schema validation and result contract, without disease-specific rules."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
from pathlib import Path
import re
import string
from typing import Any, Mapping

import numpy as np

from logic.units import validate_declared_units
from utils.build_provenance import capture_build_provenance

DOMAIN_IDS = (
    "white_cells", "marrow_malignancies", "platelets_bleeding", "thrombosis",
    "transfusion", "morphology_quality",
)
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
STATUS_LABELS = {
    "incomplete": "ข้อมูลยังไม่เพียงพอ", "review": "มีผลสำหรับทบทวนตามขอบเขต",
    "urgent": "มีประเด็นที่ต้องประเมินโดยเร็ว", "invalid": "ข้อมูลต้องแก้ไขก่อนใช้ข้อสรุป",
}


def _reject_constant(value: str) -> None:
    raise ValueError("non-finite JSON number")


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _finite(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _require(condition: bool) -> None:
    if not condition:
        raise ValueError("invalid configuration")


def _validate_domain_thresholds(module_id: str, thresholds: dict[str, Any], fields: list[dict[str, Any]]) -> None:
    """Validate the exact threshold contract before either forms or engines use it."""
    expected = {
        "white_cells": {"adult_min_age", "differential_total", "differential_tolerance_percent",
                        "absolute_conflict_relative", "absolute_conflict_floor", "severe_anc_10e9_l",
                        "fever_single_c", "fever_sustained_c", "fever_sustained_hours"},
        "marrow_malignancies": {"high_blast_review_percent", "multiple_cytopenia_lineages"},
        "platelets_bleeding": {"prolonged_ratio"},
        "thrombosis": {"adult_min_years"},
        "transfusion": {"abo_compatibility"},
        "morphology_quality": {"schistocyte_percent_upper", "differential_fields"},
    }
    _require(set(thresholds) == expected[module_id])
    if module_id in {"white_cells", "marrow_malignancies", "platelets_bleeding", "thrombosis"}:
        _require(all(_finite(value) and value > 0 for value in thresholds.values()))
    if module_id == "white_cells":
        t = thresholds
        _require(18 <= t["adult_min_age"] <= 120)
        _require(t["differential_total"] == 100 and t["differential_tolerance_percent"] < 100)
        _require(t["absolute_conflict_relative"] <= 1)
        _require(t["fever_sustained_c"] == 38 and t["fever_sustained_hours"] == 1)
        _require(t["fever_single_c"] >= t["fever_sustained_c"])
    elif module_id == "marrow_malignancies":
        _require(thresholds["high_blast_review_percent"] <= 100)
        _require(type(thresholds["multiple_cytopenia_lineages"]) is int and 2 <= thresholds["multiple_cytopenia_lineages"] <= 3)
    elif module_id == "platelets_bleeding":
        _require(thresholds["prolonged_ratio"] == 1)
    elif module_id == "thrombosis":
        _require(18 <= thresholds["adult_min_years"] <= 120)
    elif module_id == "transfusion":
        table = thresholds["abo_compatibility"]
        _require(isinstance(table, dict) and set(table) == {"rbc", "plasma"})
        groups = {"O", "A", "B", "AB"}
        for rows in table.values():
            _require(isinstance(rows, dict) and set(rows) == groups)
            for choices in rows.values():
                _require(isinstance(choices, list) and bool(choices))
                _require(all(isinstance(value, str) and value in groups for value in choices))
                _require(len(choices) == len(set(choices)))
    elif module_id == "morphology_quality":
        by_key = {item["key"]: item for item in fields}
        populations = thresholds["schistocyte_percent_upper"]
        _require(isinstance(populations, dict) and set(populations) == {"adult", "term_neonate", "preterm_neonate"})
        _require(all(_finite(value) and 0 < value <= 100 for value in populations.values()))
        _require(by_key["schistocyte_percent"]["type"] == "number")
        _require(set(populations) <= {option["value"] for option in by_key["population"]["options"]})
        differential = thresholds["differential_fields"]
        expected_counts = {"diff_neutrophils", "diff_lymphocytes", "diff_monocytes", "diff_eosinophils",
                           "diff_basophils", "diff_immature_granulocytes", "diff_blasts", "diff_other"}
        _require(isinstance(differential, list) and all(isinstance(key, str) for key in differential))
        _require(len(differential) == len(expected_counts) and set(differential) == expected_counts)
        for key in [*differential, "nrbc_count"]:
            _require(by_key[key]["type"] == "number" and by_key[key]["min"] == 0)
        _require(by_key["diff_total_reported"]["type"] == "number" and by_key["diff_total_reported"]["min"] > 0)


def load_domain_rules(module_id: str, path: str | Path | None = None) -> dict[str, Any]:
    """Read reviewed reference files only; no dynamic code imports or evaluation."""
    if module_id not in DOMAIN_IDS:
        raise ValueError("ไม่พบกลุ่มงานที่รองรับ")
    try:
        rules = json.loads(
            Path(path or DATA_DIR / f"{module_id}_rules.json").read_text(encoding="utf-8-sig"),
            parse_constant=_reject_constant, object_pairs_hook=_unique_pairs,
        )
        metadata = rules["metadata"]
        _require(metadata["module_id"] == module_id)
        for name in ("title", "version", "status", "scope", "disclaimer"):
            _require(isinstance(metadata[name], str) and bool(metadata[name].strip()))
        _require(metadata["status"] == "draft_requires_local_validation")
        _require(isinstance(metadata["sources"], list) and bool(metadata["sources"]))
        for source in metadata["sources"]:
            _require(all(isinstance(source[name], str) and bool(source[name].strip()) for name in ("title", "url", "use")))
            _require(source["url"].startswith("https://"))
        _require(isinstance(rules["fields"], list) and bool(rules["fields"]))
        keys: set[str] = set()
        for item in rules["fields"]:
            key = item["key"]
            _require(isinstance(key, str) and re.fullmatch(r"[a-z][a-z0-9_]*", key) is not None and key not in keys)
            keys.add(key)
            _require(all(isinstance(item[name], str) and bool(item[name].strip()) for name in ("label", "section")))
            _require(item["type"] in {"number", "select", "multiselect"})
            if item["type"] == "number":
                _require(_finite(item["min"]) and _finite(item["max"]) and item["min"] < item["max"])
            else:
                options = item["options"]
                _require(isinstance(options, list) and bool(options))
                values: set[str] = set()
                for option in options:
                    _require(all(isinstance(option[name], str) and bool(option[name]) for name in ("value", "label")))
                    _require(option["value"] not in values)
                    values.add(option["value"])
                if item["type"] == "select":
                    _require(options[0]["value"] == "unknown")
        _require(isinstance(rules["thresholds"], dict) and isinstance(rules["messages"], dict))
        _validate_domain_thresholds(module_id, rules["thresholds"], rules["fields"])
        for text in rules["messages"].values():
            _require(isinstance(text, str))
            for _, name, spec, conversion in string.Formatter().parse(text):
                if name is not None:
                    _require(re.fullmatch(r"[a-z][a-z0-9_]*", name) is not None)
                    _require(conversion is None and re.fullmatch(r"(?:\.?\d{0,2})?[fg%]?", spec) is not None)
        for name in ("limitations", "counseling"):
            _require(isinstance(rules[name], list) and all(isinstance(value, str) for value in rules[name]))
        _require(isinstance(rules["examples"], list))
        for example in rules["examples"]:
            _require(isinstance(example["name"], str) and isinstance(example["data"], dict))
            _require(set(example["data"]) <= keys)
        # Disallow overflowed JSON numeric literals as well as NaN/Infinity tokens.
        json.dumps(rules, ensure_ascii=False, allow_nan=False)
        return rules
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError):
        raise ValueError(f"ไฟล์กฎของกลุ่มงาน {module_id} ไม่ถูกต้อง กรุณาทบทวนโครงสร้าง เกณฑ์ และข้อความ") from None


def rule_text(rules: Mapping[str, Any], key: str, **values: Any) -> str:
    try:
        return rules["messages"][key].format(**values)
    except (KeyError, ValueError, TypeError):
        raise ValueError("ข้อความในไฟล์กฎไม่สอดคล้องกับข้อมูลที่ใช้แปลผล") from None


def _missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"", "nan", "none", "null", "na"}
    try:
        return bool(math.isnan(value))
    except (TypeError, ValueError):
        return False


def field_label(item: Mapping[str, Any]) -> str:
    """Keep units visible in forms, validation errors and exported snapshots."""
    label, unit = item["label"], item.get("unit", "")
    return f"{label} [{unit}]" if unit and unit not in label else label


def validate_domain_inputs(data: Mapping[str, Any], rules: Mapping[str, Any]) -> tuple[dict[str, Any], list[str], list[str]]:
    normalized: dict[str, Any] = {}
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(data, Mapping):
        return {}, ["ข้อมูลนำเข้าต้องเป็นรายการผลตรวจตามแบบฟอร์ม"], []
    keys = {item["key"] for item in rules["fields"]}
    numeric_units = {item["key"]: item.get("unit") for item in rules["fields"] if item["type"] == "number"}
    # D-dimer has a selected unit and a separately selected FEU/DDU basis.
    # An explicit declaration must agree with that selection, never fill it in.
    for field, selector in (("ddimer_value", "ddimer_unit"), ("ddimer_cutoff", "cutoff_unit")):
        if field in numeric_units:
            selected = data.get(selector)
            numeric_units[field] = {"ng_ml": "ng/mL", "ug_l": "µg/L", "mg_l": "mg/L"}.get(selected) if isinstance(selected, str) else None
    unit_fields = {key + "_unit" for key in numeric_units}
    if set(data) - keys - unit_fields - {"units"}:
        warnings.append("ไม่ใช้ข้อมูลนอกแบบฟอร์มของกลุ่มงานนี้ และไม่เก็บข้อมูลดังกล่าวในผลหรือรายงาน")
    unit_errors, invalid_units, declared_units = validate_declared_units(
        data, numeric_units, canonical_units=numeric_units, input_fields=keys,
    )
    errors.extend(unit_errors)
    if declared_units:
        normalized["declared_units"] = declared_units
    for item in rules["fields"]:
        key, label = item["key"], field_label(item)
        raw = data.get(key)
        if item["type"] == "number":
            number = None
            if key not in invalid_units and not _missing(raw):
                try:
                    number = float(raw) if not isinstance(raw, (bool, np.bool_)) else float("inf")
                    if not math.isfinite(number) or not item["min"] <= number <= item["max"]:
                        raise ValueError("outside data bounds")
                except (ValueError, TypeError, OverflowError):
                    errors.append(f"{label}: กรุณาระบุตัวเลขระหว่าง {item['min']:g}–{item['max']:g} ตามหน่วยที่ระบุ หรือเว้นว่างเมื่อไม่มีผล")
                    number = None
            normalized[key] = number
        elif item["type"] == "select":
            choices = {option["value"] for option in item["options"]}
            # Explicit enum values such as 'none' are observations, not missingness.
            value = str(raw) if isinstance(raw, str) and raw in choices else "unknown" if _missing(raw) else str(raw)
            if value not in choices:
                errors.append(f"{label}: ค่าที่ระบุไม่ตรงกับตัวเลือกที่รองรับ")
                value = "unknown"
            normalized[key] = value
        else:
            choices = {option["value"] for option in item["options"]}
            values = [] if raw is None else raw
            if not isinstance(values, (list, tuple)):
                errors.append(f"{label}: กรุณาเลือกจากรายการที่รองรับ")
                values = []
            elif any(not isinstance(value, str) or value not in choices for value in values):
                errors.append(f"{label}: พบตัวเลือกที่ไม่รองรับ กรุณาทบทวน; ระบบคงข้อสังเกตที่ถูกต้องไว้เพื่อตรวจข้อเตือน")
                values = [value for value in values if isinstance(value, str) and value in choices]
            normalized[key] = list(dict.fromkeys(values))
    return normalized, errors, warnings


@dataclass
class ReviewResult:
    module_id: str
    title: str
    scope: str
    ruleset_version: str
    ruleset_hash: str
    disclaimer: str
    normalized: dict[str, Any]
    validation_errors: list[str] = field(default_factory=list)
    validation_warnings: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    rationale: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    counseling: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)
    rules_used: list[str] = field(default_factory=list)
    thresholds_used: dict[str, Any] = field(default_factory=dict)
    calculated: dict[str, Any] = field(default_factory=dict)
    status: str = "incomplete"
    sources: list[dict[str, str]] = field(default_factory=list)
    field_labels: dict[str, str] = field(default_factory=dict)
    value_labels: dict[str, dict[str, str]] = field(default_factory=dict)
    confidence_note: str = "เป็นผลทบทวนตามข้อมูลและขอบเขตที่ระบุ ไม่ใช่ความน่าจะเป็นของโรคหรือผลวินิจฉัย"
    build_provenance: dict[str, Any] = field(default_factory=capture_build_provenance)
    clinical_use_status: str = "draft_not_clinically_validated"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def start_review(module_id: str, data: Mapping[str, Any], *, rules_path: str | Path | None = None) -> tuple[ReviewResult, dict[str, Any]]:
    rules = load_domain_rules(module_id, rules_path)
    normalized, errors, warnings = validate_domain_inputs(data, rules)
    if not normalized:
        normalized, _, _ = validate_domain_inputs({}, rules)
    meta = rules["metadata"]
    fingerprint = hashlib.sha256(json.dumps(rules, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    result = ReviewResult(
        module_id=module_id, title=meta["title"], scope=meta["scope"],
        ruleset_version=meta["version"], ruleset_hash=fingerprint,
        disclaimer=meta["disclaimer"], normalized=normalized,
        validation_errors=errors, validation_warnings=warnings,
        limitations=list(rules["limitations"]), counseling=list(rules["counseling"]),
        sources=meta["sources"],
        field_labels={item["key"]: field_label(item) for item in rules["fields"]},
        value_labels={item["key"]: {option["value"]: option["label"] for option in item["options"]}
                      for item in rules["fields"] if "options" in item},
    )
    return result, rules


def finish_review(result: ReviewResult) -> ReviewResult:
    for name in ("validation_errors", "validation_warnings", "findings", "rationale", "recommendations", "counseling", "limitations", "alerts", "rules_used"):
        setattr(result, name, list(dict.fromkeys(getattr(result, name))))
    if result.validation_errors:
        result.status = "invalid"
    elif result.alerts:
        result.status = "urgent"
    elif not any(value is not None and value != "unknown" and value != [] for value in result.normalized.values()):
        result.status = "incomplete"
    if result.status not in STATUS_LABELS:
        raise ValueError("สถานะผลทบทวนไม่รองรับ")
    # A result is a reproducible snapshot; NaN must never leak into exported JSON.
    json.dumps(result.to_dict(), ensure_ascii=False, allow_nan=False)
    return result
