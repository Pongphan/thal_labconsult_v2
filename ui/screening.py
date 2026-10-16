"""Thai screening UI. Clinical decisions come only from the shared engine."""

from __future__ import annotations

from hashlib import sha256
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd
import streamlit as st

from ui.streamlit_compat import dataframe, plotly_chart

from thalab.core import DEFAULT_THRESHOLDS, SCREENING_COLUMNS, analyze_dataframe, analyze_screening, example_screening_dataframe
from thalab.ml import ml_feature_matrix, phenotype_similarity
from thalab.reporting import screening_report_markdown, to_json_bytes
from thalab.styles import disclaimer, hero, inject_css, metric_card, pastel_card, primary_action_type, production_footer, section, top_navigation
from thalab.viz import batch_mcv_hba2_scatter, batch_risk_distribution, cbc_reference_bars, hb_fraction_donut, hplc_chromatogram, population_sankey, reflex_sankey, score_heatmap, score_radar
from ui.data_io import ScreeningCSVError, deidentify_demo, read_screening_csv
from utils.reporting import RISK_LABELS, batch_report_csv, screening_report_csv


CALL_LABELS = {"Not performed": "ยังไม่ได้ตรวจ / ไม่มีข้อมูล", "Negative": "ผลลบ", "Positive": "ผลบวก", "Indeterminate": "ยังสรุปผลไม่ได้", "Invalid": "ผลตรวจใช้ไม่ได้"}
SEX_LABELS = {"Not specified": "ยังไม่ระบุเกณฑ์", "Female": "เกณฑ์หญิง", "Male": "เกณฑ์ชาย", "Other": "อื่น ๆ — ต้องให้ผู้ทบทวนเลือกเกณฑ์ก่อนแปลผล"}
HISTORY_LABELS = {"Not performed": "ไม่ทราบ / ไม่มีข้อมูล", "Yes": "ใช่", "No": "ไม่ใช่"}
COLUMN_LABELS = {
    "clinical_group_labels": "กลุ่มผลที่ต้องทบทวน",
    "declared_units": "หน่วยที่ระบุยืนยัน",
    "sample_id": "รหัสตัวอย่างสมมติ", "age": "อายุ (ปี)", "sex": "เพศ", "hb_g_dl": "Hb (g/dL)",
    "rbc_10e12_l": "RBC (10¹²/L)", "hct_percent": "Hct (%)", "mcv_fl": "MCV (fL)", "mch_pg": "MCH (pg)",
    "mchc_g_dl": "MCHC (g/dL)", "rdw_percent": "RDW (%)", "retic_percent": "Reticulocyte (%)", "ferritin_ng_ml": "Ferritin (ng/mL)",
    "hba_percent": "HbA (%)", "hba2_percent": "HbA2 ที่แยกวัด (%)", "hba2e_percent": "HbA2/E รวม (%)", "hbe_percent": "HbE ที่แยกวัด (%)", "hbf_percent": "HbF (%)",
    "bart_percent": "Hb Bart’s (%)", "hbh_percent": "HbH (%)", "hbcs_percent": "Hb Constant Spring (%)", "hb_method": "วิธีแยกฮีโมโกลบิน",
    "of_method": "วิธีตรวจ OF", "oft": "ผล OF / NESTROFT", "dcip": "ผล DCIP", "hbh_inclusion": "ผล HbH inclusion",
    "partner_oft": "ผล OF ของคู่", "partner_dcip": "ผล DCIP ของคู่", "partner_screening": "ข้อเสนอแนะคัดกรองของคู่",
    "transfusion_recent": "ประวัติรับเลือดช่วงที่ผ่านมา", "pregnant": "ตั้งครรภ์", "smear_target_cells": "พบ target cells", "family_history": "ประวัติครอบครัว / คู่มีพาหะ",
    "top_pattern": "รูปแบบที่ควรทบทวน", "consult_risk": "ระดับการทบทวน", "consult_score": "คะแนนรูปแบบ",
    "beta_trait_score": "คะแนนรูปแบบ β-thal", "alpha_trait_score": "คะแนนรูปแบบ α-thal / HbH", "hbe_score": "คะแนนรูปแบบ HbE", "iron_deficiency_score": "คะแนนรูปแบบขาดธาตุเหล็ก",
    "severe_anemia_flag": "ระบบแจ้ง Hb ต่ำรุนแรง", "microcytosis": "ระบบพบ MCV ต่ำ", "hypochromia": "ระบบพบ MCH ต่ำ", "anemia": "ระบบพบภาวะซีด",
    "evidence": "หลักฐานจากข้อมูล", "recommendations": "ข้อเสนอแนะ", "caveats": "ข้อจำกัดการแปลผล", "validation_errors": "ข้อผิดพลาดของข้อมูล", "validation_warnings": "ข้อสังเกตของข้อมูล",
    "counseling": "ประเด็นให้คำปรึกษา", "suspected_genotypes": "จีโนไทป์ที่ควรตรวจยืนยัน", "rule_ids": "กฎที่ใช้", "ruleset_version": "รุ่นชุดกฎ", "confidence_note": "ความหมายและข้อจำกัดของคะแนน", "thresholds_used": "เกณฑ์ที่ใช้จริง", "ee_assessment": "การประเมิน EE",
    "mentzer_index": "ดัชนี Mentzer", "rdwi": "ดัชนี RDWI", "shine_lal_index": "ดัชนี Shine–Lal", "england_fraser_index": "ดัชนี England–Fraser", "green_king_index": "ดัชนี Green–King", "calculated_mchc": "MCHC คำนวณ",
    "ml_prototype_pattern": "ต้นแบบที่คล้าย (ทดลอง)", "ml_similarity_score": "คะแนนความคล้าย (ทดลอง)", "ml_runner_up": "ต้นแบบลำดับสอง (ทดลอง)", "ml_runner_up_score": "คะแนนลำดับสอง (ทดลอง)", "ml_note": "ข้อจำกัดส่วนทดลอง",
    "ee_applicable": "EE score ใช้ได้กับข้อมูลนี้", "ee_score": "EE score", "ee_interpretation": "ข้อจำกัด EE score", "partner_status": "สถานะการคัดกรองของคู่", "partner_interpretation": "การประเมินคัดกรองของคู่", "partner_complete": "ข้อมูลคัดกรองคู่ครบถ้วน", "partner_recommendations": "ข้อเสนอแนะสำหรับคู่", "input_origin": "ที่มาของข้อมูล", "ruleset_hash": "ลายนิ้วมือชุดกฎ",
}


def _clear_session() -> None:
    for key in list(st.session_state):
        if key.startswith("screening_"):
            del st.session_state[key]


def _clear_single_result() -> None:
    for key in ("screening_single_result", "screening_single_thresholds", "screening_single_inputs", "screening_partner_result", "screening_partner_oft", "screening_partner_dcip"):
        st.session_state.pop(key, None)


def _reset_single_form() -> None:
    _clear_single_result()
    for key in list(st.session_state):
        if key.startswith("screening_input_") or key in {"screening_method", "screening_case_id"}:
            del st.session_state[key]


def _clear_batch_result() -> None:
    for key in ("screening_batch_results", "screening_batch_thresholds", "screening_batch_notes", "screening_batch_input_digest"):
        st.session_state.pop(key, None)


def _capture_batch_upload() -> None:
    """Retain files over page changes, but respect an explicit uploader removal."""
    uploaded = st.session_state.get("screening_batch_upload")
    if uploaded is None:
        st.session_state.pop("screening_batch_upload_bytes", None)
    else:
        st.session_state["screening_batch_upload_bytes"] = uploaded.getvalue()


def _batch_upload_changed() -> bool:
    """Compare bytes with the evaluated upload without retaining another file copy."""
    evaluated = st.session_state.get("screening_batch_input_digest")
    payload = st.session_state.get("screening_batch_upload_bytes")
    return evaluated is not None and (payload is None or sha256(payload).hexdigest() != evaluated)


def _number(value: Any) -> float | None:
    """Prepare optional values without replacing missing values with zero."""
    try:
        number = float(value)
        return number if np.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _messages(title: str, items: Any) -> None:
    st.markdown(f"**{title}**")
    if isinstance(items, str):
        items = [items] if items.strip() else []
    if not items:
        st.caption("ไม่มีรายการเพิ่มเติม")
        return
    for item in items:
        st.markdown(f"- {item}")


def _display_value(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return " | ".join(str(item) for item in value)
    if isinstance(value, dict):
        return "; ".join(f"{key}: {item}" for key, item in value.items())
    if isinstance(value, (bool, np.bool_)):
        return "ใช่" if value else "ไม่ใช่"
    if isinstance(value, str):
        statuses = {"incomplete": "ข้อมูลยังไม่ครบ", "both_positive": "ทั้งสองมีผลคัดกรองบวก", "one_positive": "หนึ่งรายมีผลคัดกรองบวก", "negative": "ทั้งสองมีผลลบในรายการที่ตรวจ"}
        origins = {"demo": "ข้อมูลสมมติ", "manual": "กรอกด้วยตนเอง", "csv": "นำเข้า CSV", "unknown": "ไม่ได้บันทึกที่มา"}
        return {**CALL_LABELS, **SEX_LABELS, **RISK_LABELS, **statuses, **origins}.get(value, value)
    return value


def _display_frame(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.copy()
    for column in work.columns:
        work[column] = work[column].map(_display_value)
    return work.rename(columns=COLUMN_LABELS)


def _threshold_controls() -> dict[str, float]:
    with st.expander("เกณฑ์การประเมินตาม SOP ของห้องปฏิบัติการ", expanded=False, icon=":material/tune:"):
        st.caption("ผลประเมินและรายงานบันทึกเกณฑ์ที่ใช้จริง ต้องกดประเมินใหม่หลังเปลี่ยนค่า")
        override_indices = st.checkbox("กำหนด MCV/MCH เอง (ใช้แทนเกณฑ์ตามอายุ)", value=False, key="screening_override_indices", persist_state="session")
        first, second, third = st.columns(3)
        with first:
            hba2 = st.slider("เกณฑ์ HbA2 ที่แยกวัด (%)", 3.0, 4.5, float(DEFAULT_THRESHOLDS["hba2_beta_trait"]), 0.1, key="screening_threshold_hba2", persist_state="session")
        with second:
            mcv = st.slider("เกณฑ์ MCV ที่กำหนดเอง (fL)", 70.0, 85.0, float(DEFAULT_THRESHOLDS["mcv_microcytosis"]), 0.5, key="screening_threshold_mcv", disabled=not override_indices, persist_state="session")
        with third:
            mch = st.slider("เกณฑ์ MCH ที่กำหนดเอง (pg)", 24.0, 29.0, float(DEFAULT_THRESHOLDS["mch_hypochromia"]), 0.5, key="screening_threshold_mch", disabled=not override_indices, persist_state="session")
        st.caption("ระบบประเมินร่วมเลือกเกณฑ์ตามอายุและวิธีตรวจ ดูเกณฑ์ที่ใช้จริงในผลลัพธ์")
    thresholds = {"hba2_beta_trait": hba2}
    if override_indices:
        thresholds.update({"mcv_microcytosis": mcv, "mch_hypochromia": mch})
    return thresholds


def _optional_number(key: str, defaults: dict[str, Any], label: str | None = None, step: float = 0.1) -> float | None:
    return st.number_input(label or COLUMN_LABELS[key], value=_number(defaults.get(key)), step=step, format="%.3f" if key == "age" else "%.2f", key=f"screening_input_{key}", placeholder="เว้นว่างหากไม่มีผลตรวจ", persist_state="session")


def _call_input(key: str, defaults: dict[str, Any]) -> str:
    options = list(CALL_LABELS)
    default = defaults.get(key, "Not performed")
    return st.selectbox(COLUMN_LABELS[key], options, index=options.index(default) if default in options else 0, format_func=CALL_LABELS.get, key=f"screening_input_{key}", persist_state="session")


def _history_input(key: str, defaults: dict[str, Any]) -> bool | str:
    value = defaults.get(key)
    default = ("Yes" if value else "No") if isinstance(value, (bool, np.bool_)) else "Not performed"
    choice = st.selectbox(COLUMN_LABELS[key], list(HISTORY_LABELS), index=list(HISTORY_LABELS).index(default), format_func=HISTORY_LABELS.get, key=f"screening_input_{key}", persist_state="session")
    return {"Yes": True, "No": False, "Not performed": "Not performed"}[choice]


def _patient_form() -> tuple[bool, dict[str, Any]]:
    source = st.radio("เริ่มต้นข้อมูล", ["กรอกข้อมูลใหม่", "ใช้ข้อมูลตัวอย่าง"], horizontal=True, key="screening_single_source", on_change=_reset_single_form, persist_state="session")
    defaults: dict[str, Any] = {}
    if source == "ใช้ข้อมูลตัวอย่าง":
        examples = example_screening_dataframe().reset_index(drop=True)
        if not examples.empty:
            choice = st.selectbox("เลือกข้อมูลสมมติ", list(range(len(examples))), format_func=lambda position: f"ตัวอย่างที่ {position + 1}", key="screening_demo_index", on_change=_reset_single_form, persist_state="session")
            defaults = examples.iloc[choice].to_dict()
        st.caption(":material/science: กำลังใช้ข้อมูลสมมติ ต้องกดประเมินก่อนแสดงผล")
    st.caption("ค่าที่แก้ไขจะคงอยู่ระหว่างเปลี่ยนหน้าในเซสชันนี้ กดประเมินเพื่ออัปเดตผลและรายงาน")
    st.session_state.setdefault("screening_case_id", f"CASE-{uuid4().hex[:10].upper()}")
    st.caption(f"รหัสตัวอย่างสมมติ: {st.session_state['screening_case_id']} · ไม่ต้องกรอกชื่อหรือ HN")
    method = st.radio("วิธีแยกฮีโมโกลบิน", ["HPLC", "CZE"], index=1 if defaults.get("hb_method") == "CZE" else 0, horizontal=True, key="screening_method", on_change=_clear_single_result, persist_state="session")
    row: dict[str, Any] = {"sample_id": st.session_state["screening_case_id"], "hb_method": method}
    with pastel_card("screening_card_inputs", "sky"):
        section("1 · ข้อมูลประกอบตัวอย่าง")
        age_column, sex_column = st.columns(2)
        with age_column:
            row["age"] = _optional_number("age", defaults, "อายุ (ปีทศนิยม เช่น 0.5 = 6 เดือน)", 0.01)
        with sex_column:
            options = list(SEX_LABELS)
            default = defaults.get("sex", "Not specified")
            row["sex"] = st.selectbox("เพศที่ใช้เลือกเกณฑ์อ้างอิง", options, index=options.index(default) if default in options else 0, format_func=SEX_LABELS.get, key="screening_input_sex", persist_state="session")
        with st.expander("ประวัติและผลสเมียร์ประกอบ", expanded=True, icon=":material/clinical_notes:"):
            columns = st.columns(2)
            for position, field in enumerate(("pregnant", "transfusion_recent", "family_history", "smear_target_cells")):
                with columns[position % 2]:
                    row[field] = _history_input(field, defaults)
        section("2 · CBC และสถานะธาตุเหล็ก", "เว้นช่องที่ไม่มีผลตรวจไว้ ช่องว่างจะไม่ถูกแทนด้วยศูนย์")
        columns = st.columns(3)
        for position, field in enumerate(("hb_g_dl", "rbc_10e12_l", "hct_percent", "mcv_fl", "mch_pg", "mchc_g_dl", "rdw_percent", "retic_percent", "ferritin_ng_ml")):
            with columns[position % 3]:
                row[field] = _optional_number(field, defaults)
        section("3 · ผลคัดกรองเบื้องต้น")
        first, second = st.columns(2)
        with first:
            options = ["Not performed", "OF", "NESTROFT"]
            default = defaults.get("of_method", "Not performed")
            row["of_method"] = st.selectbox("วิธีตรวจ osmotic fragility", options, index=options.index(default) if default in options else 0, format_func=lambda value: "ยังไม่ได้ตรวจ / ไม่ระบุ" if value == "Not performed" else value, key="screening_input_of_method", persist_state="session")
            row["oft"] = _call_input("oft", defaults)
        with second:
            row["dcip"] = _call_input("dcip", defaults)
            row["hbh_inclusion"] = _call_input("hbh_inclusion", defaults)
        section("4 · ผลแยกฮีโมโกลบิน")
        st.caption("กรอกเฉพาะค่าที่รายงานจริง HbA2 ที่แยกวัดและ HbA2/E รวมเป็นคนละข้อมูล")
        columns = st.columns(3)
        fields = ["hba_percent", "hba2_percent", "hbf_percent", "hbe_percent", "bart_percent", "hbh_percent", "hbcs_percent"]
        if method == "HPLC":
            fields.insert(1, "hba2e_percent")
            st.caption("ช่อง HbA2 และ HbE ที่แยกวัด ใช้เมื่อรายงานวิธีตรวจยืนยันว่าแยกได้ ไม่คัดลอกค่าพีครวม HbA2/E มาใส่")
        else:
            row["hba2e_percent"] = None
        for position, field in enumerate(fields):
            with columns[position % 3]:
                row[field] = _optional_number(field, defaults)
        submitted = st.button("ประเมินผลคัดกรอง", key="screening_single_submit", type=primary_action_type(), width="stretch", icon=":material/analytics:")
    return submitted, row


def _render_result_messages(result: Any) -> None:
    for error in result.validation_errors:
        st.error(error)
    for warning in result.validation_warnings:
        st.warning(warning)
    evidence_column, recommendations_column = st.columns(2)
    with evidence_column:
        with pastel_card("screening_card_evidence", "lavender"):
            _messages("หลักฐานจากข้อมูล", result.evidence)
            _messages("จีโนไทป์ที่ควรตรวจยืนยัน", result.suspected_genotypes)
    with recommendations_column:
        with pastel_card("screening_card_recommendations", "mint"):
            _messages("ข้อเสนอแนะ", result.recommendations)
            _messages("ประเด็นให้คำปรึกษา", result.counseling)
            _messages("ข้อจำกัดการแปลผล", result.caveats)


def _submit_partner_screening() -> None:
    """Update the saved snapshot before the page renders the submitted form."""
    result = st.session_state.get("screening_single_result")
    if result is None:
        return
    updated_row = {
        **result.normalized,
        "partner_oft": st.session_state.get("screening_partner_oft", "Not performed"),
        "partner_dcip": st.session_state.get("screening_partner_dcip", "Not performed"),
    }
    updated_result = analyze_screening(updated_row, st.session_state["screening_single_thresholds"], input_origin=result.input_origin)
    st.session_state["screening_single_result"] = updated_result
    st.session_state["screening_partner_result"] = updated_result.partner_screening


def _render_partner(result: Any) -> None:
    section("ข้อมูลคัดกรองของคู่", "เสนอการตรวจเพิ่มเติมจาก OF/DCIP ไม่คำนวณความเสี่ยงทารกจากผลคัดกรองเพียงอย่างเดียว")
    patient_oft = result.normalized.get("oft", "Not performed")
    patient_dcip = result.normalized.get("dcip", "Not performed")
    with pastel_card("screening_card_partner", "peach"):
        st.caption(f"ตัวอย่างนี้: OF / NESTROFT = {CALL_LABELS.get(patient_oft, patient_oft)} · DCIP = {CALL_LABELS.get(patient_dcip, patient_dcip)}")
        with st.container(border=True):
            left, right = st.columns(2)
            with left:
                st.selectbox("ผล OF / NESTROFT ของคู่", list(CALL_LABELS), format_func=CALL_LABELS.get, key="screening_partner_oft", persist_state="session")
            with right:
                st.selectbox("ผล DCIP ของคู่", list(CALL_LABELS), format_func=CALL_LABELS.get, key="screening_partner_dcip", persist_state="session")
            st.button("ประเมินข้อมูลคัดกรองของคู่", key="screening_partner_submit", icon=":material/group:", on_click=_submit_partner_screening)
        if any(st.session_state.get(key, "Not performed") != result.normalized.get(field, "Not performed")
               for key, field in (("screening_partner_oft", "partner_oft"), ("screening_partner_dcip", "partner_dcip"))):
            st.warning("ข้อมูลของคู่ถูกแก้ไขแล้ว ผลและไฟล์ดาวน์โหลดยังใช้ข้อมูลครั้งก่อน กดประเมินข้อมูลคัดกรองของคู่เพื่ออัปเดต")
        assessment = st.session_state.get("screening_partner_result")
        if assessment:
            st.info(assessment.get("interpretation", ""))
            _messages("ข้อเสนอแนะสำหรับคู่", assessment.get("recommendations", []))


def _fraction_plot_data(row: dict[str, Any]) -> tuple[list[float], str, str]:
    """Select one representation of Hb channels, matching validation precedence."""
    method = row.get("hb_method", "HPLC")
    combined = _number(row.get("hba2e_percent")) if method == "HPLC" else None
    measured_a2 = _number(row.get("hba2_percent"))
    measured_e = _number(row.get("hbe_percent"))
    resolved_pair = measured_a2 is not None and measured_e is not None
    use_combined = combined is not None and not resolved_pair
    chart_method = "HPLC (HbA2 แยกวัด)" if method == "HPLC" and not use_combined else method
    second_fraction = combined if use_combined else measured_a2
    separate_e = None if use_combined else measured_e
    fractions = [_number(row.get("hba_percent")), second_fraction, _number(row.get("hbf_percent")), separate_e, _number(row.get("bart_percent")), _number(row.get("hbh_percent")), _number(row.get("hbcs_percent"))]
    plot_fractions = [np.nan if value is None else value for value in fractions]
    note = ""
    if use_combined:
        note = "แสดง HbA2/E เป็นพีครวม จึงไม่บวก HbA2 หรือ HbE ที่แยกวัดซ้ำในกราฟนี้"
    elif combined is not None and resolved_pair:
        note = "มี HbA2 และ HbE ที่แยกวัดครบ จึงใช้สองค่านี้ตามลำดับที่ระบบตรวจข้อมูลเลือก และไม่บวกพีครวม HbA2/E ซ้ำ"
    return plot_fractions, chart_method, note


def _render_single_charts(result: Any) -> None:
    row = result.normalized
    plot_fractions, chart_method, channel_note = _fraction_plot_data(row)
    has_fractions = any(np.isfinite(value) and value > 0 for value in plot_fractions)
    scores = {"รูปแบบ β-thal": result.beta_trait_score, "รูปแบบ α-thal / HbH": result.alpha_trait_score, "รูปแบบ HbE": result.hbe_score, "รูปแบบขาดธาตุเหล็ก": result.iron_deficiency_score}
    section("ภาพประกอบผลคัดกรอง", "คะแนนเป็นการสรุปกฎ ไม่ใช่ความน่าจะเป็นของโรค")
    board, analytical, reflex = st.tabs(["ภาพรวมผลตรวจ", "รูปแบบฮีโมโกลบิน", "แนวทางตรวจต่อ"])
    with board:
        score_column, fraction_column = st.columns(2)
        with score_column:
            plotly_chart(score_radar(scores), width="stretch", theme=None, alt="คะแนนสนับสนุนแต่ละรูปแบบจากระบบกฎ ไม่ใช่ความน่าจะเป็น")
        with fraction_column:
            if has_fractions:
                plotly_chart(hb_fraction_donut(*plot_fractions, method=chart_method), width="stretch", theme=None, alt="สัดส่วนฮีโมโกลบินที่รายงานจริง ไม่รวมค่าที่ไม่ได้ตรวจ")
                if channel_note:
                    st.caption(channel_note)
            else:
                st.info("ยังไม่มีสัดส่วนฮีโมโกลบินที่ใช้สร้างกราฟได้")
        if any(_number(row.get(field)) is not None for field in ("hb_g_dl", "rbc_10e12_l", "mcv_fl", "mch_pg", "rdw_percent")):
            plotly_chart(cbc_reference_bars(row, thresholds=result.thresholds_used), width="stretch", theme=None, alt="ค่าตรวจ CBC และ ferritin เทียบจุดตัดที่ใช้จริง แต่ละแถวมีหน่วยต่างกัน")
    with analytical:
        st.caption("แผนภาพสังเคราะห์จากค่าร้อยละที่กรอก ไม่ใช่ chromatogram หรือ electropherogram จากเครื่องตรวจ")
        if has_fractions:
            plotly_chart(hplc_chromatogram(*plot_fractions, method=chart_method), width="stretch", theme=None, alt="แผนภาพสังเคราะห์จากค่าฮีโมโกลบิน ไม่ใช่ผลจากเครื่องตรวจ")
        else:
            st.info("ยังไม่มีสัดส่วนฮีโมโกลบินที่ใช้สร้างแผนภาพได้")
    with reflex:
        plotly_chart(reflex_sankey(result), width="stretch", theme=None, alt="เส้นทางจากผลคัดกรองสู่ข้อเสนอแนะของระบบกฎ")


def _render_single_downloads(result: Any) -> None:
    with pastel_card("screening_card_downloads", "rose"):
        st.markdown("**ดาวน์โหลดผลประเมิน**")
        st.caption("ทุกไฟล์ใช้ข้อมูลและเกณฑ์จากผลที่ส่งครั้งล่าสุด เป็นร่างสำหรับทบทวน")
        st.caption(f"ที่มาของข้อมูล: {_display_value(result.input_origin)} · ประเมินเมื่อ {result.evaluated_at}")
        with st.container(horizontal=True):
            st.download_button("รายงาน Markdown", screening_report_markdown(result).encode("utf-8"), f"{result.sample_id}_consult.md", "text/markdown", icon=":material/description:")
            st.download_button("ข้อมูล JSON", to_json_bytes(result), f"{result.sample_id}_consult.json", "application/json", icon=":material/data_object:")
            st.download_button("ผลประเมิน CSV", screening_report_csv(result), f"{result.sample_id}_consult.csv", "text/csv", icon=":material/download:")


def _render_clinical_grouping(result: Any) -> None:
    grouping = getattr(result, "clinical_grouping", {})
    if not grouping:
        return
    with st.container(border=True):
        st.markdown("**กลุ่มผลและขั้นตอนทบทวน**")
        st.caption("ร่างการจัดกลุ่มรอผู้เชี่ยวชาญทบทวน อาจมีหลายกลุ่มร่วมกัน ไม่ยืนยันหรือตัดการเป็นพาหะ")
        for label in grouping.get("group_labels", []):
            st.markdown(f"- {label}")
        for step in grouping.get("next_actions", []):
            st.write(f"{step['owner']}: {step['action']}")
        with st.expander("ข้อจำกัดและข้อความรายงาน", icon=":material/description:"):
            _messages("สิ่งที่ยังต้องทบทวน", grouping.get("uncertainty_reasons", []))
            st.markdown("**สำหรับผู้ประกอบวิชาชีพ**")
            st.write(grouping.get("clinician_summary", ""))
            st.markdown("**ร่างคำอธิบายผู้รับบริการ — ต้องให้ผู้ประกอบวิชาชีพทบทวนก่อนส่งต่อ**")
            st.write(grouping.get("patient_summary", ""))


def _render_single(thresholds: dict[str, float]) -> None:
    submitted, row = _patient_form()
    if submitted:
        _clear_single_result()
        origin = "demo" if st.session_state["screening_single_source"] == "ใช้ข้อมูลตัวอย่าง" else "manual"
        st.session_state["screening_single_result"] = analyze_screening(row, thresholds, input_origin=origin)
        st.session_state["screening_single_thresholds"] = dict(thresholds)
        st.session_state["screening_single_inputs"] = dict(row)
    result = st.session_state.get("screening_single_result")
    if result is None:
        st.info("กรอกผลตรวจแล้วกดประเมิน ระบบจะไม่วิเคราะห์ข้อมูลก่อนส่งแบบฟอร์ม")
        return
    if st.session_state.get("screening_single_thresholds") != thresholds:
        st.warning("เกณฑ์บนหน้าจอเปลี่ยนแล้ว ผลด้านล่างยังเป็นผลที่ส่งครั้งก่อน กรุณากดประเมินใหม่เพื่อใช้เกณฑ์ใหม่")
    saved_inputs = st.session_state.get("screening_single_inputs")
    if saved_inputs is not None and row != saved_inputs:
        st.warning("แบบฟอร์มถูกแก้ไขแล้ว ผลและไฟล์ดาวน์โหลดด้านล่างยังใช้ข้อมูลครั้งก่อน กดประเมินผลคัดกรองเพื่ออัปเดต")
    section("สรุปผลประเมิน", f"รหัสตัวอย่าง: {result.sample_id}")
    st.warning("กฎฉบับร่าง · ยังไม่ผ่านการตรวจสอบความใช้ได้ทางคลินิก — คะแนนและระดับการทบทวนยังไม่ได้สอบเทียบ ไม่ใช่ความน่าจะเป็นของโรค")
    st.caption("ผลด้านล่างอ้างอิงข้อมูลที่ส่งครั้งล่าสุด หากแก้แบบฟอร์มแล้วต้องกดประเมินอีกครั้ง")
    valid = not result.validation_errors and result.consult_risk != "Invalid / incomplete"
    first, second, third = st.columns(3)
    with first:
        level = {"Critical review": "danger", "High": "high", "Moderate": "moderate", "Invalid / incomplete": "warn"}.get(result.consult_risk, "info")
        metric_card("ระดับการทบทวนตามกฎร่าง", RISK_LABELS.get(result.consult_risk, result.consult_risk), "ยังไม่ได้สอบเทียบกับผลยืนยัน", level)
    with second:
        metric_card("คะแนนรูปแบบที่ยังไม่สอบเทียบ", f"{result.consult_score:g}/100" if valid else "—", "คะแนนตามกฎ ไม่ใช่โอกาสเกิดโรค", "info")
    with third:
        metric_card("รุ่นชุดกฎ", result.ruleset_version, "ตรวจสอบกฎและเกณฑ์ในรายละเอียด", "info")
    st.info(result.top_pattern)
    if result.confidence_note:
        st.caption(result.confidence_note)
    _render_result_messages(result)
    _render_clinical_grouping(result)
    _render_single_downloads(result)
    assessment = getattr(result, "ee_assessment", {})
    if assessment:
        with st.expander("EE score: เงื่อนไขและข้อจำกัด", icon=":material/info:"):
            if assessment.get("applicable") and _number(assessment.get("score")) is not None:
                st.metric("EE score", f"{float(assessment['score']):.2f}")
            st.info(assessment.get("interpretation", "ยังไม่มีผลประเมิน EE ที่ใช้ได้สำหรับข้อมูลนี้"))
    if valid:
        with st.expander("เพิ่มผลคัดกรองของคู่ (ถ้ามี)", icon=":material/group:"):
            _render_partner(result)
        _render_single_charts(result)
    else:
        st.info("ยังไม่แสดงกราฟคะแนนหรือคำประเมินของคู่สำหรับแถวที่ข้อมูลไม่ถูกต้อง / ไม่เพียงพอ กรุณาแก้ไขแล้วส่งใหม่")
    with st.expander("รายละเอียดข้อมูล ดัชนี และเกณฑ์ที่ใช้จริง", icon=":material/manage_search:"):
        dataframe(_display_frame(pd.DataFrame([result.normalized])), width="stretch", hide_index=True)
        dataframe(pd.DataFrame([{"ดัชนี": COLUMN_LABELS.get(key, key), "ค่า": value} for key, value in result.derived.items()]), width="stretch", hide_index=True)
        st.json(result.thresholds_used)
        _messages("รหัสกฎที่ใช้", result.rule_ids)


def _has_validation_errors(value: Any) -> bool:
    if isinstance(value, (list, tuple)):
        return bool(value)
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() not in {"", "[]", "nan", "None"}
    try:
        return not bool(pd.isna(value))
    except (TypeError, ValueError):
        return True


def _valid_batch_mask(results: pd.DataFrame) -> pd.Series:
    mask = results["consult_risk"].ne("Invalid / incomplete")
    if "validation_errors" in results:
        mask &= ~results["validation_errors"].map(_has_validation_errors)
    return mask


def _add_experimental_similarity(results: pd.DataFrame, valid_mask: pd.Series) -> pd.DataFrame:
    """Assign by row position, so repeated IDs cannot multiply input rows."""
    work = results.copy().reset_index(drop=True)
    positions = np.flatnonzero(valid_mask.to_numpy())
    if not len(positions):
        return work
    inputs = work.iloc[positions][[column for column in SCREENING_COLUMNS if column in work]].reset_index(drop=True)
    similarity = phenotype_similarity(inputs).reset_index(drop=True)
    if len(similarity) != len(positions):
        st.error("ส่วนทดลองคืนจำนวนแถวไม่ตรงกับข้อมูล จึงไม่แสดงคะแนนความคล้าย")
        return work
    for column in similarity.columns:
        if column != "sample_id":
            values = pd.Series([None] * len(work), dtype=object)
            values.iloc[positions] = similarity[column].to_numpy()
            work[column] = values
    return work


def _render_batch_charts(valid_results: pd.DataFrame) -> None:
    if valid_results.empty:
        st.info("ไม่มีแถวที่ผ่านการตรวจข้อมูลสำหรับสร้างกราฟ แถวที่มีปัญหายังคงอยู่ในตารางและรายงาน")
        return
    section("ภาพรวมชุดข้อมูล", "กราฟใช้เฉพาะแถวที่ข้อมูลผ่านการตรวจสอบ")
    st.warning("ระดับการทบทวนและคะแนนในกราฟมาจากกฎฉบับร่างที่ยังไม่ได้สอบเทียบ ไม่ใช่ความเสี่ยงหรือความน่าจะเป็นของโรค")
    first, second = st.columns(2)
    with first:
        plotly_chart(batch_risk_distribution(valid_results), width="stretch", theme=None, alt="จำนวนตัวอย่างในแต่ละระดับการทบทวนตามกฎร่าง ไม่ใช่ความเสี่ยงโรคที่สอบเทียบแล้ว")
    with second:
        plotly_chart(score_heatmap(valid_results), width="stretch", theme=None, alt="คะแนนสนับสนุนแต่ละรูปแบบจากกฎที่ยังไม่สอบเทียบ อ่านตัวเลขได้จากตารางผล")
    scatter_rows = valid_results.copy()
    for field in ("mcv_fl", "hba2_percent"):
        if field not in scatter_rows:
            scatter_rows[field] = np.nan
        scatter_rows[field] = pd.to_numeric(scatter_rows[field], errors="coerce")
    scatter_rows = scatter_rows[np.isfinite(scatter_rows["mcv_fl"]) & np.isfinite(scatter_rows["hba2_percent"])]
    if scatter_rows.empty:
        st.info("ยังไม่มีแถวที่มีทั้ง MCV และ HbA2 ที่แยกวัดสำหรับกราฟกระจาย ไม่ใช้ HbA2/E รวมแทน HbA2")
    else:
        plotly_chart(batch_mcv_hba2_scatter(scatter_rows), width="stretch", theme=None, alt="ความสัมพันธ์ระหว่าง MCV และ HbA2 ที่แยกวัดในแถวที่ผ่านการตรวจข้อมูล")
    plotly_chart(population_sankey(valid_results), width="stretch", theme=None, alt="การจัดกลุ่มรูปแบบของตัวอย่างที่ผ่านการตรวจข้อมูลเพื่อทบทวน ไม่ใช่ผลวินิจฉัย")


def _render_batch(thresholds: dict[str, float]) -> None:
    section("ประเมินชุดข้อมูล CSV", "ทุกแถวจะมีผลตรวจข้อมูล แถวที่ผิดพลาดจะไม่ถูกลบทิ้ง")
    st.caption("ใช้หัวคอลัมน์ภาษาอังกฤษตามไฟล์ตัวอย่าง ห้ามใส่ชื่อผู้ป่วยหรือ HN ระบบใช้รหัส CASE ใหม่ตามลำดับแถวแทนรหัสเดิม")
    with st.expander("คอลัมน์ที่ระบบรองรับ"):
        st.caption("หน่วยยึดตามชื่อคอลัมน์ เช่น hb_g_dl ใช้ g/dL และ mcv_fl ใช้ fL หากมีคอลัมน์กำกับหน่วยใช้ชื่อ เช่น hb_g_dl_unit; หน่วยไม่ตรงจะระงับผล ระบบไม่แปลงหน่วยอัตโนมัติ")
        dataframe(pd.DataFrame([{"คอลัมน์ CSV": field, "ความหมาย": COLUMN_LABELS.get(field, field)} for field in SCREENING_COLUMNS]), width="stretch", hide_index=True)
    template = example_screening_dataframe()
    st.download_button("ดาวน์โหลดตัวอย่าง CSV", template.to_csv(index=False).encode("utf-8-sig"), "example_screening.csv", "text/csv")
    source = st.radio("แหล่งชุดข้อมูล", ["อัปโหลด CSV", "ใช้ชุดข้อมูลตัวอย่าง"], horizontal=True, key="screening_batch_source", on_change=_clear_batch_result, persist_state="session")
    with pastel_card("screening_card_batch_inputs", "lavender"):
        uploaded = None
        if source == "อัปโหลด CSV":
            uploaded = st.file_uploader("เลือกไฟล์ CSV", type=["csv"], key="screening_batch_upload", on_change=_capture_batch_upload)
            if uploaded is not None:
                st.session_state["screening_batch_upload_bytes"] = uploaded.getvalue()
            elif "screening_batch_upload_bytes" in st.session_state:
                st.caption("ไฟล์ CSV ที่เลือกไว้ยังอยู่ในเซสชันนี้ เลือกไฟล์ใหม่เพื่อแทนที่ หรือล้างข้อมูลคัดกรองหน้านี้")
        else:
            st.info("ระบบจะประเมินข้อมูลสมมติเมื่อกดปุ่มด้านล่าง")
        submitted = st.button("ประเมินชุดข้อมูล", key="screening_batch_submit", type=primary_action_type(), width="stretch", icon=":material/analytics:")
    if submitted:
        _clear_batch_result()
        try:
            if source == "อัปโหลด CSV":
                csv_data = st.session_state.get("screening_batch_upload_bytes")
                if csv_data is None:
                    raise ScreeningCSVError("กรุณาเลือกไฟล์ CSV ก่อนกดประเมิน")
                frame, notes = read_screening_csv(csv_data, SCREENING_COLUMNS)
            else:
                frame = deidentify_demo(template, SCREENING_COLUMNS)
                notes = ["ชุดข้อมูลนี้เป็นข้อมูลสมมติสำหรับทดลองการทำงาน"]
            origin = "csv" if source == "อัปโหลด CSV" else "demo"
            results = analyze_dataframe(frame, thresholds, input_origin=origin).reset_index(drop=True)
            if len(results) != len(frame):
                st.error("จำนวนแถวผลลัพธ์ไม่ตรงกับข้อมูลนำเข้า จึงหยุดแสดงผล กรุณาทบทวนระบบประเมิน")
            else:
                st.session_state["screening_batch_results"] = results
                st.session_state["screening_batch_thresholds"] = dict(thresholds)
                st.session_state["screening_batch_notes"] = notes
                if source == "อัปโหลด CSV":
                    st.session_state["screening_batch_input_digest"] = sha256(csv_data).hexdigest()
        except ScreeningCSVError as exc:
            st.error(str(exc))
        except (ValueError, TypeError, pd.errors.ParserError, pd.errors.EmptyDataError):
            st.error("ประเมินไฟล์นี้ไม่ได้ กรุณาตรวจหัวคอลัมน์และรูปแบบข้อมูลเทียบไฟล์ตัวอย่าง")
    stored = st.session_state.get("screening_batch_results")
    if stored is None:
        st.info("ยังไม่มีผลชุดข้อมูล เลือกไฟล์หรือข้อมูลตัวอย่างแล้วกดประเมิน")
        return
    if stored.empty:
        st.info("ไม่มีแถวข้อมูลสำหรับแสดงผล")
        return
    st.caption("ผลและไฟล์ดาวน์โหลดอ้างอิงชุดข้อมูลที่กดประเมินครั้งล่าสุด หากเปลี่ยนไฟล์ให้กดประเมินชุดข้อมูลอีกครั้ง")
    if _batch_upload_changed():
        st.warning("ไฟล์ CSV ถูกเปลี่ยนหรือนำออกแล้ว ผลและไฟล์ดาวน์โหลดด้านล่างยังเป็นชุดข้อมูลที่ประเมินก่อนหน้า กรุณาเลือกไฟล์ที่ต้องการและกดประเมินชุดข้อมูลใหม่")
    for note in st.session_state.get("screening_batch_notes", []):
        st.info(note)
    if st.session_state.get("screening_batch_thresholds") != thresholds:
        st.warning("เกณฑ์เปลี่ยนแล้ว ผลชุดข้อมูลยังใช้เกณฑ์ที่ส่งครั้งก่อน กรุณากดประเมินชุดข้อมูลใหม่")
    results = stored.copy().reset_index(drop=True)
    valid_mask = _valid_batch_mask(results)
    urgent_count = int(results["severe_anemia_flag"].eq(True).sum()) if "severe_anemia_flag" in results else 0
    if urgent_count:
        st.error(f"ระบบแจ้งเตือน Hb ต่ำรุนแรง {urgent_count} แถว ต้องทบทวนเร่งด่วน รวมถึงแถวที่ข้อมูลส่วนอื่นไม่ถูกต้อง กรุณาดูรายละเอียดและข้อเสนอแนะจากระบบประเมิน")
    first, second, third, fourth = st.columns(4)
    with first:
        metric_card("จำนวนแถวทั้งหมด", str(len(results)), "คงทุกแถวตามลำดับนำเข้า", "info")
    with second:
        metric_card("ผ่านการตรวจข้อมูล", str(int(valid_mask.sum())), "ใช้ในการแสดงกราฟ", "info")
    with third:
        metric_card("ข้อมูลผิด / ไม่เพียงพอ", str(int((~valid_mask).sum())), "ดูข้อผิดพลาดในตาราง", "moderate")
    with fourth:
        high_count = int(results["consult_risk"].isin(["High", "Critical review"]).sum())
        metric_card("ควรทบทวนลำดับสูง", str(high_count), "จากทุกแถว รวมข้อมูลที่ต้องแก้ไข", "high")
    if st.checkbox("แสดงความคล้ายกับต้นแบบ (ส่วนทดลอง)", value=False, key="screening_experimental_ml", persist_state="session"):
        st.warning("ส่วนทดลองเปรียบเทียบกับต้นแบบที่กำหนดไว้ ไม่ใช่โมเดลวินิจฉัยที่ผ่านการฝึกหรือทดสอบ และไม่เปลี่ยนผลจากชุดกฎ")
        results = _add_experimental_similarity(results, valid_mask)
    dataframe(_display_frame(results.drop(columns=["clinical_grouping"], errors="ignore")), width="stretch", hide_index=True)
    st.download_button("ดาวน์โหลดผลทุกแถว CSV", batch_report_csv(results), "screening_results.csv", "text/csv", width="stretch")
    with st.expander("ชุดคุณลักษณะสำหรับงานทดลอง ML"):
        st.caption("ส่งออกเฉพาะแถวที่ผ่านการตรวจข้อมูล ค่าที่ไม่มีผลตรวจยังคงเป็นค่าว่าง")
        valid_inputs = results.loc[valid_mask, [column for column in SCREENING_COLUMNS if column in results]].reset_index(drop=True)
        if valid_inputs.empty:
            st.info("ยังไม่มีแถวที่ใช้สร้างชุดคุณลักษณะได้")
        else:
            features = ml_feature_matrix(valid_inputs)
            dataframe(_display_frame(features), width="stretch", hide_index=True)
            st.download_button("ดาวน์โหลดคุณลักษณะ ML CSV", features.to_csv(index=False).encode("utf-8-sig"), "screening_ml_features.csv", "text/csv")
    _render_batch_charts(results.loc[valid_mask].copy())


def render_screening_page() -> None:
    st.set_page_config(page_title="คัดกรองธาลัสซีเมีย | ThalLink", page_icon="🧪", layout="wide", initial_sidebar_state="auto")
    inject_css()
    top_navigation("Laboratory screening")
    hero("ThalLink: ระบบช่วยทบทวนผลธาลัสซีเมีย", "ประเมินข้อมูล CBC ธาตุเหล็ก และฮีโมโกลบิน พร้อมหลักฐาน ข้อจำกัด และแนวทางตรวจยืนยัน", "คัดกรองทางห้องปฏิบัติการ")
    disclaimer()
    note_column, clear_column = st.columns([3, 1], vertical_alignment="center")
    with note_column:
        st.caption("ข้อมูลอยู่ในหน่วยความจำของเซสชันนี้ ไม่มีการบันทึกลงฐานข้อมูล ใช้รหัสสมมติ CASE เท่านั้น")
    with clear_column:
        st.button("ล้างข้อมูลคัดกรองหน้านี้", on_click=_clear_session, width="stretch", icon=":material/restart_alt:")
    thresholds = _threshold_controls()
    mode = st.radio("รูปแบบการทำงาน", ["ประเมินตัวอย่างเดียว", "ประเมินชุดข้อมูล CSV"], horizontal=True, key="screening_mode", persist_state="session")
    if mode == "ประเมินตัวอย่างเดียว":
        _render_single(thresholds)
    else:
        _render_batch(thresholds)
    production_footer()
