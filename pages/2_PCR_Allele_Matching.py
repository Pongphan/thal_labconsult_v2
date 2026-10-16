from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from ui.streamlit_compat import dataframe, plotly_chart, data_editor

from thalab.genetics import (
    ALPHA_GENOTYPES,
    BETA_GENOTYPES,
    PCR_INPUT_COLUMNS,
    PANEL_ID,
    match_pcr_bands,
    pcr_template,
    prepare_pcr_calls,
    read_pcr_csv,
)
from thalab.styles import (
    disclaimer,
    hero,
    inject_css,
    metric_card,
    pastel_card,
    section,
    production_footer,
    top_navigation,
)
from thalab.viz import (
    allele_method_bar,
    virtual_gel,
)
from ui.pcr_visuals import (
    CALL_LABELS,
    CONTROL_LABELS,
    TABLE_LABELS,
    allele_lollipop,
    cached_allele_database,
    coverage_map_summary,
    display_table,
    export_csv,
    molecular_panel,
    panel_coverage_treemap,
    render_couple_risk_results,
    select_parent_genotypes,
    workflow_stepper,
)


# -----------------------------------------------------------------------------
# Page configuration and design system
# -----------------------------------------------------------------------------

st.set_page_config(
    page_title="จับคู่แถบ PCR และความเสี่ยงพันธุกรรม | Thal Lab Consult",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

inject_css()
top_navigation("PCR allele matching")


# -----------------------------------------------------------------------------
# Page body
# -----------------------------------------------------------------------------

hero(
    "ThalLink · งานโมเลกุลและพันธุกรรมธาลัสซีเมีย",
    "ทบทวนชุดตรวจ α/β-globin จำลองการถ่ายทอด genotype และเปรียบเทียบแถบ PCR",
    "การตรวจโมเลกุลและแบบจำลองความเสี่ยง genotype",
)
disclaimer()
workflow_stepper()

st.caption("สำรวจเป้าหมาย วิธีตรวจ และชื่อ allele พร้อมหลักฐานประกอบการให้คำปรึกษา ข้อมูลชุดตรวจและขนาดแถบนี้เป็นข้อมูลสาธิต")

# Global data objects
db = cached_allele_database()

tabs = st.tabs([":material/biotech: ฐานข้อมูลชุดตรวจ", ":material/group: ความเสี่ยง genotype ของคู่", ":material/description: ส่งออกรายงาน", ":material/science: บันทึกผล PCR"])


# -----------------------------------------------------------------------------
# Tab 1: Allele knowledge base
# -----------------------------------------------------------------------------
with tabs[0]:
    section(
        ":material/biotech: ฐานข้อมูลเป้าหมายโมเลกุล",
        "สำรวจระบบ globin ประเภท variant และวิธีตรวจในฐานข้อมูลสาธิตก่อนทบทวนแถบ PCR",
    )

    total_targets = len(db)
    alpha_n = int((db["system"].astype(str).str.lower() == "alpha").sum())
    beta_n = int((db["system"].astype(str).str.lower() == "beta").sum())
    methods_n = db["method"].nunique(dropna=True)
    classes_n = db["variant_class"].nunique(dropna=True)

    cards = [
        ("เป้าหมายทั้งหมด", str(total_targets), "รายการชุดตรวจสาธิต", "info"),
        ("α-globin", str(alpha_n), "HBA deletion/nondeletion", "moderate"),
        ("β-globin", str(beta_n), "HBB β0/β+/structural", "high"),
        ("วิธีตรวจ", str(methods_n), "Gap-PCR / ARMS / sequencing", "low"),
        ("ประเภท", str(classes_n), "ประเภท variant", "info"),
    ]
    with st.container(horizontal=True, gap="small"):
        for card in cards:
            with st.container(width=210):
                metric_card(*card)

    control_left, control_right = st.columns([1.2, 0.8])
    with control_left:
        search = st.text_input("ค้นหาเป้าหมาย allele วิธีตรวจ หรือประเภท", value="", placeholder="เช่น HbE, SEA, CD41/42, gap-PCR", key="pcr_database_search", persist_state="session")
    with control_right:
        sort_mode = st.selectbox("เรียงตารางตาม", ["system", "variant_class", "method", "common_name"], index=1, format_func=lambda value: TABLE_LABELS[value], key="pcr_database_sort", persist_state="session")

    f1, f2, f3 = st.columns(3)
    with f1:
        sys_filter = st.multiselect("ระบบ globin", sorted(db["system"].dropna().astype(str).unique()), default=sorted(db["system"].dropna().astype(str).unique()), key="pcr_database_system", persist_state="session")
    with f2:
        class_filter = st.multiselect("ประเภท variant", sorted(db["variant_class"].dropna().astype(str).unique()), default=sorted(db["variant_class"].dropna().astype(str).unique()), key="pcr_database_class", persist_state="session")
    with f3:
        method_filter = st.multiselect("วิธีตรวจ", sorted(db["method"].dropna().astype(str).unique()), default=sorted(db["method"].dropna().astype(str).unique()), key="pcr_database_method", persist_state="session")

    view = db[
        db["system"].astype(str).isin(sys_filter)
        & db["variant_class"].astype(str).isin(class_filter)
        & db["method"].astype(str).isin(method_filter)
    ].copy()
    if search.strip():
        query = search.strip().lower()
        mask = view.astype(str).apply(lambda col: col.str.lower().str.contains(query, na=False, regex=False)).any(axis=1)
        view = view[mask]
    if sort_mode in view.columns:
        view = view.sort_values([sort_mode])

    coverage_map_summary(view)
    plotly_chart(panel_coverage_treemap(view), width='stretch', theme=None)

    c3, c4 = st.columns([1, 1])
    with c3:
        plotly_chart(allele_lollipop(view), width='stretch', theme=None)
    with c4:
        # Keep original project visual for compatibility, but place it as a secondary view.
        try:
            method_chart = allele_method_bar(view)
            method_chart.update_layout(title_text="จำนวนเป้าหมายตามวิธีตรวจ", legend_title_text="ระบบ globin")
            method_chart.update_xaxes(title="วิธีตรวจ")
            method_chart.update_yaxes(title="จำนวนเป้าหมาย")
            method_chart.update_traces(hovertemplate="วิธีตรวจ: %{x}<br>จำนวนเป้าหมาย: %{y}<extra>%{fullData.name}</extra>")
            plotly_chart(method_chart, width='stretch', theme=None)
        except Exception:
            plotly_chart(panel_coverage_treemap(view), width='stretch', theme=None)

    molecular_panel(
        "ข้อจำกัดของฐานข้อมูลสาธิต",
        "ชื่อ allele และขนาดแถบใช้สาธิตการทำงาน ต้องใช้ชุดตรวจและ SOP ที่ห้องปฏิบัติการตรวจสอบความใช้ได้ รวมถึง controls และระบบรายงานที่เหมาะสมก่อนใช้งานจริง",
        card_key="pcr_card_panel_limitations", tone="butter",
    )
    dataframe(display_table(view), width="stretch", hide_index=True, alt="เป้าหมาย allele หลังใช้ตัวกรอง")
    st.download_button(
        "⬇️ ดาวน์โหลดฐานข้อมูล allele ที่กรองแล้ว (CSV)",
        export_csv(display_table(view)),
        "thalassemia_filtered_allele_knowledge_base.csv",
        "text/csv",
        width='stretch',
    )


# -----------------------------------------------------------------------------
# Tab 2: Couple genotype risk
# -----------------------------------------------------------------------------
with tabs[1]:
    section(
        ":material/group: แบบจำลองการถ่ายทอด genotype ของคู่",
        "เลือกที่มาของ genotype และ genotype ของทั้งสองบุคคลด้วยตนเอง แบบจำลองไม่อนุมาน genotype จากแถบ PCR และไม่ยืนยัน phenotype ของลูก",
    )

    evidence_basis = st.selectbox(
        "ที่มาของ genotype ที่เลือกด้วยตนเอง",
        ["ข้อมูลจำลอง", "ผลยืนยันทางห้องปฏิบัติการ", "ผลอนุมานที่ยังไม่ยืนยัน"],
        index=0, key="couple_evidence_basis", persist_state="session",
    )
    st.info("ข้อมูลจำลองใช้เพื่อการเรียนรู้เท่านั้น ผลยืนยันหรือผลอนุมานต้องเลือกตามหลักฐานของทั้งสองบุคคล ไม่ใช้ชื่อหรือเลขประจำตัวผู้ป่วย")
    st.caption("แบบจำลองใช้การถ่ายทอด allele แบบ Mendelian และจัดกลุ่มความเสี่ยงอย่างง่าย ไม่พยากรณ์ความรุนแรงจริงหรือการต้องรับเลือด โดยเฉพาะ HbE/β-thalassemia และ variant ที่มีความรุนแรงแปรผัน")
    alpha_inputs, beta_inputs = st.columns(2)
    with alpha_inputs, pastel_card("pcr_card_alpha_inputs", "sky"):
        alpha_pair = select_parent_genotypes("alpha", ALPHA_GENOTYPES)
    with beta_inputs, pastel_card("pcr_card_beta_inputs", "rose"):
        beta_pair = select_parent_genotypes("beta", BETA_GENOTYPES)

    if alpha_pair:
        render_couple_risk_results("alpha", *alpha_pair, evidence_basis=evidence_basis)
    if beta_pair:
        render_couple_risk_results("beta", *beta_pair, evidence_basis=evidence_basis)
    if not alpha_pair and not beta_pair:
        st.caption("เลือก genotype ของทั้งสองบุคคลในระบบที่ต้องการ เพื่อแสดงตารางและกราฟความเสี่ยง")


# -----------------------------------------------------------------------------
# Tab 3: Export/report area
# -----------------------------------------------------------------------------
with tabs[2]:
    section(
        ":material/description: รายการรายงานและการส่งออก",
        "ดาวน์โหลดข้อมูลจากแต่ละส่วนเพื่อทบทวนร่วมกับวิธีตรวจและหลักฐาน รายงานเป็นร่างสาธิตและยังไม่ลงนาม",
    )

    molecular_panel(
        "สิ่งที่ต้องมีสำหรับการใช้งานจริง",
        "ต้องกำหนดชุด primer และ SOP ของห้องปฏิบัติการ ตรวจสอบ controls มาตรฐาน HGVS/HbVar สิทธิ์เข้าถึง และการเชื่อมต่อ LIS/LIMS ก่อนใช้งานจริง รุ่นนี้ไม่เก็บข้อมูลตัวอย่างลงไฟล์หรือฐานข้อมูล",
        card_key="pcr_card_report_requirements", tone="lilac",
    )

    report_items = pd.DataFrame(
        [
            {"ส่วนงาน": "ฐานข้อมูล allele", "ส่งออก": "CSV", "เนื้อหา": "เป้าหมายและวิธีตรวจในชุดข้อมูลสาธิต"},
            {"ส่วนงาน": "ความเสี่ยงของคู่", "ส่งออก": "CSV", "เนื้อหา": "Punnett genotype / ความเสี่ยง phenotype / ที่มาของหลักฐาน"},
            {"ส่วนงาน": "บันทึกผล PCR", "ส่งออก": "CSV", "เนื้อหา": "สถานะ controls หลักฐานแถบ และข้อจำกัดการจับคู่"},
        ]
    )
    dataframe(report_items, width="stretch", hide_index=True, alt="ตำแหน่งและเนื้อหารายงานที่ส่งออกได้ในแต่ละส่วนงาน")

    st.markdown(
        """
        **การส่งออก:** ฐานข้อมูล allele อยู่ในแท็บแรก รายงานการถ่ายทอด genotype อยู่ในแท็บคู่ และรายงานแถบ PCR อยู่ในแท็บบันทึกผล PCR ทุกไฟล์ต้องได้รับการทบทวนก่อนนำไปใช้
        """
    )



# -----------------------------------------------------------------------------
# Tab 4: Demonstration PCR call sheet, held only in this session
# -----------------------------------------------------------------------------
with tabs[3]:
    section(":material/science: บันทึกผลและจับคู่แถบ PCR", f"ชุดตรวจ {PANEL_ID} และขนาดแถบเป็นข้อมูลสาธิต ไม่ใช่ชุดตรวจที่ผ่านการตรวจสอบความใช้ได้ของห้องปฏิบัติการ")
    st.info("ใช้รหัสสมมติตัวอย่างเท่านั้น ห้ามใส่ชื่อ HN เลขประจำตัว หรือข้อมูลที่ระบุตัวบุคคล รวมถึงชื่อไฟล์ CSV การนำเข้าจะแทนรหัสเดิมด้วย PCR-001, PCR-002 ตามลำดับในหน่วยความจำ")
    st.caption("รับเฉพาะ sample_id, target_code, observed_bp, result, lane • ไม่เก็บข้อมูลลงดิสก์ log หรือ shared cache • รองรับไม่เกิน 200 แถว / 2 MB")

    def blank_calls() -> pd.DataFrame:
        return pd.DataFrame([{"sample_id": "PCR-001", "target_code": "UNKNOWN", "observed_bp": np.nan, "result": "Unknown", "lane": "L1"}])

    st.session_state.setdefault("pcr_call_sheet", blank_calls())
    st.session_state.setdefault("pcr_editor_epoch", 0)
    st.session_state.setdefault("pcr_upload_epoch", 0)
    st.session_state.setdefault("pcr_is_demo", False)
    st.session_state.setdefault("pcr_input_origin", "demo" if st.session_state["pcr_is_demo"] else "manual")
    st.session_state.setdefault("pcr_run_controls", "not_confirmed")
    st.session_state.setdefault("pcr_tolerance", 25.0)

    def reset_pcr_calls(demo: bool = False) -> None:
        st.session_state["pcr_call_sheet"] = prepare_pcr_calls(pcr_template(), pseudonymize=True) if demo else blank_calls()
        st.session_state["pcr_editor_epoch"] += 1
        st.session_state["pcr_upload_epoch"] += 1
        st.session_state["pcr_run_controls"] = "not_confirmed"
        st.session_state["pcr_tolerance"] = 25.0
        st.session_state["pcr_is_demo"] = demo
        st.session_state["pcr_input_origin"] = "demo" if demo else "manual"

    with st.container(horizontal=True):
        st.download_button("ดาวน์โหลด CSV ตัวอย่างสาธิต", export_csv(pcr_template()), "pcr_demo_template.csv", "text/csv", key="pcr_template_download", icon=":material/download:")
        st.button("โหลดข้อมูลสาธิต", key="pcr_load_demo", on_click=reset_pcr_calls, args=(True,), icon=":material/science:")
        st.button("ล้างข้อมูล PCR ในเซสชัน", key="pcr_clear", on_click=reset_pcr_calls, icon=":material/restart_alt:")

    upload = st.file_uploader("นำเข้า CSV ที่ไม่มีข้อมูลระบุตัวบุคคล", type=["csv"], key=f"pcr_upload_{st.session_state['pcr_upload_epoch']}")
    if upload is not None and st.button("นำเข้าและแทนรหัสตัวอย่าง", key="pcr_import"):
        try:
            imported, import_notes = read_pcr_csv(upload.getvalue())
            st.session_state["pcr_call_sheet"] = imported
            st.session_state["pcr_editor_epoch"] += 1
            st.session_state["pcr_run_controls"] = "not_confirmed"
            st.session_state["pcr_is_demo"] = False
            st.session_state["pcr_input_origin"] = "csv"
            st.success("นำเข้าข้อมูลที่จำเป็นและแทนรหัสตัวอย่างแล้ว ข้อความผลที่ไม่รู้จักคงสถานะไม่ทราบ")
            for note in import_notes:
                st.caption(note)
        except ValueError as exc:
            reset_pcr_calls()
            st.error(str(exc))

    if st.session_state["pcr_is_demo"]:
        st.warning("กำลังแสดงข้อมูลสาธิต ไม่ใช่ผลตัวอย่างจริง")
    assay_col, tolerance_col, controls_col = st.columns(3)
    with assay_col:
        assay_id = st.selectbox("รหัสชุดตรวจ / panel", [PANEL_ID], key="pcr_assay_id", persist_state="session")
    with tolerance_col:
        tolerance = st.number_input("ความคลาดเคลื่อนขนาดแถบ (± bp)", min_value=1.0, max_value=100.0, step=1.0, key="pcr_tolerance", persist_state="session")
    with controls_col:
        controls = st.selectbox("สถานะ controls ของ run ตาม SOP", list(CONTROL_LABELS), format_func=lambda value: CONTROL_LABELS[value], key="pcr_run_controls", persist_state="session")
    st.caption("เลือกผ่านเมื่อผู้ตรวจได้ทบทวน controls ตาม SOP แล้ว ระบบไม่ตรวจภาพ control และไม่ยืนยัน QC ให้อัตโนมัติ เมื่อยังไม่ยืนยันหรือไม่ผ่าน ระบบจะระงับข้อสรุปทุกแถว")

    editor_key = f"pcr_rows_{st.session_state['pcr_editor_epoch']}"
    # The editor stores row deltas against a stable base. Keep that base unchanged
    # during editing, and rebase from the latest snapshot after page navigation.
    if editor_key not in st.session_state or "pcr_editor_base" not in st.session_state:
        st.session_state["pcr_editor_base"] = st.session_state["pcr_call_sheet"].copy(deep=True)
    editor_source = st.session_state["pcr_editor_base"].copy(deep=True)
    editor_source["result"] = editor_source["result"].map(CALL_LABELS).fillna(CALL_LABELS["Unknown"])
    sample_options = [f"PCR-{i:03d}" for i in range(1, 201)]
    edited = data_editor(
        editor_source, key=editor_key, num_rows="dynamic", hide_index=True, width="stretch",
        alt="ตารางแก้ไขผล PCR ที่เก็บเฉพาะในเซสชัน",
        column_config={
            "sample_id": st.column_config.SelectboxColumn(TABLE_LABELS["sample_id"], options=sample_options, required=True, default="PCR-001"),
            "target_code": st.column_config.SelectboxColumn(TABLE_LABELS["target_code"], options=["UNKNOWN", *db["target_code"].tolist()], required=True, default="UNKNOWN"),
            "observed_bp": st.column_config.NumberColumn(TABLE_LABELS["observed_bp"], min_value=1.0, max_value=10000.0, step=1.0, format="%.0f"),
            "result": st.column_config.SelectboxColumn(TABLE_LABELS["result"], options=list(CALL_LABELS.values()), default=CALL_LABELS["Unknown"], required=True),
            "lane": st.column_config.TextColumn("ช่องแถบ (กำหนดตามแถว)", disabled=True),
        },
    )
    st.caption("เพิ่มหรือลบแถวในตารางได้ เว้นขนาดแถบว่างเมื่อไม่มีข้อมูล ผลที่ไม่ทราบจะไม่ถูกถือเป็นผลลบ เลือกรหัสตัวอย่างเดียวกันสำหรับเป้าหมายหลายรายการของตัวอย่างนั้น")
    st.caption("แก้ไขแล้วออกจากเซลล์เพื่อเก็บค่าในเซสชัน สลับหน้าแล้วกลับมาได้ ผล PCR อัปเดตตามตารางและ controls ปัจจุบัน")

    calls = edited.reindex(columns=PCR_INPUT_COLUMNS).reset_index(drop=True).copy()
    # Re-validate editor values server-side and discard unapproved text.
    calls["sample_id"] = calls["sample_id"].where(calls["sample_id"].isin(sample_options), "PCR-001")
    calls["target_code"] = calls["target_code"].where(calls["target_code"].isin(db["target_code"]), "UNKNOWN")
    calls["result"] = calls["result"].map({value: key for key, value in CALL_LABELS.items()}).fillna("Unknown")
    calls["lane"] = [f"L{i+1}" for i in range(len(calls))]
    # This ordinary state key survives widget cleanup. Preserve incomplete/invalid
    # numeric drafts too so users can return and correct them without losing work.
    st.session_state["pcr_call_sheet"] = calls.copy(deep=True)

    if edited.empty:
        st.info("เพิ่มแถวหรือโหลดข้อมูลสาธิตเพื่อเริ่มทบทวน")
    elif len(edited) > 200:
        st.error("ตารางเกิน 200 แถว กรุณาลดจำนวนก่อนแสดงผล")
    else:
        try:
            calls = prepare_pcr_calls(calls)
            matched = match_pcr_bands(calls, tolerance_bp=tolerance, controls_status=controls)
        except ValueError:
            st.error("ระงับผล PCR: ตรวจขนาดแถบให้เป็นตัวเลขมากกว่า 0 ถึง 10000 bp หรือเว้นว่าง และกำหนด tolerance เป็นจำนวนบวกพร้อมสถานะ controls ที่ถูกต้อง")
        else:
            if controls != "pass":
                st.warning("ระงับการแปลผลทั้งหมด: controls ยังไม่ยืนยันผ่านหรือไม่ผ่าน ทบทวนข้อมูลแถบและแก้ไขข้อขัดแย้งก่อนแปลผล")
            st.caption("คะแนนขนาดแถบ = ความใกล้เคียงกับขนาดสาธิต 0–100 ไม่ใช่ความน่าจะเป็น ความไว ความจำเพาะ หรือความมั่นใจในการวินิจฉัย คะแนนไม่ลบล้างผลที่ขัดแย้งหรือ controls ที่ไม่ผ่าน")
            output_columns = ["sample_id", "lane", "target_code", "observed_bp", "expected_bp", "result", "delta_bp", "match_score", "evidence_status", "controls_status", "match_status", "call", "interpretation"]
            dataframe(display_table(matched[output_columns]), width="stretch", hide_index=True)
            st.caption("ภาพด้านล่างเป็นภาพจำลองจากขนาดแถบที่บันทึก ไม่ใช่ภาพ gel จากเครื่อง และไม่ใช่หลักฐาน QC")
            plotly_chart(virtual_gel(matched), width="stretch", theme=None, alt="เจลจำลองตามขนาดแถบที่บันทึก ไม่ใช่ภาพเจลจริงหรือหลักฐาน QC")

            report = matched[output_columns].copy()
            evaluation = matched.attrs["evaluation"]
            report.insert(0, "ชุดตรวจ", evaluation["panel_id"])
            report.insert(1, "ข้อมูล", {"demo": "ข้อมูลสาธิต (อาจมีการแก้ไข)", "csv": "นำเข้า CSV (อาจมีการแก้ไข)", "manual": "บันทึกด้วยตนเอง"}[st.session_state["pcr_input_origin"]])
            report["input_origin"] = st.session_state["pcr_input_origin"]
            report["เวลาประเมิน (UTC+07:00)"] = evaluation["evaluated_at"]
            report["ลายนิ้วมือชุดตรวจ (SHA-256)"] = evaluation["panel_sha256"]
            report["ความคลาดเคลื่อน (bp)"] = evaluation["tolerance_bp"]
            report["ข้อจำกัดรายงาน"] = "ร่างสาธิต ยังไม่ลงนาม; ชุดตรวจและขนาดแถบยังไม่ผ่านการตรวจสอบความใช้ได้; ไม่ยืนยัน genotype หรือการวินิจฉัย; คะแนนไม่ใช่ความน่าจะเป็น"
            st.download_button("ดาวน์โหลดรายงาน PCR พร้อมสถานะ controls (CSV)", export_csv(display_table(report)), "pcr_review_report.csv", "text/csv", key="pcr_report_download", width="stretch", icon=":material/download:")


production_footer()
