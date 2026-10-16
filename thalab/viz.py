from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from thalab.styles import current_theme_type

BLOOD = "#D98FA5"
DANGER = "#C57894"
GOLD = "#E1C18A"
TEAL = "#92C5B8"
BLUE = "#9DBCC2"
VIOLET = "#B6A0CE"
INK = "#160F1B"
PALETTE = [BLOOD, BLUE, VIOLET, TEAL, GOLD, DANGER, "#E5B4C6", "#CBBAD9"]
SEVERITY_COLORS = {"minimal": TEAL, "low": BLUE, "moderate": GOLD, "high": BLOOD, "critical": DANGER}

# Use pastel fills with saturated strokes so small marks stay legible.
LIGHT_STROKES = {
    BLOOD: "#982E53", DANGER: "#8E264C", GOLD: "#8C651D",
    TEAL: "#236A58", BLUE: "#2B617B", VIOLET: "#69448D",
    "#E5B4C6": "#94486B", "#CBBAD9": "#665083",
}


def stroke_color(color: str) -> str:
    """Return a series stroke suited to the current canvas theme."""
    return color if current_theme_type() == "dark" else LIGHT_STROKES.get(color, color)


def _rgba(color: str, opacity: float) -> str:
    red, green, blue = (int(color[index:index + 2], 16) for index in (1, 3, 5))
    return f"rgba({red},{green},{blue},{opacity})"


def apply_chart_theme(fig: go.Figure, title: str | None = None, height: int = 420) -> go.Figure:
    """Apply shared legible typography, axes and boundaries without changing data."""
    dark = current_theme_type() == "dark"
    text = "#FBF5FC" if dark else INK
    grid = "rgba(218,201,224,.30)" if dark else "rgba(93,70,105,.24)"
    axis = "#BCAAC5" if dark else "#715D7A"
    fill_edge = "#35263F" if dark else "#65516F"
    # Keep the app gradient visible, but give hover labels a solid surface.
    plot_bg = "rgba(0,0,0,0)"
    fig.update_layout(
        template="plotly_dark" if dark else "plotly_white",
        height=height,
        title={"text": title or "", "x": 0.02, "xanchor": "left", "font": {"size": 24, "color": text}},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor=plot_bg,
        margin=dict(l=48, r=32, t=72 if title else 34, b=50),
        font=dict(family="Segoe UI, Tahoma, Arial, sans-serif", color=text, size=18),
        colorway=PALETTE,
        legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="left", x=0,
                    bgcolor="rgba(0,0,0,0)", font=dict(color=text, size=17)),
        hoverlabel=dict(
            bgcolor="#281F32" if dark else "#FFFAFD",
            bordercolor=axis,
            font=dict(color=text, size=18),
        ),
    )
    for update_axes in (fig.update_xaxes, fig.update_yaxes):
        update_axes(gridcolor=grid, zerolinecolor=axis, linecolor=axis,
                    tickcolor=axis, tickfont=dict(color=text, size=17),
                    title_font=dict(color=text, size=18), automargin=True)
    if "polar" in fig.layout:
        fig.update_layout(polar=dict(
            bgcolor=plot_bg,
            radialaxis=dict(gridcolor=grid, linecolor=axis, tickfont=dict(color=text, size=16)),
            angularaxis=dict(gridcolor=grid, linecolor=axis, tickfont=dict(color=text, size=17)),
        ))
    for trace_type in ("pie", "sunburst"):
        # Labels over pastel sectors need dark ink in both themes.
        fig.update_traces(insidetextfont=dict(color=INK, size=17),
                          marker_line=dict(color=fill_edge, width=1.5),
                          selector=dict(type=trace_type))
    fig.update_traces(outsidetextfont=dict(color=text, size=17), selector=dict(type="pie"))
    fig.update_traces(marker_line=dict(color=fill_edge, width=1.25),
                      insidetextfont=dict(color=INK), outsidetextfont=dict(color=text),
                      cliponaxis=False, selector=dict(type="bar"))
    fig.update_traces(node_line=dict(color=fill_edge, width=1.5),
                      textfont=dict(color=text, size=17),
                      link_color="rgba(197,175,224,.52)" if dark else "rgba(108,72,139,.40)",
                      selector=dict(type="sankey"))
    return fig


def _layout(fig: go.Figure, title: str | None = None, height: int = 420) -> go.Figure:
    return apply_chart_theme(fig, title, height)

def risk_gauge(score: float, title: str = "Consult score") -> go.Figure:
    dark = current_theme_type() == "dark"
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number+delta",
            value=float(score),
            number={"suffix":" / 100", "font":{"size":46}},
            delta={"reference":45, "increasing":{"color":"#E6A6BA" if dark else "#725487"}, "decreasing":{"color":"#B7D1C3" if dark else "#486B5A"}},
            gauge={
                "axis":{"range":[0,100]},
                "bar":{"color":stroke_color(BLOOD)},
                "bgcolor":"rgba(0,0,0,0)",
                "borderwidth":1,
                "bordercolor":"rgba(255,244,246,.16)" if dark else "rgba(217,143,165,.30)",
                "steps":[
                    {"range":[0,45],"color":"#384C44" if dark else "#E6EFE9"},
                    {"range":[45,75],"color":"#544936" if dark else "#F5EBD9"},
                    {"range":[75,100],"color":"#583B47" if dark else "#F4DFE5"},
                ],
                "threshold":{"line":{"color":stroke_color(DANGER),"width":5},"thickness":.78,"value":75},
            },
        )
    )
    return _layout(fig, title, 360)

def score_radar(scores: dict[str, float]) -> go.Figure:
    labels=list(scores.keys()); values=[float(scores[k]) for k in labels]
    fig=go.Figure(go.Scatterpolar(r=values+[values[0]], theta=labels+[labels[0]], fill="toself", fillcolor=_rgba(BLOOD, .20), name="Phenotype score", line=dict(width=4, color=stroke_color(BLOOD))))
    fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0,100], gridcolor="rgba(182,160,206,.25)")), showlegend=False)
    return _layout(fig, "คะแนนสนับสนุนรูปแบบ (ไม่ใช่ความน่าจะเป็น)", 430)

def hb_fraction_donut(hba: float, hba2: float, hbf: float, hbe: float, bart: float = 0,
                      hbh: float = 0, hbcs: float = 0, method: str = "HPLC") -> go.Figure:
    labels = ["HbA", "HbA2/E" if method == "HPLC" else "HbA2", "HbF", "HbE", "Bart", "HbH", "HbCS"]
    pairs = [(label, float(value)) for label, value in zip(labels, [hba, hba2, hbf, hbe, bart, hbh, hbcs])
             if value is not None and np.isfinite(float(value)) and float(value) > 0]
    fig = go.Figure(go.Pie(labels=[p[0] for p in pairs], values=[p[1] for p in pairs],
                          hole=.62, sort=False, textinfo="label+value",
                          marker=dict(colors=[[BLOOD, GOLD, BLUE, VIOLET, "#CBBAD9", DANGER, TEAL][labels.index(p[0])] for p in pairs])))
    fig.update_traces(hovertemplate="%{label}: %{value:.2f}% ที่รายงาน<extra></extra>")
    return _layout(fig, "สัดส่วน Hb ที่กรอก (ไม่เติมค่าที่ไม่ได้ตรวจ)", 390)


def hplc_chromatogram(hba: float, hba2: float, hbf: float, hbe: float, bart: float = 0,
                     hbh: float = 0, hbcs: float = 0, method: str = "HPLC") -> go.Figure:
    x = np.linspace(0, 7.5, 900)
    peaks = [("Bart", .6, .08, bart, "#CBBAD9"), ("HbH", .9, .08, hbh, DANGER),
             ("HbF", 1.15, .09, hbf, BLUE), ("HbA", 2.72, .13, hba, BLOOD),
             ("HbA2/E" if method == "HPLC" else "HbA2", 3.72, .085, hba2, GOLD),
             ("HbE", 4.05, .095, hbe, VIOLET), ("HbCS", 5.8, .12, hbcs, TEAL)]
    fig = go.Figure()
    for name, mu, sigma, value, color in peaks:
        if value is None or not np.isfinite(float(value)) or float(value) <= 0:
            continue
        y = float(value) * np.exp(-.5 * ((x - mu) / sigma) ** 2)
        fig.add_trace(go.Scatter(x=x, y=y, mode="lines", fill="tozeroy", name=name,
                                line=dict(width=3, color=stroke_color(color)), fillcolor=_rgba(color, .28)))
    fig.update_xaxes(title="ตำแหน่งสมมติ (ไม่ใช่ retention time/zone ของเครื่องตรวจ)")
    fig.update_yaxes(title="สัญญาณจำลอง", showticklabels=False)
    return _layout(fig, f"ภาพจำลองจากค่า Hb ({method}) — ไม่ใช่ผลจากเครื่องตรวจ", 430)


def thalassemia_spectrum_chart() -> go.Figure:
    """Categorical teaching map; coordinates do not encode clinical severity."""
    colors = {"ข้อมูลอ้างอิง": TEAL, "α-globin": BLUE, "β-globin": VIOLET,
              "HbE / β-globin variant": BLOOD, "α หรือ β-globin": GOLD}
    # Positions are only for label layout. No quantitative risk or signal scale.
    # Phenotype context: GeneReviews Beta-Thalassemia and Fucharoen & Weatherall
    # (2012), The Hemoglobin E Thalassemias; linked in learning_modules.json.
    df = pd.DataFrame([
        ("Normal genotype", "ข้อมูลอ้างอิง", .45, .9, "ผล CBC และ Hb ต้องอ่านร่วมกับบริบทและช่วงอ้างอิง", "top center"),
        ("Silent α carrier", "α-globin", 1.05, 1.35, "CBC อาจเปลี่ยนแปลงเพียงเล็กน้อย การคัดกรองไม่ยืนยันจีโนไทป์", "bottom center"),
        ("α-thal carrier", "α-globin", 1.35, 2.05, "อาจพบเม็ดเลือดแดงขนาดเล็ก ต้องทบทวนธาตุเหล็กและผลยืนยัน", "top left"),
        ("β-thal trait", "β-globin", 1.58, 3.35, "มักพบ MCV/MCH ต่ำและ HbA2 สูง แต่ต้องอ่านตามวิธีตรวจและบริบท", "top center"),
        ("HbE trait", "HbE / β-globin variant", 1.45, 2.72, "ทบทวน HbE ตามวิธีตรวจ พีครวม HbA2/E ไม่ใช่ HbA2 แยกวัด", "bottom right"),
        ("Trait phenotype", "α หรือ β-globin", 2.12, 2.35, "รูปแบบพาหะต้องทบทวนผลยืนยันและข้อมูลของคู่ก่อนให้คำปรึกษา", "bottom center"),
        ("Homozygous HbE", "HbE / β-globin variant", 2.48, 3.08, "โดยลำพังมักไม่มีอาการสำคัญหรือซีดเล็กน้อย; ภาวะร่วมอาจเปลี่ยนลักษณะโรค", "top right"),
        ("HbH disease", "α-globin", 3.28, 3.78, "อาจพบ HbH และภาวะเม็ดเลือดแดงแตก ความรุนแรงแตกต่างกันได้", "bottom left"),
        ("β-thal intermedia", "β-globin", 3.82, 3.22, "ภาวะซีดและความต้องการเลือดแตกต่างกัน ต้องประเมินรายบุคคล", "bottom right"),
        ("HbH-Constant Spring", "α-globin", 3.76, 4.36, "Nondeletional HbH มักมีอาการมากกว่า deletional HbH แต่ยังต้องประเมินรายบุคคล", "top center"),
        ("Homozygous β-thal", "β-globin", 4.55, 3.78, "ลักษณะโรคขึ้นกับ variants และปัจจัยร่วม ไม่ระบุความรุนแรงจากชื่อนี้เพียงอย่างเดียว", "bottom center"),
        ("HbE/β0-thal", "HbE / β-globin variant", 4.72, 4.43, "ลักษณะโรคแปรผันได้ตั้งแต่ไม่รุนแรงถึงรุนแรง ต้องประเมินอาการและปัจจัยร่วม", "top left"),
        ("Hb Bart's hydrops", "α-globin", 4.95, 4.95, "ภาวะรุนแรงที่ต้องดูแลโดยทีมเฉพาะทาง ไม่ใช้ตำแหน่งในภาพประเมินทารก", "top center"),
    ], columns=["label", "system", "x", "y", "cue", "textposition"])
    fig = go.Figure()
    for system, group in df.groupby("system", sort=False):
        fig.add_trace(go.Scatter(
            x=group["x"], y=group["y"], mode="markers+text",
            text=group["label"], textposition=group["textposition"].tolist(),
            customdata=group[["system", "cue"]].to_numpy(),
            marker=dict(size=30, color=colors[system], opacity=1,
                        line=dict(width=2, color=stroke_color(colors[system]))),
            name=system,
            hovertemplate="<b>%{text}</b><br>กลุ่ม: %{customdata[0]}<br>%{customdata[1]}<extra></extra>",
        ))
    fig.update_xaxes(visible=False, range=[0, 5.5], fixedrange=True)
    fig.update_yaxes(visible=False, range=[.55, 5.45], fixedrange=True)
    fig.update_layout(hovermode="closest")
    return _layout(fig, "ภาพรวมกลุ่มธาลัสซีเมียเพื่อการเรียนรู้", 560)


def mcv_hba2_quadrant(mcv: float, hba2: float, background: pd.DataFrame | None = None) -> go.Figure:
    if background is None:
        rng=np.random.default_rng(42); background=pd.DataFrame({"mcv_fl":np.concatenate([rng.normal(88,5,80),rng.normal(68,5,65),rng.normal(72,6,55)]),"hba2_percent":np.concatenate([rng.normal(2.6,.25,80),rng.normal(4.8,.55,65),rng.normal(2.5,.35,55)]),"pattern":["reference-like"]*80+["β-thal trait-like"]*65+["α/iron-like microcytosis"]*55})
    fig=px.scatter(background,color_discrete_sequence=PALETTE,x="mcv_fl",y="hba2_percent",color="pattern",opacity=.85,labels={"mcv_fl":"MCV (fL)","hba2_percent":"HbA2 (%)"})
    fig.update_traces(marker=dict(size=8, line=dict(width=1, color="#D8C7E0" if current_theme_type() == "dark" else "#65516F")))
    fig.add_vline(x=80,line_width=2,line_dash="dash",line_color="#CCBBCE" if current_theme_type() == "dark" else "#6F5A70"); fig.add_hline(y=3.5,line_width=2,line_dash="dash",line_color="#CCBBCE" if current_theme_type() == "dark" else "#6F5A70")
    fig.add_trace(go.Scatter(x=[mcv],y=[hba2],mode="markers+text",text=["Patient"],textposition="top center",marker=dict(size=18,symbol="diamond",color=stroke_color(DANGER),line=dict(color="#F8F0F5" if current_theme_type() == "dark" else INK,width=2)),name="Current sample"))
    fig.add_annotation(x=67,y=5.4,text="β-thal trait-like zone",showarrow=False,font=dict(color="#F8F0F5" if current_theme_type() == "dark" else INK,size=17)); fig.add_annotation(x=67,y=2.2,text="α-thal / iron-like microcytosis",showarrow=False,font=dict(color="#F8F0F5" if current_theme_type() == "dark" else INK,size=17))
    return _layout(fig, "MCV–HbA2 diagnostic quadrant", 470)

def cbc_reference_bars(row: dict, thresholds: dict | None = None) -> go.Figure:
    from thalab.core import analyze_screening
    limits = thresholds if thresholds is not None else analyze_screening(row).thresholds_used
    metrics = [("Hb", "hb_g_dl", "anemia_hb", "g/dL"),
               ("MCV", "mcv_fl", "mcv_microcytosis", "fL"),
               ("MCH", "mch_pg", "mch_hypochromia", "pg"),
               ("RDW", "rdw_percent", "rdw_high", "%"),
               ("Ferritin", "ferritin_ng_ml", "ferritin_deficient", "ng/mL")]
    fig = go.Figure()
    for label, key, threshold_key, unit in metrics:
        value = row.get(key)
        threshold = limits.get(threshold_key)
        if value is None or not np.isfinite(float(value)):
            continue
        fig.add_trace(go.Bar(y=[label], x=[float(value)], orientation="h", name=label,
                            text=[f"{value:g} {unit}"], showlegend=False))
        if threshold is not None and np.isfinite(float(threshold)):
            fig.add_trace(go.Scatter(y=[label], x=[threshold], mode="markers",
                                    marker=dict(symbol="line-ns", size=22, color="#F8F0F5" if current_theme_type() == "dark" else INK),
                                    name=f"เกณฑ์ {label}: {threshold:g} {unit}",
                                    hovertemplate=f"เกณฑ์ {label}: {threshold:g} {unit}<extra></extra>"))
    fig.update_xaxes(title="ค่าที่วัดและจุดตัดที่ใช้จริง (แต่ละแถวมีหน่วยต่างกัน)")
    return _layout(fig, "CBC และ ferritin เทียบจุดตัดของกฎ", 430)


def diagnostic_waterfall(result) -> go.Figure:
    # Display actual engine scores, without creating a second rule calculation.
    measures=["absolute"]*4
    labels=["β-thal", "α-thal/HbH", "HbE", "ขาดธาตุเหล็ก"]
    vals=[result.beta_trait_score,result.alpha_trait_score,result.hbe_score,result.iron_deficiency_score]
    fig=go.Figure(go.Waterfall(name="score",orientation="v",measure=measures,x=labels,y=vals,connector={"line":{"color":"rgba(111,90,112,.35)"}},increasing={"marker":{"color":BLOOD}},decreasing={"marker":{"color":TEAL}},totals={"marker":{"color":GOLD}})); fig.update_yaxes(title="Score contribution")
    return _layout(fig,"คะแนนสนับสนุนจากระบบกฎ (ไม่ใช่ความน่าจะเป็น)",410)

def reflex_sankey(result) -> go.Figure:
    recommendations = list(result.recommendations)
    labels = ["ข้อมูลคัดกรอง", result.top_pattern, *recommendations]
    sources = [0] + [1] * len(recommendations)
    targets = [1] + list(range(2, len(labels)))
    fig = go.Figure(go.Sankey(node=dict(label=labels, pad=18, thickness=18, color=[PALETTE[i % len(PALETTE)] for i in range(len(labels))]),
                             link=dict(source=sources, target=targets, value=[1] * len(targets), color="rgba(182,160,206,.25)")))
    return _layout(fig, "แผนตรวจเพิ่มเติมจากผลแปลเดียวกับรายงาน", 430)


def batch_risk_distribution(df: pd.DataFrame) -> go.Figure:
    from utils.reporting import RISK_LABELS
    order=list(RISK_LABELS); counts=df["consult_risk"].value_counts().reindex(order).fillna(0).reset_index(); counts.columns=["risk","count"]
    counts["risk"] = counts["risk"].map(RISK_LABELS)
    fig=px.bar(counts,color_discrete_sequence=PALETTE,x="risk",y="count",text="count",labels={"risk":"ระดับการทบทวน","count":"จำนวนตัวอย่าง"}); fig.update_traces(marker_line_color="white",marker_line_width=2,textposition="outside")
    return _layout(fig,"จำนวนตัวอย่างตามระดับการทบทวน",420)

def batch_mcv_hba2_scatter(df: pd.DataFrame) -> go.Figure:
    # Marker size is independent of the uncalibrated support score.
    fig=px.scatter(df,color_discrete_sequence=PALETTE,x="mcv_fl",y="hba2_percent",color="top_pattern",hover_name="sample_id",hover_data=["consult_risk","ferritin_ng_ml","mentzer_index"],labels={"mcv_fl":"MCV (fL)","hba2_percent":"HbA2 (%)"})
    fig.update_traces(marker=dict(size=9, opacity=1, line=dict(width=1.25, color="#D8C7E0" if current_theme_type() == "dark" else "#65516F")))
    # No fixed cutoffs: each sample can use a different age/SOP profile.
    return _layout(fig,"ภาพรวม MCV–HbA2 ที่แยกวัด",500)

def score_heatmap(df: pd.DataFrame) -> go.Figure:
    cols=["beta_trait_score","alpha_trait_score","hbe_score","iron_deficiency_score"]; z=df[cols].fillna(0).to_numpy().T
    fig=go.Figure(go.Heatmap(z=z,x=df["sample_id"].astype(str),y=["β-thal","α-thal","HbE","Iron"],colorscale=[[0,"#F7EDF3"],[.5,BLOOD],[1,"#725487"]],colorbar=dict(title="score"), xgap=2, ygap=2)); fig.update_xaxes(tickangle=45)
    return _layout(fig,"คะแนนสนับสนุนแต่ละรูปแบบรายตัวอย่าง",470)

def population_sankey(df: pd.DataFrame) -> go.Figure:
    from utils.reporting import RISK_LABELS
    risks = list(df["consult_risk"].dropna().unique())
    patterns = list(df["top_pattern"].dropna().unique())
    labels = ["ตัวอย่างทั้งหมด"] + [RISK_LABELS.get(r, r) for r in risks] + patterns
    sources, targets, values = [], [], []
    for i, risk in enumerate(risks, 1):
        sub = df[df["consult_risk"] == risk]
        sources.append(0); targets.append(i); values.append(len(sub))
        for pattern, count in sub["top_pattern"].value_counts().items():
            sources.append(i); targets.append(1 + len(risks) + patterns.index(pattern)); values.append(int(count))
    fig = go.Figure(go.Sankey(node=dict(label=labels, pad=18, thickness=17, color=[PALETTE[i % len(PALETTE)] for i in range(len(labels))]),
                             link=dict(source=sources, target=targets, value=values, color="rgba(182,160,206,.25)")))
    return _layout(fig, "ภาพรวมระดับการทบทวนและรูปแบบที่สงสัย", 480)


def allele_sunburst(db: pd.DataFrame) -> go.Figure:
    fig=px.sunburst(db,color_discrete_sequence=PALETTE,path=["system","variant_class","common_name"],values="clinical_weight",color="system",hover_data=["gene","method","expected_bp"])
    return _layout(fig,"Allele knowledge-base sunburst",520)

def allele_method_bar(db: pd.DataFrame) -> go.Figure:
    counts=db.groupby(["method","system"],as_index=False).size(); fig=px.bar(counts,color_discrete_sequence=PALETTE,x="method",y="size",color="system",barmode="group",labels={"size":"Number of targets","method":"Molecular method"}); fig.update_xaxes(tickangle=25)
    return _layout(fig,"PCR panel composition by method",430)

def virtual_gel(matched: pd.DataFrame) -> go.Figure:
    lanes = list(matched["lane"].astype(str)) if "lane" in matched else [f"L{i+1}" for i in range(len(matched))]
    height, lane_width = 560, 28
    gel = np.full((height, len(lanes) * lane_width + 20), .08)
    observed = pd.to_numeric(matched.get("observed_bp", pd.Series(dtype=float)), errors="coerce")
    finite = observed[np.isfinite(observed) & (observed > 0)]
    max_bp = max(2500, float(finite.max()) + 200) if len(finite) else 2500
    for i, (_, row) in enumerate(matched.iterrows()):
        value = pd.to_numeric(row.get("observed_bp"), errors="coerce")
        if pd.isna(value) or not np.isfinite(value) or value <= 0:
            continue
        y = int((np.log(max_bp) - np.log(value)) / np.log(max_bp) * (height - 60) + 30)
        x0 = 16 + i * lane_width
        for delta in range(-3, 4):
            if 0 <= y + delta < height:
                gel[y + delta, x0:x0+lane_width-12] += .85 * np.exp(-delta**2 / 6)
    fig = go.Figure(go.Heatmap(z=np.clip(gel, 0, 1), colorscale="Greys", showscale=False))
    fig.update_xaxes(tickmode="array", tickvals=[24+i*lane_width for i in range(len(lanes))],
                     ticktext=lanes, title="ช่อง PCR")
    fig.update_yaxes(showticklabels=False, autorange="reversed")
    return _layout(fig, "เจลจำลองจากขนาดแถบที่กรอก — ไม่ใช่ภาพเจลจริง", 560)


def pcr_confidence_lollipop(matched: pd.DataFrame) -> go.Figure:
    m=matched.copy(); m["label"]=m["sample_id"].astype(str)+" • "+m["target_code"].astype(str); m=m.sort_values("confidence"); fig=go.Figure(); fig.add_trace(go.Scatter(x=m["confidence"]*100,y=m["label"],mode="markers",marker=dict(size=15,color=np.where(m["detected"],DANGER,TEAL),line=dict(width=1.5,color="#35263F" if current_theme_type() == "dark" else "#65516F")),name="Confidence"))
    for _,r in m.iterrows(): fig.add_shape(type="line",x0=0,x1=float(r["confidence"])*100,y0=r["label"],y1=r["label"],line=dict(color=stroke_color(BLOOD),width=4))
    fig.update_xaxes(range=[0,100],title="คะแนนตรงกันของขนาดแถบ (ไม่ใช่ความน่าจะเป็น)")
    return _layout(fig,"คะแนนเปรียบเทียบขนาดแถบ PCR",max(380,70+len(m)*34))

def punnett_heatmap(punnett_df: pd.DataFrame, parent1: list[str], parent2: list[str], system: str) -> go.Figure:
    from thalab.genetics import classify_alpha, classify_beta
    cell_text=[]; z=[]; sevmap={"minimal":0,"low":1,"moderate":2,"high":3,"critical":4}
    for g1 in parent1:
        row_text=[]; row_z=[]
        for g2 in parent2:
            if system=="alpha": ph,sev,_=classify_alpha(g1,g2)
            else: ph,sev=classify_beta(g1,g2)
            row_text.append(f"{g1}/{g2}<br>{ph}"); row_z.append(sevmap.get(sev,0))
        cell_text.append(row_text); z.append(row_z)
    fig=go.Figure(go.Heatmap(z=z,x=parent2,y=parent1,text=cell_text,texttemplate="%{text}",textfont=dict(color=INK),colorscale=[[0,TEAL],[.25,BLUE],[.5,GOLD],[.75,BLOOD],[1,DANGER]],showscale=True,colorbar=dict(title="severity"),xgap=3,ygap=3)); fig.update_xaxes(title="Parent 2 gamete"); fig.update_yaxes(title="Parent 1 gamete")
    return _layout(fig,f"{system.capitalize()}-globin Punnett risk matrix",510)

def punnett_sunburst(punnett_df: pd.DataFrame) -> go.Figure:
    fig=px.sunburst(punnett_df,color_discrete_map=SEVERITY_COLORS,path=["severity","phenotype","offspring_genotype"],values="probability",color="severity")
    return _layout(fig,"Offspring genotype probability sunburst",500)

def risk_probability_bar(punnett_df: pd.DataFrame) -> go.Figure:
    d=punnett_df.groupby(["severity"],as_index=False)["probability"].sum(); order=["critical","high","moderate","low","minimal"]; d["severity"]=pd.Categorical(d["severity"],categories=order,ordered=True); d=d.sort_values("severity")
    fig=px.bar(d,color="severity",color_discrete_map=SEVERITY_COLORS,x="severity",y="probability",text="probability",labels={"severity":"Severity class","probability":"Offspring probability (%)"}); fig.update_traces(texttemplate="%{text:.0f}%",textposition="outside"); fig.update_yaxes(range=[0,100])
    return _layout(fig,"Reproductive-risk probability by severity",420)
