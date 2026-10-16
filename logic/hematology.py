"""Explicit dispatcher for the six additional hematology workspaces."""
from __future__ import annotations

from importlib import import_module
from typing import Any, Mapping

from logic.hematology_common import DOMAIN_IDS, ReviewResult


def analyze_domain(module_id: str, data: Mapping[str, Any]) -> ReviewResult:
    if module_id not in DOMAIN_IDS:
        raise ValueError("ไม่พบกลุ่มงานที่รองรับ")
    # Module and function names come only from the fixed allowlist above.
    module = import_module(f"logic.{module_id}")
    analyzer = getattr(module, f"analyze_{module_id}")
    return analyzer(data)
