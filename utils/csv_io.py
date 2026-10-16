"""Bounded, strict CSV parsing shared by the local review workspaces."""
from __future__ import annotations

import csv
from io import StringIO
from typing import Mapping, Sequence
import unicodedata

import pandas as pd

MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 200
MAX_COLUMNS = 128
MAX_FIELD_CHARS = 4096


class CSVInputError(ValueError):
    """A safe user-facing error that never repeats uploaded cell contents."""


def _header_key(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def read_csv_table(
    payload: bytes,
    allowed_columns: Sequence[str],
    *,
    aliases: Mapping[str, str] | None = None,
    required_columns: Sequence[str] = (),
    unit_columns: Mapping[str, str] | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Validate the full CSV before removing unknown columns; retain blank rows.

    Row limits are enforced while reading, before materializing a DataFrame.
    Header aliases, case, Unicode width, and surrounding spaces are normalized
    before duplicate detection, so conflicting results can never be discarded.
    If unit_columns is supplied, unit declarations must be recognized and have
    a matching measurement header before unknown columns are removed.
    """
    if len(payload) > MAX_BYTES:
        raise CSVInputError("ไฟล์ต้องมีขนาดไม่เกิน 2 MB")
    if not payload or not payload.strip():
        raise CSVInputError("ไฟล์ว่าง กรุณาเลือก CSV ที่มีหัวคอลัมน์และแถวข้อมูล")
    text = None
    for encoding in ("utf-8-sig", "cp874"):
        try:
            text = payload.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None or "\x00" in text:
        raise CSVInputError("อ่านภาษาในไฟล์ไม่ได้ กรุณาบันทึกเป็น CSV แบบ UTF-8 แล้วอัปโหลดอีกครั้ง")

    canonical = {_header_key(column): column for column in allowed_columns}
    canonical.update({_header_key(key): value for key, value in (aliases or {}).items()})
    try:
        reader = csv.reader(StringIO(text, newline=""), strict=True)
        original_headers = next(reader, [])
        if not original_headers or all(not cell.strip() for cell in original_headers):
            raise CSVInputError("ไม่พบหัวคอลัมน์ กรุณาใช้ไฟล์ตัวอย่างเป็นโครงสร้าง")
        if len(original_headers) > MAX_COLUMNS:
            raise CSVInputError(f"รองรับไม่เกิน {MAX_COLUMNS} คอลัมน์ กรุณาใช้โครงสร้างไฟล์ตัวอย่าง")
        if any(len(cell) > MAX_FIELD_CHARS for cell in original_headers):
            raise CSVInputError("หัวคอลัมน์ยาวเกินขอบเขต กรุณาใช้โครงสร้างไฟล์ตัวอย่าง")
        headers = [canonical.get(_header_key(column), _header_key(column)) for column in original_headers]
        if any(not column for column in headers):
            raise CSVInputError("หัวคอลัมน์มีช่องว่าง กรุณาระบุชื่อคอลัมน์ให้ครบ")
        if len(headers) != len(set(headers)):
            raise CSVInputError("พบชื่อคอลัมน์ซ้ำหรือชื่อย่อที่อ้างถึงผลเดียวกัน กรุณาเลือกคอลัมน์ต้นฉบับเพียงหนึ่งคอลัมน์")
        if unit_columns is not None:
            for column in headers:
                if column in unit_columns and unit_columns[column] not in headers:
                    raise CSVInputError("พบคอลัมน์หน่วยที่ไม่มีคอลัมน์ผลตรวจจับคู่ กรุณาทบทวนหัวคอลัมน์ก่อนประเมิน")
                if (column.endswith("_unit") or column == "units") and column not in allowed_columns:
                    raise CSVInputError("พบคอลัมน์หน่วยที่ไม่รองรับ กรุณาใช้ชื่อหน่วยที่จับคู่กับผลตรวจตามไฟล์ตัวอย่าง")
        if not set(required_columns).issubset(headers):
            raise CSVInputError("คอลัมน์ที่จำเป็นไม่ครบ กรุณาใช้หัวคอลัมน์จากไฟล์ตัวอย่าง")
        if not set(allowed_columns).intersection(headers):
            raise CSVInputError("ไม่พบคอลัมน์ที่ระบบรองรับ กรุณาตรวจหัวคอลัมน์เทียบไฟล์ตัวอย่าง")
        rows: list[list[str]] = []
        for row_number, record in enumerate(reader, start=2):
            if len(rows) >= MAX_ROWS:
                raise CSVInputError("ประเมินได้ไม่เกิน 200 แถวต่อครั้ง กรุณาแบ่งไฟล์")
            if not record:
                record = [""] * len(headers)
            if len(record) != len(headers):
                raise CSVInputError(f"แถวที่ {row_number} มีจำนวนช่องไม่ตรงกับหัวคอลัมน์ กรุณาตรวจตัวคั่นและเครื่องหมายคำพูด")
            if any(len(cell) > MAX_FIELD_CHARS for cell in record):
                raise CSVInputError(f"แถวที่ {row_number} มีข้อความยาวเกิน {MAX_FIELD_CHARS} ตัวอักษรต่อช่อง กรุณาตรวจข้อมูล")
            rows.append(record)
    except csv.Error:
        raise CSVInputError("รูปแบบ CSV ไม่ถูกต้อง กรุณาตรวจเครื่องหมายคำพูดและตัวคั่นคอลัมน์") from None
    if not rows:
        raise CSVInputError("ไฟล์มีเฉพาะหัวคอลัมน์ ยังไม่มีแถวข้อมูลสำหรับประเมิน")
    frame = pd.DataFrame(rows, columns=headers)
    unknown = [column for column in headers if column not in allowed_columns]
    notes = []
    if unknown:
        notes.append(f"ไม่นำคอลัมน์ที่ระบบไม่รองรับ {len(unknown)} คอลัมน์มาใช้หรือส่งออก กรุณาตรวจชื่อคอลัมน์เทียบไฟล์ตัวอย่าง")
    return frame[[column for column in allowed_columns if column in frame.columns]].copy(), notes
