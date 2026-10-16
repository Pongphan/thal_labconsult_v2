"""Hematology-focused portal with native navigation and distinct workspaces."""
from __future__ import annotations

import streamlit as st

from thalab.styles import hero, pastel_card, production_footer, section
from utils.module_registry import PLATFORM_DISCLAIMER, load_modules, navigation_groups


def render_platform_home() -> None:
    from ui.home_visuals import collection_counts, render_home_visuals
    from ui.wbc_learning import render_wbc_learning

    modules = load_modules()
    available = [module for module in modules if module.status == "draft"]
    counts = collection_counts()
    hero(
        "หน้าหลัก",
        "เลือกหัวข้อในกลุ่มเม็ดเลือดแดง เม็ดเลือดขาว หรือกลุ่มงานอื่น ๆ "
        "เพื่อทบทวนผลตรวจและเรียนรู้จากกรณีสมมติทีละขั้น",
        "ThalLink · สังเกต เชื่อมโยง เข้าใจโลหิตวิทยา",
    )
    with st.container(horizontal=True, gap="small", key="home_overview"):
        for label, value in (
            ("กลุ่มหลัก", len(navigation_groups())),
            ("โมดูลเปิดทดลอง", len(available)),
            ("พื้นที่ทบทวนผลตรวจ", sum(len(module.routes) for module in available)),
            ("กรณีสมมติสำหรับฝึก", sum(counts.values())),
        ):
            st.metric(label, f"{value:02d}", border=True, width="stretch")
    st.caption("สำหรับการเรียนรู้และทบทวนภายในเครื่อง · ใช้ข้อมูลที่ตัดการระบุตัวบุคคล · ผลเป็นร่าง ไม่ใช่การวินิจฉัย")
    render_home_visuals(counts)
    render_wbc_learning()
    section("เรียนรู้จากหลักฐานและตัวอย่าง", "อ่านแนวคิด ทดลองกรณีสมมติ และทบทวนแหล่งอ้างอิง")
    _render_learning()
    with st.expander("เกี่ยวกับแพลตฟอร์มและทีมพัฒนา", icon=":material/info:"):
        st.info(PLATFORM_DISCLAIMER)
        _render_contributors()
    production_footer()


def _render_learning() -> None:
    from ui.learning import render_learning

    render_learning()


def _render_contributors() -> None:
    section("ทีมพัฒนาและอาจารย์ที่ปรึกษา")
    contributors, advisors = st.columns(2, gap="small")
    with contributors:
        with pastel_card("home_contributors", tone="rose", height="stretch", gap="small"):
            st.subheader(":material/groups: ผู้ร่วมพัฒนา", anchor=False)
            st.markdown("- นางสาวจารวดี หมื่นจัก\n- นางสาวณัฐธิดา คำพีระเมา")
            st.caption("นักศึกษาระดับบัณฑิตศึกษา บัณฑิตวิทยาลัย มหาวิทยาลัยวลัยลักษณ์")
    with advisors:
        with pastel_card("home_advisors", tone="peach", height="stretch", gap="small"):
            st.subheader(":material/school: อาจารย์ที่ปรึกษา", anchor=False)
            st.markdown("- ผศ.ดร.เพ็ญโฉม พงศ์พนิตานนท์\n- รศ.ดร.มานิตย์ นุ้ยนุ่น")
            st.caption("อาจารย์ประจำหลักสูตรเทคนิคการแพทย์ สำนักวิชาสหเวชศาสตร์ มหาวิทยาลัยวลัยลักษณ์")
