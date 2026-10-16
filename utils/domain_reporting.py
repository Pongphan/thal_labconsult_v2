"""In-memory Thai reports for all hematology workspaces."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from typing import Any
from uuid import uuid4

from logic.hematology_common import ReviewResult, STATUS_LABELS
from utils.reporting import csv_bytes, to_json_bytes

RESULT_LABELS = {
    "build_provenance": "รุ่นซอร์สโค้ดและสภาพแวดล้อมขณะประเมิน",
    "clinical_use_status": "สถานะการตรวจสอบความใช้ได้ทางคลินิก",
    "module_id": "รหัสกลุ่มงาน", "title": "กลุ่มงาน", "scope": "ขอบเขตการใช้ผล",
    "ruleset_version": "รุ่นชุดกฎ", "ruleset_hash": "ลายนิ้วมือชุดกฎ",
    "disclaimer": "คำชี้แจง", "validation_errors": "ข้อผิดพลาดที่ต้องแก้ไข",
    "validation_warnings": "ข้อควรทบทวนของข้อมูล", "findings": "สิ่งที่พบ",
    "rationale": "เหตุผลประกอบ", "recommendations": "การตรวจและขั้นตอนที่แนะนำ",
    "counseling": "ประเด็นให้คำปรึกษา", "limitations": "ข้อจำกัด",
    "alerts": "ประเด็นที่ต้องประเมินโดยเร็ว", "rules_used": "รหัสกฎที่ใช้",
    "thresholds_used": "เกณฑ์และขอบเขตที่ใช้จริง", "calculated": "ค่าคำนวณและสรุปหลักฐาน",
    "status": "สถานะผลทบทวน", "sources": "เอกสารอ้างอิงของชุดกฎ",
    "confidence_note": "ความแน่นอนและขอบเขตข้อสรุป",
}


def report_metadata(
    module_id: str, origin: str = "manual", *, source_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "report_id": f"HEM-{uuid4().hex[:10].upper()}",
        "evaluated_at": datetime.now(timezone(timedelta(hours=7))).isoformat(timespec="seconds"),
        "document_status": "ร่างเพื่อทบทวน ยังไม่ลงนาม",
        "module_id": module_id, "input_origin": origin,
    }
    if source_snapshot is not None:
        metadata["source_snapshot"] = deepcopy(source_snapshot)
    return metadata


def display_input(result: ReviewResult, key: str, value: Any) -> Any:
    labels = result.value_labels.get(key, {})
    if value is None:
        return "ไม่ได้ตรวจ / ไม่ทราบ"
    if isinstance(value, list):
        return " | ".join(labels.get(str(item), str(item)) for item in value) or "ไม่ได้ระบุ"
    return labels.get(str(value), value)


def report_payload(result: ReviewResult, metadata: dict[str, Any]) -> dict[str, Any]:
    return {"report": deepcopy(metadata), "result": result.to_dict()}


def report_json(result: ReviewResult, metadata: dict[str, Any]) -> bytes:
    return to_json_bytes(report_payload(result, metadata))


def report_csv(result: ReviewResult, metadata: dict[str, Any]) -> bytes:
    rows: list[list[Any]] = [
        ["รายการ", "ผล"], ["รายงาน", result.title],
        ["รหัสการประเมินสมมติ", metadata["report_id"]],
        ["เวลาประเมิน (UTC+07:00)", metadata["evaluated_at"]],
        ["สถานะเอกสาร", metadata["document_status"]],
        ["ที่มาของข้อมูล", metadata["input_origin"]],
    ]
    if "source_snapshot" in metadata:
        rows.append(["ข้อมูลต้นทางที่คัดลอก (JSON)", metadata["source_snapshot"]])
    for key, label in RESULT_LABELS.items():
        value = getattr(result, key)
        rows.append([label, STATUS_LABELS[value] if key == "status" else value])
    rows.append(["ข้อมูลที่ใช้ประเมิน", "ค่าจากการส่งแบบฟอร์มครั้งนี้"])
    for key, value in result.normalized.items():
        rows.append([result.field_labels.get(key, key), display_input(result, key, value)])
    return csv_bytes(rows)


def batch_report_csv(results: list[ReviewResult], metadata: list[dict[str, Any]]) -> bytes:
    if len(results) != len(metadata):
        raise ValueError("จำนวนผลประเมินและข้อมูลกำกับรายงานต้องตรงกัน เพื่อไม่ให้รายงานขาดแถว")
    rows: list[list[Any]] = [[
        "ลำดับแถว", "รหัสสมมติ", "กลุ่มงาน", "สถานะ", "สิ่งที่พบ", "ข้อเร่งด่วน",
        "ข้อผิดพลาด", "ข้อควรทบทวน", "เหตุผล", "ข้อแนะนำ", "ข้อจำกัด", "คำชี้แจง",
        "รุ่นกฎ", "ลายนิ้วมือกฎ", "เกณฑ์ที่ใช้จริง", "ข้อมูลที่ใช้ (JSON)",
        "ค่าคำนวณและสรุปหลักฐาน", "ประเด็นให้คำปรึกษา", "รหัสกฎที่ใช้", "ขอบเขตการใช้ผล",
        "ความแน่นอนและข้อจำกัดข้อสรุป", "แหล่งอ้างอิง", "เวลาประเมิน (UTC+07:00)",
        "ที่มาของข้อมูล", "สถานะเอกสาร", "ชื่อและหน่วยข้อมูล", "ความหมายรหัสตัวเลือก",
        "ข้อมูลต้นทางที่คัดลอก (JSON)", "รุ่นซอร์สโค้ดและสภาพแวดล้อมขณะประเมิน (JSON)",
    ]]
    for index, (result, meta) in enumerate(zip(results, metadata, strict=True), start=1):
        rows.append([
            index, meta["report_id"], result.title, STATUS_LABELS[result.status], result.findings,
            result.alerts, result.validation_errors, result.validation_warnings, result.rationale,
            result.recommendations, result.limitations, result.disclaimer, result.ruleset_version,
            result.ruleset_hash, result.thresholds_used,
            json.dumps(result.normalized, ensure_ascii=False, allow_nan=False),
            result.calculated, result.counseling, result.rules_used, result.scope,
            result.confidence_note, result.sources, meta["evaluated_at"], meta["input_origin"],
            meta["document_status"], result.field_labels, result.value_labels,
            meta.get("source_snapshot"), result.build_provenance,
        ])
    return csv_bytes(rows)
