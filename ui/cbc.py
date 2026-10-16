"""Thai CBC presentation and in-memory reports; no clinical decision rules."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any
from uuid import uuid4

import pandas as pd
import streamlit as st

from ui.streamlit_compat import dataframe

from logic.cbc import CBC_DISCLAIMER, analyze_cbc
from thalab.styles import disclaimer, hero, inject_css, pastel_card, primary_action_type, production_footer, section, top_navigation
from utils.reporting import csv_bytes, to_json_bytes


INPUT_LABELS = {
    "age": "อายุ (ปีทศนิยม)",
    "sex": "เพศที่ใช้เลือกเกณฑ์อ้างอิง",
    "pregnant": "สถานะการตั้งครรภ์",
    "hb_g_dl": "Hb (g/dL)",
    "mcv_fl": "MCV (fL)",
    "rbc_10e12_l": "RBC (10¹²/L)",
    "hct_percent": "Hct (%)",
    "mch_pg": "MCH (pg)",
    "mchc_g_dl": "MCHC (g/dL)",
    "rdw_percent": "RDW (%)",
    "wbc_10e9_l": "WBC (10⁹/L)",
    "platelets_10e9_l": "เกล็ดเลือด (10⁹/L)",
    "ferritin_ng_ml": "Ferritin (ng/mL)",
    "retic_abs_10e9_l": "Absolute reticulocyte (10⁹/L)",
}
RESULT_LABELS = {
    "build_provenance": "รุ่นซอร์สโค้ดและสภาพแวดล้อมขณะประเมิน",
    "anemia_status": "การประเมิน Hb ตามขอบเขตที่รองรับ",
    "anemia_code": "รหัสผลประเมิน Hb",
    "pattern": "รูปแบบที่ระบบช่วยทบทวน",
    "pattern_code": "รหัสรูปแบบที่ระบบช่วยทบทวน",
    "support_status": "สถานะการสนับสนุนผล",
    "support_code": "รหัสสถานะการสนับสนุน",
    "scope": "ขอบเขตการใช้เกณฑ์",
    "scope_supported": "ข้อมูลอยู่ในขอบเขตเกณฑ์ที่รองรับ",
    "findings": "สิ่งที่พบจากข้อมูล",
    "rationale": "เหตุผลประกอบ",
    "recommended_tests": "การตรวจหรือข้อมูลเพิ่มเติมที่แนะนำ",
    "counseling": "ประเด็นให้คำปรึกษา",
    "limitations": "ข้อจำกัด",
    "validation_errors": "ข้อผิดพลาดของข้อมูล",
    "validation_warnings": "ข้อควรทบทวนของข้อมูล",
    "ruleset_version": "รุ่นชุดกฎ",
    "ruleset_hash": "ลายนิ้วมือชุดกฎ",
    "rules_used": "กฎที่ใช้",
    "thresholds_used": "เกณฑ์ที่ใช้จริง",
    "reference_intervals_used": "ช่วงอ้างอิงของห้องปฏิบัติการที่ใช้จริง",
    "severe_anemia_flag": "การแจ้งเตือน Hb ต่ำรุนแรงตามขอบเขตเกณฑ์ผู้ใหญ่",
    "low_hb_alert": "การแจ้งเตือน Hb ต่ำที่ต้องทบทวน",
    "disclaimer": "คำชี้แจง",
    "normalized": "ข้อมูลที่ใช้ประเมิน",
}
SEX_LABELS = {"Unknown": "ไม่ทราบ / ไม่ระบุ", "Female": "หญิง", "Male": "ชาย"}
PREGNANCY_LABELS = {"Unknown": "ไม่ทราบ / ไม่ระบุ", "No": "ไม่ตั้งครรภ์", "Yes": "ตั้งครรภ์"}
INTERVAL_FIELDS = ("wbc_10e9_l", "platelets_10e9_l", "rdw_percent", "ferritin_ng_ml", "retic_abs_10e9_l")
DEMO_VALUES = {"age": 35.0, "sex": "Female", "pregnant": False, "hb_g_dl": 10.8, "mcv_fl": 74.0}


def _clear_cbc_session() -> None:
    """Clear this module's state without touching the thalassemia workspace."""
    for key in list(st.session_state):
        if key.startswith("cbc_"):
            del st.session_state[key]


def _clear_result() -> None:
    for key in ("cbc_result", "cbc_report_metadata", "cbc_submitted_inputs"):
        st.session_state.pop(key, None)


def _change_source() -> None:
    for key in list(st.session_state):
        if key.startswith("cbc_") and key != "cbc_source":
            del st.session_state[key]


def _optional_number(field: str, defaults: dict[str, Any]) -> float | None:
    return st.number_input(
        INPUT_LABELS[field], value=defaults.get(field), step=0.01 if field == "age" else 0.1,
        format="%.3f" if field == "age" else "%.2f", key=f"cbc_input_{field}",
        placeholder="เว้นว่างเมื่อไม่มีข้อมูล", persist_state="session",
    )


def _cbc_form() -> tuple[bool, dict[str, Any], dict[str, dict[str, float | None]]]:
    with st.container(gap="xsmall"):
        st.markdown("### :material/edit_note: 01 · เตรียมข้อมูล")
        source = st.radio(
            "เริ่มต้นข้อมูล", ["blank", "demo"], horizontal=True, key="cbc_source",
            format_func=lambda value: "กรอกข้อมูลใหม่" if value == "blank" else "ใช้ตัวอย่างสมมติ",
            on_change=_change_source, persist_state="session",
        )
        defaults = DEMO_VALUES if source == "demo" else {}
        if source == "demo":
            st.caption(":material/science: กำลังใช้ข้อมูลสมมติสำหรับทดลอง ต้องกดประเมินก่อนแสดงผล")
        st.session_state.setdefault("cbc_report_id", f"CBC-{uuid4().hex[:10].upper()}")
        st.caption(f"รหัสการประเมินสมมติ: {st.session_state['cbc_report_id']} · ไม่กรอกชื่อหรือ HN")
        use_intervals = st.checkbox(
            "เพิ่มช่วงอ้างอิงจากห้องปฏิบัติการสำหรับผลตรวจประกอบ", value=False,
            key="cbc_use_lab_intervals", persist_state="session",
        )
    row: dict[str, Any] = {}
    intervals: dict[str, dict[str, float | None]] = {}
    st.caption("ขอบเขตชุดกฎเริ่มต้น: ผู้ใหญ่อายุ 18–65 ปีที่ทราบอายุและเพศ โดยหญิงต้องยืนยันว่าไม่ตั้งครรภ์ ระบบระบุข้อจำกัดเมื่อเป็นเด็ก ตั้งครรภ์ อยู่นอกช่วงอายุ หรือข้อมูลขอบเขตไม่ครบ")
    st.markdown("### :material/hematology: 02 · บันทึกผลตรวจ CBC")
    st.caption("ค่าที่แก้ไขจะเก็บไว้ในเซสชันเมื่อออกจากช่องกรอก สลับหน้าแล้วกลับมาแก้ต่อได้ กดประเมินเพื่ออัปเดตผลและรายงาน")
    with pastel_card("cbc_card_inputs", "sky", gap="small"):
        st.markdown("**:material/person: ข้อมูลสำหรับเลือกขอบเขตเกณฑ์**")
        first, second, third = st.columns(3, gap="medium")
        with first:
            row["age"] = _optional_number("age", defaults)
        with second:
            sexes = list(SEX_LABELS)
            row["sex"] = st.selectbox(
                INPUT_LABELS["sex"], sexes, index=sexes.index(defaults.get("sex", "Unknown")),
                format_func=SEX_LABELS.get, key="cbc_input_sex", persist_state="session",
            )
        with third:
            pregnancies = list(PREGNANCY_LABELS)
            default_pregnancy = "Yes" if defaults.get("pregnant") is True else "No" if defaults.get("pregnant") is False else "Unknown"
            pregnancy = st.selectbox(
                INPUT_LABELS["pregnant"], pregnancies, index=pregnancies.index(default_pregnancy),
                format_func=PREGNANCY_LABELS.get, key="cbc_input_pregnant", persist_state="session",
            )
            row["pregnant"] = {"Unknown": None, "No": False, "Yes": True}.get(pregnancy)
        st.caption("ระบบตรวจขอบเขตก่อนใช้เกณฑ์ ไม่ใช้เกณฑ์ผู้ใหญ่แทนข้อมูลเด็ก การตั้งครรภ์ หรือข้อมูลที่ยังไม่ครบโดยอัตโนมัติ")
        st.markdown("**:material/bloodtype: Hb และ MCV**")
        st.caption("กรอกค่าจากรายงานจริง ช่องว่างหมายถึงไม่มีข้อมูล ไม่ใช่ศูนย์")
        first, second = st.columns(2, gap="medium")
        with first:
            row["hb_g_dl"] = _optional_number("hb_g_dl", defaults)
        with second:
            row["mcv_fl"] = _optional_number("mcv_fl", defaults)
        with st.expander("ผล CBC และข้อมูลประกอบเพิ่มเติม (ไม่บังคับ)", icon=":material/add_circle:"):
            fields = ("rbc_10e12_l", "hct_percent", "mch_pg", "mchc_g_dl", "rdw_percent", "wbc_10e9_l", "platelets_10e9_l", "ferritin_ng_ml", "retic_abs_10e9_l")
            for start in range(0, len(fields), 3):
                columns = st.columns(3, gap="medium")
                for column, field in zip(columns, fields[start:start + 3]):
                    with column:
                        row[field] = _optional_number(field, defaults)
            st.caption("กรอก reticulocyte เป็นจำนวนสัมบูรณ์ตามหน่วยที่ระบุ ไม่ใช่ร้อยละ")
            st.caption("ผล WBC และเกล็ดเลือดในรุ่นนี้ใช้เทียบช่วงอ้างอิงที่ระบุจากห้องปฏิบัติการ การประเมินโรคของเม็ดเลือดขาวและเกล็ดเลือดแบบครบถ้วนยังอยู่นอกขอบเขต")
        if use_intervals:
            with st.expander("ช่วงอ้างอิงที่ระบุโดยห้องปฏิบัติการ", expanded=True, icon=":material/tune:"):
                st.caption("กรอกเฉพาะช่วงอ้างอิงที่ห้องปฏิบัติการระบุสำหรับวิธีตรวจและกลุ่มอายุของตัวอย่างนี้ ใช้หน่วยเดียวกับผลตรวจ เว้นว่างเมื่อไม่มีช่วงอ้างอิง ระบบประเมินจะตรวจความถูกต้องอีกครั้ง")
                for field in INTERVAL_FIELDS:
                    label, lower, upper = st.columns([2, 1, 1], vertical_alignment="center")
                    with label:
                        st.markdown(f"**{INPUT_LABELS[field]}**")
                    with lower:
                        low = st.number_input(f"ขอบเขตล่าง {INPUT_LABELS[field]}", value=None, step=0.1, key=f"cbc_interval_{field}_low", placeholder="ไม่ระบุ", persist_state="session")
                    with upper:
                        high = st.number_input(f"ขอบเขตบน {INPUT_LABELS[field]}", value=None, step=0.1, key=f"cbc_interval_{field}_high", placeholder="ไม่ระบุ", persist_state="session")
                    intervals[field] = {"low": low, "high": high}
        submitted = st.button("ประเมิน CBC และภาวะโลหิตจาง", type=primary_action_type(), key="cbc_submit", width="stretch", icon=":material/analytics:")
    return submitted, row, intervals


def _text_list(title: str, items: list[str]) -> None:
    with st.container(gap="xsmall"):
        st.markdown(f"**{title}**")
        if not items:
            st.caption("ไม่มีรายการเพิ่มเติม")
        for item in items:
            st.markdown(f"- {item}")


def _input_display(value: Any) -> str:
    if value is None:
        return "ไม่มีข้อมูล"
    if isinstance(value, bool):
        return "ใช่" if value else "ไม่ใช่"
    if isinstance(value, (int, float)):
        return f"{value:g}" if isfinite(value) else "ไม่มีข้อมูล"
    return SEX_LABELS.get(str(value), str(value))


def cbc_report_payload(result: Any, metadata: dict[str, str]) -> dict[str, Any]:
    """Export exactly the engine snapshot and its evaluation metadata."""
    return {**metadata, **result.to_dict()}


def cbc_report_csv(result: Any, metadata: dict[str, str]) -> bytes:
    """Build a safe, Thai-labelled CSV entirely in memory."""
    payload = result.to_dict()
    rows: list[list[Any]] = [
        ["รายการ", "ผล"], ["รายงาน", "รายงานช่วยทบทวน CBC และภาวะโลหิตจาง"],
        ["รหัสการประเมินสมมติ", metadata["report_id"]],
        ["เวลาประเมิน (UTC+07:00)", metadata["evaluated_at"]],
        ["แหล่งข้อมูลเริ่มต้น (อาจมีการแก้ไข)", metadata.get("input_origin", "unspecified")],
        ["สถานะเอกสาร", "ร่างเพื่อทบทวน ยังไม่ลงนาม"],
    ]
    for key, value in payload.items():
        if key == "normalized":
            rows.extend([[INPUT_LABELS.get(field, field), item] for field, item in value.items()])
        else:
            rows.append([RESULT_LABELS.get(key, key), value])
    return csv_bytes(rows)


def _render_result(result: Any, metadata: dict[str, str]) -> None:
    st.markdown("### :material/fact_check: 03 · ผลช่วยทบทวน CBC และภาวะโลหิตจาง")
    st.caption(f"รหัสการประเมิน: {metadata['report_id']}")
    st.caption("ผลและไฟล์ดาวน์โหลดอ้างอิงข้อมูลที่ส่งครั้งล่าสุด หากแก้แบบฟอร์มต้องกดประเมินใหม่")
    for error in result.validation_errors:
        st.error(error)
    for warning in result.validation_warnings:
        st.warning(warning)
    if result.low_hb_alert:
        st.error("ระบบแจ้งเตือน Hb ต่ำที่ต้องทบทวน กรุณาตรวจข้อความจากระบบและบริบททางคลินิกโดยเร็ว แม้ข้อมูลส่วนอื่นยังไม่ครบหรืออยู่นอกขอบเขต")
    with pastel_card("cbc_card_result", "lavender", gap="xsmall"):
        overview, pattern = st.columns([1.1, 1], gap="medium")
        with overview:
            st.markdown("**:material/bloodtype: การประเมิน Hb**")
            st.write(result.anemia_status)
        with pattern:
            st.markdown("**:material/labs: รูปแบบเม็ดเลือดแดง**")
            st.write(result.pattern)
        st.caption(result.support_status)
        st.caption(result.scope)
    left, right = st.columns([1.1, 1], gap="medium")
    with left:
        with pastel_card("cbc_card_findings", "mint", height="stretch", gap="small"):
            _text_list(":material/labs: สิ่งที่พบจากข้อมูล", result.findings)
            with st.expander("เหตุผลประกอบ", icon=":material/fact_check:"):
                _text_list("ที่มาของผลประเมิน", result.rationale)
    with right:
        with pastel_card("cbc_card_recommendations", "peach", height="stretch", gap="medium"):
            _text_list(":material/assignment: การตรวจหรือข้อมูลเพิ่มเติมที่แนะนำ", result.recommended_tests)
            _text_list(":material/forum: ประเด็นให้คำปรึกษา", result.counseling)
    with pastel_card("cbc_card_limitations", "butter", gap="xsmall"):
        _text_list(":material/info: ข้อจำกัดการใช้ผล", result.limitations)
        st.caption(result.disclaimer)
    st.markdown("### :material/download: 04 · บันทึกผลเพื่อทบทวน")
    with pastel_card("cbc_card_downloads", "rose", gap="xsmall"):
        st.markdown("**:material/description: ดาวน์โหลดร่างผลประเมิน**")
        st.caption(f"ประเมินเมื่อ {metadata['evaluated_at']} · รายงานจากข้อมูลที่ส่งครั้งล่าสุด ยังไม่ลงนาม")
        with st.container(horizontal=True, gap="small"):
            st.download_button("ดาวน์โหลดรายงาน CSV", cbc_report_csv(result, metadata), f"{metadata['report_id']}_cbc.csv", "text/csv", key="cbc_download_csv", icon=":material/download:")
            st.download_button("ดาวน์โหลดข้อมูล JSON", to_json_bytes(cbc_report_payload(result, metadata)), f"{metadata['report_id']}_cbc.json", "application/json", key="cbc_download_json", icon=":material/data_object:")
    with st.expander("ข้อมูลที่ใช้ เกณฑ์อ้างอิง และรุ่นชุดกฎ", icon=":material/manage_search:"):
        inputs = [{"รายการ": INPUT_LABELS.get(key, key), "ค่าที่ใช้": _input_display(value)} for key, value in result.normalized.items()]
        dataframe(pd.DataFrame(inputs), width="stretch", hide_index=True, alt="ข้อมูล CBC ที่ระบบใช้ประเมิน")
        st.markdown("**:material/rule: เกณฑ์ที่ใช้จริงจากระบบประเมิน**")
        st.json(result.thresholds_used)
        st.markdown("**:material/tune: ช่วงอ้างอิงของห้องปฏิบัติการที่ใช้จริง**")
        st.json(result.reference_intervals_used)
        st.caption(f"รุ่นชุดกฎ: {result.ruleset_version}")
        st.caption(f"ลายนิ้วมือชุดกฎ: {result.ruleset_hash}")
        _text_list("รหัสกฎที่ใช้", result.rules_used)


def render_cbc_page() -> None:
    st.set_page_config(page_title="ThalLink | CBC และภาวะโลหิตจาง", page_icon="🩸", layout="wide", initial_sidebar_state="auto")
    inject_css()
    top_navigation("CBC and anemia")
    hero("CBC และภาวะโลหิตจาง", "ช่วยทบทวน Hb และรูปแบบเม็ดเลือดแดงจาก MCV พร้อมเหตุผล ขอบเขต และข้อมูลตรวจเพิ่มเติม", "โมดูลเริ่มต้นสำหรับทบทวนตาม SOP")
    disclaimer(CBC_DISCLAIMER)
    note, reset = st.columns([3, 1], vertical_alignment="center")
    with note:
        st.caption("ใช้ข้อมูลสมมติหรือข้อมูลที่ไม่ระบุตัวบุคคล ข้อมูลและรายงานอยู่ในหน่วยความจำของเซสชัน ไม่มีการบันทึกลงไฟล์หรือฐานข้อมูลโดยแอป")
    with reset:
        st.button("ล้างข้อมูลโมดูล CBC", key="cbc_reset", on_click=_clear_cbc_session, width="stretch", icon=":material/restart_alt:")
    submitted, row, intervals = _cbc_form()
    if submitted:
        _clear_result()
        st.session_state["cbc_result"] = analyze_cbc(row, reference_intervals=intervals)
        st.session_state["cbc_submitted_inputs"] = deepcopy({"row": row, "intervals": intervals})
        st.session_state["cbc_report_metadata"] = {
            "report_id": st.session_state["cbc_report_id"],
            "evaluated_at": datetime.now(timezone(timedelta(hours=7))).isoformat(timespec="seconds"),
            "document_status": "ร่างเพื่อทบทวน ยังไม่ลงนาม",
            "input_origin": "demo" if st.session_state["cbc_source"] == "demo" else "manual",
        }
    result = st.session_state.get("cbc_result")
    if result is None:
        st.info("กรอกข้อมูลแล้วกดประเมิน ระบบจะยังไม่วิเคราะห์หรือสร้างรายงานก่อนส่งแบบฟอร์ม")
    else:
        previous_inputs = st.session_state.get("cbc_submitted_inputs")
        if previous_inputs is not None and previous_inputs != {"row": row, "intervals": intervals}:
            st.warning("มีค่าในแบบฟอร์มที่แก้ไขแล้วยังไม่ได้ประเมิน ผลและไฟล์ดาวน์โหลดด้านล่างยังใช้ข้อมูลครั้งก่อน กดประเมินเพื่ออัปเดต")
        _render_result(result, st.session_state["cbc_report_metadata"])
    production_footer()
