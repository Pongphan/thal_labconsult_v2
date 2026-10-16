"""Additive, conservative workflow labels derived from existing screening rules.

No clinical cutoff, score, or genotype is introduced here. Multiple findings are
retained. This presentation policy requires expert review before service use.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .validation import normalize_threshold_sex

POLICY_VERSION = "screening-workflow-draft-2026.10.15-1"
POLICY_HASH = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
SOURCES = [
    "https://arupconsult.com/content/thalassemias",
    "https://www.thalassaemia.org.cy/wp-content/uploads/2017/08/PreventionVol2_English.pdf",
]
# Rule IDs, rather than pattern text or arbitrary score cutoffs, drive grouping.
RULE_GROUPS = {
    "alpha_variant": "suspected_alpha",
    "beta_trait": "suspected_beta",
    "hbe_pattern": "suspected_hb_variant",
    "iron_deficiency": "iron_or_mixed",
    "combined_peak": "indeterminate",
    "high_fraction_review": "indeterminate",
    "micro_unresolved": "indeterminate",
    "of_screen": "indeterminate",
    "pediatric_review": "indeterminate",
}
GROUP_LABELS = {
    "invalid": "ข้อมูลไม่ผ่านการตรวจสอบ — ยังจัดกลุ่มไม่ได้",
    "suspected_alpha": "สงสัยกลุ่ม α-thalassemia / HbH / Hb Constant Spring — ต้องยืนยัน",
    "suspected_beta": "สงสัย β-thalassemia trait — ต้องทบทวนและยืนยันตามข้อบ่งชี้",
    "suspected_hb_variant": "สงสัย Hb E / ฮีโมโกลบินผิดปกติ — ยังไม่ยืนยันชนิด",
    "iron_or_mixed": "หลักฐานสนับสนุนขาดธาตุเหล็ก / อาจมีภาวะร่วม",
    "indeterminate": "ยังสรุปไม่ได้ / ต้องเติมข้อมูลหรือทดสอบเพิ่มเติม",
    "no_specific_pattern": "ยังไม่พบรูปแบบจำเพาะจากข้อมูลชุดนี้ — ไม่ได้ตัดพาหะธาลัสซีเมีย",
}
GROUP_ACTIONS = {
    "invalid": ("นักเทคนิคการแพทย์", "ตรวจข้อมูล หน่วย และบริบท แก้ไขแล้วประเมินใหม่ก่อนรายงานข้อสรุป"),
    "suspected_alpha": ("นักเทคนิคการแพทย์ร่วมกับแพทย์", "ทบทวน smear/Hb analysis; พิจารณา HBA1/HBA2 testing ตาม SOP และบริบท"),
    "suspected_beta": ("นักเทคนิคการแพทย์ร่วมกับแพทย์", "ยืนยันว่า HbA2 แยกวัดได้ ทบทวน iron status/วิธีตรวจ; พิจารณา HBB testing และการตรวจคู่ตามข้อบ่งชี้"),
    "suspected_hb_variant": ("นักเทคนิคการแพทย์ร่วมกับแพทย์", "ยืนยันชนิด Hb ด้วยวิธีเสริมหรือวิธีที่แยกพีคได้; พิจารณา molecular testing ตามข้อบ่งชี้"),
    "iron_or_mixed": ("แพทย์ร่วมกับห้องปฏิบัติการ", "ประเมิน iron status และการอักเสบ; วางแผนทบทวนผลตามบริบทโดยไม่ตัดภาวะธาลัสซีเมียร่วม"),
    "indeterminate": ("นักเทคนิคการแพทย์ร่วมกับแพทย์", "ทบทวนข้อมูลที่ขาด อายุ ประวัติรับเลือด และวิธีตรวจ; เลือก Hb typing หรือ DNA ตามข้อบ่งชี้และ SOP"),
    "no_specific_pattern": ("แพทย์ผู้ดูแล", "ทบทวนประวัติครอบครัว/คู่และข้อบ่งชี้ตรวจเพิ่มเติม; ไม่ออกข้อความยืนยันว่าไม่เป็นพาหะ"),
}


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def group_screening_findings(
    normalized: Mapping[str, Any], rule_ids: Sequence[str], errors: Sequence[str],
    *, severe: bool, anemia: bool | None, microcytosis: bool | None,
    hypochromia: bool | None,
) -> dict[str, Any]:
    """Group reviewed evidence without upgrading incomplete evidence to normal."""
    groups: list[str] = []
    reasons: list[str] = []
    if errors:
        groups = ["invalid"]
        reasons.append("ข้อมูลไม่ผ่าน validation; งดจัดกลุ่มโรคและยังคงข้อเตือนเร่งด่วนที่ประเมินได้แยกต่างหาก")
    else:
        groups = list(dict.fromkeys(RULE_GROUPS.get(rule_id, "indeterminate") for rule_id in rule_ids))
        required_numbers = ("age", "hb_g_dl", "mcv_fl", "mch_pg", "ferritin_ng_ml", "hba2_percent", "hbf_percent", "hbe_percent")
        missing = [key for key in required_numbers if not _finite(normalized.get(key))]
        if missing:
            reasons.append("ข้อมูลสำหรับทบทวนภาพรวมยังไม่ครบ: " + ", ".join(missing))
        sex = normalize_threshold_sex(normalized.get("sex"))
        if sex is None or (sex == "Female" and normalized.get("pregnant") is not False):
            reasons.append("ต้องทบทวนบริบทเพศที่ใช้เลือกเกณฑ์และสถานะการตั้งครรภ์")
        if normalized.get("transfusion_recent") is not False:
            reasons.append("มีประวัติรับเลือดล่าสุดหรือยังไม่ทราบประวัติ ต้องทบทวนการแปลผล Hb")
        if str(normalized.get("hb_method", "")).upper() not in {"HPLC", "CZE"}:
            reasons.append("ยังไม่ระบุวิธี Hb analysis ที่รองรับ")
        if any(normalized.get(key) not in {"Positive", "Negative"} for key in ("oft", "dcip")):
            reasons.append("ผลคัดกรอง OF/DCIP ยังไม่ครบหรือไม่ชัดเจน; ไม่ถือเป็นผลลบ")
        if any(value is None for value in (anemia, microcytosis, hypochromia)):
            reasons.append("ยังประเมินเกณฑ์ CBC ตามบริบทได้ไม่ครบ")
        if normalized.get("family_history") is not False:
            reasons.append("ต้องทบทวนประวัติครอบครัวหรือคู่เพิ่มเติม")
        if not groups and any(value is True for value in (anemia, microcytosis, hypochromia)):
            reasons.append("พบข้อสังเกต CBC ที่ยังไม่มีรูปแบบจำเพาะรองรับ")
        if reasons and "indeterminate" not in groups:
            groups.append("indeterminate")
        if not groups:
            groups = ["no_specific_pattern"]
    actions = [{"owner": GROUP_ACTIONS[code][0], "action": GROUP_ACTIONS[code][1]} for code in groups]
    if severe:
        actions.insert(0, {"owner": "นักเทคนิคการแพทย์ / แพทย์ผู้ดูแล", "action": "แจ้งและทบทวน Hb ต่ำเร่งด่วนตาม SOP โดยไม่รอการตรวจยืนยันธาลัสซีเมีย"})
    labels = [GROUP_LABELS[code] for code in groups]
    return {
        "policy_version": POLICY_VERSION, "policy_hash": POLICY_HASH,
        "expert_review_status": "pending", "group_codes": groups, "group_labels": labels,
        "evidence_rule_ids": list(rule_ids), "uncertainty_reasons": reasons,
        "urgent_review": bool(severe), "next_actions": actions,
        "clinician_summary": "; ".join(labels) + ". ผลสนับสนุนการทบทวน ไม่ยืนยันโรคหรือจีโนไทป์",
        "patient_summary": (
            "ข้อมูลยังต้องแก้ไขหรือทบทวนก่อนอธิบายผล กรุณารับคำอธิบายจากผู้ดูแล"
            if errors else "ผลชุดนี้ยังไม่ยืนยันหรือปฏิเสธการเป็นพาหะ ผู้ดูแลจะอธิบายผลและพิจารณาว่าต้องตรวจเพิ่มเติมหรือไม่"
        ),
        "patient_release_status": "draft_requires_professional_review",
        "sources": list(SOURCES),
    }
