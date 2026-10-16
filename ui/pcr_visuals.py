"""Reusable PCR presentation helpers; importing this module never runs a page.

Chart builders consume the supplied reference or evaluated result. The page owns
session state, input workflows and report evaluation metadata.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from thalab.genetics import allele_dataframe, punnett, summarize_risk
from thalab.styles import clinical_box, current_theme_type, metric_card, pastel_card, section
from thalab.viz import apply_chart_theme, stroke_color
from ui.streamlit_compat import dataframe, plotly_chart
from utils.reporting import csv_bytes


HEM_COLORS = {
    "blood": "#C57894", "blood2": "#D98FA5", "plasma": "#E1C18A",
    "marrow": "#CBBAD9", "cyan": "#9DBCC2", "blue": "#B6A0CE",
    "green": "#92C5B8", "amber": "#E1C18A",
}


RISK_LABELS = {"minimal": "ต่ำสุดในแบบจำลอง", "low": "ต่ำ", "moderate": "ปานกลาง", "high": "สูง", "critical": "สูงมาก", "review": "ต้องทบทวน"}
TABLE_LABELS = {
    "system": "ระบบ globin", "target_code": "รหัสเป้าหมาย", "common_name": "ชื่อ allele",
    "gene": "ยีน", "variant_class": "ประเภท variant", "hgvs": "HGVS / รายละเอียด",
    "method": "วิธีตรวจ", "expected_bp": "ขนาดอ้างอิงสาธิต (bp)",
    "clinical_weight": "น้ำหนักในแบบจำลอง", "interpretation": "คำอธิบาย / ข้อจำกัด",
    "sample_id": "รหัสสมมติตัวอย่าง", "lane": "ช่องแถบ", "observed_bp": "ขนาดแถบที่บันทึก (bp)",
    "result": "ผลที่ผู้ตรวจระบุ", "match_status": "สถานะการจับคู่", "match_score": "คะแนนขนาดแถบ (0–100)",
    "delta_bp": "ผลต่างขนาด (bp)", "controls_status": "สถานะ controls", "call": "ข้อสรุปการจับคู่",
    "offspring_genotype": "genotype ลูกในแบบจำลอง", "phenotype": "ความเสี่ยง phenotype ในแบบจำลอง",
    "severity": "ระดับความเสี่ยงในแบบจำลอง", "probability": "โอกาสได้รับ genotype (%)",
    "parent1_gamete": "gamete บุคคลที่ 1", "parent2_gamete": "gamete บุคคลที่ 2",
    "evidence_basis": "ที่มาของ genotype", "evidence_status": "สถานะหลักฐานก่อนตรวจ controls",
    "allele_burden": "ภาระ allele ในแบบจำลอง (ไม่ใช่จำนวนยีนที่ยืนยัน)",
}
PCR_STATUS_LABELS = {
    "Evidence: positive call and band agree": "ผลผู้ตรวจบวกและขนาดแถบสอดคล้อง",
    "Evidence: negative call without target band": "ผลผู้ตรวจลบและไม่มีแถบตรงเป้าหมาย",
    "Unresolved: qualitative call unavailable": "ยังสรุปไม่ได้: ขาดผลเชิงคุณภาพ",
    "Unresolved: unknown target": "ยังสรุปไม่ได้: ไม่รู้จักเป้าหมาย",
    "Needs review: invalid band size": "ต้องทบทวน: ขนาดแถบไม่ถูกต้อง",
    "Needs review: negative call with matched band": "ต้องทบทวน: ผลลบแต่ขนาดแถบตรงเป้าหมาย",
    "Needs review: positive call with mismatched band": "ต้องทบทวน: ผลบวกแต่ขนาดแถบไม่ตรงเป้าหมาย",
    "Unresolved: positive call without band size": "ยังสรุปไม่ได้: ผลบวกไม่มีขนาดแถบ",
    "Detected: band-size matched": "พบผลสอดคล้องกับเป้าหมายสาธิต",
    "Not detected in selected assay": "ไม่พบตามผลผู้ตรวจในชุดตรวจที่เลือก",
    "Unresolved: run controls not passed": "ระงับการแปลผล: controls ยังไม่ผ่าน",
}
CONTROL_LABELS = {"not_confirmed": "ยังไม่ยืนยัน", "pass": "ผ่าน", "fail": "ไม่ผ่าน"}
CALL_LABELS = {"Positive": "บวก", "Negative": "ลบ", "Unknown": "ไม่ทราบ / ยังไม่อ่านผล"}


def display_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Translate presentation values while preserving machine-readable exports."""
    view = frame.copy()
    mappings = {"severity": RISK_LABELS, "match_status": PCR_STATUS_LABELS,
                "evidence_status": PCR_STATUS_LABELS, "controls_status": CONTROL_LABELS,
                "result": CALL_LABELS, "call": {"detected": "สอดคล้อง", "not_detected": "ไม่พบในชุดตรวจ", "unresolved": "ยังสรุปไม่ได้"}}
    for column, labels in mappings.items():
        if column in view:
            view[column] = view[column].map(lambda value: labels.get(value, value))
    return view.rename(columns=TABLE_LABELS)


def export_csv(frame: pd.DataFrame) -> bytes:
    return csv_bytes([list(frame.columns), *frame.itertuples(index=False, name=None)])

def _theme_layout(fig: go.Figure, title: str | None = None, height: int = 430) -> go.Figure:
    return apply_chart_theme(fig, title, height)


def _chart_neutrals() -> dict[str, str]:
    if current_theme_type() == "dark":
        return {
            "root": "rgba(255,255,255,.06)",
            "border": "#85728F",
            "strong_border": "rgba(255,255,255,.92)",
            "treemap_grid": "#493451",
            "soft_fill": "rgba(255,255,255,.035)",
            "muted_fill": "rgba(255,255,255,.18)",
            "muted_text": "#D4C8DA",
            "guide": "rgba(218,201,224,.30)",
            "gauge_bg": "rgba(255,255,255,.06)",
            "tick": "#D4C8DA",
            "text": "#FBF5FC",
        }
    return {
        "root": "rgba(63,2,8,.05)",
        "border": "#8A718E",
        "strong_border": "rgba(63,2,8,.78)",
        "treemap_grid": "#65516F",
        "soft_fill": "rgba(177,18,38,.035)",
        "muted_fill": "rgba(63,2,8,.16)",
        "muted_text": "#58485F",
        "guide": "rgba(93,70,105,.24)",
        "gauge_bg": "rgba(177,18,38,.05)",
        "tick": "#58485F",
        "text": "#160F1B",
    }


def _safe_col(df: pd.DataFrame, candidates: Sequence[str], fallback: str | None = None) -> str | None:
    for col in candidates:
        if col in df.columns:
            return col
    return fallback


def _num(series: pd.Series, default: float = np.nan) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(default)


def workflow_stepper() -> None:
    steps = [
        ("1 · ทบทวนชุดตรวจ", "ฐานข้อมูลเป้าหมาย α/β-globin"),
        ("2 · จำลองการถ่ายทอด", "gamete ของคู่และ genotype ลูก"),
        ("3 · ทบทวนหลักฐาน", "ความเสี่ยง phenotype และแถบ PCR"),
    ]
    with st.container(horizontal=True, gap="small"):
        for index, (title, body) in enumerate(steps):
            with pastel_card(f"pcr_card_step_{index}", ("sky", "lavender", "mint")[index], width=280, gap="xsmall"):
                st.markdown(f"**{title}**")
                st.caption(body)


def molecular_panel(title: str, body: str, *, card_key: str = "pcr_card_panel", tone: str = "peach") -> None:
    with pastel_card(card_key, tone):
        st.markdown(f"**{title}**")
        st.write(body)


def coverage_map_summary(db: pd.DataFrame) -> None:
    if db.empty:
        st.info("ไม่มีเป้าหมายตรงกับตัวกรอง")
        return
    system_counts = db["system"].fillna("unknown").astype(str).value_counts()
    method_counts = db["method"].fillna("unknown").astype(str).value_counts()
    class_counts = db["variant_class"].fillna("unknown").astype(str).value_counts()
    st.caption(
        f"แสดง {len(db)} รายการ · {db['target_code'].nunique()} รหัสเป้าหมาย · "
        + " / ".join(f"{system} {int(count)}" for system, count in system_counts.items())
        + f" · วิธีตรวจที่พบมากที่สุด: {method_counts.index[0]} ({int(method_counts.iloc[0])})"
        + f" · ประเภทที่พบมากที่สุด: {class_counts.index[0]} ({int(class_counts.iloc[0])})"
    )


# -----------------------------------------------------------------------------
# Data preparation helpers
# -----------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def cached_allele_database() -> pd.DataFrame:
    db = allele_dataframe().copy()
    for col in ["system", "variant_class", "method", "common_name", "target_code"]:
        if col not in db.columns:
            db[col] = "Unknown"
    return db


# -----------------------------------------------------------------------------
# Visualizations: Allele knowledge base
# -----------------------------------------------------------------------------


def panel_coverage_treemap(db: pd.DataFrame) -> go.Figure:
    neutral = _chart_neutrals()
    work = db.copy()
    if work.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="ไม่มีเป้าหมายโมเลกุลตรงกับตัวกรอง",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(size=20, color=neutral["muted_text"]),
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return _theme_layout(fig, "แผนผังเป้าหมายในชุดตรวจ", 340)

    label_col = _safe_col(work, ["common_name", "target_code", "variant_class"], "variant_class")
    code_col = _safe_col(work, ["target_code", "common_name"], label_col)
    work["_target_label"] = (
        work[label_col].fillna("เป้าหมายที่ไม่ทราบ").astype(str)
        + " ["
        + work[code_col].fillna("NA").astype(str)
        + "]"
    )
    work["_target_count"] = 1
    hover_data: dict[str, bool | str] = {
        "_target_count": False,
        "system": True,
        "variant_class": True,
        "method": True,
        "target_code": True,
    }
    if "expected_bp" in work.columns:
        hover_data["expected_bp"] = ":.0f"

    fig = px.treemap(
        work,
        path=["system", "variant_class", "method", "_target_label"],
        values="_target_count",
        color="system",
        color_discrete_map={
            "alpha": HEM_COLORS["cyan"],
            "beta": HEM_COLORS["blood2"],
            "(?)": neutral["muted_fill"],
        },
        hover_data=hover_data,
    )
    treemap_text_colors = []
    for node_id, parent_id in zip(fig.data[0].ids, fig.data[0].parents):
        key = str(node_id or parent_id).lower()
        if key == "alpha" or key.startswith("alpha/"):
            treemap_text_colors.append("#160F1B")
        elif key == "beta" or key.startswith("beta/"):
            treemap_text_colors.append("#160F1B")
        else:
            treemap_text_colors.append(neutral["text"])

    fig.update_traces(
        branchvalues="total",
        marker=dict(
            cornerradius=5,
            line=dict(color=neutral["treemap_grid"], width=2.2),
        ),
        pathbar=dict(
            textfont=dict(color=neutral["text"], size=17),
            thickness=28,
        ),
        selector=dict(type="treemap"),
        textinfo="label+value+percent parent",
        textfont=dict(color=treemap_text_colors, size=17),
        texttemplate="<b>%{label}</b><br>%{value} เป้าหมาย<br>%{percentParent:.0%} ของกลุ่ม",
        hovertemplate=(
            "<b>%{label}</b><br>"
            "เป้าหมาย: %{value}<br>"
            "สัดส่วนทั้งชุดตรวจ: %{percentRoot:.1%}<br>"
            "สัดส่วนในกลุ่ม: %{percentParent:.1%}"
            "<extra></extra>"
        ),
        root_color=neutral["root"],
        tiling=dict(packing="squarify", pad=4),
        maxdepth=4,
    )
    fig.update_layout(
        uniformtext=dict(minsize=14, mode="show"),
        colorway=[HEM_COLORS["cyan"], HEM_COLORS["blood2"], HEM_COLORS["plasma"], HEM_COLORS["green"]],
    )
    return _theme_layout(fig, "แผนผังเป้าหมายในชุดตรวจ", 560)


def allele_lollipop(db: pd.DataFrame) -> go.Figure:
    neutral = _chart_neutrals()
    bp_col = _safe_col(db, ["expected_bp", "amplicon_bp", "bp"], None)
    label_col = _safe_col(db, ["common_name", "target_code"], "variant_class")
    plot_df = db.copy()
    if bp_col is None or plot_df[bp_col].isna().all():
        plot_df["_bp"] = np.arange(len(plot_df)) * 70 + 120
        bp_col = "_bp"
    plot_df[bp_col] = _num(plot_df[bp_col])
    plot_df = plot_df.sort_values(bp_col).tail(35)
    fig = go.Figure()
    color_map = {"alpha": HEM_COLORS["cyan"], "beta": HEM_COLORS["blood2"]}
    for system, g in plot_df.groupby("system", dropna=False):
        fig.add_trace(
            go.Scatter(
                x=g[bp_col],
                y=g[label_col].astype(str),
                mode="markers+lines",
                line=dict(width=3, color=stroke_color(color_map.get(system, HEM_COLORS["plasma"]))),
                marker=dict(size=12, color=color_map.get(system, HEM_COLORS["plasma"]), line=dict(color=neutral["strong_border"], width=1)),
                name=str(system),
                hovertemplate="%{y}<br>ขนาดอ้างอิงสาธิต: %{x:.0f} bp<extra></extra>",
            )
        )
    fig.update_xaxes(title="ขนาด amplicon อ้างอิงสาธิต (bp)")
    fig.update_yaxes(title="เป้าหมาย", automargin=True)
    return _theme_layout(fig, "ขนาด amplicon ของแต่ละเป้าหมาย", 620)


# -----------------------------------------------------------------------------
# Visualizations: couple genotype risk
# -----------------------------------------------------------------------------


def _risk_col(result: pd.DataFrame) -> str | None:
    return _safe_col(result, ["risk_class", "risk_level", "severity", "risk", "clinical_risk"], None)


def genotype_outcome_sunburst(result: pd.DataFrame) -> go.Figure:
    neutral = _chart_neutrals()
    work = result.copy()
    geno_col = _safe_col(work, ["offspring_genotype", "genotype", "child_genotype"], work.columns[-1])
    pheno_col = _safe_col(work, ["phenotype", "offspring_phenotype", "clinical_phenotype"], geno_col)
    risk_col = _risk_col(work)
    if risk_col is None:
        work["risk_class"] = "review"
        risk_col = "risk_class"
    work[risk_col] = work[risk_col].map(lambda value: RISK_LABELS.get(value, value))
    count = work.groupby([risk_col, pheno_col, geno_col], dropna=False)["probability"].sum().reset_index()
    fig = px.sunburst(
        count,
        path=[risk_col, pheno_col, geno_col],
        values="probability",
        labels={**TABLE_LABELS, risk_col: "ระดับความเสี่ยงในแบบจำลอง"},
        color=risk_col,
        color_discrete_map={
            RISK_LABELS["minimal"]: HEM_COLORS["green"],
            RISK_LABELS["low"]: HEM_COLORS["cyan"],
            RISK_LABELS["moderate"]: HEM_COLORS["amber"],
            RISK_LABELS["high"]: HEM_COLORS["blood2"],
            RISK_LABELS["critical"]: HEM_COLORS["blood"],
        },
    )
    fig.update_traces(insidetextorientation="radial", marker=dict(line=dict(color=neutral["border"], width=1)))
    return _theme_layout(fig, "สัดส่วน genotype ลูกตามโอกาสถ่ายทอด", 520)


def risk_probability_donut(result: pd.DataFrame) -> go.Figure:
    neutral = _chart_neutrals()
    work = result.copy()
    risk_col = _risk_col(work)
    if risk_col is None:
        work["risk_class"] = "review"
        risk_col = "risk_class"
    if "probability" in work.columns:
        agg = work.groupby(risk_col, dropna=False)["probability"].sum().reset_index(name="probability")
    else:
        agg = work.groupby(risk_col, dropna=False).size().reset_index(name="probability")
        agg["probability"] = agg["probability"] / agg["probability"].sum() * 100
    if agg["probability"].max() <= 1.1:
        agg["probability"] *= 100
    fig = go.Figure(
        data=[
            go.Pie(
                labels=agg[risk_col].map(lambda value: RISK_LABELS.get(value, value)),
                values=agg["probability"],
                hole=0.58,
                textinfo="label+percent",
                marker=dict(colors=[{"minimal": HEM_COLORS["green"], "low": HEM_COLORS["cyan"], "moderate": HEM_COLORS["amber"], "high": HEM_COLORS["blood2"], "critical": HEM_COLORS["blood"]}.get(value, HEM_COLORS["blue"]) for value in agg[risk_col]], line=dict(color=neutral["border"], width=1)),
            )
        ]
    )
    fig.add_annotation(text="โอกาส<br>ถ่ายทอด", x=0.5, y=0.5, showarrow=False, font=dict(size=22, color=neutral["text"]))
    return _theme_layout(fig, "สัดส่วนความเสี่ยง phenotype ในแบบจำลอง", 440)


def genotype_evidence_table(result: pd.DataFrame) -> pd.DataFrame:
    keep = [
        c
        for c in [
            "parent1_gamete",
            "parent2_gamete",
            "offspring_genotype",
            "phenotype",
            "risk_class",
            "risk_level",
            "severity",
            "probability",
            "evidence_basis",
        ]
        if c in result.columns
    ]
    return result[keep] if keep else result


def select_parent_genotypes(system: str, genotype_db: dict[str, list[str]]) -> tuple[str, str, list[str], list[str]] | None:
    labels = list(genotype_db.keys())
    system_label = "α" if system == "alpha" else "β"
    st.markdown(f"#### :material/genetics: {system_label}-globin")
    p1_label = st.selectbox(
        f"genotype {system_label} ของบุคคลที่ 1",
        labels,
        index=None,
        placeholder="เลือก genotype ตามหลักฐานหรือสถานการณ์จำลอง",
        key=f"{system}_parent1_genotype", persist_state="session",
    )
    p2_label = st.selectbox(
        f"genotype {system_label} ของบุคคลที่ 2",
        labels,
        index=None,
        placeholder="เลือก genotype ตามหลักฐานหรือสถานการณ์จำลอง",
        key=f"{system}_parent2_genotype", persist_state="session",
    )
    if p1_label is None or p2_label is None:
        return None
    return p1_label, p2_label, genotype_db[p1_label], genotype_db[p2_label]


def render_couple_risk_results(
    system: str,
    p1_label: str,
    p2_label: str,
    p1: list[str],
    p2: list[str],
    evidence_basis: str,
) -> pd.DataFrame:
    system_label = "α" if system == "alpha" else "β"
    result = punnett(p1, p2, system).copy()
    result["evidence_basis"] = evidence_basis
    risk = summarize_risk(result)
    high_risk = float(risk.get("critical", 0) + risk.get("high", 0))

    section(
        f":material/family_restroom: ความเสี่ยง phenotype ลูกจาก {system_label}-globin",
        f"ที่มาของ genotype: {evidence_basis} • โอกาสถ่ายทอดตาม Mendelian model ไม่ใช่การยืนยัน phenotype หรือความต้องการเลือดของลูก",
    )

    cards = [
        ("gamete บุคคลที่ 1", " / ".join(map(str, p1)), p1_label, "info"),
        ("gamete บุคคลที่ 2", " / ".join(map(str, p2)), p2_label, "info"),
        ("กลุ่มสูง / สูงมาก", f"{high_risk:.0f}%", "โอกาสได้รับ genotype กลุ่มนี้", "high" if high_risk else "low"),
        ("รูปแบบลูก", str(result.shape[0]), "genotype หลังรวมรายการซ้ำ", "moderate"),
        ("กลุ่มความเสี่ยง", str(len(risk)), "phenotype ในแบบจำลอง", "info"),
    ]
    with st.container(horizontal=True, gap="small"):
        for index, card in enumerate(cards):
            with st.container(width=240):
                metric_card(*card, key=f"pcr_{system}_metric_{index}")

    with st.expander(f"หลักฐาน genotype ลูกในแบบจำลอง {system_label}-globin", expanded=True):
        risk_table = genotype_evidence_table(result)
        dataframe(display_table(risk_table), width='stretch', hide_index=True)
        st.download_button(
            f"ดาวน์โหลดตารางความเสี่ยงคู่ {system_label}-globin (CSV)",
            export_csv(display_table(result)),
            f"{system}_globin_couple_risk_expert.csv",
            "text/csv",
            width='stretch',
            key=f"{system}_risk_download",
            icon=":material/download:",
        )

    donut_col, sunburst_col = st.columns([1, 1])
    with donut_col:
        plotly_chart(risk_probability_donut(result), width='stretch', theme=None)
    with sunburst_col:
        plotly_chart(genotype_outcome_sunburst(result), width='stretch', theme=None)

    if high_risk > 0:
        clinical_box(
            f"<b>ประเด็นสำหรับการให้คำปรึกษาพันธุกรรม:</b> แบบจำลอง {system_label}-globin นี้ให้โอกาสได้รับ genotype ในกลุ่มความเสี่ยงสูง/สูงมาก {high_risk:.0f}% ต่อการตั้งครรภ์ ควรยืนยัน genotype และ phase ก่อนใช้ให้คำปรึกษา ระดับความเสี่ยงนี้เป็นการจัดกลุ่มในแบบจำลอง ไม่ยืนยันการวินิจฉัยหรือความรุนแรงจริง",
            "danger",
        )
    else:
        clinical_box(
            f"ไม่พบกลุ่มความเสี่ยงสูง/สูงมากในคู่ genotype {system_label}-globin ที่เลือก ผลจำลองนี้ไม่ครอบคลุม variant นอกชุดข้อมูล ปฏิสัมพันธ์ระหว่างยีน และ hemoglobinopathy รูปแบบอื่น",
            "info",
        )

    return result
