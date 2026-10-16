"""Synthetic report validation prototype; no clinical release policy is installed.

The configured tolerances are demonstration inputs, never reference intervals.
Exact UCUM strings are checked without conversion. Formula agreement is an
arithmetic check, not independent evidence of analytical accuracy. REJECT means
quarantine the input record; it does not direct disposal of a specimen.
"""
from __future__ import annotations

from utils.build_provenance import capture_build_provenance

from collections.abc import Mapping, Sequence
from math import isfinite, ulp
from numbers import Integral, Real
from typing import Any


def _test(name_th: str, name_en: str, unit: str) -> dict[str, str]:
    return {"name_th": name_th, "name_en": name_en, "unit": unit}


TEST_CATALOG: dict[str, dict[str, str]] = {
    "hb_g_dl": _test("ฮีโมโกลบิน", "Hemoglobin", "g/dL"),
    "hct_percent": _test("ฮีมาโตคริต", "Hematocrit", "%"),
    "rbc_10e12_l": _test("จำนวนเม็ดเลือดแดง", "RBC count", "10*12/L"),
    "mcv_fl": _test("ปริมาตรเม็ดเลือดแดงเฉลี่ย", "MCV", "fL"),
    "mch_pg": _test("ฮีโมโกลบินเฉลี่ยต่อเม็ดเลือดแดง", "MCH", "pg"),
    "mchc_g_dl": _test("ความเข้มข้นฮีโมโกลบินในเม็ดเลือดแดง", "MCHC", "g/dL"),
    "rdw_percent": _test("การกระจายขนาดเม็ดเลือดแดง", "RDW-CV", "%"),
    "wbc_10e9_l": _test("จำนวนเม็ดเลือดขาว", "WBC count", "10*9/L"),
    "platelets_10e9_l": _test("จำนวนเกล็ดเลือด", "Platelet count", "10*9/L"),
    "neutrophils_percent": _test("นิวโทรฟิล", "Neutrophils", "%"),
    "lymphocytes_percent": _test("ลิมโฟไซต์", "Lymphocytes", "%"),
    "monocytes_percent": _test("โมโนไซต์", "Monocytes", "%"),
    "eosinophils_percent": _test("อีโอซิโนฟิล", "Eosinophils", "%"),
    "basophils_percent": _test("เบโซฟิล", "Basophils", "%"),
    "anc_10e9_l": _test("นิวโทรฟิลสัมบูรณ์", "Absolute neutrophils", "10*9/L"),
    "alc_10e9_l": _test("ลิมโฟไซต์สัมบูรณ์", "Absolute lymphocytes", "10*9/L"),
    "amc_10e9_l": _test("โมโนไซต์สัมบูรณ์", "Absolute monocytes", "10*9/L"),
    "aec_10e9_l": _test("อีโอซิโนฟิลสัมบูรณ์", "Absolute eosinophils", "10*9/L"),
    "abc_10e9_l": _test("เบโซฟิลสัมบูรณ์", "Absolute basophils", "10*9/L"),
    "retic_percent": _test("เรติคูโลไซต์", "Reticulocytes", "%"),
    "retic_abs_10e9_l": _test("เรติคูโลไซต์สัมบูรณ์", "Absolute reticulocytes", "10*9/L"),
    "pt_seconds": _test("โปรทรอมบินไทม์", "Prothrombin time", "s"),
    "inr": _test("อัตราส่วนมาตรฐานสากล", "INR", "1"),
    "aptt_seconds": _test("เอพีทีที", "Activated partial thromboplastin time", "s"),
    "fibrinogen_g_l": _test("ไฟบริโนเจน", "Fibrinogen", "g/L"),
    "hba_percent": _test("ฮีโมโกลบินเอ", "Hb A", "%"),
    "hba2_percent": _test("ฮีโมโกลบินเอทู", "Hb A2", "%"),
    "hbf_percent": _test("ฮีโมโกลบินเอฟ", "Hb F", "%"),
    "hbe_percent": _test("ฮีโมโกลบินอี", "Hb E", "%"),
    "ferritin_ng_ml": _test("เฟอร์ริติน", "Ferritin", "ng/mL"),
}
_CBC = ("hb_g_dl", "hct_percent", "rbc_10e12_l", "mcv_fl", "mch_pg", "mchc_g_dl",
        "rdw_percent", "wbc_10e9_l", "platelets_10e9_l")
_DIFF_PAIRS = {"neutrophils_percent": "anc_10e9_l", "lymphocytes_percent": "alc_10e9_l",
               "monocytes_percent": "amc_10e9_l", "eosinophils_percent": "aec_10e9_l",
               "basophils_percent": "abc_10e9_l"}
_FRACTION_FIELDS = {"hct_percent", "retic_percent", "hba_percent", "hba2_percent", "hbf_percent", "hbe_percent", *_DIFF_PAIRS}
PANEL_FIELDS: dict[str, tuple[str, ...]] = {
    "cbc": _CBC,
    "cbc_diff": _CBC + tuple(_DIFF_PAIRS) + tuple(_DIFF_PAIRS.values()),
    "reticulocyte": _CBC + ("retic_percent", "retic_abs_10e9_l"),
    "coagulation": ("pt_seconds", "inr", "aptt_seconds", "fibrinogen_g_l"),
    "thalassemia": _CBC + ("hba_percent", "hba2_percent", "hbf_percent", "hbe_percent", "ferritin_ng_ml"),
    "combined": tuple(TEST_CATALOG),
}
PANEL_LABELS = {
    "cbc": "ความสมบูรณ์ของเม็ดเลือด (CBC)",
    "cbc_diff": "CBC และแยกชนิดเม็ดเลือดขาว",
    "reticulocyte": "CBC และเรติคูโลไซต์",
    "coagulation": "การแข็งตัวของเลือด",
    "thalassemia": "CBC และข้อมูลประกอบการตรวจธาลัสซีเมีย",
    "combined": "รายงานรวมทุกกลุ่ม (ข้อมูลสังเคราะห์)",
}

_DEMO_VALUES = {
    "hb_g_dl": 7.2, "hct_percent": 30.5, "rbc_10e12_l": 3.1,
    "mcv_fl": 98.0, "mch_pg": 23.2, "mchc_g_dl": 23.6,
    "rdw_percent": 15.1, "wbc_10e9_l": 8.0, "platelets_10e9_l": 220.0,
    "neutrophils_percent": 60.0, "lymphocytes_percent": 30.0,
    "monocytes_percent": 6.0, "eosinophils_percent": 3.0, "basophils_percent": 1.0,
    "anc_10e9_l": 4.8, "alc_10e9_l": 2.4, "amc_10e9_l": 0.48,
    "aec_10e9_l": 0.24, "abc_10e9_l": 0.08,
    "retic_percent": 2.0, "retic_abs_10e9_l": 62.0,
    "pt_seconds": 12.5, "inr": 1.0, "aptt_seconds": 30.0, "fibrinogen_g_l": 3.0,
    "hba_percent": 96.5, "hba2_percent": 2.5, "hbf_percent": 1.0,
    "hbe_percent": 0.0, "ferritin_ng_ml": 50.0,
}


def demo_rows(panel: str) -> list[dict[str, Any]]:
    """Fresh fictional observations; values are not suggested clinical limits."""
    return [
        {"code": code, "result": _DEMO_VALUES[code], "unit": TEST_CATALOG[code]["unit"],
         "previous_result": 12.8 if code == "hb_g_dl" else None,
         "previous_days": 7.0 if code == "hb_g_dl" else None}
        for code in PANEL_FIELDS[panel]
    ]


def _snapshot(value: Any) -> Any:
    """Keep raw content JSON-safe; invalid nonfinite/type values remain explicit."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        numeric = float(value)
        return numeric if isfinite(numeric) else {"nonfinite": repr(numeric)}
    if isinstance(value, Mapping):
        return {str(key): _snapshot(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_snapshot(item) for item in value]
    return {"python_type": type(value).__name__, "repr": repr(value)}


def report_input_snapshot(value: Any) -> Any:
    """Return a detached JSON-safe snapshot for binding exports to evaluated inputs."""
    return _snapshot(value)


def _missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    try:
        numeric = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    return numeric if isfinite(numeric) else None


def validate_report(
    rows: Any, *, panel: str, specimen_flags: Sequence[str] = (),
    tolerances: Mapping[str, Any] | None = None, previous_comparable: bool = False,
) -> dict[str, Any]:
    """Validate synthetic rows without releasing or modifying reported results.

    Row fields: code/result/unit required; previous_result/previous_days optional.
    None or blank is missing; booleans, numeric strings and nonfinite numbers are
    invalid. Current and previous values must be nonnegative; actual fractions
    must be <=100%. RDW-CV is a coefficient of variation, not a bounded fraction.
    Every present row needs its exact catalog unit, even if its result is missing.

    Tolerances are finite nonnegative numbers, inclusive at the boundary. index_abs
    maps mcv_fl/mch_pg/mchc_g_dl to absolute tolerances. Other supported keys are
    diff_sum_abs, absolute_count_abs, delta_hb_abs, delta_hb_percent, delta_max_days,
    rule_three_abs and rule_three_applicable (bool). A delta signal occurs if any
    configured threshold is exceeded, only with confirmed comparable prior data
    within delta_max_days. Differential sum assumes the complete, mutually
    exclusive five-category synthetic panel, with no separately counted IG/NRBC.
    No reference intervals, critical limits or clinical diagnoses are inferred.
    """
    findings: list[dict[str, Any]] = []
    derived: dict[str, Any] = {}
    validation_context = report_input_snapshot({
        "specimen_flags": specimen_flags,
        "tolerances": tolerances if tolerances is not None else {},
        "previous_comparable": previous_comparable,
    })

    def finding(rule: str, status: str, message: str, **evidence: Any) -> None:
        findings.append({"rule_id": rule, "status": status, "message": message,
                         "evidence": _snapshot(evidence)})

    finding("POLICY_NOT_APPROVED", "HOLD", "ต้นแบบข้อมูลสังเคราะห์: ยังไม่มีนโยบายที่อนุมัติ จึงห้ามปล่อยผลอัตโนมัติ")
    finding("CLINICAL_POLICY", "NOT_EVALUATED", "ไม่ได้ประเมินช่วงอ้างอิง ค่าวิกฤต หรือกฎเฉพาะเครื่องมือ ต้องใช้ SOP ที่ตรวจสอบและอนุมัติของห้องปฏิบัติการ")
    required = PANEL_FIELDS.get(panel) if isinstance(panel, str) else None
    if required is None:
        finding("PANEL_SCHEMA", "REJECT", "ไม่รู้จักกลุ่มการตรวจ", panel=panel)
        required = ()
    if not isinstance(rows, (list, tuple)):
        finding("ROW_SCHEMA", "REJECT", "ข้อมูลผลตรวจต้องเป็นรายการของแถว")
        source_rows: Sequence[Any] = ()
    else:
        source_rows = rows

    accepted: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    duplicate: set[str] = set()
    fields = {"code", "result", "unit", "previous_result", "previous_days"}
    for position, row in enumerate(source_rows):
        if not isinstance(row, Mapping) or not {"code", "result", "unit"}.issubset(row) or set(row) - fields:
            finding("ROW_SCHEMA", "REJECT", "โครงสร้างแถวไม่ถูกต้อง", row=position)
            continue
        code = row["code"]
        if not isinstance(code, str) or code not in TEST_CATALOG:
            finding("UNKNOWN_TEST", "REJECT", "รหัสผลตรวจไม่อยู่ในพจนานุกรม", row=position, code=code)
            continue
        if code in seen:
            duplicate.add(code)
            accepted.pop(code, None)
            finding("DUPLICATE_TEST", "REJECT", "พบรหัสผลตรวจซ้ำ ต้องกักข้อมูลเพื่อตรวจสอบ", row=position, code=code)
            continue
        seen.add(code)
        valid = True
        if not isinstance(row["unit"], str) or row["unit"] != TEST_CATALOG[code]["unit"]:
            finding("UNIT_MISMATCH", "REJECT", "หน่วยไม่ตรง UCUM ที่กำหนด ระบบไม่แปลงหน่วยหรือคาดเดา", row=position, code=code, received=row["unit"], expected=TEST_CATALOG[code]["unit"])
            valid = False
        normalized: dict[str, Any] = {"code": code, "unit": TEST_CATALOG[code]["unit"]}
        for field in ("result", "previous_result", "previous_days"):
            value = row.get(field)
            if _missing(value):
                normalized[field] = None
                continue
            numeric = _number(value)
            if numeric is None or numeric < 0 or (field != "previous_days" and code in _FRACTION_FIELDS and numeric > 100):
                finding("INVALID_VALUE", "REJECT", "ค่าต้องเป็นตัวเลขจำกัดที่ไม่ติดลบ และค่าที่เป็นสัดส่วนจริงต้องไม่เกิน 100% (ไม่รวม RDW-CV)", row=position, code=code, field=field, received=value)
                valid = False
            normalized[field] = numeric
        if valid:
            accepted[code] = normalized
    for code in duplicate:
        accepted.pop(code, None)
    values = {code: row["result"] for code, row in accepted.items() if row["result"] is not None}
    missing = [code for code in required if code not in values]
    if missing:
        finding("REQUIRED_TESTS", "HOLD", "ผลตรวจที่ต้องใช้ยังไม่ครบหรือใช้ประเมินไม่ได้", missing=missing)
    else:
        finding("REQUIRED_TESTS", "PASS", "มีค่าผลตรวจที่จำเป็นครบตามแผงข้อมูลสังเคราะห์")
    if not any(item["status"] == "REJECT" for item in findings):
        finding("TECHNICAL_INPUT", "PASS", "โครงสร้างและหน่วยของข้อมูลที่ให้มาผ่านการตรวจทางเทคนิค ไม่ใช่การรับรองผลทางคลินิก")

    if isinstance(specimen_flags, (str, bytes)) or not isinstance(specimen_flags, Sequence):
        finding("SPECIMEN_FLAG_SCHEMA", "REJECT", "รายการข้อสังเกตสิ่งส่งตรวจมีโครงสร้างไม่ถูกต้อง")
    else:
        for flag in specimen_flags:
            if not isinstance(flag, str) or not flag.strip():
                finding("SPECIMEN_FLAG_SCHEMA", "REJECT", "ข้อสังเกตสิ่งส่งตรวจต้องเป็นข้อความที่ไม่ว่าง", flag=flag)
            else:
                finding("SPECIMEN_REVIEW", "HOLD", "ต้องให้ผู้รับผิดชอบพิจารณาข้อสังเกตสิ่งส่งตรวจตาม SOP ไม่ใช่คำสั่งทิ้งตัวอย่าง", flag=flag)

    config: dict[str, Any] = {}
    numeric_keys = {"diff_sum_abs", "absolute_count_abs", "delta_hb_abs", "delta_hb_percent", "delta_max_days", "rule_three_abs"}
    if tolerances is not None and not isinstance(tolerances, Mapping):
        finding("CONFIG_INVALID", "HOLD", "การตั้งค่าความคลาดเคลื่อนต้องเป็น mapping")
    elif tolerances is not None:
        for key, value in tolerances.items():
            if key in numeric_keys:
                numeric = _number(value)
                if numeric is None or numeric < 0:
                    finding("CONFIG_INVALID", "HOLD", "ค่าความคลาดเคลื่อนหรือกรอบเวลาต้องเป็นตัวเลขจำกัดที่ไม่ติดลบ", key=key, received=value)
                else:
                    config[key] = numeric
            elif key == "rule_three_applicable" and type(value) is bool:
                config[key] = value
            elif key == "index_abs" and isinstance(value, Mapping):
                config[key] = {}
                for index, limit in value.items():
                    numeric = _number(limit)
                    if index not in ("mcv_fl", "mch_pg", "mchc_g_dl") or numeric is None or numeric < 0:
                        finding("CONFIG_INVALID", "HOLD", "ค่าความคลาดเคลื่อนดัชนีเม็ดเลือดแดงไม่ถูกต้อง", key=index, received=limit)
                    else:
                        config[key][index] = numeric
            else:
                finding("CONFIG_INVALID", "HOLD", "พบการตั้งค่าที่ไม่รองรับหรือชนิดข้อมูลไม่ถูกต้อง", key=key, received=value)
    if type(previous_comparable) is not bool:
        finding("CONFIG_INVALID", "HOLD", "สถานะการเปรียบเทียบผลเดิมต้องเป็น boolean")
        previous_comparable = False

    def compare(rule: str, observed: float | None, expected: float | None, limit: float | None, **evidence: Any) -> None:
        if observed is None or expected is None or limit is None:
            finding(rule, "NOT_EVALUATED", "ข้อมูลหรือค่าความคลาดเคลื่อนที่กำหนดยังไม่ครบ", observed=observed, calculated=expected, tolerance=limit, **evidence)
            return
        residual = abs(observed - expected)
        # Avoid binary floating-point noise at a configured inclusive boundary.
        arithmetic_slack = 4 * max(ulp(observed), ulp(expected), ulp(limit))
        exceeds = residual > limit and residual - limit > arithmetic_slack
        finding(rule, "HOLD" if exceeds else "PASS", "ผลต่างเกินเกณฑ์สาธิต ต้องทบทวน" if exceeds else "ผ่านการเปรียบเทียบทางคณิตศาสตร์ตามเกณฑ์สาธิต", observed=observed, calculated=expected, absolute_difference=residual, tolerance=limit, **evidence)

    if set(values) & set(_CBC) or set(required) & set(_CBC):
        equations = {"mcv_fl": ("hct_percent", "rbc_10e12_l", 10.0),
                     "mch_pg": ("hb_g_dl", "rbc_10e12_l", 10.0),
                     "mchc_g_dl": ("hb_g_dl", "hct_percent", 100.0)}
        for index, (numerator, denominator, scale) in equations.items():
            calculated = None
            if numerator in values and denominator in values and values[denominator] > 0:
                result = values[numerator] / values[denominator] * scale
                if isfinite(result):
                    calculated = derived[index] = result
            compare("INDEX_" + index.upper(), values.get(index), calculated, config.get("index_abs", {}).get(index), numerator=numerator, denominator=denominator)

        if "hb_g_dl" in values:
            prior = accepted["hb_g_dl"]["previous_result"]
            days = accepted["hb_g_dl"]["previous_days"]
            if prior is not None:
                delta = values["hb_g_dl"] - prior
                derived["delta_hb_g_dl"] = delta
                derived["previous_days"] = days
                if prior > 0:
                    percent = delta / prior * 100.0
                    if isfinite(percent):
                        derived["delta_hb_percent"] = percent
            eligible = (prior is not None and days is not None and previous_comparable
                        and "delta_max_days" in config and days <= config["delta_max_days"])
            configured_delta = [key for key in ("delta_hb_abs", "delta_hb_percent") if key in config]
            if not eligible or not configured_delta:
                finding("DELTA_HB", "NOT_EVALUATED", "ต้องมีผลเดิมที่ยืนยันว่าเปรียบเทียบได้ กรอบเวลา และเกณฑ์ delta ที่กำหนด", comparable=previous_comparable, previous_result=prior, previous_days=days, max_days=config.get("delta_max_days"))
            else:
                for key, derived_key in (("delta_hb_abs", "delta_hb_g_dl"), ("delta_hb_percent", "delta_hb_percent")):
                    change = derived.get(derived_key)
                    compare(key.upper(), abs(change) if change is not None else None, 0.0, config.get(key), previous_days=days)
        else:
            finding("DELTA_HB", "NOT_EVALUATED", "ไม่มีค่า Hb ปัจจุบันที่ใช้ประเมินได้")

        if "hb_g_dl" in values and "hct_percent" in values:
            estimate = values["hb_g_dl"] * 3.0
            if isfinite(estimate):
                derived["rule_three_hct_percent"] = estimate
                derived["rule_three_difference_percent"] = values["hct_percent"] - estimate
        applicability = config.get("rule_three_applicable")
        if applicability is False:
            finding("RULE_OF_THREE", "NOT_APPLICABLE", "ปิดการตรวจ rule of three ตามบริบทที่กำหนด ไม่ใช่การยืนยันว่าผลปกติ")
        elif applicability is not True:
            finding("RULE_OF_THREE", "NOT_EVALUATED", "ยังไม่ยืนยันบริบทที่เหมาะสมของ rule of three; ไม่ใช้เป็นกฎสากลหรือการวินิจฉัย")
        else:
            compare("RULE_OF_THREE", values.get("hct_percent"), derived.get("rule_three_hct_percent"), config.get("rule_three_abs"), context="Explicit demonstration applicability; requires locally verified method/SOP")

    if set(required) & set(_DIFF_PAIRS) or set(values) & set(_DIFF_PAIRS):
        total = sum(values[code] for code in _DIFF_PAIRS) if all(code in values for code in _DIFF_PAIRS) else None
        if total is not None:
            derived["differential_sum_percent"] = total
        compare("DIFFERENTIAL_SUM", total, 100.0, config.get("diff_sum_abs"), categories=list(_DIFF_PAIRS), scope="Five mutually exclusive synthetic categories; no separate IG/NRBC")
        absolute: dict[str, float] = {}
        for percent_code, absolute_code in _DIFF_PAIRS.items():
            if "wbc_10e9_l" in values and percent_code in values:
                calculated = values["wbc_10e9_l"] * (values[percent_code] / 100.0)
                if isfinite(calculated):
                    absolute[absolute_code] = calculated
            compare("ABSOLUTE_" + absolute_code.upper(), values.get(absolute_code), absolute.get(absolute_code), config.get("absolute_count_abs"), unit="10*9/L")
        derived["absolute_counts_10e9_l"] = absolute

    if "retic_percent" in required or "retic_percent" in values or "retic_abs_10e9_l" in values:
        calculated = None
        if "rbc_10e12_l" in values and "retic_percent" in values:
            result = values["rbc_10e12_l"] * values["retic_percent"] * 10.0
            if isfinite(result):
                calculated = derived["retic_abs_10e9_l"] = result
        compare("ABSOLUTE_RETIC", values.get("retic_abs_10e9_l"), calculated, config.get("absolute_count_abs"), unit="10*9/L")

    return {"panel": panel, "decision": "REJECT" if any(item["status"] == "REJECT" for item in findings) else "HOLD",
            "release_eligible": False, "findings": findings, "derived": derived,
            "raw_rows": report_input_snapshot(rows), "normalized_rows": list(accepted.values()),
            "validation_context": validation_context,
            "build_provenance": capture_build_provenance()}
