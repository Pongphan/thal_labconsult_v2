"""Catalog visualizations: educational structure and actual bundled examples only."""
from __future__ import annotations

import math

import plotly.graph_objects as go
import streamlit as st

from logic.examples import example_screening_dataframe
from logic.hematology_common import DOMAIN_IDS, load_domain_rules
from thalab.styles import current_theme_type, pastel_card
from thalab.viz import apply_chart_theme
from ui.palette import CARD_TONES, TEXT_TOKENS
from ui.streamlit_compat import plotly_chart
from utils.module_registry import load_modules

def collection_counts() -> dict[str, int]:
    """Count cases actually available in the workspaces, without running engines."""
    from ui.cbc import DEMO_VALUES

    return {
        "cbc_anemia": int(bool(DEMO_VALUES)),
        "thalassemia": len(example_screening_dataframe()),
        **{key: len(load_domain_rules(key)["examples"]) for key in DOMAIN_IDS},
    }


def learning_map(selected: str, counts: dict[str, int] | None = None) -> go.Figure:
    """Fixed-size nodes describe a catalog, not clinical severity or prevalence."""
    modules = load_modules()
    counts = collection_counts() if counts is None else counts
    dark = current_theme_type() == "dark"
    ink = TEXT_TOKENS["dark" if dark else "light"]["ink"]
    fig = go.Figure()
    for index, module in enumerate(modules):
        angle = math.pi / 2 - index * 2 * math.pi / len(modules)
        x, y = math.cos(angle), math.sin(angle)
        tone = CARD_TONES[module.presentation.tone]
        accent = tone.dark_accent if dark else tone.accent
        fig.add_trace(go.Scatter(
            x=[0, x], y=[0, y], mode="lines", line=dict(color=accent, width=2 if module.id == selected else 1),
            opacity=0.8 if module.id == selected else 0.22, hoverinfo="skip", showlegend=False,
        ))
        fig.add_trace(go.Scatter(
            x=[x], y=[y], mode="markers+text", text=[module.presentation.short_name.replace(" & ", " &<br>")],
            textposition="top center" if y >= 0 else "bottom center", textfont=dict(size=16, color=ink),
            marker=dict(size=39, color=tone.dark if dark else tone.light,
                        line=dict(color=accent, width=4 if module.id == selected else 1.5)),
            customdata=[[module.title, len(module.routes), counts[module.id]]],
            hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]} พื้นที่ทำงาน · %{customdata[2]} กรณีสมมติ<extra></extra>",
            showlegend=False, name=module.id,
        ))
    fig.add_trace(go.Scatter(
        x=[0], y=[0], mode="markers+text", text=["ThalLink"], textfont=dict(size=21, color=ink),
        marker=dict(size=108, color="#302535" if dark else "#FFF9F7", line=dict(color="#B8829A", width=2)),
        hoverinfo="skip", showlegend=False,
    ))
    apply_chart_theme(fig, height=410)
    fig.update_layout(margin=dict(l=24, r=24, t=32, b=32), dragmode=False)
    fig.update_xaxes(visible=False, range=[-1.48, 1.48], fixedrange=True)
    fig.update_yaxes(visible=False, range=[-1.38, 1.38], fixedrange=True)
    return fig


def example_chart(counts: dict[str, int], selected: str) -> go.Figure:
    modules = load_modules()
    dark = current_theme_type() == "dark"
    tones = [CARD_TONES[module.presentation.tone] for module in modules]
    fig = go.Figure(go.Bar(
        y=[module.presentation.short_name for module in modules], x=[counts[module.id] for module in modules],
        orientation="h", marker_color=[tone.dark_accent if dark else tone.light for tone in tones],
        marker_line_color=[tone.dark_accent if dark else tone.accent for tone in tones],
        marker_line_width=[2.5 if module.id == selected else 1 for module in modules],
        text=[counts[module.id] for module in modules], textposition="outside",
        hovertemplate="%{y}<br>%{x} กรณีสมมติในพื้นที่ทำงาน<extra></extra>",
    ))
    apply_chart_theme(fig, height=365)
    fig.update_traces(marker_line_color=[tone.dark_accent if dark else tone.accent for tone in tones],
                      marker_line_width=[2.5 if module.id == selected else 1 for module in modules])
    fig.update_layout(margin=dict(l=8, r=38, t=14, b=50), bargap=0.40, dragmode=False)
    fig.update_yaxes(autorange="reversed", showgrid=False, fixedrange=True)
    fig.update_xaxes(title="จำนวนกรณีสมมติ", dtick=1, range=[0, max(counts.values()) + 1], fixedrange=True)
    return fig


def render_home_visuals(counts: dict[str, int] | None = None) -> None:
    modules = {module.id: module for module in load_modules()}
    counts = collection_counts() if counts is None else counts
    st.subheader("สำรวจโลหิตวิทยา เชื่อมข้อมูลให้เป็นภาพ", anchor=False)
    st.caption("เลือกโมดูลเพื่อดูขอบเขตและเริ่มฝึก · ชี้ที่จุดเพื่อดูชื่อและพื้นที่ทำงาน")
    left, right = st.columns([1.35, 1], gap="medium")
    # Render the selector first in Python so both charts reflect this run's choice.
    with right, pastel_card("home_explorer", "lavender", height="stretch", gap="small"):
        selected = st.selectbox("โมดูลที่ต้องการสำรวจ", list(modules), format_func=lambda key: modules[key].title,
                                key="home_explorer_module", persist_state="session")
        module = modules[selected]
        st.badge("เรียนรู้ · ทบทวน · ตั้งคำถาม", color="violet", icon=":material/school:")
        st.markdown(f"**{module.title}**")
        st.write(module.summary)
        st.caption(f"{len(module.routes)} พื้นที่ทำงาน · {counts[selected]} กรณีสมมติพร้อมให้ลอง")
        st.caption(module.scope)
        for route in module.routes:
            st.page_link(route.path, label=f"เปิด {route.title}", icon=":material/arrow_forward:", width="stretch")
    with left, st.container(border=True):
        plotly_chart(learning_map(selected, counts), key="home_learning_map", width="stretch",
                     config={"displayModeBar": False, "scrollZoom": False},
                     alt=f"แผนที่ {len(modules)} โมดูลโลหิตวิทยา จุดขนาดเท่ากัน โมดูลที่เลือกมีกรอบเน้น")
        st.caption("เส้นแสดงการจัดกลุ่มในแพลตฟอร์ม ไม่ใช่เส้นทางวินิจฉัย ขนาดและตำแหน่งไม่แทนความรุนแรง")
    charts, guidance = st.columns([1.35, 1], gap="medium")
    with charts, st.container(border=True):
        st.markdown("**คลังตัวอย่างสำหรับฝึกทบทวน**")
        plotly_chart(example_chart(counts, selected), key="home_example_counts", width="stretch",
                     config={"displayModeBar": False}, alt="จำนวนกรณีสมมติที่มีจริงในแต่ละโมดูล")
        st.caption(f"รวม {sum(counts.values())} กรณีจากข้อมูลในโปรเจกต์ · ไม่ใช่จำนวนผู้ป่วย ความชุก หรือความแม่นยำ")
    with guidance, pastel_card("home_study_path", "mint", height="stretch", gap="small"):
        st.badge("YOUR LEARNING PATH", color="green", icon=":material/route:")
        st.subheader("อ่านผลอย่างมีบริบท", anchor=False)
        for number, title, body in (
            ("01", "สังเกตข้อมูล", "เริ่มจากหน่วย อายุ วิธีตรวจ และสิ่งที่ยังไม่ทราบ"),
            ("02", "เชื่อมหลักฐาน", "ดูเหตุผล ข้อขัดแย้ง และข้อจำกัดของผลแต่ละโมดูล"),
            ("03", "ทบทวนและเรียนรู้", "เปรียบเทียบตัวอย่าง อ่านแหล่งอ้างอิง แล้วทดลองด้วยตนเอง"),
        ):
            st.markdown(f"**{number} · {title}**")
            st.caption(body)
        st.page_link("pages/3_CBC_Anemia.py", label="เริ่มฝึกจาก CBC", icon=":material/arrow_forward:")
