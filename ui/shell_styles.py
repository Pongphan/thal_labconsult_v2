"""Presentation scoped to app-owned keys and markup, inspired by the learning lab."""
from __future__ import annotations


def shell_styles(dark: bool, tones: dict, tokens: dict) -> str:
    text = tokens["dark" if dark else "light"]
    paper = "#293247" if dark else "#FFFFFF"
    edge = "#9EACC5" if dark else "#CDBDCA"
    css = f"""
:root {{ --thal-ink:{text['ink']}; --thal-muted:{text['muted']}; --thal-paper:{paper}; --thal-edge:{edge}; --thal-focus:{text['focus']}; }}
/* One layout boundary; forms, warnings, tables and chart canvases stay native. */
.stMainBlockContainer {{ max-width:1280px; padding-top:4.75rem; padding-bottom:2.5rem; }}
.thal-brand {{ display:flex; align-items:center; gap:13px; margin:0 0 6px; }}
.thal-brand p {{ color:var(--thal-ink); font:700 34px/1.25 Georgia,serif; letter-spacing:-.8px; margin:0; }}
.thal-brand p span {{ font:400 17px/1.5 system-ui,sans-serif; letter-spacing:0; margin-left:10px; color:var(--thal-muted); }}
.thal-brand small {{ display:block; color:var(--thal-muted); font:600 14px/1.8 system-ui,sans-serif; letter-spacing:1.8px; text-transform:uppercase; }}
.thal-brand-mark {{ position:relative; width:48px; height:48px; flex-shrink:0; background:{'#392938' if dark else '#F4E0E8'}; border:1px solid var(--thal-edge); border-radius:15px; }}
.thal-brand-mark span {{ position:absolute; width:25px; height:18px; border:5px solid {'#DEABC0' if dark else '#A85576'}; border-radius:50%; transform:rotate(-30deg); top:8px; left:6px; }}
.thal-brand-mark span+span {{ top:22px; left:19px; width:19px; height:14px; border-width:4px; }}
.thal-edition {{ margin-left:auto; color:var(--thal-muted); border:1px solid var(--thal-edge); border-radius:99px; padding:7px 13px; font:600 14px/1.5 system-ui,sans-serif; letter-spacing:1.4px; white-space:nowrap; }}
.st-key-thal_top_nav {{ margin:4px 0 8px; }}
/* Global app-owned wrappers also match native popover content in its portal. */
[class*="st-key-thal_top_"][class] button {{ min-height:calc(52px * 1.1); border:1px solid var(--nav-border, var(--thal-edge)); border-radius:12px; font-size:1rem; font-weight:600; white-space:normal; background:var(--nav-bg, var(--thal-paper)); color:var(--thal-ink); }}
[class*="st-key-thal_top_"][class*="_active_"] button {{ border:2px solid var(--nav-accent); box-shadow:inset 0 -3px 0 var(--nav-accent); }}
[class*="st-key-thal_top_"][class] button:hover {{ filter:brightness({'1.06' if dark else '.98'}); }}
[class*="st-key-thal_top_"][class] button:focus-visible {{ outline:3px solid var(--thal-focus); outline-offset:3px; }}
[class*="st-key-thal_card_"][class] {{ background:var(--thal-card-bg); border:1px solid var(--thal-card-border); border-radius:18px; padding:clamp(1rem,1.7vw,1.5rem); box-sizing:border-box; min-width:0; }}
[class*="st-key-thal_card_"][class] p {{ line-height:1.7; }}
[class*="st-key-thal_card_"][class]:focus-within {{ outline:2px solid var(--thal-focus); outline-offset:3px; }}
[class*="__page_intro"][class] {{ padding:clamp(1.4rem,2.5vw,2rem); }}
/* Content remains unconstrained when large Thai labels or expanders grow.
   Intrinsic sizing adds 10% to the card itself where supported; other engines
   receive 10% more vertical padding without imposing a scrolling fixed height.
   https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Values/calc-size */
[class*="__home_module_"][class], [class*="__home_group_intro_"][class] {{ padding-block:calc(clamp(1rem,1.7vw,1.5rem) * 1.1); }}
[class*="__page_intro"][class] {{ padding-block:calc(clamp(1.4rem,2.5vw,2rem) * 1.1); }}
@supports (height:calc-size(auto, size * 1.1)) {{
 [class*="__home_module_"][class], [class*="__home_group_intro_"][class] {{ padding-block:clamp(1rem,1.7vw,1.5rem); height:calc-size(auto, size * 1.1); flex-grow:0; }}
 [class*="__page_intro"][class] {{ padding-block:clamp(1.4rem,2.5vw,2rem); height:calc-size(auto, size * 1.1); flex-grow:0; }}
}}
.thal-hero {{ display:grid; grid-template-columns:minmax(0,1.6fr) minmax(180px,1fr); align-items:center; gap:1.5rem; }}
.thal-eyebrow {{ color:var(--thal-card-accent); font-size:.72rem; font-weight:650; letter-spacing:1.8px; text-transform:uppercase; margin:0 0 12px; }}
.thal-hero-title {{ color:var(--thal-ink); font-size:calc(clamp(28px,3.2vw,42px) + 4px); line-height:1.35; font-weight:700; margin:0 0 12px; letter-spacing:-.8px; }}
.thal-hero-description {{ color:var(--thal-muted); font-size:1rem; line-height:1.8; max-width:58ch; margin:0; }}
.thal-hero-tags {{ display:flex; gap:8px; flex-wrap:wrap; margin-top:18px; font-size:16px; align-items:center; color:var(--thal-card-accent); }}
.thal-hero-tags span {{ border:1px solid var(--thal-card-border); border-radius:99px; padding:4px 11px; }}
.thal-hero-tags b {{ font-weight:400; }}
.thal-hero-visual {{ max-width:330px; justify-self:end; width:100%; }}
.thal-cell-art {{ display:block; width:100%; height:auto; }}
.thal-hero--compact {{ display:block; }}
.thal-hero--compact .thal-hero-title {{ font-size:calc(clamp(24px,2.4vw,32px) + 4px); margin-bottom:8px; }}
.thal-hero--compact .thal-hero-description {{ max-width:90ch; }}
.thal-hero--compact .thal-hero-visual,.thal-hero--compact .thal-hero-tags {{ display:none; }}
.thal-module-heading {{ display:flex; gap:12px; align-items:center; color:var(--thal-card-accent); }}
.thal-module-icon {{ display:grid; place-items:center; width:42px; height:42px; border:1px solid var(--thal-card-border); border-radius:12px; flex-shrink:0; }}
.thal-module-category {{ flex:1; font-size:16px; }} .thal-module-index {{ font-size:15px; }}
.st-key-thal_footer {{ border-top:1px solid var(--thal-edge); margin-top:28px; padding-top:18px; }}
@media(max-width:700px) {{
 .thal-brand p {{ font-size:30px; }} .thal-brand p span,.thal-edition {{ display:none; }}
 .thal-hero {{ grid-template-columns:1fr; }} .thal-hero-visual {{ display:none; }}
 .st-key-thal_top_nav {{ flex-wrap:wrap; }} .st-key-thal_top_nav > div {{ min-width:135px; }}
 [class*="st-key-thal_top_"][class] button {{ min-height:calc(48px * 1.1); }} .stMainBlockContainer {{ padding-top:4.5rem; }}
}}
@media(prefers-reduced-motion:reduce) {{ .st-key-thal_top_nav button {{ transition:none; }} }}
@media(forced-colors:active) {{ [class*="st-key-thal_card_"][class] {{ border-color:CanvasText; }} }}
"""
    for name, tone in tones.items():
        background = tone.dark if dark else tone.light
        accent = tone.dark_accent if dark else tone.accent
        border = tone.dark_border if dark else tone.border
        css += f"""
[class*="st-key-thal_card_{name}__"] {{ --thal-card-bg:{background}; --thal-card-accent:{accent}; --thal-card-border:{border}; }}
[class*="st-key-thal_top_{name}_"] {{ --nav-bg:{background}; --nav-accent:{accent}; --nav-border:{border}; }}
"""
    return css
