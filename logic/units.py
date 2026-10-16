"""Optional explicit unit declarations shared by screening and domain review.

Legacy field names already declare their canonical units. When callers provide
extra unit metadata, reject mismatches; never guess or silently convert values.
"""
from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any

from pandas import isna
from pandas.api.types import is_scalar

CANONICAL_UNITS = {
    "age": "years", "hb_g_dl": "g/dL", "rbc_10e12_l": "10^12/L",
    "hct_percent": "%", "mcv_fl": "fL", "mch_pg": "pg", "mchc_g_dl": "g/dL",
    "rdw_percent": "%", "retic_percent": "%", "ferritin_ng_ml": "ng/mL",
    "wbc_10e9_l": "10^9/L", "platelets_10e9_l": "10^9/L", "retic_abs_10e9_l": "10^9/L",
    **{field: "%" for field in ("hba_percent", "hba2_percent", "hba2e_percent", "hbf_percent", "hbe_percent", "bart_percent", "hbh_percent", "hbcs_percent")},
}
UNIT_ALIASES = {
    "ปี": "years", "year": "years", "10¹²/L": "10^12/L", "10⁹/L": "10^9/L",
    "วินาที": "s", "seconds": "s", "second": "s",
    "ชั่วโมง": "h", "hours": "h", "hour": "h", "เซลล์": "cells",
}
# These aliases identify the same measurand, never a combined/resolved Hb peak.
MEASUREMENT_ALIASES = {
    "hba2": "hba2_percent", "HbA2": "hba2_percent",
    "hba2e": "hba2e_percent", "HbA2/E": "hba2e_percent",
}


def canonical_unit(value: str) -> str:
    """Normalize documented spelling aliases only; never rescale a measurement."""
    return UNIT_ALIASES.get(value.strip(), value.strip())


def _missing_declaration(value: Any) -> bool:
    """Treat scalar dataframe missingness like an omitted optional declaration."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return True
    # Containers are malformed declarations, even if every element is missing.
    # In particular, bool(isna([None])) would accidentally accept a list.
    if not is_scalar(value):
        return False
    try:
        return bool(isna(value))
    except (TypeError, ValueError):
        return False


def validate_declared_units(
    source: Mapping[str, Any], fields: Mapping[str, Any],
    *, canonical_units: Mapping[str, str | None] | None = None,
    input_fields: Collection[str] = (),
) -> tuple[list[str], set[str], dict[str, str]]:
    """Accept `units={field: unit}` or `<field>_unit`; preserve declared strings.

    Missing optional metadata uses the unit fixed by the field schema. Aliased
    metadata and suffix/map declarations are checked together, without choosing
    one over a conflicting declaration. Orphan or unknown declarations fail.
    A mismatched string is retained while its measurement is invalidated.
    ``input_fields`` distinguishes actual schema fields such as ``ddimer_unit``
    from optional metadata suffixes. A None expected unit requires resolving the
    method/unit selector before accepting an explicit declaration.
    """
    errors: list[str] = []
    invalid: set[str] = set()
    metadata: dict[str, str] = {}
    expected_units = CANONICAL_UNITS if canonical_units is None else canonical_units
    aliases = {alias: target for alias, target in MEASUREMENT_ALIASES.items() if target in fields}
    declarations: dict[str, list[Any]] = {}

    def add(name: Any, value: Any) -> None:
        field = aliases.get(name, name) if isinstance(name, str) else None
        if field not in fields or field not in expected_units:
            errors.append("พบชื่อผลตรวจในข้อมูลหน่วยที่ระบบไม่รองรับ กรุณาตรวจโครงสร้างข้อมูล")
            return
        declarations.setdefault(field, []).append(value)

    declared = source.get("units", {})
    if _missing_declaration(declared):
        declared = {}
    elif not isinstance(declared, Mapping):
        errors.append("ข้อมูล units ต้องเป็น mapping ของชื่อผลตรวจกับหน่วย กรุณาตรวจหน่วยก่อนแปลผล")
        invalid.update(fields)
        declared = {}
    for name, value in declared.items():
        add(name, value)
    for name, value in source.items():
        if isinstance(name, str) and name.endswith("_unit") and name not in input_fields:
            add(name.removesuffix("_unit"), value)
    for field, values in declarations.items():
        names = {field, *(alias for alias, target in aliases.items() if target == field)}
        orphan = not names.intersection(source)
        expected = expected_units[field]
        expected = canonical_unit(expected) if isinstance(expected, str) else None
        for value in values:
            # Blank optional CSV metadata uses the unit declared in the header.
            if _missing_declaration(value):
                continue
            unit = value.strip() if isinstance(value, str) else None
            canonical = canonical_unit(unit) if unit is not None else None
            if orphan or expected is None or canonical != expected:
                if orphan:
                    errors.append(f"ระบุหน่วย {field} แต่ไม่มีช่องผลตรวจที่จับคู่กัน กรุณาทบทวนโครงสร้างข้อมูล")
                elif expected is None:
                    errors.append(f"ยังไม่ระบุหน่วยอ้างอิงของ {field} ที่ใช้ตรวจสอบได้ กรุณาทบทวนตัวเลือกวิธีตรวจและหน่วย")
                else:
                    errors.append(f"หน่วย {field} ไม่ตรงกับ {expected}; กรุณาแปลงและตรวจสอบข้อมูลก่อนประเมิน ระบบไม่แปลงหน่วยอัตโนมัติ")
                invalid.add(field)
                if unit is not None:
                    metadata[field] = unit
            elif field not in invalid:
                metadata[field] = canonical
    return errors, invalid, metadata
