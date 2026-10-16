"""Module learning overviews, with opt-in demonstrations isolated from forms."""
from __future__ import annotations

import streamlit as st

from logic.cbc import CBCResult
from logic.hematology_common import STATUS_LABELS
from thalab.styles import pastel_card
from ui.streamlit_compat import dataframe, plotly_chart
from utils.learning import build_learning_demo, load_learning_modules
from utils.module_registry import load_modules


def _items(title: str, values: list[str]) -> None:
    st.markdown(f"**{title}**")
    for value in values:
        st.markdown(f"- {value}")


def _render_example(module_id: str, question: str) -> None:
    st.caption("ข้อมูลสมมติสำหรับการเรียนรู้ ไม่ใช่ข้อมูลผู้ป่วย และไม่คัดลอกไปยังแบบฟอร์มของโมดูล")
    st.markdown(f"**ชวนทบทวน:** {question}")
    if module_id == "thalassemia":
        if st.toggle("แสดงภาพรวมธาลัสซีเมียและชุดข้อมูลจำลองเดิม", key="platform_show_thal_demo", persist_state="session"):
            from thalab.core import analyze_dataframe, example_screening_dataframe
            from thalab.viz import population_sankey, thalassemia_spectrum_chart

            st.caption("สีแยกกลุ่มโกลบิน ตำแหน่งและระยะห่างใช้จัดวางภาพเท่านั้น ไม่ใช่คะแนนความรุนแรง ความเสี่ยง หรือความแรงของผลตรวจ; ชี้ที่จุดเพื่ออ่านคำอธิบาย")
            plotly_chart(thalassemia_spectrum_chart(), width="stretch", alt="ภาพรวมกลุ่มธาลัสซีเมียเพื่อการเรียนรู้")
            st.caption("ข้อมูลจำลอง 6 ราย ไม่ใช่ข้อมูลผู้ป่วยหรือสัดส่วนความชุกของโรค; ระดับในกราฟเป็นระดับการทบทวนตามกฎ ไม่ใช่ความรุนแรงของโรค")
            plotly_chart(
                population_sankey(analyze_dataframe(example_screening_dataframe())),
                width="stretch", alt="รูปแบบคัดกรองจากข้อมูลจำลองธาลัสซีเมีย 6 ราย",
            )
        return
    if not st.toggle("แสดงกรณีสมมติและผลทบทวน", key=f"platform_learning_demo_{module_id}", persist_state="session"):
        return
    try:
        demo = build_learning_demo(module_id)
    except ValueError as exc:
        st.error(str(exc))
        return
    result = demo.result
    st.badge("กรณีสมมติ · ไม่ใช่ผลผู้ป่วย", color="violet", icon=":material/science:")
    st.markdown(f"**{demo.name}**")
    with st.expander("ดูข้อมูลสมมติที่ใช้และหน่วย", icon=":material/table_view:"):
        dataframe(demo.input_rows, hide_index=True, width="stretch", alt="ข้อมูลสมมติที่นำเข้าระบบกฎสำหรับหัวข้อที่เลือก")
    for error in result.validation_errors:
        st.error(f"ข้อมูลสมมติที่ต้องทบทวน: {error}")
    for warning in result.validation_warnings:
        st.warning(f"ข้อควรทบทวนในตัวอย่าง: {warning}")
    if isinstance(result, CBCResult):
        if result.low_hb_alert:
            st.error("ข้อเตือนจากข้อมูลสมมติ: Hb ต่ำที่ต้องทบทวนร่วมกับขอบเขตและบริบท")
        st.markdown(f"**{result.anemia_status}**")
        st.write(result.pattern)
        st.caption(result.support_status)
        recommendations = result.recommended_tests
    else:
        for alert in result.alerts:
            st.error(f"ข้อเตือนจากข้อมูลสมมติ: {alert}")
        st.badge(STATUS_LABELS[result.status], color={"urgent": "red", "invalid": "red", "incomplete": "orange", "review": "violet"}[result.status])
        st.caption(result.confidence_note)
        recommendations = result.recommendations
    st.caption(result.scope)
    findings, next_steps = st.columns(2, gap="medium")
    with findings:
        _items("สิ่งที่ระบบพบในตัวอย่าง", result.findings)
    with next_steps:
        _items("แนวทางทบทวนต่อจากตัวอย่าง", recommendations)
    with st.expander("เหตุผล ข้อจำกัด และรุ่นกฎของตัวอย่าง", icon=":material/fact_check:"):
        _items("เหตุผลประกอบ", result.rationale)
        _items("ข้อจำกัดของผล", result.limitations)
        _items("ประเด็นให้คำปรึกษา", result.counseling)
        st.caption(f"รุ่นกฎ {result.ruleset_version} · SHA-256 {result.ruleset_hash}")
    st.caption(result.disclaimer)


def render_learning() -> None:
    try:
        content = load_learning_modules()
    except ValueError as exc:
        st.error(str(exc))
        return
    modules = {module.id: module for module in load_modules()}
    with pastel_card("home_learning", tone="mint", gap="small"):
        st.badge(f"พื้นที่เรียนรู้ · {len(modules)} โมดูล", icon=":material/school:", color="green")
        st.subheader("การเรียนรู้และภาพรวมโลหิตวิทยา", anchor=False)
        st.caption("สำรวจข้อมูลที่ใช้ หลักการทบทวน และตัวอย่างสมมติของแต่ละโมดูล เนื้อหาเพื่อการเรียนรู้ ไม่ใช้แทนการวินิจฉัย")
        module_id = st.selectbox(
            "เลือกหัวข้อการเรียนรู้", list(modules), index=list(modules).index("thalassemia"),
            format_func=lambda key: modules[key].title, key="platform_learning_module", persist_state="session",
        )
    module, topic = modules[module_id], content[module_id]
    with pastel_card(f"learning_overview_{module_id}", tone=module_id, gap="small"):
        st.subheader(module.title, anchor=False)
        st.markdown(topic["intro"])
        overview, demo_tab, references = st.tabs(["ภาพรวมและลำดับการทบทวน", "ตัวอย่างจำลอง", "ขอบเขตและแหล่งเรียนรู้"])
        with overview:
            st.caption("ลำดับสำหรับทำความเข้าใจข้อมูล ไม่ใช่อัลกอริทึมวินิจฉัยโรค")
            for index, (column, step) in enumerate(zip(st.columns(3, gap="medium"), topic["pathway"]), 1):
                with column:
                    st.badge(f"0{index}", color="violet")
                    st.markdown(f"**{step['title']}**")
                    st.markdown(step["body"])
            _items("ประเด็นที่ควรเรียนรู้", topic["focus"])
        with demo_tab:
            _render_example(module_id, topic["example_question"])
        with references:
            _items("ข้อจำกัดสำคัญ", topic["limitations"])
            st.caption(f"ขอบเขตเครื่องมือรุ่นนี้: {module.scope}")
            st.markdown("**อ่านเพิ่มเติมจากแหล่งอ้างอิง**")
            for source in topic["sources"]:
                st.markdown(f"- [{source['title']}]({source['url']})")
            st.caption(f"ทบทวนเนื้อหาประกอบเมื่อ {topic['reviewed_on']} · ไม่ใช่การรับรองกฎของแพลตฟอร์ม")
        st.markdown("**เข้าสู่พื้นที่ทำงานที่เกี่ยวข้อง**")
        with st.container(horizontal=True, gap="small"):
            for route in module.routes:
                st.page_link(route.path, label=route.title, icon=":material/arrow_forward:")
