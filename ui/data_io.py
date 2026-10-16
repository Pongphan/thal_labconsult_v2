"""In-memory CSV ingestion and de-identification; no clinical interpretation."""

from __future__ import annotations

from uuid import uuid4

import pandas as pd
from logic.units import CANONICAL_UNITS, MEASUREMENT_ALIASES

from utils.csv_io import CSVInputError, MAX_BYTES, MAX_ROWS, read_csv_table


# Compatibility name for existing UI consumers.
ScreeningCSVError = CSVInputError


def read_screening_csv(payload: bytes, allowed_columns: list[str], batch_id: str | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Retain every data row, remove unknown fields, and replace identifiers."""
    aliases = {alias: field for alias, field in MEASUREMENT_ALIASES.items() if field in allowed_columns}
    aliases.update({alias + "_unit": field + "_unit" for alias, field in list(aliases.items())})
    unit_columns = {field + "_unit": field for field in CANONICAL_UNITS if field in allowed_columns}
    frame, notes = read_csv_table(payload, [*allowed_columns, *unit_columns], aliases=aliases, unit_columns=unit_columns)
    token = batch_id or uuid4().hex[:8].upper()
    frame["sample_id"] = [f"CASE-{token}-{position + 1:04d}" for position in range(len(frame))]
    notes.append("ระบบแทนรหัสต้นฉบับด้วยรหัส CASE ตามลำดับแถว และไม่เก็บชื่อหรือ HN ในตารางผลลัพธ์")
    return frame.reset_index(drop=True), notes


def deidentify_demo(frame: pd.DataFrame, allowed_columns: list[str]) -> pd.DataFrame:
    """Keep the same ingestion schema for an explicitly selected demonstration."""
    work = frame[[column for column in allowed_columns if column in frame.columns]].copy()
    token = uuid4().hex[:8].upper()
    work["sample_id"] = [f"CASE-{token}-{position + 1:04d}" for position in range(len(work))]
    return work.reset_index(drop=True)
