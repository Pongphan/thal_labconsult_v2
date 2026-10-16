"""Thai reports generated in memory from the same result used by the UI."""
from __future__ import annotations

import csv
import io
import json
import math
from dataclasses import asdict, is_dataclass
from typing import Any

DISCLAIMER = (
    "เครื่องมือนี้ใช้สนับสนุนการคัดกรองธาลัสซีเมีย ไม่ใช่การวินิจฉัยโรค "
    "ผลและจีโนไทป์ที่สงสัยต้องได้รับการทบทวนโดยผู้ประกอบวิชาชีพ "
    "และตรวจยืนยันตามแนวทางของห้องปฏิบัติการก่อนนำไปใช้ตัดสินใจทางคลินิก"
)
RISK_LABELS = {
    "Critical review": "ต้องทบทวนเร่งด่วน", "High": "ควรตรวจยืนยัน",
    "Moderate": "ควรประเมินเพิ่มเติม", "Low / inconclusive": "หลักฐานน้อยหรือยังสรุปไม่ได้",
    "Invalid / incomplete": "ข้อมูลไม่ถูกต้องหรือไม่เพียงพอ",
}
FIELD_LABELS = {
    "build_provenance": "รุ่นซอร์สโค้ดและสภาพแวดล้อมขณะประเมิน",
    "clinical_use_status": "สถานะการตรวจสอบความใช้ได้ทางคลินิก",
    "declared_units": "หน่วยที่ระบุยืนยันในข้อมูลนำเข้า",
    "clinical_grouping": "กลุ่มผลและขั้นตอนทบทวน (ร่างรอผู้เชี่ยวชาญ)",
    "clinical_group_labels": "กลุ่มผลที่ต้องทบทวน",
    "sample_id": "รหัสตัวอย่างสมมติ", "age": "อายุ (ปี)", "sex": "เพศ",
    "hb_g_dl": "Hb (g/dL)", "rbc_10e12_l": "RBC (10^12/L)", "hct_percent": "Hct (%)",
    "mcv_fl": "MCV (fL)", "mch_pg": "MCH (pg)", "mchc_g_dl": "MCHC (g/dL)",
    "rdw_percent": "RDW (%)", "retic_percent": "Reticulocyte (%)", "ferritin_ng_ml": "Ferritin (ng/mL)",
    "hba_percent": "HbA (%)", "hba2_percent": "HbA2 แยกวัด (%)", "hba2e_percent": "HbA2/E รวม (%)",
    "hbf_percent": "HbF (%)", "hbe_percent": "HbE (%)", "bart_percent": "Hb Bart's (%)",
    "hbh_percent": "HbH (%)", "hbcs_percent": "Hb CS (%)", "hb_method": "วิธีตรวจ Hb",
    "oft": "ผล OF/NESTROFT", "screening_method": "วิธีคัดกรอง", "oft_method": "วิธี OF/NESTROFT",
    "dcip": "ผล DCIP", "hbh_inclusion": "HbH inclusion", "transfusion_recent": "ได้รับเลือดเมื่อไม่นานมานี้",
    "pregnant": "ตั้งครรภ์", "smear_target_cells": "พบ target cells", "family_history": "ประวัติครอบครัวหรือคู่เป็นพาหะ",
    "top_pattern": "รูปแบบที่สงสัย", "consult_risk": "ระดับการทบทวน",
    "consult_score": "คะแนนสนับสนุนรูปแบบ (ไม่ใช่ความน่าจะเป็น)",
    "beta_trait_score": "คะแนนสนับสนุน beta-thalassemia", "alpha_trait_score": "คะแนนสนับสนุน alpha-thalassemia",
    "hbe_score": "คะแนนสนับสนุน HbE", "iron_deficiency_score": "คะแนนสนับสนุนภาวะขาดธาตุเหล็ก",
    "severe_anemia_flag": "แจ้งเตือน Hb ต่ำรุนแรง", "microcytosis": "MCV ต่ำกว่าเกณฑ์",
    "hypochromia": "MCH ต่ำกว่าเกณฑ์", "anemia": "Hb/Hct ต่ำกว่าเกณฑ์", "evidence": "เหตุผลประกอบ",
    "recommendations": "การตรวจยืนยันที่แนะนำ", "caveats": "ข้อจำกัด", "counseling": "ประเด็นให้คำปรึกษา",
    "suspected_genotypes": "จีโนไทป์ที่ควรพิจารณา (ยังไม่ยืนยัน)", "validation_errors": "ข้อผิดพลาดของข้อมูล",
    "validation_warnings": "ข้อควรทบทวนของข้อมูล", "confidence_note": "ความแน่นอนและขอบเขตการแปลผล",
    "rule_ids": "รหัสกฎที่ใช้", "ruleset_version": "เวอร์ชันกฎ", "thresholds_used": "เกณฑ์ที่ใช้จริง",
    "mentzer_index": "Mentzer index", "rdwi": "RDWI", "shine_lal_index": "Shine–Lal index",
    "england_fraser_index": "England–Fraser index", "green_king_index": "Green–King index",
    "calculated_mchc": "MCHC คำนวณ", "ruleset_hash": "ลายนิ้วมือไฟล์กฎ",
    "evaluated_at": "เวลาประเมิน (UTC+07:00)",
    "input_origin": "ที่มาของข้อมูล",
    "ee_assessment": "การประเมิน EE score", "partner_screening": "การคัดกรองคู่",
    "of_method": "วิธี OF/NESTROFT", "partner_oft": "ผล OF/NESTROFT ของคู่", "partner_dcip": "ผล DCIP ของคู่",
    "ee_applicable": "EE score อยู่ในขอบเขตที่ใช้ได้", "ee_score": "ค่า EE score",
    "ee_interpretation": "ข้อจำกัด EE score", "partner_status": "สถานะคัดกรองคู่",
    "partner_interpretation": "ข้อแนะนำการคัดกรองคู่",
    "partner_complete": "ข้อมูลคัดกรองคู่ครบถ้วน",
    "partner_recommendations": "ข้อเสนอแนะสำหรับคู่",
}
VALUE_LABELS = {
    "Positive": "บวก", "Negative": "ลบ", "Not performed": "ไม่ได้ตรวจ/ไม่ทราบ",
    "Indeterminate": "ก้ำกึ่ง", "Invalid": "ใช้แปลผลไม่ได้", "Male": "ชาย", "Female": "หญิง",
    "Not specified": "ไม่ระบุ", "Unknown": "ไม่ทราบ", **RISK_LABELS,
}
ORIGIN_LABELS = {
    "demo": "ข้อมูลสมมติ", "manual": "กรอกด้วยตนเอง", "csv": "นำเข้า CSV",
    "unknown": "ไม่ได้บันทึกที่มา",
}


def _clean(value: Any) -> Any:
    """Produce strict JSON values; missing numbers never become NaN tokens."""
    if is_dataclass(value):
        return _clean(asdict(value))
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if hasattr(value, "item"):
        return _clean(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _display(value: Any) -> str:
    value = _clean(value)
    if value is None:
        return "ไม่ได้ตรวจ/ไม่ทราบ"
    if isinstance(value, bool):
        return "ใช่" if value else "ไม่ใช่"
    if isinstance(value, (list, tuple)):
        return " | ".join(_display(v) for v in value) or "ไม่มี"
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    return VALUE_LABELS.get(str(value), str(value))


def _safe_cell(value: Any) -> str:
    text = _display(value)
    # Protect spreadsheet consumers from formulas in uploaded text cells.
    if isinstance(value, str) and text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


def csv_bytes(rows: list[list[Any]]) -> bytes:
    buffer = io.StringIO(newline="")
    csv.writer(buffer).writerows([[_safe_cell(cell) for cell in row] for row in rows])
    return buffer.getvalue().encode("utf-8-sig")


def _report_rows(result: Any) -> list[list[Any]]:
    rows: list[list[Any]] = [["รายการ", "ผล"], ["รายงาน", "รายงานสนับสนุนการคัดกรองธาลัสซีเมีย"],
                            [FIELD_LABELS["evaluated_at"], getattr(result, "evaluated_at", "ไม่ได้บันทึก")],
                            [FIELD_LABELS["input_origin"], ORIGIN_LABELS.get(getattr(result, "input_origin", "unknown"), "ไม่ได้บันทึกที่มา")],
                            ["สถานะ", "ร่างเพื่อทบทวน ยังไม่ลงนาม"],
                            ["คำชี้แจง", DISCLAIMER]]
    for key in ("sample_id", "top_pattern", "consult_risk", "consult_score", "severe_anemia_flag",
                "anemia", "microcytosis", "hypochromia", "suspected_genotypes",
                "confidence_note", "evidence", "recommendations", "counseling", "caveats",
                "validation_errors", "validation_warnings", "ruleset_version", "ruleset_hash", "rule_ids", "thresholds_used",
                "build_provenance", "clinical_use_status",
                "ee_assessment", "partner_screening", "beta_trait_score", "alpha_trait_score", "hbe_score", "iron_deficiency_score"):
        rows.append([FIELD_LABELS.get(key, key), getattr(result, key, "")])
    grouping = getattr(result, "clinical_grouping", {})
    if grouping:
        rows.extend([
            ["กลุ่มผลที่ต้องทบทวน", grouping.get("group_labels", [])],
            ["สรุปสำหรับผู้ประกอบวิชาชีพ", grouping.get("clinician_summary", "")],
            ["ร่างคำอธิบายผู้รับบริการ — ต้องให้ผู้ประกอบวิชาชีพทบทวน", grouping.get("patient_summary", "")],
            [FIELD_LABELS["clinical_grouping"], grouping],
        ])
    for group in ("normalized", "derived"):
        for key, value in getattr(result, group, {}).items():
            rows.append([FIELD_LABELS.get(key, key), value])
    return rows


def screening_report_csv(result: Any) -> bytes:
    return csv_bytes(_report_rows(result))


def batch_report_csv(results: Any) -> bytes:
    columns = [c for c in results.columns if c in FIELD_LABELS]
    rows: list[list[Any]] = [[FIELD_LABELS[c] for c in columns] + ["คำชี้แจง"]]
    rows.extend([[ORIGIN_LABELS.get(record.get(c), "ไม่ได้บันทึกที่มา") if c == "input_origin" else record.get(c)
                  for c in columns] + [DISCLAIMER] for record in results.to_dict("records")])
    return csv_bytes(rows)


def screening_report_markdown(result: Any) -> str:
    return "# รายงานสนับสนุนการคัดกรองธาลัสซีเมีย\n\n" + "\n\n".join(
        f"**{label}**: {_display(value)}" for label, value in _report_rows(result)[2:]
    )


def to_json_bytes(obj: Any) -> bytes:
    """Export a lossless snapshot; CSV flattening must not erase JSON structure."""
    if is_dataclass(obj) and hasattr(obj, "to_flat_dict"):
        # Keep existing top-level input/index aliases for readers of v1 reports.
        # The dataclass wins for native lists and dictionaries, including all
        # partner recommendations and the exact thresholds used in evaluation.
        obj = {
            **obj.to_flat_dict(), **asdict(obj),
            "report_schema_version": 2,
            "document_status": "ร่างเพื่อทบทวน ยังไม่ลงนาม",
            "disclaimer": DISCLAIMER,
        }
    elif hasattr(obj, "to_dict"):
        obj = obj.to_dict()
    return json.dumps(_clean(obj), ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
