"""Preserve chart/table/embed descriptions across Streamlit signatures.

Some installations lack the native ``alt`` parameter on display commands.
Use an adjacent visible description there, and native accessible names when
available. A caption does not set a legacy iframe's accessible title. Other
arguments and return values are forwarded without filtering.
"""
from __future__ import annotations

from inspect import signature
from typing import Any, Callable

import streamlit as st


def _described_render(
    renderer: Callable[..., Any], data: Any, *args: Any,
    alt: str | None = None, **kwargs: Any,
) -> Any:
    if alt is not None:
        if "alt" in signature(renderer).parameters:
            kwargs["alt"] = alt
        elif alt:
            st.caption(alt)
    return renderer(data, *args, **kwargs)


def dataframe(data: Any = None, *args: Any, alt: str | None = None, **kwargs: Any) -> Any:
    return _described_render(st.dataframe, data, *args, alt=alt, **kwargs)


def data_editor(data: Any, *args: Any, alt: str | None = None, **kwargs: Any) -> Any:
    return _described_render(st.data_editor, data, *args, alt=alt, **kwargs)


def plotly_chart(figure_or_data: Any, *args: Any, alt: str | None = None, **kwargs: Any) -> Any:
    return _described_render(st.plotly_chart, figure_or_data, *args, alt=alt, **kwargs)


def iframe(src: Any, *args: Any, alt: str | None = None, **kwargs: Any) -> Any:
    return _described_render(st.iframe, src, *args, alt=alt, **kwargs)
