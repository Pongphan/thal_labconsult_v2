"""Use the existing strict CSV parser with domain-specific fields and no identities."""
from __future__ import annotations

from typing import Any

from ui.data_io import MAX_BYTES, MAX_ROWS, ScreeningCSVError
from utils.csv_io import read_csv_table
from utils.reporting import csv_bytes

def domain_template(rules: dict[str, Any], *, example: bool = False) -> bytes:
    fields = rules["fields"]
    headers = [item["key"] for item in fields]
    data = rules["examples"][0]["data"] if example and rules["examples"] else {}
    values = []
    for item in fields:
        value = data.get(item["key"], "unknown" if item["type"] == "select" else "")
        values.append("|".join(value) if isinstance(value, list) else value)
    return csv_bytes([headers, values])


def read_domain_csv(payload: bytes, rules: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    fields = rules["fields"]
    unit_columns = {item["key"] + "_unit": item["key"] for item in fields if item["type"] == "number"}
    frame, notes = read_csv_table(payload, [*[item["key"] for item in fields], *unit_columns], unit_columns=unit_columns)
    rows = []
    for source in frame.to_dict("records"):
        row: dict[str, Any] = {}
        for item in fields:
            value = source.get(item["key"])
            if item["type"] == "multiselect":
                value = [token.strip() for token in str(value).split("|") if token.strip()] if value else []
            row[item["key"]] = value
        row.update({key: source[key] for key in unit_columns if key in source})
        rows.append(row)
    # Domain reports generate their own identifiers; no uploaded identifiers survive.
    return rows, notes
