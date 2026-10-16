"""Independent, declarative adult CBC review; no patient persistence or diagnosis."""
from __future__ import annotations

from .units import validate_declared_units

from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
from pathlib import Path
import string
from typing import Any, Mapping

import numpy as np

from .validation import normalize_threshold_sex, sex_is_unspecified
from utils.build_provenance import capture_build_provenance


CBC_RULES_PATH = Path(__file__).resolve().parents[1] / "data" / "cbc_rules.json"
NUMERIC_FIELDS = frozenset({
    "age", "hb_g_dl", "rbc_10e12_l", "hct_percent", "mcv_fl", "mch_pg", "mchc_g_dl",
    "rdw_percent", "wbc_10e9_l", "platelets_10e9_l", "ferritin_ng_ml", "retic_abs_10e9_l",
})
REFERENCE_FIELDS = ("wbc_10e9_l", "platelets_10e9_l", "rdw_percent", "ferritin_ng_ml", "retic_abs_10e9_l")
_MESSAGE_KEYS = frozenset({
    "invalid_number", "invalid_sex", "invalid_pregnancy", "contradictory_demographics",
    "missing_age", "missing_sex", "missing_pregnancy", "missing_hb", "missing_mcv",
    "age_out_of_scope", "pregnant_out_of_scope", "scope_supported", "scope_limited",
    "status_supported", "status_incomplete", "status_out_of_scope", "status_invalid",
    "anemia_below", "anemia_not_below", "anemia_not_assessed", "hb_below_reason",
    "hb_not_below_reason", "mcv_micro", "mcv_normo", "mcv_macro", "mcv_micro_reason",
    "mcv_macro_reason", "mcv_normo_reason", "pattern_unavailable", "pattern_invalid",
    "anemia_pattern", "severe_adult", "low_hb_outside_scope", "reference_missing",
    "reference_invalid", "reference_unsupported", "reference_low", "reference_high",
    "reference_within", "reference_scope", "ferritin_caveat", "retic_caveat",
    "tests_baseline", "tests_micro", "tests_macro", "tests_normo", "tests_ferritin_low",
    "tests_invalid", "tests_missing", "counseling", "limitation_scope",
    "limitation_adjustments", "limitation_no_diagnosis",
})
_MESSAGE_FIELDS = {
    "invalid_number": {"label", "low", "high"},
    "age_out_of_scope": {"age_min", "age_max"},
    "scope_supported": {"age_min", "age_max"},
    "limitation_scope": {"age_min", "age_max"},
    "hb_below_reason": {"value", "threshold"},
    "hb_not_below_reason": {"value", "threshold"},
    "mcv_micro_reason": {"value", "threshold"},
    "mcv_macro_reason": {"value", "threshold"},
    "mcv_normo_reason": {"value", "low", "high"},
    "anemia_pattern": {"pattern"},
    "severe_adult": {"value", "threshold"},
    "low_hb_outside_scope": {"value", "threshold"},
    "reference_missing": {"label"},
    "reference_invalid": {"label"},
    "reference_low": {"label", "value", "threshold"},
    "reference_high": {"label", "value", "threshold"},
    "reference_within": {"label", "value"},
}


def _finite_number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def load_cbc_rules(path: str | Path | None = None) -> dict[str, Any]:
    """Reject malformed config and executable expressions rather than falling back."""
    try:
        config = json.loads(Path(path or CBC_RULES_PATH).read_text(encoding="utf-8-sig"))
        metadata, thresholds, validation, messages = [config[key] for key in ("metadata", "thresholds", "validation", "messages")]
        if not all(isinstance(part, dict) for part in (metadata, thresholds, validation, messages)):
            raise ValueError("invalid section")
        if not all(isinstance(metadata[key], str) and metadata[key] for key in ("version", "status", "description_th", "disclaimer_th")):
            raise ValueError("invalid metadata")
        if not isinstance(metadata["sources"], list) or not metadata["sources"]:
            raise ValueError("missing sources")
        for source in metadata["sources"]:
            if not all(isinstance(source[key], str) and source[key] for key in ("id", "title", "url", "use")) or not source["url"].startswith("https://"):
                raise ValueError("invalid source")
        expected = {"age_min_years", "age_max_years", "hb_male_g_dl", "hb_female_g_dl", "severe_hb_g_dl", "mcv_micro_fl", "mcv_macro_fl"}
        if set(thresholds) != expected or not all(_finite_number(value) and value > 0 for value in thresholds.values()):
            raise ValueError("invalid thresholds")
        if not (thresholds["age_min_years"] < thresholds["age_max_years"] and thresholds["mcv_micro_fl"] < thresholds["mcv_macro_fl"]
                and thresholds["severe_hb_g_dl"] < min(thresholds["hb_male_g_dl"], thresholds["hb_female_g_dl"])):
            raise ValueError("unordered thresholds")
        if set(validation["ranges"]) != NUMERIC_FIELDS or set(validation["reference_fields"]) != set(REFERENCE_FIELDS):
            raise ValueError("invalid fields")
        for bounds in validation["ranges"].values():
            if not isinstance(bounds, list) or len(bounds) != 3 or not all(_finite_number(value) for value in bounds[:2]) or not 0 <= bounds[0] < bounds[1] or not isinstance(bounds[2], str):
                raise ValueError("invalid numeric bounds")
        if not isinstance(validation["bounds_note_th"], str) or not _MESSAGE_KEYS <= messages.keys():
            raise ValueError("missing messages")
        for key, message in messages.items():
            if not isinstance(message, str):
                raise ValueError("invalid message")
            for _, name, spec, conversion in string.Formatter().parse(message):
                if name is not None and (name not in _MESSAGE_FIELDS.get(key, set()) or spec not in {"", "g"} or conversion is not None):
                    raise ValueError("unsupported message template")
                if spec == "g" and name not in {"low", "high", "age_min", "age_max", "value", "threshold"}:
                    raise ValueError("numeric format used on a text field")
        return config
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, AttributeError, IndexError):
        raise ValueError("ไฟล์กฎ CBC ไม่ผ่านการตรวจสอบ กรุณาทบทวนโครงสร้าง เกณฑ์ และข้อความก่อนใช้งาน") from None


CBC_DISCLAIMER = load_cbc_rules()["metadata"]["disclaimer_th"]


@dataclass
class CBCResult:
    normalized: dict[str, Any]
    validation_errors: list[str]
    validation_warnings: list[str]
    anemia_status: str
    anemia_code: str
    pattern: str
    pattern_code: str
    findings: list[str]
    rationale: list[str]
    recommended_tests: list[str]
    counseling: list[str]
    limitations: list[str]
    ruleset_version: str
    ruleset_hash: str
    rules_used: list[str]
    scope: str
    scope_supported: bool
    support_status: str
    support_code: str
    disclaimer: str
    severe_anemia_flag: bool
    low_hb_alert: bool
    thresholds_used: dict[str, Any]
    reference_intervals_used: dict[str, dict[str, float | None]]
    build_provenance: dict[str, Any] = field(default_factory=capture_build_provenance)

    @property
    def title(self) -> str:
        return self.pattern

    @property
    def status(self) -> str:
        return self.support_status

    @property
    def recommendations(self) -> list[str]:
        return self.recommended_tests

    @property
    def scope_note(self) -> str:
        return self.scope

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"", "nan", "na", "none", "null", "unknown", "not specified", "not performed", "ไม่ทราบ", "ไม่ระบุ"}
    try:
        return bool(math.isnan(value))
    except (ValueError, TypeError):
        return False


def _number(value: Any) -> float | None:
    if isinstance(value, (bool, np.bool_)):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError, OverflowError):
        return None


def analyze_cbc(
    row: Mapping[str, Any],
    reference_intervals: Mapping[str, Mapping[str, Any]] | None = None,
    *, rules_path: str | Path | None = None,
) -> CBCResult:
    """Assess validated adult Hb/MCV and supplied lab intervals without diagnosing causes."""
    config = load_cbc_rules(rules_path)
    thresholds, ranges, messages = config["thresholds"], config["validation"]["ranges"], config["messages"]

    def msg(key: str, **values: Any) -> str:
        return messages[key].format(**values)

    errors: list[str] = []
    warnings: list[str] = []
    normalized: dict[str, Any] = {}
    unit_errors, invalid_units, declared_units = validate_declared_units(row, ranges)
    errors.extend(unit_errors)
    if declared_units:
        normalized["declared_units"] = declared_units
    for field, (low, high, label) in ranges.items():
        if field in invalid_units:
            normalized[field] = None
            continue
        raw = row.get(field)
        value = None if _missing(raw) else _number(raw)
        if not _missing(raw) and (value is None or not low <= value <= high):
            errors.append(msg("invalid_number", label=label, low=low, high=high))
            value = None
        normalized[field] = value

    raw_sex = row.get("sex")
    sex = normalize_threshold_sex(raw_sex)
    if not sex_is_unspecified(raw_sex) and sex is None:
        errors.append(msg("invalid_sex"))
    normalized["sex"] = sex
    raw_pregnancy = row.get("pregnant")
    pregnant = None
    if not _missing(raw_pregnancy):
        token = str(raw_pregnancy).strip().lower()
        if raw_pregnancy is True or token in {"true", "yes", "1", "ใช่", "ตั้งครรภ์"}:
            pregnant = True
        elif raw_pregnancy is False or token in {"false", "no", "0", "ไม่ใช่", "ไม่ตั้งครรภ์", "not applicable", "ไม่เกี่ยวข้อง"}:
            pregnant = False
        else:
            errors.append(msg("invalid_pregnancy"))
    normalized["pregnant"] = pregnant
    if sex == "Male" and pregnant is True:
        errors.append(msg("contradictory_demographics"))

    lab_ranges: dict[str, dict[str, float | None]] = {}
    if reference_intervals is not None and not isinstance(reference_intervals, Mapping):
        errors.append(msg("reference_invalid", label="CBC"))
    elif reference_intervals:
        for field, interval in reference_intervals.items():
            if field not in REFERENCE_FIELDS:
                warnings.append(msg("reference_unsupported"))
                continue
            invalid = not isinstance(interval, Mapping) or not set(interval) <= {"low", "high"}
            clean: dict[str, float | None] = {"low": None, "high": None}
            if not invalid:
                for bound in ("low", "high"):
                    raw = interval.get(bound)
                    clean[bound] = None if _missing(raw) else _number(raw)
                    if not _missing(raw) and (clean[bound] is None or clean[bound] < 0):
                        invalid = True
                if all(value is not None for value in clean.values()) and clean["low"] >= clean["high"]:
                    invalid = True
            if invalid:
                errors.append(msg("reference_invalid", label=ranges[field][2]))
            elif any(value is not None for value in clean.values()):
                lab_ranges[field] = clean

    age = normalized["age"]
    age_ok = age is not None and thresholds["age_min_years"] <= age <= thresholds["age_max_years"]
    nonpregnant = pregnant is False or (sex == "Male" and pregnant is None)
    scope_supported = bool(age_ok and sex is not None and nonpregnant)
    mcv_scope = bool(age_ok and nonpregnant)
    if age is None:
        warnings.append(msg("missing_age"))
    elif not age_ok:
        warnings.append(msg("age_out_of_scope", age_min=thresholds["age_min_years"], age_max=thresholds["age_max_years"]))
    if sex is None:
        warnings.append(msg("missing_sex"))
    if pregnant is True:
        warnings.append(msg("pregnant_out_of_scope"))
    elif not nonpregnant:
        warnings.append(msg("missing_pregnancy"))
    if normalized["hb_g_dl"] is None:
        warnings.append(msg("missing_hb"))
    if normalized["mcv_fl"] is None:
        warnings.append(msg("missing_mcv"))

    findings: list[str] = []
    rationale: list[str] = []
    tests: list[str] = []
    rules_used: list[str] = []
    effective: dict[str, Any] = {"age_min_years": thresholds["age_min_years"], "age_max_years": thresholds["age_max_years"], "low_hb_alert_g_dl": thresholds["severe_hb_g_dl"]}
    limitations = [msg("limitation_scope", age_min=thresholds["age_min_years"], age_max=thresholds["age_max_years"]), msg("limitation_adjustments"), msg("limitation_no_diagnosis"), config["validation"]["bounds_note_th"]]
    hb, mcv = normalized["hb_g_dl"], normalized["mcv_fl"]
    low_hb_alert = bool(hb is not None and hb < thresholds["severe_hb_g_dl"])
    severe_anemia_flag = low_hb_alert and scope_supported
    if low_hb_alert:
        findings.append(msg("severe_adult" if severe_anemia_flag else "low_hb_outside_scope", value=hb, threshold=thresholds["severe_hb_g_dl"]))
        rules_used.append("CBC_LOW_HB_ALERT_ADULT" if severe_anemia_flag else "CBC_LOW_HB_ALERT_UNSCOPED")

    anemia_code, pattern_code = "not_assessed", "unavailable"
    anemia_status, pattern = msg("anemia_not_assessed"), msg("pattern_unavailable")
    if not errors:
        if scope_supported and hb is not None:
            hb_threshold = thresholds["hb_male_g_dl" if sex == "Male" else "hb_female_g_dl"]
            effective["hb_anemia_g_dl"] = hb_threshold
            anemia_code = "below_cutoff" if hb < hb_threshold else "not_below_cutoff"
            anemia_status = msg("anemia_below" if anemia_code == "below_cutoff" else "anemia_not_below")
            rationale.append(msg("hb_below_reason" if anemia_code == "below_cutoff" else "hb_not_below_reason", value=hb, threshold=hb_threshold))
            findings.append(anemia_status)
            rules_used.append("CBC_WHO_HB_MALE" if sex == "Male" else "CBC_WHO_HB_FEMALE")
        if mcv_scope and mcv is not None:
            effective.update({"mcv_micro_fl": thresholds["mcv_micro_fl"], "mcv_macro_fl": thresholds["mcv_macro_fl"]})
            pattern_code = "micro" if mcv < thresholds["mcv_micro_fl"] else "macro" if mcv > thresholds["mcv_macro_fl"] else "normo"
            pattern = msg("mcv_" + pattern_code)
            if pattern_code == "normo":
                rationale.append(msg("mcv_normo_reason", value=mcv, low=thresholds["mcv_micro_fl"], high=thresholds["mcv_macro_fl"]))
            else:
                rationale.append(msg("mcv_" + pattern_code + "_reason", value=mcv, threshold=thresholds["mcv_" + pattern_code + "_fl"]))
            if anemia_code == "below_cutoff":
                pattern = msg("anemia_pattern", pattern=pattern)
            findings.append(pattern)
            rules_used.append("CBC_MCV_" + pattern_code.upper())
            if anemia_code == "below_cutoff" or pattern_code != "normo":
                tests.append(msg("tests_" + pattern_code))
        for field in REFERENCE_FIELDS:
            value = normalized[field]
            if value is None:
                continue
            interval = lab_ranges.get(field)
            if interval is None:
                warnings.append(msg("reference_missing", label=ranges[field][2]))
                continue
            low, high = interval["low"], interval["high"]
            direction = "low" if low is not None and value < low else "high" if high is not None and value > high else "within"
            finding = msg("reference_" + direction, label=ranges[field][2], value=value, threshold=low if direction == "low" else high)
            findings.append(finding)
            rationale.append(finding)
            rules_used.append("CBC_LAB_REFERENCE_" + field.upper() + "_" + direction.upper())
            if field == "ferritin_ng_ml" and direction == "low":
                tests.append(msg("tests_ferritin_low"))
        tests.insert(0, msg("tests_baseline"))
        if anemia_code == "not_assessed":
            tests.insert(0, msg("tests_missing"))
    else:
        pattern = msg("pattern_invalid")
        pattern_code = "invalid"
        tests.append(msg("tests_invalid"))
    if normalized["ferritin_ng_ml"] is not None:
        limitations.append(msg("ferritin_caveat"))
    if normalized["retic_abs_10e9_l"] is not None:
        limitations.append(msg("retic_caveat"))
    if lab_ranges:
        limitations.append(msg("reference_scope"))

    support_code = "invalid" if errors else "out_of_scope" if not scope_supported else "incomplete" if hb is None or mcv is None else "supported"
    scope = msg("scope_supported", age_min=thresholds["age_min_years"], age_max=thresholds["age_max_years"]) if scope_supported else msg("scope_limited")
    fingerprint = hashlib.sha256(json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return CBCResult(
        normalized=normalized, validation_errors=errors, validation_warnings=list(dict.fromkeys(warnings)),
        anemia_status=anemia_status, anemia_code=anemia_code, pattern=pattern, pattern_code=pattern_code,
        findings=findings, rationale=rationale, recommended_tests=list(dict.fromkeys(tests)),
        counseling=[msg("counseling")], limitations=limitations, ruleset_version=config["metadata"]["version"],
        ruleset_hash=fingerprint, rules_used=rules_used, scope=scope, scope_supported=scope_supported,
        support_status=msg("status_" + support_code), support_code=support_code,
        disclaimer=config["metadata"]["disclaimer_th"], severe_anemia_flag=severe_anemia_flag,
        low_hb_alert=low_hb_alert, thresholds_used=effective,
        reference_intervals_used={field: bounds for field, bounds in lab_ranges.items() if normalized[field] is not None} if not errors else {},
    )
