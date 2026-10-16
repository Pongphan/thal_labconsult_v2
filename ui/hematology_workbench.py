"""Schema-driven forms for hematology modules; all interpretation stays in logic/."""
from __future__ import annotations

from copy import deepcopy
from collections import OrderedDict
from math import isfinite
from typing import Any

import pandas as pd
import streamlit as st

from logic.hematology import analyze_domain
from logic.hematology_common import ReviewResult, STATUS_LABELS, field_label, load_domain_rules
from thalab.styles import disclaimer, hero, inject_css, pastel_card, primary_action_type, production_footer, section, top_navigation
from ui.data_io import ScreeningCSVError
from ui.domain_io import domain_template, read_domain_csv
from ui.streamlit_compat import dataframe
from utils.domain_reporting import (
    batch_report_csv, display_input, report_csv, report_json, report_metadata, report_payload,
)
from utils.module_registry import load_modules
from utils.reporting import to_json_bytes


# Identity transfers only: aliases describe the same unit, never a conversion.
CBC_TRANSFER_UNITS = {
    "age": {"ปี"}, "hb_g_dl": {"g/dL"}, "rbc_10e12_l": {"10^12/L", "10¹²/L"},
    "hct_percent": {"%"}, "mcv_fl": {"fL"}, "mch_pg": {"pg"}, "mchc_g_dl": {"g/dL"},
    "rdw_percent": {"%"}, "wbc_10e9_l": {"10^9/L", "10⁹/L"},
    "platelets_10e9_l": {"10^9/L", "10⁹/L"}, "ferritin_ng_ml": {"ng/mL"},
    "retic_abs_10e9_l": {"10^9/L", "10⁹/L"},
}


def _prefix(module_id: str) -> str:
    return f"domain_{module_id}_"


def _clear_module(module_id: str) -> None:
    prefix = _prefix(module_id)
    for key in list(st.session_state):
        if key.startswith(prefix):
            del st.session_state[key]


def _clear_result(module_id: str, kind: str = "single") -> None:
    prefix = _prefix(module_id)
    for suffix in (f"{kind}_result", f"{kind}_metadata", f"{kind}_inputs", "batch_detail"):
        st.session_state.pop(prefix + suffix, None)


def _change_batch_upload(module_id: str) -> None:
    """Retain the selected bytes across pages; an explicit remove clears them."""
    prefix = _prefix(module_id)
    upload = st.session_state.get(prefix + "upload")
    if upload is None:
        st.session_state.pop(prefix + "batch_csv_bytes", None)
    else:
        st.session_state[prefix + "batch_csv_bytes"] = upload.getvalue()
    _clear_result(module_id, "batch")


def _load_source(module_id: str) -> None:
    prefix = _prefix(module_id)
    for suffix in ("copy_note", "copy_error", "source_snapshot"):
        st.session_state.pop(prefix + suffix, None)
    rules = load_domain_rules(module_id)
    source = st.session_state.get(prefix + "source", "blank")
    values = {} if source == "blank" else rules["examples"][int(source)]["data"]
    for item in rules["fields"]:
        default = None if item["type"] == "number" else [] if item["type"] == "multiselect" else "unknown"
        value = values.get(item["key"], default)
        if item["type"] == "number" and value is not None:
            value = float(value)
        st.session_state[prefix + "input_" + item["key"]] = value
    st.session_state[prefix + "origin"] = "กรอกแบบฟอร์ม" if source == "blank" else "ข้อมูลสมมติ"
    _clear_result(module_id)


def _copy_cbc_values(module_id: str) -> None:
    """Transfer a valid evaluated snapshot with its lineage, never a CBC draft."""
    prefix = _prefix(module_id)
    result = st.session_state.get("cbc_result")
    if result is None:
        return
    if result.validation_errors or result.support_code == "invalid":
        st.session_state[prefix + "copy_error"] = (
            "ยังไม่นำค่าจาก CBC มาใช้: ผลต้นทางมีข้อมูลไม่ถูกต้อง "
            "กรุณากลับไปทบทวนและแก้ไขข้อมูลในหน้า CBC แล้วกดประเมินใหม่ก่อนคัดลอก"
        )
        return
    fields = load_domain_rules(module_id)["fields"]
    copied: dict[str, float] = {}
    units: dict[str, str] = {}
    for item in fields:
        key = item["key"]
        value = result.normalized.get(key)
        if item["type"] != "number" or key not in CBC_TRANSFER_UNITS or value is None:
            continue
        if item.get("unit") not in CBC_TRANSFER_UNITS[key] or type(value) not in (int, float) or not isfinite(value):
            st.session_state[prefix + "copy_error"] = (
                "ยังไม่นำค่าจาก CBC มาใช้: ชนิดข้อมูลหรือหน่วยของผลต้นทางไม่ตรงกับแบบฟอร์ม "
                "กรุณาทบทวนหน่วยและผล CBC ก่อนคัดลอก"
            )
            return
        copied[key] = float(value)
        units[key] = item["unit"]
    if not copied:
        st.session_state[prefix + "copy_error"] = "ไม่มีค่าตัวเลขจากผล CBC ที่ใช้หน่วยตรงกับแบบฟอร์มนี้ กรุณากรอกผลที่มีด้วยตนเอง"
        return
    metadata = st.session_state.get("cbc_report_metadata", {})
    source_snapshot = {
        "module_id": "cbc_anemia", "report_id": metadata.get("report_id"),
        "evaluated_at": metadata.get("evaluated_at"), "input_origin": metadata.get("input_origin", "unknown"),
        "ruleset_version": result.ruleset_version, "ruleset_hash": result.ruleset_hash,
        "support_code": result.support_code, "copied_values": copied, "copied_units": units,
    }
    # Validate before replacing any destination draft or result.
    st.session_state[prefix + "source"] = "blank"
    _load_source(module_id)
    for key, value in copied.items():
        st.session_state[prefix + "input_" + key] = value
    st.session_state[prefix + "source_snapshot"] = deepcopy(source_snapshot)
    st.session_state[prefix + "origin"] = "คัดลอกค่าตัวเลขจากผล CBC ในเซสชัน แล้วกรอกบริบทเพิ่มเติม"
    st.session_state[prefix + "copy_note"] = f"คัดลอกค่าตัวเลข {len(copied)} รายการจาก CBC ที่ประเมินล่าสุด กรุณาทบทวนว่าเป็นตัวอย่างเดียวกันและเติมบริบทก่อนประเมิน"


def _input_widget(module_id: str, item: dict[str, Any]) -> Any:
    key = _prefix(module_id) + "input_" + item["key"]
    label = field_label(item)
    help_text = item.get("help")
    if item["type"] == "number":
        return st.number_input(
            label, value=None, step=float(item.get("step", 0.1)), format="%.3f",
            key=key, help=help_text, placeholder="เว้นว่างเมื่อไม่มีผล", persist_state="session",
        )
    options = [option["value"] for option in item["options"]]
    labels = {option["value"]: option["label"] for option in item["options"]}
    if item["type"] == "select":
        return st.selectbox(label, options, key=key, format_func=lambda value: labels[value], help=help_text, persist_state="session")
    return st.multiselect(label, options, key=key, format_func=lambda value: labels[value], help=help_text, persist_state="session")


def _text_items(title: str, values: list[str]) -> None:
    with st.container(gap="xsmall"):
        st.markdown(f"**{title}**")
        if not values:
            st.caption("ไม่มีรายการเพิ่มเติม")
        for value in values:
            st.markdown(f"- {value}")


def _render_result(result: ReviewResult, metadata: dict[str, Any], key: str) -> None:
    title = "รายละเอียดผลรายแถว" if key.endswith("detail") else "03 · ผลช่วยทบทวน"
    st.markdown(f"### :material/fact_check: {title}")
    st.caption("อ่านสถานะและข้อควรทบทวน ก่อนดูหลักฐานและขั้นตอนถัดไป")
    color = {"incomplete": "orange", "review": "violet", "urgent": "red", "invalid": "red"}[result.status]
    icon = {"incomplete": "pending", "review": "fact_check", "urgent": "priority_high", "invalid": "error"}[result.status]
    with pastel_card(key=key + "_surface_summary", tone="lavender", gap="xsmall"):
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            st.badge(STATUS_LABELS[result.status], color=color, icon=f":material/{icon}:")
            st.badge(metadata["document_status"], color="gray", icon=":material/description:")
        st.caption(f"รหัสสมมติ {metadata['report_id']} · {metadata['evaluated_at']}")
        st.caption(f"ที่มาของข้อมูล: {metadata['input_origin']}")
        source_snapshot = metadata.get("source_snapshot")
        if source_snapshot:
            st.caption(f"CBC ต้นทาง: {source_snapshot.get('report_id') or 'ไม่ได้บันทึกรหัส'} · {source_snapshot.get('evaluated_at') or 'ไม่ได้บันทึกเวลา'}")
            if source_snapshot.get("input_origin") == "demo":
                st.warning("ผลนี้เริ่มจากข้อมูลสมมติของ CBC อาจมีการแก้ไขเพิ่มเติม ไม่ใช่ข้อมูลผู้ป่วยที่ยืนยันแล้ว")
        st.caption(result.scope)
        st.caption(result.confidence_note)
        st.caption("ผลและรายงานเป็นข้อมูลจากการกดประเมินครั้งล่าสุด หากแก้แบบฟอร์มให้กดประเมินใหม่")
    if result.alerts:
        st.error("**ประเด็นที่ต้องประเมินโดยเร็ว**\n\n" + "\n\n".join(f"- {value}" for value in result.alerts), icon=":material/priority_high:")
    if result.validation_errors:
        st.error("**ข้อมูลที่ต้องแก้ไข**\n\n" + "\n\n".join(f"- {value}" for value in result.validation_errors), icon=":material/error:")
    if result.validation_warnings:
        st.warning("**ข้อควรทบทวนของข้อมูล**\n\n" + "\n\n".join(f"- {value}" for value in result.validation_warnings), icon=":material/info:")
    left, right = st.columns([1.1, 1], gap="medium")
    with left:
        with pastel_card(key=key + "_surface_findings", tone="mint", height="stretch", gap="small"):
            _text_items(":material/labs: สิ่งที่พบ", result.findings)
            if result.rationale:
                with st.expander("เหตุผลประกอบ", icon=":material/format_list_bulleted:"):
                    for value in result.rationale:
                        st.markdown(f"- {value}")
    with right:
        with pastel_card(key=key + "_surface_next", tone="peach", height="stretch", gap="small"):
            _text_items(":material/assignment: การตรวจและขั้นตอนที่แนะนำ", result.recommendations)
            with st.expander("ประเด็นให้คำปรึกษา", icon=":material/forum:"):
                for value in result.counseling:
                    st.markdown(f"- {value}")
                if not result.counseling:
                    st.caption("ไม่มีรายการเพิ่มเติม")
    with st.expander("ข้อจำกัดของผลทบทวน", icon=":material/info:"):
        for value in result.limitations:
            st.markdown(f"- {value}")
    if result.calculated:
        with st.expander("รายละเอียดค่าคำนวณและสรุปหลักฐาน", icon=":material/functions:"):
            st.json(result.calculated)
    with st.expander("ทบทวนข้อมูลที่ใช้และเกณฑ์อ้างอิง", icon=":material/manage_search:"):
        records = [{"รายการ": result.field_labels[name], "ค่าที่ใช้": str(display_input(result, name, value))}
                   for name, value in result.normalized.items()]
        dataframe(pd.DataFrame(records), hide_index=True, width="stretch", alt="ข้อมูลที่ใช้สร้างผลทบทวนครั้งนี้")
        st.markdown("**:material/rule: เกณฑ์ที่ใช้จริง**")
        st.json(result.thresholds_used)
        st.caption(f"รุ่นกฎ {result.ruleset_version} · SHA-256 {result.ruleset_hash}")
        _text_items("รหัสกฎที่ใช้", result.rules_used)
        st.markdown("**:material/menu_book: เอกสารอ้างอิงของผลประเมินครั้งนี้**")
        for source in result.sources:
            st.markdown(f"- [{source['title']}]({source['url']}) — {source['use']}")
    with pastel_card(key=key + "_surface_exports", tone="rose", gap="xsmall"):
        export_title = "บันทึกรายงานรายแถวเพื่อทบทวน" if key.endswith("detail") else "04 · บันทึกรายงานเพื่อทบทวน"
        st.markdown(f"**:material/download: {export_title}**")
        st.caption("รายงานร่างจากผลที่แสดง พร้อมข้อมูลที่ใช้ เกณฑ์ และแหล่งอ้างอิง")
        with st.container(horizontal=True, gap="small"):
            st.download_button(
                "รายงาน CSV ภาษาไทย", report_csv(result, metadata), f"{metadata['report_id']}.csv",
                "text/csv", key=key + "_download_csv", icon=":material/table_view:",
            )
            st.download_button(
                "ข้อมูลและผล JSON", report_json(result, metadata), f"{metadata['report_id']}.json",
                "application/json", key=key + "_download_json", icon=":material/data_object:",
            )


def _render_single(module_id: str, rules: dict[str, Any]) -> None:
    prefix = _prefix(module_id)
    labels = {"blank": "กรอกข้อมูลใหม่", **{str(index): example["name"] for index, example in enumerate(rules["examples"])}}
    st.session_state.setdefault(prefix + "origin", "กรอกแบบฟอร์ม")
    with pastel_card(key=prefix + "surface_setup", tone="sky", gap="small"):
        st.markdown("**:material/edit_note: 01 · เตรียมข้อมูล**")
        source = st.selectbox("เริ่มต้นข้อมูล", list(labels), format_func=lambda value: labels[value],
                              key=prefix + "source", on_change=_load_source, args=(module_id,), persist_state="session")
        if source != "blank":
            st.badge("ข้อมูลสมมติสำหรับทดลอง", color="violet", icon=":material/science:")
            st.caption("ต้องกดประเมินก่อนแสดงผล ตัวอย่างนี้ไม่ได้เป็นข้อมูลผู้ป่วย")
        else:
            st.badge("กรอกแบบฟอร์ม", color="gray", icon=":material/edit_note:")
            st.caption("เพิ่มเฉพาะผลที่มี ช่องว่างและไม่ทราบยังคงเป็นข้อมูลที่ไม่ได้ประเมิน")
        if st.session_state.get("cbc_result") is not None:
            st.button("นำค่าตัวเลขจาก CBC ที่ประเมินล่าสุดมาใช้", key=prefix + "copy_cbc",
                      on_click=_copy_cbc_values, args=(module_id,), icon=":material/content_copy:")
        if prefix + "copy_note" in st.session_state:
            st.warning(st.session_state[prefix + "copy_note"])
        if st.session_state.get(prefix + "source_snapshot", {}).get("input_origin") == "demo":
            st.warning("ค่าที่นำเข้าจาก CBC เป็นข้อมูลสมมติสำหรับทดลอง อาจมีการแก้ไขเพิ่มเติม")
        if prefix + "copy_error" in st.session_state:
            st.error(st.session_state[prefix + "copy_error"])
    sections: dict[str, list[dict[str, Any]]] = OrderedDict()
    for item in rules["fields"]:
        sections.setdefault(item["section"], []).append(item)
    values: dict[str, Any] = {}
    st.markdown("### :material/labs: 02 · กรอกผลที่มี")
    st.caption(f"เปิดหมวดที่เกี่ยวข้องจาก {len(sections)} หมวด ค่าที่แก้ไขจะเก็บไว้ในเซสชันเมื่อออกจากช่องกรอก สลับหน้าแล้วกลับมาแก้ต่อได้")
    with st.container(key=prefix + "form", border=False):
        for index, (name, items) in enumerate(sections.items()):
            with st.expander(f"{index + 1:02d} · {name}", expanded=index == 0, icon=":material/edit_note:"):
                for start in range(0, len(items), 2):
                    columns = st.columns(2, gap="medium")
                    for column, item in zip(columns, items[start:start + 2]):
                        with column:
                            values[item["key"]] = _input_widget(module_id, item)
        with st.container(horizontal=True, vertical_alignment="center", gap="medium"):
            submitted = st.button("ประเมินข้อมูล", type=primary_action_type(), key=prefix + "submit", icon=":material/fact_check:")
            st.caption("แก้ไขข้อมูลแล้วกดประเมินใหม่ เพื่อปรับผลและรายงาน")
    if submitted:
        _clear_result(module_id)
        try:
            result = analyze_domain(module_id, values)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state[prefix + "single_result"] = result
            st.session_state[prefix + "single_inputs"] = deepcopy(values)
            st.session_state[prefix + "single_metadata"] = report_metadata(
                module_id, st.session_state[prefix + "origin"],
                source_snapshot=st.session_state.get(prefix + "source_snapshot"),
            )
    result = st.session_state.get(prefix + "single_result")
    if result is None:
        with pastel_card(key=prefix + "surface_summary", tone="lavender", gap="xsmall"):
            st.markdown("**:material/description: ผลทบทวนจะปรากฏที่นี่**")
            st.caption("กรอกเฉพาะผลที่มี และกดประเมินเพื่อเริ่มทบทวน ช่องว่างไม่ใช่ศูนย์หรือผลลบ")
    else:
        previous_inputs = st.session_state.get(prefix + "single_inputs")
        if previous_inputs is not None and previous_inputs != values:
            st.warning("มีค่าในแบบฟอร์มที่แก้ไขแล้วยังไม่ได้ประเมิน ผลและไฟล์ดาวน์โหลดด้านล่างยังใช้ข้อมูลครั้งก่อน กดประเมินเพื่ออัปเดต")
        _render_result(result, st.session_state[prefix + "single_metadata"], prefix + "single")


def _render_batch(module_id: str, rules: dict[str, Any]) -> None:
    prefix = _prefix(module_id)
    st.markdown("### :material/table_view: 01 · เตรียมชุดข้อมูล")
    st.caption("เริ่มจากแม่แบบ หรือทดลองด้วยชุดข้อมูลสมมติของกลุ่มงานนี้")
    st.caption("CSV สูงสุด 2 MB / 200 แถว ใช้ข้อมูลที่ตัดการระบุตัวบุคคลแล้ว รหัสในรายงานสร้างใหม่ตามแถว")
    with st.container(horizontal=True):
        st.download_button("แม่แบบ CSV", domain_template(rules), f"{module_id}_template.csv", "text/csv", key=prefix + "template", icon=":material/download:")
        st.download_button("CSV ข้อมูลสมมติ", domain_template(rules, example=True), f"{module_id}_example.csv", "text/csv", key=prefix + "example_csv", icon=":material/science:")
    with st.expander("คำอธิบายคอลัมน์และรหัสตัวเลือก", icon=":material/menu_book:"):
        records = [{"คอลัมน์": item["key"], "ความหมาย/หน่วย": field_label(item),
                    "ตัวเลือก": " | ".join(f"{o['value']} = {o['label']}" for o in item.get("options", [])) or "ตัวเลข; เว้นว่างเมื่อไม่มีข้อมูล"}
                   for item in rules["fields"]]
        dataframe(pd.DataFrame(records), hide_index=True, width="stretch", alt="คู่มือคอลัมน์สำหรับนำเข้า CSV")
        st.caption("ตัวเลือกหลายค่าคั่นด้วย |; ผลไม่ทราบใช้ unknown; ระบุหน่วยในช่องที่แบบฟอร์มกำหนดให้ครบ")
    with pastel_card(key=prefix + "surface_setup", tone="sky", gap="small"):
        st.markdown("**:material/upload_file: 02 · เลือกข้อมูลและประเมิน**")
        source = st.radio("แหล่งชุดข้อมูล", ["upload", "demo"], format_func=lambda value: "อัปโหลด CSV" if value == "upload" else "ใช้ชุดข้อมูลสมมติ",
                          key=prefix + "batch_source", on_change=_clear_result, args=(module_id, "batch"), horizontal=True, persist_state="session")
        upload = None
        if source == "upload":
            upload = st.file_uploader("เลือก CSV ที่ไม่มีข้อมูลระบุตัวบุคคล", type=["csv"], key=prefix + "upload",
                                      on_change=_change_batch_upload, args=(module_id,))
            if upload is not None:
                st.session_state[prefix + "batch_csv_bytes"] = upload.getvalue()
            elif prefix + "batch_csv_bytes" in st.session_state:
                st.caption("ไฟล์ CSV ที่เลือกไว้ยังอยู่ในเซสชันนี้ เลือกไฟล์ใหม่เพื่อแทนที่ หรือล้างข้อมูลกลุ่มงานนี้")
        else:
            st.badge("ชุดข้อมูลสมมติสำหรับทดลอง", color="violet", icon=":material/science:")
            st.caption(f"มีตัวอย่าง {len(rules['examples'])} แถว ต้องกดประเมินก่อนแสดงผล")
        submitted = st.button("ประเมินชุดข้อมูล", type=primary_action_type(), key=prefix + "batch_submit", icon=":material/fact_check:")
    if submitted:
        _clear_result(module_id, "batch")
        try:
            if source == "demo":
                rows, notes = [example["data"] for example in rules["examples"]], ["ใช้ข้อมูลสมมติสำหรับทดลอง ไม่ใช่ข้อมูลผู้ป่วย"]
            elif prefix + "batch_csv_bytes" not in st.session_state:
                raise ScreeningCSVError("กรุณาเลือกไฟล์ CSV ก่อนประเมิน")
            else:
                rows, notes = read_domain_csv(st.session_state[prefix + "batch_csv_bytes"], rules)
            results = [analyze_domain(module_id, row) for row in rows]
            metadata = [report_metadata(module_id, "CSV ที่ตัดการระบุตัวบุคคลแล้ว" if source == "upload" else "ชุดข้อมูลสมมติ") for _ in rows]
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state[prefix + "batch_result"] = results
            st.session_state[prefix + "batch_metadata"] = metadata
            st.session_state[prefix + "batch_notes"] = notes
    results = st.session_state.get(prefix + "batch_result")
    if not results:
        st.caption("เมื่อประเมินแล้ว จะแสดงภาพรวมทุกแถว พร้อมรายละเอียดและรายงานดาวน์โหลด")
        return
    st.markdown("### :material/fact_check: 03 · ภาพรวมชุดข้อมูล")
    st.caption("ทุกแถวยังคงอยู่ในผลรวม รวมถึงแถวที่ข้อมูลต้องแก้ไข")
    metadata = st.session_state[prefix + "batch_metadata"]
    for note in st.session_state.get(prefix + "batch_notes", []):
        st.caption(note)
    alerts = sum(bool(result.alerts) for result in results)
    invalid = sum(result.status == "invalid" for result in results)
    incomplete = sum(result.status == "incomplete" for result in results)
    with st.container(horizontal=True, gap="small"):
        st.badge(f"ทั้งหมด {len(results)} แถว", color="violet", icon=":material/table_chart:")
        st.badge(f"ข้อเร่งด่วน {alerts} แถว", color="red" if alerts else "gray", icon=":material/priority_high:")
        st.badge(f"ต้องแก้ไข {invalid} แถว", color="orange" if invalid else "gray", icon=":material/edit_note:")
        st.badge(f"ข้อมูลไม่พอ {incomplete} แถว", color="orange" if incomplete else "gray", icon=":material/pending:")
    if alerts:
        st.error(f"มีข้อเตือนที่ต้องประเมินโดยเร็ว {alerts} แถว รวมแถวที่มีข้อมูลส่วนอื่นผิดพลาด", icon=":material/priority_high:")
    table = [{"แถว": index, "รหัสสมมติ": meta["report_id"], "สถานะ": STATUS_LABELS[result.status],
              "สิ่งที่พบ": " | ".join(result.findings), "ข้อเร่งด่วน": " | ".join(result.alerts),
              "ข้อผิดพลาด": " | ".join(result.validation_errors)}
             for index, (result, meta) in enumerate(zip(results, metadata), start=1)]
    dataframe(pd.DataFrame(table), hide_index=True, width="stretch", alt="ผลทบทวนทุกแถวรวมแถวข้อมูลผิดพลาด")
    with pastel_card(key=prefix + "batch_surface_exports", tone="rose", gap="xsmall"):
        st.markdown("**:material/download: 04 · บันทึกรายงานทั้งชุด**")
        with st.container(horizontal=True):
            st.download_button("รายงานรวม CSV", batch_report_csv(results, metadata), f"{module_id}_batch.csv", "text/csv", key=prefix + "batch_csv", icon=":material/table_view:")
            st.download_button("ผลครบทุกแถว JSON", to_json_bytes([report_payload(result, meta) for result, meta in zip(results, metadata)]),
                               f"{module_id}_batch.json", "application/json", key=prefix + "batch_json", icon=":material/data_object:")
    index = st.selectbox("ดูรายละเอียดแถว", range(len(results)),
                         format_func=lambda value: f"แถวที่ {value + 1} · {STATUS_LABELS[results[value].status]}", key=prefix + "batch_detail", persist_state="session")
    _render_result(results[index], metadata[index], prefix + "detail")


def render_domain_page(module_id: str) -> None:
    rules = load_domain_rules(module_id)
    module = next(item for item in load_modules() if item.id == module_id)
    st.set_page_config(page_title=f"ThalLink | {module.title}", page_icon="🩸", layout="wide", initial_sidebar_state="auto")
    inject_css()
    top_navigation(module.routes[0].key)
    hero(module.title, module.summary, "Hematologic Platform · เครื่องมือช่วยทบทวน")
    disclaimer(rules["metadata"]["disclaimer"])
    st.caption(rules["metadata"]["scope"])
    st.caption("กฎรุ่นทดลองรอทบทวนตาม SOP ของหน่วยงาน ไม่ใช้ผลนี้แทนการวินิจฉัย การลงนาม หรือการอนุมัติทางคลินิก")
    with st.container(key=_prefix(module_id) + "surface_controls"):
        controls, reset = st.columns([3, 1], vertical_alignment="bottom")
        with controls:
            mode = st.radio("รูปแบบการทบทวน", ["single", "batch"], format_func=lambda value: "รายตัวอย่าง" if value == "single" else "ชุดข้อมูล CSV",
                            key=_prefix(module_id) + "mode", horizontal=True, persist_state="session")
        with reset:
            st.button("ล้างข้อมูลกลุ่มงานนี้", key=_prefix(module_id) + "reset", on_click=_clear_module, args=(module_id,),
                      icon=":material/restart_alt:", width="stretch")
    if mode == "single":
        _render_single(module_id, rules)
    else:
        _render_batch(module_id, rules)
    production_footer()
