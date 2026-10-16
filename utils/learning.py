"""Reviewed learning content and isolated, in-memory demonstration inputs."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from logic.cbc import CBCResult, analyze_cbc
from logic.hematology import analyze_domain
from logic.hematology_common import DOMAIN_IDS, ReviewResult, load_domain_rules
from utils.domain_reporting import display_input
from utils.module_registry import load_modules

LEARNING_PATH = Path(__file__).resolve().parents[1] / "data" / "learning_modules.json"


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def load_learning_modules(path: Path = LEARNING_PATH) -> dict[str, dict[str, Any]]:
    """Reject incomplete catalog coverage and malformed source links."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if payload["schema_version"] != 1 or not _text(payload["reviewed_on"]):
            raise ValueError("Unsupported learning catalog")
        expected = {module.id for module in load_modules()}
        modules: dict[str, dict[str, Any]] = {}
        for item in payload["modules"]:
            module_id = item["id"]
            if module_id not in expected or module_id in modules:
                raise ValueError("Unknown or repeated module")
            if not all(_text(item[key]) for key in ("intro", "example_question")):
                raise ValueError("Missing description")
            for key, count in (("focus", 3), ("limitations", 2)):
                values = item[key]
                if not isinstance(values, list) or len(values) != count or not all(map(_text, values)):
                    raise ValueError("Incomplete learning points")
            if not isinstance(item["pathway"], list) or len(item["pathway"]) != 3:
                raise ValueError("Incomplete pathway")
            for step in item["pathway"]:
                if not all(_text(step[key]) for key in ("title", "body")):
                    raise ValueError("Empty pathway step")
            if not isinstance(item["sources"], list) or not item["sources"]:
                raise ValueError("Missing sources")
            for source in item["sources"]:
                if not _text(source["title"]) or not _text(source["url"]):
                    raise ValueError("Invalid source")
                url = urlsplit(source["url"])
                if url.scheme != "https" or not url.hostname or url.username or url.password:
                    raise ValueError("Invalid source URL")
            modules[module_id] = {**item, "reviewed_on": payload["reviewed_on"]}
        if set(modules) != expected:
            raise ValueError("Missing module overview")
        return modules
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, AttributeError):
        raise ValueError("ข้อมูลการเรียนรู้ไม่ครบหรือรูปแบบไม่ถูกต้อง กรุณาทบทวน data/learning_modules.json") from None


@dataclass
class LearningDemo:
    name: str
    input_rows: list[dict[str, str]]
    result: CBCResult | ReviewResult


def build_learning_demo(module_id: str) -> LearningDemo:
    """Use pure clinical engines without importing UI or touching session state.

    Thalassemia keeps its existing spectrum and six-case Sankey demonstrations.
    The other modules use a fresh copy of their existing synthetic example.
    """
    if module_id == "cbc_anemia":
        values = {"age": 35.0, "sex": "Female", "pregnant": False, "hb_g_dl": 10.8, "mcv_fl": 74.0}
        rows = [
            {"รายการ": "อายุ (ปี)", "ข้อมูลสมมติ": "35"},
            {"รายการ": "เพศที่ใช้เลือกเกณฑ์", "ข้อมูลสมมติ": "หญิง"},
            {"รายการ": "สถานะการตั้งครรภ์", "ข้อมูลสมมติ": "ไม่ตั้งครรภ์"},
            {"รายการ": "Hb (g/dL)", "ข้อมูลสมมติ": "10.8"},
            {"รายการ": "MCV (fL)", "ข้อมูลสมมติ": "74"},
        ]
        return LearningDemo("ผู้ใหญ่ที่มี Hb และ MCV ต่ำในข้อมูลสมมติ", rows, analyze_cbc(values))
    if module_id not in DOMAIN_IDS:
        raise ValueError("ไม่พบตัวอย่างการเรียนรู้ของกลุ่มงานนี้")
    rules = load_domain_rules(module_id)
    if not rules["examples"]:
        raise ValueError("กลุ่มงานนี้ยังไม่มีข้อมูลสมมติสำหรับสาธิต")
    example = rules["examples"][0]
    values = deepcopy(example["data"])
    result = analyze_domain(module_id, values)
    rows = [
        {"รายการ": result.field_labels[key], "ข้อมูลสมมติ": str(display_input(result, key, value))}
        for key, value in result.normalized.items() if key in values
    ]
    return LearningDemo(example["name"], rows, result)
