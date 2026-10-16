"""An isolated, synthetic WBC balance lesson using the workspace's engine."""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from logic.white_cells import analyze_white_cells
from thalab.styles import current_theme_type, pastel_card
from thalab.viz import apply_chart_theme
from ui.palette import CARD_TONES, TEXT_TOKENS
from ui.streamlit_compat import plotly_chart


CASES = {
    "balanced": ("01 · ผลรวมเท่ากับ WBC", {"age": 35, "wbc_10e9_l": 4, "anc_10e9_l": 1, "lymphocytes_percent": 75}),
    "exceeds": ("02 · ผลรวมเกิน WBC", {"age": 35, "wbc_10e9_l": 4, "anc_10e9_l": 3, "lymphocytes_percent": 75}),
    "partial": ("03 · ข้อมูลยังไม่ครบ", {"age": 35, "wbc_10e9_l": 4, "anc_10e9_l": 1}),
}


def case_result(case: str):
    # A fresh mapping and result on every run; never read/write clinical session keys.
    return analyze_white_cells(dict(CASES[case][1]))


def balance_chart(total: dict) -> go.Figure:
    """Absolute quantities remain absolute, including values beyond total WBC."""
    dark = current_theme_type() == "dark"
    ink = TEXT_TOKENS["dark" if dark else "light"]["ink"]
    fig = go.Figure()
    labels = {"anc": "ANC · ค่าวัด", "alc": "ALC · คำนวณ"}
    for key, component in total["components"].items():
        tone = CARD_TONES["lavender" if component["source"] == "calculated" else "rose"]
        fig.add_trace(go.Bar(
            x=[component["value"]], y=["องค์ประกอบที่ทราบ"], orientation="h",
            name=labels.get(key, key.upper()), text=[f"{component['value']:g}"], textposition="inside",
            marker=dict(color=tone.light, pattern_shape="/" if component["source"] == "calculated" else ""),
            hovertemplate=f"{labels.get(key, key.upper())}: %{{x:g}} ×10⁹/L<extra></extra>",
        ))
    known, wbc = total["known_total_10e9_l"], total["wbc_10e9_l"]
    remainder = max(0, wbc - known)
    if remainder:
        fig.add_trace(go.Bar(
            x=[remainder], y=["องค์ประกอบที่ทราบ"], orientation="h", name="ส่วนที่ยังอธิบายไม่ได้",
            text=[f"{remainder:g} ?"], textposition="inside",
            marker=dict(color="#E6E1EA", pattern_shape="."),
            hovertemplate="ส่วนต่าง %{x:g} ×10⁹/L · ยังไม่ได้ระบุชนิดเซลล์<extra></extra>",
        ))
    apply_chart_theme(fig, height=240)
    fig.update_layout(barmode="stack", bargap=0.52, margin=dict(l=4, r=20, t=45, b=85),
                      legend=dict(y=-0.48, font=dict(size=15)), dragmode=False)
    fig.add_vline(x=wbc, line_color=ink, line_dash="dash", line_width=2,
                  annotation_text=f"WBC {wbc:g}", annotation_position="top", annotation_font_color=ink)
    fig.update_xaxes(title="จำนวนเซลล์ ×10⁹/L", range=[0, max(wbc, known) * 1.18], dtick=1, fixedrange=True)
    fig.update_yaxes(visible=False, fixedrange=True)
    return fig


def render_wbc_learning() -> None:
    st.subheader("มอง WBC เป็นส่วนประกอบ", anchor=False)
    st.caption("ห้องทดลองสั้น ๆ · ข้อมูลสมมติสำหรับฝึกอ่านผล ไม่ใช่ผลจากแบบฟอร์มของคุณ")
    with pastel_card("home_wbc_lesson", "sky", gap="small"):
        controls, visual = st.columns([1, 1.6], gap="large")
        with controls:
            selected = st.selectbox("เลือกสถานการณ์ WBC", list(CASES), format_func=lambda key: CASES[key][0],
                                    key="home_wbc_case", persist_state="session")
            result = case_result(selected)
            total = result.calculated["absolute_total"]
            data = CASES[selected][1]
            st.markdown(f"**WBC {data['wbc_10e9_l']:g} · ANC ที่วัด {data['anc_10e9_l']:g}** ×10⁹/L")
            if "lymphocytes_percent" in data:
                st.caption("Lymphocytes 75% → ALC = 4 × 75 / 100 = 3 ×10⁹/L")
            else:
                st.caption("ยังไม่ระบุ lymphocytes และเซลล์กลุ่มอื่น")
            st.page_link("pages/4_White_Cells.py", label="เปิดพื้นที่ทบทวนเม็ดเลือดขาว", icon=":material/arrow_forward:")
        with visual:
            known, wbc = total["known_total_10e9_l"], total["wbc_10e9_l"]
            plotly_chart(balance_chart(total), key="home_wbc_balance", width="stretch",
                         config={"displayModeBar": False, "scrollZoom": False},
                         alt=f"ผลรวมองค์ประกอบที่ทราบ {known:g} เทียบกับ WBC {wbc:g} หน่วยสิบยกกำลังเก้าต่อลิตร")
            if total["consistent"] is False:
                st.error(f"ผลรวม {known:g} เกิน WBC {wbc:g} อยู่ {known - wbc:g} ×10⁹/L — ต้องทบทวนข้อมูล")
            elif known < wbc:
                st.info(f"ทราบเพียง {known:g} จาก WBC {wbc:g} ×10⁹/L — ส่วนต่างไม่ใช่ผลตรวจที่วัดได้")
            else:
                st.success(f"ผลรวมที่ทราบ {known:g} เท่ากับ WBC {wbc:g} ×10⁹/L")
            st.caption("รวมแต่ละชนิดเพียงครั้งเดียว · ลายเฉียง = ค่าคำนวณ · ผลรวมเท่ากันยังไม่ยืนยันว่า differential ครบหรือผลปกติ")
