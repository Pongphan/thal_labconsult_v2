"""Validate screening input without treating missing or invalid tests as negative."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import math
import numpy as np
import pandas as pd
from .rules import load_rules
from .units import MEASUREMENT_ALIASES, validate_declared_units

SCREENING_COLUMNS = [
    "sample_id", "age", "sex", "hb_g_dl", "rbc_10e12_l", "hct_percent", "mcv_fl", "mch_pg",
    "mchc_g_dl", "rdw_percent", "retic_percent", "ferritin_ng_ml", "hba_percent", "hba2_percent",
    "hba2e_percent", "hbf_percent", "hbe_percent", "bart_percent", "hbh_percent", "hbcs_percent",
    "hb_method", "of_method", "oft", "dcip", "hbh_inclusion", "transfusion_recent", "pregnant",
    "smear_target_cells", "family_history", "partner_oft", "partner_dcip",
]
POSITIVE = {"yes", "y", "true", "positive", "pos", "1", "+", "detected", "present", "บวก", "ใช่"}
NEGATIVE = {"no", "n", "false", "negative", "neg", "0", "-", "not detected", "absent", "ลบ", "ไม่ใช่"}
MISSING = {"", "nan", "na", "none", "null", "unknown", "not performed", "not done", "ไม่ทราบ", "ไม่ได้ตรวจ"}
UNSPECIFIED_SEX = {"not specified", "ไม่ระบุ"}


def normalize_threshold_sex(value: Any) -> str | None:
    """Normalize the reference-interval context, without inferring missing sex."""
    return {"male": "Male", "m": "Male", "ชาย": "Male",
            "female": "Female", "f": "Female", "หญิง": "Female"}.get(str(value).strip().lower())


def sex_is_unspecified(value: Any) -> bool:
    return is_missing(value) or str(value).strip().lower() in UNSPECIFIED_SEX


def is_missing(value: Any) -> bool:
    if value is None or (isinstance(value, str) and value.strip().lower() in MISSING):
        return True
    try:
        return bool(pd.isna(value))
    except (ValueError, TypeError):
        return False


def safe_num(value: Any, default: float = np.nan) -> float:
    try:
        number = float(value) if not is_missing(value) else default
        return number if math.isfinite(number) else default
    except (ValueError, TypeError, OverflowError):
        return default


def normalize_call(value: Any) -> str:
    if is_missing(value):
        return "Not performed"
    call = str(value).strip().lower()
    if isinstance(value, (int, float, np.integer, np.floating)) and value in (0, 1):
        return "Positive" if value == 1 else "Negative"
    if call in POSITIVE or value is True:
        return "Positive"
    if call in NEGATIVE or value is False:
        return "Negative"
    if call in {"indeterminate", "equivocal", "borderline", "ก้ำกึ่ง", "ไม่ชัดเจน"}:
        return "Indeterminate"
    return "Invalid"


def yn(value: Any) -> bool:
    """Compatibility helper: use normalized statuses for clinical interpretation."""
    return normalize_call(value) == "Positive"


@dataclass
class ValidationResult:
    normalized: dict[str, Any]
    errors: list[str]
    warnings: list[str]


def validate_screening(row: dict[str, Any] | pd.Series, *, rules: dict | None = None) -> ValidationResult:
    config = rules or load_rules()
    source = row.to_dict() if hasattr(row, "to_dict") else dict(row)
    errors, warnings = [], []
    alias_conflicts: set[str] = set()
    # Resolve values before their paired metadata is checked. Never choose one
    # conflicting canonical/alias value and silently discard the other.
    for target in dict.fromkeys(MEASUREMENT_ALIASES.values()):
        names = [target, *(alias for alias, field in MEASUREMENT_ALIASES.items() if field == target)]
        candidates = [source[name] for name in names if name in source and not is_missing(source[name])]
        if not candidates:
            continue
        if len(candidates) > 1:
            values = [safe_num(value) for value in candidates]
            if (any(isinstance(value, (bool, np.bool_)) for value in candidates)
                    or not all(math.isfinite(value) for value in values)
                    or any(value != values[0] for value in values[1:])):
                errors.append(f"ค่า {target} จากชื่อคอลัมน์และชื่อย่อขัดแย้งกัน กรุณาเลือกผลต้นฉบับที่ถูกต้อง")
                alias_conflicts.add(target)
        source[target] = candidates[0]
    n = {key: source.get(key, np.nan) for key in SCREENING_COLUMNS}
    unit_errors, invalid_units, declared_units = validate_declared_units(source, config["validation"]["ranges"])
    errors.extend(unit_errors)
    invalid_units.update(alias_conflicts)
    if declared_units:
        n["declared_units"] = declared_units
    n["sample_id"] = "CASE-001" if is_missing(n["sample_id"]) else str(n["sample_id"])
    for field in ("sex", "hb_method", "of_method"):
        n[field] = "Not specified" if is_missing(n[field]) else str(n[field]).strip()
    sex = normalize_threshold_sex(n["sex"])
    if sex is None and not sex_is_unspecified(n["sex"]):
        errors.append("ข้อมูลเพศที่ใช้เลือกเกณฑ์ Hb ไม่อยู่ในตัวเลือกที่รองรับ กรุณาทบทวนก่อนใช้ผล")
    for key, (low, high, label) in config["validation"]["ranges"].items():
        if key in invalid_units:
            n[key] = np.nan
            continue
        raw = n.get(key)
        if is_missing(raw):
            n[key] = np.nan
            if key in config["validation"]["required"]:
                errors.append(f"กรุณาระบุ {label} เพื่อแปลผลคัดกรอง")
            continue
        value = safe_num(raw)
        if isinstance(raw, (bool, np.bool_)) or not math.isfinite(value) or not low <= value <= high:
            errors.append(f"{label} ต้องเป็นตัวเลขจำกัดในช่วง {low:g}–{high:g}; กรุณาตรวจหน่วยและข้อมูล")
            n[key] = np.nan
        else:
            n[key] = value
    for field in ("oft", "dcip", "hbh_inclusion", "partner_oft", "partner_dcip"):
        n[field] = normalize_call(n[field])
        if n[field] == "Invalid":
            message = f"ผล {field} ไม่ถูกต้อง กรุณาเลือกบวก ลบ ไม่ได้ตรวจ หรือไม่ชัดเจน"
            # A separate partner assay must not invalidate the patient's measurements.
            if field.startswith("partner_"):
                warnings.append(message + "; ยังสรุปผลคัดกรองของคู่ไม่ได้")
            else:
                errors.append(message)
        elif n[field] == "Indeterminate":
            warnings.append(f"ผล {field} ไม่ชัดเจน ต้องทบทวนหรือตรวจซ้ำ ไม่ถือเป็นผลลบ")
    for field in ("transfusion_recent", "pregnant", "smear_target_cells", "family_history"):
        state = normalize_call(n[field])
        n[field] = True if state == "Positive" else False if state == "Negative" else state
        if state == "Invalid":
            errors.append(f"ข้อมูล {field} ไม่ถูกต้อง กรุณาระบุใช่ ไม่ใช่ หรือไม่ทราบ")
    if sex == "Male" and n["pregnant"] is True:
        errors.append("ข้อมูลเพศที่เลือกเกณฑ์เป็นชายแต่ระบุว่าตั้งครรภ์ กรุณาทบทวนเกณฑ์ที่เหมาะสมกับบุคคลก่อนใช้ผล")
    fractions = [n[k] for k in ("hba_percent", "hbf_percent", "bart_percent", "hbh_percent", "hbcs_percent")]
    separate = [n["hba2_percent"], n["hbe_percent"]]
    combined = n["hba2e_percent"]
    # Check each representation separately. Even an incomplete resolved pair is
    # a lower bound on its total and must never be hidden by a combined peak.
    # Do not add overlapping combined/resolved values or assume cross-method equality.
    base_total = sum(v for v in fractions if math.isfinite(v))
    totals = {"HbA2/HbE แยกวัด": base_total + sum(v for v in separate if math.isfinite(v))}
    if math.isfinite(combined):
        totals["HbA2/E รวม"] = base_total + combined
    for channel, total in totals.items():
        if total > config["validation"]["fraction_sum_max"]:
            errors.append(f"ผลรวมสัดส่วน Hb ชุด {channel} ({total:g}%) สูงเกินขอบเขต กรุณาตรวจการนับพีคซ้ำและหน่วย")
    if math.isfinite(combined):
        warnings.append(config["messages"]["combined"])
        if any(math.isfinite(value) for value in separate):
            warnings.append(config["messages"]["resolved_and_combined"])
    if not math.isfinite(n["age"]):
        warnings.append("ไม่ระบุอายุ: ยังไม่ใช้เกณฑ์ CBC ตามวัยหรือกฎ HbA2/HbF ที่กำหนดอายุ กรุณาระบุอายุก่อนสรุปรูปแบบ")
    if sex is None:
        warnings.append("ไม่ระบุเพศที่ใช้กำหนดเกณฑ์ Hb: ต้องให้ผู้ทบทวนเลือกเกณฑ์ที่เหมาะสม")
    if not math.isfinite(n["ferritin_ng_ml"]):
        warnings.append("ไม่มีผล ferritin จึงยังประเมินภาวะขาดธาตุเหล็กหรือภาวะร่วมไม่ได้")
    if n["transfusion_recent"] == "Not performed":
        warnings.append("ไม่ทราบประวัติรับเลือดล่าสุด ต้องทบทวนก่อนแปลผลสัดส่วน Hb")
    if n["pregnant"] not in (True, False):
        warnings.append("ไม่ทราบสถานะการตั้งครรภ์: งดใช้เกณฑ์ Hb/Hct สำหรับหญิงที่ต้องยืนยันว่าไม่ตั้งครรภ์; เกณฑ์ตามอายุที่ไม่ขึ้นกับสถานะนี้และการแจ้ง Hb ต่ำมากยังพิจารณาแยกได้")
    if n["hb_method"].upper() not in {"HPLC", "CZE"} and any(
        math.isfinite(n[key]) for key in ("hba_percent", "hba2_percent", "hba2e_percent", "hbf_percent", "hbe_percent")
    ):
        warnings.append("ไม่ระบุวิธี Hb analysis ที่รองรับ (HPLC/CZE): ต้องทบทวนวิธีตรวจและพีคก่อนใช้ข้อสรุป")
    return ValidationResult(n, errors, warnings)
