"""Native Streamlit template designer using only synthetic demonstration data."""
from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

from logic.reporting import PANEL_FIELDS, PANEL_LABELS, TEST_CATALOG, demo_rows, validate_report
from thalab.styles import hero, inject_css, pastel_card, production_footer, section, top_navigation
from ui.streamlit_compat import data_editor, dataframe, iframe
from ui.drafts import render_synthetic_draft_controls
from utils.report_layout import (
    ReportTemplate, build_report_payload, json_bytes,
    render_report_html, template_payload,
)


LANGUAGE_LABELS = {"th": "ภาษาไทย", "en": "English", "bilingual": "ไทย / English"}


def _panel_label(panel: str) -> str:
    label = PANEL_LABELS[panel]
    if isinstance(label, dict):
        return f"{label.get('name_th', panel)} / {label.get('name_en', panel)}"
    return str(label)


def _reset_demo() -> None:
    st.session_state["reporting_editor_epoch"] = st.session_state.get("reporting_editor_epoch", 0) + 1
    panel = st.session_state.get("reporting_panel", "cbc")
    st.session_state.pop(f"reporting_rows_{panel}", None)
    st.session_state.pop(f"reporting_editor_base_{panel}", None)


def _numeric_rows(frame: pd.DataFrame, panel: str) -> list[dict[str, Any]]:
    """Read editable numbers; keep test identities and units from the catalog."""
    rows = []
    for code, (_, values) in zip(PANEL_FIELDS[panel], frame.iterrows()):
        row = {"code": code, "unit": TEST_CATALOG[code]["unit"]}
        for field in ("result", "previous_result", "previous_days"):
            value = values[field]
            row[field] = None if pd.isna(value) else float(value)
        rows.append(row)
    return rows


def _preview_rows(rows: list[dict[str, Any]], language: str, show_previous: bool) -> pd.DataFrame:
    preview = []
    for row in rows:
        item = TEST_CATALOG[row["code"]]
        name = item["name_th"] if language == "th" else item["name_en"] if language == "en" else f"{item['name_th']} / {item['name_en']}"
        entry = {
            "Test / รายการ": name,
            "Synthetic result / ผลสมมติ": row["result"],
            "Unit / หน่วย": row["unit"],
            "Reference interval / ช่วงอ้างอิง": "ยังไม่กำหนด / Not configured",
            "Flag / ธงผล": "ยังไม่ประเมิน / Not assessed",
        }
        if show_previous:
            entry["Previous / ผลก่อนหน้า"] = row["previous_result"]
            entry["Days earlier / วันที่ผ่านมา"] = row["previous_days"]
        preview.append(entry)
    return pd.DataFrame(preview)


def render_reporting_page() -> None:
    st.set_page_config(page_title="ThalLink | Report design", page_icon="🧾", layout="wide", initial_sidebar_state="collapsed")
    inject_css()
    top_navigation("Report design")
    hero(
        "การออกแบบใบรายงานผล",
        "ทดลองจัดแบบรายงานโลหิตวิทยาและตรวจสอบความสอดคล้องของข้อมูลสมมติ",
        "SYNTHETIC REPORT DESIGNER · DRAFT",
    )
    st.warning(
        "DRAFT · SYNTHETIC — ใช้ข้อมูลสมมติเท่านั้น ห้ามใช้ดูแลผู้ป่วย "
        "ต้นแบบนี้ไม่มีการอนุมัติผล การลงนาม การจัดเก็บเวชระเบียน หรือการเชื่อมต่อระบบภายนอก",
        icon=":material/science:",
    )
    st.caption("เปลี่ยนตัวเลขได้เพื่อทดสอบกฎ ระบบตรวจสอบใหม่ทุกครั้งที่แก้ไข และสร้างไฟล์จากค่าชุดเดียวกับที่แสดงด้านล่าง")

    with pastel_card("reporting_template", "indigo"):
        section("1 · รูปแบบรายงาน", "ตั้งค่าแม่แบบเท่านั้น ไม่กรอกข้อมูลบุคคลจริง")
        left, right = st.columns(2, gap="large")
        with left:
            panel = st.selectbox("ชุดรายการตรวจ", tuple(PANEL_FIELDS), format_func=_panel_label, key="reporting_panel", persist_state="session")
            language = st.selectbox("ภาษารายงาน (หัวข้อและชื่อรายการ)", tuple(LANGUAGE_LABELS), format_func=LANGUAGE_LABELS.get, index=2, key="reporting_language", persist_state="session")
            institution = st.text_input("ชื่อหน่วยงานบนแม่แบบ (สมมติ)", value="ห้องปฏิบัติการสมมติ / Synthetic laboratory", max_chars=160, key="reporting_institution", persist_state="session")
        with right:
            version = st.text_input("รุ่นแม่แบบ (DRAFT เสมอ)", value="0.1", max_chars=40, key="reporting_version", persist_state="session")
            margin = st.slider("ขอบกระดาษ A4 ทุกด้าน (มม.)", min_value=10, max_value=30, value=15, key="reporting_margin", persist_state="session")
            st.caption("ข้อมูลบุคคล ตัวอย่าง และเวลาในหัวรายงานเป็นตัวอย่างคงที่ ไม่ใช่เวลาให้บริการจริง")
        options = st.columns(4)
        show_previous = options[0].checkbox("ผลก่อนหน้า", value=True, key="reporting_show_previous", persist_state="session")
        show_morphology = options[1].checkbox("ช่อง Morphology", value=False, key="reporting_show_morphology", persist_state="session")
        show_comments = options[2].checkbox("หมายเหตุ", value=True, key="reporting_show_comments", persist_state="session")
        show_trend = options[3].checkbox("เปรียบเทียบสองจุด", value=False, key="reporting_show_trend", persist_state="session")
    template = ReportTemplate(
        panel=panel, language=language, institution=institution, version=version.strip() or "0.1",
        margin_mm=margin, show_previous=show_previous, show_morphology=show_morphology,
        show_comments=show_comments, show_trend=show_trend,
    )

    section("2 · ข้อมูลตัวอย่างที่แก้ไขได้", "แก้ไขได้เฉพาะค่าตัวเลข รหัสรายการและหน่วยยึดตามรายการทดสอบสมมติ ผลก่อนหน้าไม่ถือว่าเปรียบเทียบกันได้โดยอัตโนมัติ")
    st.button("คืนค่าตัวอย่างสมมติ", key="reporting_reset", icon=":material/restart_alt:", on_click=_reset_demo)
    epoch = st.session_state.get("reporting_editor_epoch", 0)
    editor_key = f"reporting_editor_{panel}_{epoch}"
    rows_key = f"reporting_rows_{panel}"
    base_key = f"reporting_editor_base_{panel}"
    # data_editor has no persist_state option. Keep its base stable while editing,
    # then rebase from the last numeric draft after page or panel widget cleanup.
    if editor_key not in st.session_state or base_key not in st.session_state:
        st.session_state[base_key] = pd.DataFrame(st.session_state.get(rows_key, demo_rows(panel))).copy(deep=True)
    seed = st.session_state[base_key].copy(deep=True)
    seed.insert(1, "name_th", [TEST_CATALOG[code]["name_th"] for code in seed["code"]])
    seed.insert(2, "name_en", [TEST_CATALOG[code]["name_en"] for code in seed["code"]])
    for field in ("result", "previous_result", "previous_days"):
        seed[field] = pd.to_numeric(seed[field], errors="coerce").astype(float)
    edited = data_editor(
        seed,
        alt="ตารางข้อมูลสมมติ: แก้ไขผลปัจจุบัน ผลก่อนหน้า และจำนวนวันย้อนหลังได้",
        key=editor_key,
        hide_index=True, width="stretch", num_rows="fixed",
        disabled=["code", "name_th", "name_en", "unit"],
        column_config={
            "code": st.column_config.TextColumn("Code"),
            "name_th": st.column_config.TextColumn("รายการตรวจ"),
            "name_en": st.column_config.TextColumn("Test"),
            "result": st.column_config.NumberColumn("ผลสมมติ / Result", format="%.4f"),
            "unit": st.column_config.TextColumn("Unit"),
            "previous_result": st.column_config.NumberColumn("ผลก่อนหน้า (สมมติ)", format="%.4f"),
            "previous_days": st.column_config.NumberColumn("วันที่ผ่านมา", format="%.2f"),
        },
    )
    rows = _numeric_rows(edited, panel)
    st.session_state[rows_key] = [dict(row) for row in rows]

    with st.expander("เงื่อนไขจำลองสำหรับการตรวจสอบ", expanded=False):
        specimen_flags = st.multiselect(
            "ปัญหาตัวอย่างสมมติ", ("clotted", "hemolyzed", "insufficient_volume", "other"),
            key="reporting_specimen_flags", persist_state="session",
        )
        previous_comparable = st.checkbox(
            "สมมติว่าผลก่อนหน้าเปรียบเทียบกันได้ (สำหรับการจำลองเท่านั้น)",
            value=False, key="reporting_previous_comparable", persist_state="session",
        )
        tolerances: dict[str, Any] = {}
        has_indices = all(code in PANEL_FIELDS[panel] for code in ("mcv_fl", "mch_pg", "mchc_g_dl"))
        if has_indices:
            use_tolerances = st.checkbox(
                "กำหนดค่าคลาดเคลื่อนสัมบูรณ์สมมติสำหรับ RBC indices", value=False,
                key="reporting_use_tolerances", persist_state="session",
            )
            if use_tolerances:
                st.warning("ค่าด้านล่างใช้จำลองการเปรียบเทียบเท่านั้น ไม่ใช่เกณฑ์ทางคลินิกหรือ SOP ที่ได้รับอนุมัติ")
                tolerance_columns = st.columns(3)
                tolerances["index_abs"] = {
                    code: column.number_input(
                        f"{label} (simulation only)", min_value=0.0, value=0.5, step=0.1,
                        key=f"reporting_tolerance_{code}", persist_state="session",
                    )
                    for column, code, label in zip(tolerance_columns,
                        ("mcv_fl", "mch_pg", "mchc_g_dl"), ("MCV · fL", "MCH · pg", "MCHC · g/dL"))
                }
        st.caption("กฎที่ไม่มีเกณฑ์เฉพาะของหน่วยงานจะแสดงว่าไม่ได้ประเมิน ผลรวมยังคง HOLD หรือ REJECT และไม่สามารถอนุมัติได้")

    validation = validate_report(
        rows, panel=panel, specimen_flags=specimen_flags,
        tolerances=tolerances or None, previous_comparable=previous_comparable,
    )
    payload = build_report_payload(rows, TEST_CATALOG, validation, template, validation_context={
        "specimen_flags": specimen_flags, "tolerances": tolerances,
        "previous_comparable": previous_comparable,
    })
    section("3 · การตรวจสอบปัจจุบัน", "Live validation — คำนวณจากค่าปัจจุบันในตารางทุกครั้ง ไม่มีผลเก่าค้างอยู่ในไฟล์ส่งออก")
    st.caption("ข้อความกฎในต้นแบบยังเป็นภาษาไทย แม้เลือกแบบรายงาน English / Prototype rule messages remain in Thai.")
    if validation["decision"] == "REJECT":
        st.error("REJECT · ข้อมูลสมมติไม่ผ่านการตรวจสอบโครงสร้างหรือค่าข้อมูล — แก้ไขก่อนทบทวนต่อ")
    else:
        st.warning("HOLD · ร่างสมมติสำหรับทบทวน — ไม่สามารถอนุมัติผลได้")
    findings = [{
        "Rule": item["rule_id"], "Status": item["status"], "Message": item["message"],
        "Evidence": json.dumps(item.get("evidence", {}), ensure_ascii=False, default=str),
    } for item in validation["findings"]]
    dataframe(pd.DataFrame(findings), alt="ผลตรวจสอบข้อมูลสมมติปัจจุบันพร้อมหลักฐานของแต่ละกฎ", hide_index=True, width="stretch")
    if validation.get("derived"):
        with st.expander("ค่าที่คำนวณประกอบการตรวจสอบ"):
            st.json(validation["derived"])

    # This is application-owned HTML with every variable escaped by the renderer.
    # Never embed an uploaded HTML document here. Export exactly the same bytes.
    report_html = render_report_html(payload)
    with pastel_card("reporting_preview", "indigo"):
        section("4 · ตัวอย่างรายงาน HTML", "ตัวอย่างและไฟล์ดาวน์โหลดใช้เอกสารเดียวกัน · การแบ่งหน้า A4 เกิดเมื่อสั่งพิมพ์")
        iframe(report_html, height=850, width="stretch", tab_index=0,
               alt="รายงานสมมติฉบับเดียวกับไฟล์ HTML สำหรับพิมพ์ A4 พร้อมผลและสถานะ DRAFT")
        with st.expander("ตารางผลสำหรับอ่านและตรวจสอบ"):
            dataframe(_preview_rows(rows, language, show_previous), alt="ผลสมมติชุดเดียวกับรายงาน HTML", hide_index=True, width="stretch")

    section("5 · ดาวน์โหลดร่างสมมติ", "HTML ใช้เปิดในเบราว์เซอร์แล้ว Print / Save as PDF บนกระดาษ A4 ต้องตรวจรูปแบบ ตัวอักษรไทย และการแบ่งหน้าด้วยตนเอง; ยังไม่มี PDF engine ที่ผ่านการตรวจสอบ")
    st.caption("ไฟล์ทั้งหมดเป็น DRAFT / SYNTHETIC ไม่มีลายเซ็น การอนุมัติ หรือประวัติการพิมพ์ ข้อมูลคงอยู่ใน session และไฟล์ที่ผู้ใช้ดาวน์โหลดเท่านั้น")
    exports = st.columns(3)
    exports[0].download_button("HTML · DRAFT", data=report_html.encode("utf-8"), file_name=f"synthetic-{panel}-draft.html", mime="text/html", key="reporting_download_html", icon=":material/print:", width="stretch")
    exports[1].download_button("Template · JSON", data=json_bytes(template_payload(template)), file_name=f"synthetic-{panel}-template-draft.json", mime="application/json", key="reporting_download_template", icon=":material/settings:", width="stretch")
    exports[2].download_button("Validation · JSON", data=json_bytes(payload), file_name=f"synthetic-{panel}-validation-draft.json", mime="application/json", key="reporting_download_validation", icon=":material/fact_check:", width="stretch")
    st.caption(f"Snapshot SHA-256: {payload['snapshot_sha256']}")
    render_synthetic_draft_controls()
    production_footer()
