"""Shared native presentation components for the hematology platform.

Native controls follow the light/dark theme. Pastel presentation is centralized
in ui.palette and ui.shell_styles using application-owned container keys.
"""
from __future__ import annotations

import html
import re
from hashlib import sha256
from typing import Any, Literal

import streamlit as st

from ui.palette import card_styles, resolve_tone
from ui.identity import hero_markup
from utils.module_registry import REPORT_DESIGN_PAGE, PageSpec, load_modules, navigation_groups, navigation_pages

PAGES: tuple[PageSpec, ...] = navigation_pages()


def current_theme_type() -> str:
    """Read the selected app theme, independently of the operating-system theme."""
    try:
        theme_type = str(st.context.theme.type).lower()
    except (AttributeError, RuntimeError):
        theme_type = "light"
    return theme_type if theme_type in {"light", "dark"} else "light"


def inject_css() -> None:
    """Apply the learning-lab shell using the app's selected light/dark mode."""
    st.html(f"<style>{card_styles(current_theme_type() == 'dark')}</style>")


def pastel_card(key: str, tone: str = "lavender", **kwargs: Any) -> Any:
    """Create a native container with a stable, app-owned presentation class."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", key):
        raise ValueError("Card keys must contain only ASCII letters, digits, '_' or '-'")
    resolved = resolve_tone(tone)
    return st.container(key=f"thal_card_{resolved}__{key}", border=False, **kwargs)


def primary_action_type() -> Literal["primary", "secondary"]:
    """Keep native button labels readable with the lighter dark-theme accent.

    Streamlit uses fixed white primary-button text, while tabs share the accent
    as foreground text. Outlined actions avoid that contrast conflict in dark mode.
    """
    return "secondary" if current_theme_type() == "dark" else "primary"


def _is_active(page: PageSpec, active: str) -> bool:
    active_clean = active.strip().lower()
    return page.key.strip().lower() == active_clean or page.title.strip().lower() == active_clean


def top_navigation(active: str) -> None:
    """Render the complete catalog in the four grouped top controls."""
    st.session_state["_thal_active_nav"] = active
    st.html(
        '<header class="thal-brand"><div class="thal-brand-mark" aria-hidden="true">'
        '<span></span><span></span></div><div><small>Observe · connect · understand</small>'
        '<p>ThalLink <span>Hematologic Platform</span></p></div>'
        '<span class="thal-edition">LEARNING LAB</span></header>'
    )
    from ui.navigation import render_top_navigation
    render_top_navigation(active)


def page_card_navigation(active: str | None = None) -> None:
    """Compatibility no-op; top_navigation already renders all route controls."""


def module_launch_card(title: str, body: str, bullets: list[str], page_path: str, icon: str, cta: str) -> None:
    """A content card with a clear, native navigation action."""
    key = "launch_" + sha256(page_path.encode("utf-8")).hexdigest()[:12]
    with pastel_card(key, "sky"):
        st.subheader(f"{icon} {title}")
        st.markdown(body)
        for item in bullets:
            st.caption(f"• {item}")
        st.page_link(page_path, label=cta, icon=":material/arrow_forward:", width="stretch")


def hero(title: str, subtitle: str, eyebrow: str = "Hematologic decision support", show_navigation: bool = True) -> None:
    """Introduce the workspace; retain the legacy show_navigation argument."""
    active = st.session_state.get("_thal_active_nav", "Command center")
    home_group = navigation_groups()[0]
    tone = next(
        (module.id for module in load_modules() if any(_is_active(route, active) for route in module.routes)),
        "report_designer" if _is_active(REPORT_DESIGN_PAGE, active) else home_group.tone,
    )
    with pastel_card("page_intro", tone, gap="small"):
        st.html(hero_markup(title, subtitle, eyebrow, compact=not _is_active(home_group.pages[0], active)))


def section(title: str, caption: str | None = None) -> None:
    st.header(title, anchor=False)
    if caption:
        st.caption(caption)


def metric_card(label: str, value: str, caption: str = "", level: str = "info", *, key: str | None = None) -> None:
    """Keep long phenotype/genotype values readable instead of truncating them."""
    icons = {"info": "analytics", "high": "priority_high", "moderate": "info", "low": "check_circle", "danger": "warning"}
    tones = {"info": "sky", "high": "rose", "moderate": "peach", "low": "mint", "danger": "coral"}
    card_key = key or "metric_" + sha256(label.encode("utf-8")).hexdigest()[:12]
    with pastel_card(card_key, tones.get(level, "lavender"), gap="xsmall"):
        if len(str(value)) > 22:
            st.caption(label)
            st.markdown(f"**{value}**")
        else:
            st.metric(f":material/{icons.get(level, 'analytics')}: {label}", value)
        if caption:
            st.caption(caption)


def clinical_box(text: str, level: str = "warn") -> None:
    """Accept legacy emphasis tags while rendering semantic, accessible callouts."""
    markdown = re.sub(r"</?(?:b|strong)>", "**", text, flags=re.IGNORECASE)
    markdown = re.sub(r"<br\s*/?>", "\n\n", markdown, flags=re.IGNORECASE)
    markdown = html.unescape(re.sub(r"<[^>]*>", "", markdown))
    renderer, icon = {
        "warn": (st.warning, ":material/warning:"),
        "danger": (st.error, ":material/priority_high:"),
        "success": (st.success, ":material/check_circle:"),
        "info": (st.info, ":material/info:"),
    }.get(level, (st.warning, ":material/warning:"))
    renderer(markdown, icon=icon)


def pills(items: list[str], color: str = "red") -> None:
    badge_color = {"gold": "orange"}.get(color, color)
    if badge_color not in {"red", "orange", "yellow", "blue", "green", "violet", "gray", "primary"}:
        badge_color = "gray"
    with st.container(horizontal=True, gap="small"):
        for item in items:
            st.badge(str(item), color=badge_color)


def disclaimer(text: str | None = None) -> None:
    from utils.reporting import DISCLAIMER
    st.warning(DISCLAIMER if text is None else text, icon=":material/health_and_safety:")
    st.caption(":material/lock: ใช้รหัสตัวอย่างสมมติเท่านั้น ไม่กรอกชื่อ HN เลขบัตรประชาชน หรือข้อมูลระบุตัวบุคคล แอปไม่บันทึกข้อมูลตรวจลงไฟล์หรือฐานข้อมูล")


def production_footer() -> None:
    with st.container(key="thal_footer", gap="xsmall"):
        st.caption("ThalLink · Hematologic Platform — ผลเป็นร่างเพื่อสนับสนุนการคัดกรองและทบทวนผล ไม่ใช่การวินิจฉัยโรค กฎแต่ละโมดูลรอทบทวนตาม SOP ของหน่วยงาน")


def sidebar_brand(active: str) -> None:
    """Backward-compatible alias for the top toolbar."""
    top_navigation(active)
