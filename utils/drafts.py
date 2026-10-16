"""Explicit, versioned synthetic-work drafts; never serialize arbitrary sessions."""
from __future__ import annotations

from copy import deepcopy
import json
from math import isfinite
from typing import Any, Mapping, MutableMapping

from logic.reporting import PANEL_FIELDS, TEST_CATALOG, demo_rows
from utils.module_registry import load_modules
from utils.report_layout import ReportTemplate


MAX_DRAFT_BYTES = 256 * 1024
SPECIMEN_FLAGS = ("clotted", "hemolyzed", "insufficient_volume", "other")
INDEX_CODES = ("mcv_fl", "mch_pg", "mchc_g_dl")
CONTROL_KEYS = {
    "panel": "reporting_panel", "language": "reporting_language",
    "institution": "reporting_institution", "version": "reporting_version",
    "margin_mm": "reporting_margin", "show_previous": "reporting_show_previous",
    "show_morphology": "reporting_show_morphology", "show_comments": "reporting_show_comments",
    "show_trend": "reporting_show_trend", "specimen_flags": "reporting_specimen_flags",
    "previous_comparable": "reporting_previous_comparable", "use_tolerances": "reporting_use_tolerances",
}
DEFAULT_CONTROLS = {
    "panel": "cbc", "language": "bilingual",
    "institution": "ห้องปฏิบัติการสมมติ / Synthetic laboratory", "version": "0.1",
    "margin_mm": 15, "show_previous": True, "show_morphology": False,
    "show_comments": True, "show_trend": False, "specimen_flags": [],
    "previous_comparable": False, "use_tolerances": False,
    "index_tolerances": {code: 0.5 for code in INDEX_CODES},
}
_TOP_KEYS = {"schema_version", "artifact_type", "data_policy", "document_status", "release_eligible", "reporting", "learning"}
_ROW_KEYS = {"code", "result", "unit", "previous_result", "previous_days"}


def _keys(value: Any, expected: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{label}: โครงสร้างไม่ตรงกับร่างงานสมมติที่รองรับ")


def _number(value: Any, label: str, *, nullable: bool = True, nonnegative: bool = False) -> None:
    if value is None and nullable:
        return
    if type(value) not in (int, float):
        raise ValueError(f"{label}: ต้องเป็นตัวเลขหรือค่าว่าง ไม่รับ boolean/ข้อความ")
    try:
        finite = isfinite(value)
    except OverflowError:
        finite = False
    if not finite or (nonnegative and value < 0):
        raise ValueError(f"{label}: ค่าตัวเลขไม่ถูกต้องหรือไม่เป็นจำนวนจำกัด")


def validate_synthetic_draft(payload: Any) -> dict[str, Any]:
    """Accept only simulation inputs; results and provenance are re-evaluated."""
    _keys(payload, _TOP_KEYS, "draft")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise ValueError("รุ่นร่างงานไม่รองรับ")
    if (payload["artifact_type"] != "synthetic_work_draft" or payload["data_policy"] != "synthetic_only"
            or payload["document_status"] != "DRAFT" or payload["release_eligible"] is not False):
        raise ValueError("รับเฉพาะร่างงาน SYNTHETIC / DRAFT ที่ไม่สามารถอนุมัติผลได้")
    reporting = payload["reporting"]
    _keys(reporting, {"controls", "rows_by_panel"}, "reporting")
    controls = reporting["controls"]
    _keys(controls, set(DEFAULT_CONTROLS), "controls")
    template_fields = {key: controls[key] for key in (
        "panel", "language", "institution", "version", "margin_mm", "show_previous",
        "show_morphology", "show_comments", "show_trend",
    )}
    # Type guards precede membership checks in ReportTemplate.
    if not isinstance(controls["panel"], str) or not isinstance(controls["language"], str):
        raise ValueError("panel/language ต้องเป็นข้อความที่อยู่ในรายการ")
    ReportTemplate(**template_fields)
    for key in ("show_previous", "show_morphology", "show_comments", "show_trend", "previous_comparable", "use_tolerances"):
        if type(controls[key]) is not bool:
            raise ValueError(f"{key}: ต้องเป็น boolean")
    flags = controls["specimen_flags"]
    if not isinstance(flags, list) or any(not isinstance(flag, str) or flag not in SPECIMEN_FLAGS for flag in flags) or len(flags) != len(set(flags)):
        raise ValueError("รายการปัญหาตัวอย่างสมมติไม่ถูกต้อง")
    _keys(controls["index_tolerances"], set(INDEX_CODES), "index_tolerances")
    for code, value in controls["index_tolerances"].items():
        _number(value, code, nullable=False, nonnegative=True)
    panels = reporting["rows_by_panel"]
    if not isinstance(panels, dict) or any(panel not in PANEL_FIELDS for panel in panels) or controls["panel"] not in panels:
        raise ValueError("ต้องมีข้อมูลของ panel ปัจจุบันและใช้ชื่อ panel ที่รองรับเท่านั้น")
    for panel, rows in panels.items():
        if not isinstance(rows, list) or len(rows) != len(PANEL_FIELDS[panel]):
            raise ValueError(f"{panel}: จำนวนแถวไม่ตรงกับชุดรายการตรวจ")
        for expected_code, row in zip(PANEL_FIELDS[panel], rows):
            _keys(row, _ROW_KEYS, panel)
            if row["code"] != expected_code or row["unit"] != TEST_CATALOG[expected_code]["unit"]:
                raise ValueError(f"{panel}: รหัส ลำดับ หรือหน่วยรายการตรวจไม่ตรงกับพจนานุกรม")
            for field in ("result", "previous_result", "previous_days"):
                # Preserve finite invalid numerical drafts for correction, not release.
                _number(row[field], f"{panel}/{expected_code}/{field}")
    module_ids = {module.id for module in load_modules()}
    learning = payload["learning"]
    _keys(learning, {"module", "show_thal_demo", "enabled_demos"}, "learning")
    if not isinstance(learning["module"], str) or learning["module"] not in module_ids or type(learning["show_thal_demo"]) is not bool:
        raise ValueError("หัวข้อการเรียนรู้ไม่ถูกต้อง")
    enabled = learning["enabled_demos"]
    if not isinstance(enabled, list) or any(not isinstance(item, str) or item not in module_ids - {"thalassemia"} for item in enabled) or len(enabled) != len(set(enabled)):
        raise ValueError("รายการตัวอย่างบทเรียนไม่ถูกต้อง")
    return deepcopy(payload)


def capture_synthetic_draft(state: Mapping[str, Any]) -> dict[str, Any]:
    controls = {name: deepcopy(state.get(key, DEFAULT_CONTROLS[name])) for name, key in CONTROL_KEYS.items()}
    if not isinstance(controls["version"], str):
        raise ValueError("รุ่นแม่แบบต้องเป็นข้อความ")
    controls["version"] = controls["version"].strip() or "0.1"
    controls["index_tolerances"] = {code: state.get(f"reporting_tolerance_{code}", 0.5) for code in INDEX_CODES}
    rows = {panel: deepcopy(state[f"reporting_rows_{panel}"]) for panel in PANEL_FIELDS if f"reporting_rows_{panel}" in state}
    if not isinstance(controls["panel"], str) or controls["panel"] not in PANEL_FIELDS:
        raise ValueError("ชื่อ panel ไม่ถูกต้อง")
    rows.setdefault(controls["panel"], demo_rows(controls["panel"]))
    return validate_synthetic_draft({
        "schema_version": 1, "artifact_type": "synthetic_work_draft", "data_policy": "synthetic_only",
        "document_status": "DRAFT", "release_eligible": False,
        "reporting": {"controls": controls, "rows_by_panel": rows},
        "learning": {
            "module": state.get("platform_learning_module", "thalassemia"),
            "show_thal_demo": state.get("platform_show_thal_demo", False),
            "enabled_demos": [module.id for module in load_modules() if module.id != "thalassemia"
                              and state.get(f"platform_learning_demo_{module.id}", False)],
        },
    })


def synthetic_draft_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(validate_synthetic_draft(payload), ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8")


def read_synthetic_draft(data: bytes) -> dict[str, Any]:
    if not isinstance(data, bytes) or len(data) > MAX_DRAFT_BYTES:
        raise ValueError("ไฟล์ร่างงานต้องไม่เกิน 256 KiB")

    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"JSON มีชื่อฟิลด์ซ้ำ: {key}")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError(f"JSON ไม่รองรับค่าตัวเลข {value}")

    try:
        payload = json.loads(data.decode("utf-8-sig"), object_pairs_hook=unique_pairs, parse_constant=reject_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("ไม่สามารถอ่านไฟล์ JSON ร่างงานได้") from exc
    return validate_synthetic_draft(payload)


def restore_synthetic_draft(state: MutableMapping[str, Any], payload: Mapping[str, Any]) -> None:
    """Validate completely before changing only allowlisted simulation state."""
    draft = validate_synthetic_draft(payload)
    controls = draft["reporting"]["controls"]
    old_epoch = state.get("reporting_editor_epoch", 0)
    epoch = old_epoch + 1 if type(old_epoch) is int else 1
    for key in list(state):
        if key.startswith(("reporting_editor_", "reporting_rows_")):
            del state[key]
    state["reporting_editor_epoch"] = epoch
    for name, key in CONTROL_KEYS.items():
        state[key] = deepcopy(controls[name])
    for code, value in controls["index_tolerances"].items():
        state[f"reporting_tolerance_{code}"] = value
    for panel, rows in draft["reporting"]["rows_by_panel"].items():
        state[f"reporting_rows_{panel}"] = deepcopy(rows)
    learning = draft["learning"]
    state["platform_learning_module"] = learning["module"]
    state["platform_show_thal_demo"] = learning["show_thal_demo"]
    for module in load_modules():
        if module.id != "thalassemia":
            state[f"platform_learning_demo_{module.id}"] = module.id in learning["enabled_demos"]
