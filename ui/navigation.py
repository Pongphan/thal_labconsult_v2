"""Grouped top navigation using native, session-aware page controls."""
from __future__ import annotations

from pathlib import PurePosixPath

import streamlit as st

from ui.palette import resolve_tone
from utils.module_registry import REPORT_DESIGN_PAGE, STATUS_LABELS, UTILITY_PRESENTATION, PageSpec, navigation_groups

# Menu placeholders have no executable pages until their tools are implemented.
PLANNED_OTHER_ITEMS = (
    ("ai_assessment", "การประเมินผลด้วย AI", UTILITY_PRESENTATION["ai_assessment"].icon),
)


def navigation_key(path: str) -> str:
    return "thal_nav_home" if path == "app.py" else f"thal_nav_{PurePosixPath(path).stem}"


def _route_button(route: PageSpec, current: PageSpec, tone: str, icon: str) -> None:
    selected = route.path == current.path
    state = "active" if selected else "idle"
    route_key = f"thal_top_{resolve_tone(tone)}_{state}_route_{PurePosixPath(route.path).stem}"
    with st.container(key=route_key, width="stretch"):
        if st.button(route.title, icon=":material/check_circle:" if selected else icon,
                     key=f"top_{navigation_key(route.path)}", width="stretch",
                     help="กำลังใช้งาน" if selected else route.caption) and not selected:
            st.switch_page(route.path)


def render_top_navigation(active: str) -> None:
    """Home and three clinical categories preserve the current workspace state."""
    groups = navigation_groups()
    pages = tuple(page for group in groups for page in group.pages)
    active_key = active.strip().lower()
    current = next((page for page in pages if active_key in {page.key.lower(), page.title.lower()}), pages[0])
    # Navigation metadata is independent of clinical drafts and report snapshots.
    st.session_state["_platform_page"] = current.path
    st.session_state["_platform_current_page"] = current.path
    with st.container(horizontal=True, gap="small", key="thal_top_nav"):
        for group in groups:
            selected = any(page.path == current.path for page in group.pages)
            state = "active" if selected else "idle"
            with st.container(key=f"thal_top_{group.tone}_{state}_{group.id}", width="stretch"):
                icon = ":material/check_circle:" if selected else group.icon
                if group.id == "home":
                    home = group.pages[0]
                    if st.button(group.title, icon=icon, key=f"top_{navigation_key(home.path)}",
                                 width="stretch", help="กำลังใช้งาน" if selected else home.caption) and not selected:
                        st.switch_page(home.path)
                else:
                    with st.popover(group.title, icon=icon, width="stretch"):
                        for module in group.modules:
                            if len(module.routes) > 1:
                                st.caption(module.title)
                            for route in module.routes:
                                _route_button(route, current, module.presentation.tone, module.presentation.icon)
                        if group.id == "other":
                            for item_id, title, item_icon in PLANNED_OTHER_ITEMS:
                                with st.container(key=f"thal_top_{resolve_tone(item_id)}_idle_planned_{item_id}",
                                                  width="stretch", gap="xsmall"):
                                    st.button(title, icon=item_icon, key=f"top_planned_{item_id}",
                                              width="stretch", disabled=True, help=STATUS_LABELS["planned"])
                                    st.caption(STATUS_LABELS["planned"])
                            _route_button(REPORT_DESIGN_PAGE, current, "report_designer", REPORT_DESIGN_PAGE.icon)


def render_sidebar_navigation(active: str) -> None:
    """Compatibility no-op: navigation is rendered exclusively at the top."""
