"""Offline, synthetic-only report artifacts for the draft template designer.

This is an HTML print prototype, not a PDF engine or a clinical release service.
All variable content is escaped; no external assets, scripts or patient inputs are
accepted by the layout API. Reference intervals are deliberately not invented.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from hashlib import sha256
from html import escape
import json
from math import isfinite
from typing import Any, Mapping, Sequence

from logic.reporting import report_input_snapshot


SYNTHETIC_HEADER = {
    "patient_id": "SYNTHETIC-PATIENT-001",
    "patient_name": "บุคคลสมมติ / Synthetic person",
    "date_of_birth": "1981-01-01 (synthetic)",
    "sex": "Female (synthetic)",
    "requesting_physician": "แพทย์สมมติ / Synthetic requesting physician",
    "ward": "แผนกสมมติ / Synthetic ward",
    "specimen_id": "SYNTHETIC-SPECIMEN-001",
    "specimen": "Synthetic demonstration specimen",
    "collected_at": "2026-01-02T08:30:00+07:00 (synthetic)",
    "received_at": "2026-01-02T09:00:00+07:00 (synthetic)",
    "analyzed_at": "2026-01-02T09:15:00+07:00 (synthetic)",
    "reported_at": "NOT RELEASED / ยังไม่อนุมัติผล",
}
LANGUAGES = ("th", "en", "bilingual")
PANELS = ("cbc", "cbc_diff", "reticulocyte", "coagulation", "thalassemia", "combined")


@dataclass(frozen=True)
class ReportTemplate:
    panel: str = "cbc"
    language: str = "bilingual"
    institution: str = "ห้องปฏิบัติการสมมติ / Synthetic laboratory"
    version: str = "0.1"
    margin_mm: int = 15
    show_previous: bool = True
    show_morphology: bool = False
    show_comments: bool = True
    show_trend: bool = False

    def __post_init__(self) -> None:
        if self.panel not in PANELS:
            raise ValueError("Unknown report panel")
        if self.language not in LANGUAGES:
            raise ValueError("Unsupported report language")
        if type(self.margin_mm) is not int or not 10 <= self.margin_mm <= 30:
            raise ValueError("A4 margin must be an integer from 10 to 30 mm")
        if not isinstance(self.institution, str) or len(self.institution) > 160:
            raise ValueError("Institution must contain at most 160 characters")
        if not isinstance(self.version, str) or not self.version.strip() or len(self.version) > 40:
            raise ValueError("Template version must contain 1 to 40 characters")


def _clean(value: Any) -> Any:
    """Normalize missing numeric values to strict, portable JSON nulls."""
    if isinstance(value, Mapping):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    if hasattr(value, "item"):
        return _clean(value.item())
    if isinstance(value, float) and not isfinite(value):
        return None
    return value


def json_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(_clean(payload), ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8")


def _snapshot_digest(payload: Mapping[str, Any]) -> str:
    """Content consistency only; this unkeyed digest is not a signature."""
    content = {key: value for key, value in payload.items() if key != "snapshot_sha256"}
    canonical = json.dumps(_clean(content), sort_keys=True, ensure_ascii=False,
                           allow_nan=False, separators=(",", ":")).encode("utf-8")
    return sha256(canonical).hexdigest()


def template_payload(template: ReportTemplate) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "synthetic_report_template",
        "document_status": "DRAFT",
        "data_origin": "synthetic",
        "release_eligible": False,
        "paper": "A4",
        "reference_intervals": None,
        "template": asdict(template),
    }


def build_report_payload(
    rows: Sequence[Mapping[str, Any]],
    catalog: Mapping[str, Mapping[str, str]],
    validation: Mapping[str, Any],
    template: ReportTemplate,
    *, validation_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Bind template, rows and validation to one snapshot; fail closed on release."""
    if validation.get("decision") not in {"HOLD", "REJECT"} or validation.get("release_eligible") is not False:
        raise ValueError("The synthetic report must remain HOLD or REJECT and ineligible for release")
    if validation.get("panel") != template.panel:
        raise ValueError("The report panel does not match the evaluated panel")

    def canonical(value: Any) -> str:
        return json.dumps(report_input_snapshot(value), ensure_ascii=False, allow_nan=False, sort_keys=True)

    if "raw_rows" not in validation or canonical(rows) != canonical(validation["raw_rows"]):
        raise ValueError("The report input snapshot does not match the evaluated rows")
    if "validation_context" not in validation:
        raise ValueError("The validation context snapshot is missing")
    evaluated_context = validation["validation_context"]
    if validation_context is not None and canonical(validation_context) != canonical(evaluated_context):
        raise ValueError("The report context does not match the evaluated validation context")
    payload = template_payload(template)
    payload["artifact_type"] = "synthetic_report_validation_snapshot"
    payload["patient_specimen"] = deepcopy(SYNTHETIC_HEADER)
    payload["rows"] = _clean([dict(row) for row in rows])
    payload["catalog"] = _clean(dict(catalog))
    payload["validation"] = _clean(dict(validation))
    payload["validation_context"] = deepcopy(evaluated_context)
    payload["snapshot_sha256"] = _snapshot_digest(payload)
    return payload


def _text(th: str, en: str, language: str) -> str:
    return th if language == "th" else en if language == "en" else f"{th} / {en}"


def _display(value: Any) -> str:
    value = _clean(value)
    if value is None:
        return "—"
    return str(value)


def _e(value: Any) -> str:
    return escape(_display(value), quote=True)


def render_report_html(payload: Mapping[str, Any]) -> str:
    """Render a self-contained A4 print draft without scripts or remote assets."""
    if payload.get("snapshot_sha256") != _snapshot_digest(payload):
        raise ValueError("The report snapshot was changed after validation/export binding")
    template = ReportTemplate(**dict(payload["template"]))
    validation = payload["validation"]
    if validation.get("decision") not in {"HOLD", "REJECT"} or validation.get("release_eligible") is not False:
        raise ValueError("A synthetic draft cannot carry a release decision")
    language = template.language
    tr = lambda th, en: _text(th, en, language)
    columns = [tr("รายการตรวจ", "Test"), tr("ผลสมมติ", "Synthetic result"), tr("หน่วย", "Unit"), tr("ช่วงอ้างอิง", "Reference interval"), tr("ธงผล", "Flag")]
    if template.show_previous:
        columns.extend([tr("ผลก่อนหน้า (สมมติ)", "Previous (synthetic)"), tr("วันที่ผ่านมา", "Days earlier")])
    row_html = []
    trends = []
    for row in payload["rows"]:
        code = str(row.get("code", ""))
        item = payload["catalog"].get(code, {})
        name = tr(item.get("name_th", code), item.get("name_en", code))
        cells = [name, _display(row.get("result")), row.get("unit", ""), tr("ยังไม่กำหนด", "Not configured"), tr("ยังไม่ประเมิน", "Not assessed")]
        if template.show_previous:
            cells.extend([_display(row.get("previous_result")), _display(row.get("previous_days"))])
        row_html.append("<tr>" + "".join(f"<td>{_e(value)}</td>" for value in cells) + "</tr>")
        # A two-point comparison avoids suggesting an established longitudinal trend.
        if template.show_trend and row.get("previous_result") is not None:
            trends.append(
                f"<li>{_e(name)}: {_e(row.get('previous_result'))} → {_e(row.get('result'))} {_e(row.get('unit'))} "
                f"({_e(row.get('previous_days'))} {_e(tr('วัน', 'days'))})</li>"
            )
    finding_html = []
    for finding in validation.get("findings", []):
        evidence = json.dumps(_clean(finding.get("evidence", {})), ensure_ascii=False, allow_nan=False, sort_keys=True)
        finding_html.append(
            "<tr>" + "".join(f"<td>{_e(value)}</td>" for value in (
                finding.get("rule_id"), finding.get("status"), finding.get("message"), evidence,
            )) + "</tr>"
        )
    header = payload["patient_specimen"]
    header_fields = [
        (tr("รหัสบุคคล", "Person ID"), header["patient_id"]),
        (tr("ชื่อ", "Name"), header["patient_name"]),
        (tr("วันเกิด", "Date of birth"), header["date_of_birth"]),
        (tr("เพศ", "Sex"), header["sex"]),
        (tr("แพทย์ผู้สั่งตรวจ", "Requesting physician"), header["requesting_physician"]),
        (tr("แผนก", "Ward"), header["ward"]),
        (tr("รหัสตัวอย่าง", "Specimen ID"), header["specimen_id"]),
        (tr("ชนิดตัวอย่าง", "Specimen"), header["specimen"]),
        (tr("เก็บตัวอย่าง", "Collected"), header["collected_at"]),
        (tr("รับตัวอย่าง", "Received"), header["received_at"]),
        (tr("วิเคราะห์", "Analyzed"), header["analyzed_at"]),
        (tr("รายงานผล", "Reported"), header["reported_at"]),
    ]
    header_html = "".join(f"<div><dt>{_e(label)}</dt><dd>{_e(value)}</dd></div>" for label, value in header_fields)
    extra = ""
    if template.show_morphology:
        extra += f"<section><h2>{_e(tr('สัณฐานวิทยา', 'Morphology'))}</h2><p>{_e(tr('พื้นที่ตัวอย่าง — ยังไม่มีการประเมินสเมียร์', 'Placeholder only — no smear assessment performed'))}</p></section>"
    if template.show_comments:
        extra += f"<section><h2>{_e(tr('หมายเหตุ', 'Comments'))}</h2><p>{_e(tr('ข้อมูลทั้งหมดเป็นข้อมูลสมมติ ไม่มีช่วงอ้างอิงที่ได้รับอนุมัติ ผลไม่สามารถอนุมัติหรือใช้ดูแลผู้ป่วยได้', 'All values are synthetic. No approved reference intervals are configured. This draft cannot be released or used for patient care.'))}</p></section>"
    if template.show_trend:
        extra += f"<section><h2>{_e(tr('เปรียบเทียบสองจุดสมมติ', 'Two synthetic time points'))}</h2><p>{_e(tr('ยังไม่ยืนยันความเปรียบเทียบกันได้ทางคลินิก', 'Clinical comparability is not established'))}</p><ul>{''.join(trends) or '<li>—</li>'}</ul></section>"
    return f"""<!doctype html>
<html lang="{'th' if language != 'en' else 'en'}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DRAFT · SYNTHETIC · {_e(template.institution)}</title>
<style>
@page {{ size: A4; margin: {template.margin_mm}mm; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0 auto; max-width: 210mm; padding: 16px; color: #172033; background: white; font: 11pt Tahoma, "Leelawadee UI", sans-serif; line-height: 1.5; }}
.watermark {{ position: fixed; z-index: 0; inset: 40% 0 auto; text-align: center; color: #e8eaf2; transform: rotate(-25deg); font-size: 46pt; font-weight: bold; pointer-events: none; }}
main {{ position: relative; z-index: 1; }}
.draft {{ border: 3px solid #44428a; background: #f0efff; padding: 10px; font-weight: bold; }}
h1 {{ font-size: 19pt; margin-bottom: 4px; }} h2 {{ font-size: 13pt; margin-top: 20px; }}
dl {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px 18px; }} dl div {{ break-inside: avoid; }}
dt {{ font-weight: bold; }} dd {{ margin: 0; overflow-wrap: anywhere; }}
table {{ width: 100%; border-collapse: collapse; font-size: 9pt; table-layout: fixed; }}
th, td {{ border: 1px solid #c8cbd5; padding: 6px; vertical-align: top; overflow-wrap: anywhere; }}
th {{ background: #ecebfa; text-align: left; }} thead {{ display: table-header-group; }} tr {{ break-inside: avoid; }}
.muted, footer {{ font-size: 9pt; color: #4c5365; overflow-wrap: anywhere; }}
@media print {{
 body {{ padding: 0; max-width: none; }} .print-help {{ display: none; }} .draft {{ background: white; }}
 h2, h2 + p.muted {{ break-after: avoid-page; page-break-after: avoid; }}
 thead {{ break-inside: avoid; page-break-inside: avoid; }}
}}
</style></head><body><div class="watermark" aria-hidden="true">DRAFT · SYNTHETIC</div><main>
<p class="draft">DRAFT · SYNTHETIC · {_e(tr('ข้อมูลสมมติเท่านั้น — ห้ามใช้ดูแลผู้ป่วย', 'Synthetic data only — not for patient care'))}</p>
<p class="print-help">{_e(tr('เปิดเมนูพิมพ์ของเบราว์เซอร์แล้วเลือก A4 หรือ Save as PDF; ตรวจรูปแบบและตัวอักษรไทยก่อนใช้งานตัวอย่าง เอกสารนี้ไม่ใช่ PDF ที่ผ่านการตรวจสอบ', 'Use the browser Print menu with A4 / Save as PDF. Review layout and Thai glyphs; this is not a validated PDF export.'))}</p>
<h1>{_e(template.institution)}</h1><p>{_e(tr('แบบรายงานโลหิตวิทยาสมมติ', 'Synthetic hematology report'))} · {_e(template.panel)} · DRAFT-{_e(template.version)}</p>
<dl>{header_html}</dl>
<h2>{_e(tr('ผลตรวจสมมติ', 'Synthetic results'))}</h2>
<table><thead><tr>{''.join(f'<th>{_e(value)}</th>' for value in columns)}</tr></thead><tbody>{''.join(row_html)}</tbody></table>
<p class="muted">{_e(tr('ไม่ได้ประเมินค่าปกติ ค่าวิกฤต หรืออนุมัติผล ช่วงอ้างอิงและธงผลยังไม่ได้กำหนด', 'Normality, critical values and release are not assessed. Reference intervals and result flags are not configured.'))}</p>
{extra}
<h2>{_e(tr('การตรวจสอบข้อมูลสมมติ', 'Synthetic validation'))}: {_e(validation['decision'])}</h2>
<p class="muted">{_e(tr('ข้อความกฎในต้นแบบยังเป็นภาษาไทย รหัสกฎและหลักฐานคงเดิมทุกภาษา', 'Prototype rule messages remain in Thai; rule IDs and evidence are unchanged across languages.'))}</p>
<table><thead><tr><th>Rule</th><th>Status</th><th>{_e(tr('ข้อความ', 'Message'))}</th><th>{_e(tr('หลักฐาน', 'Evidence'))}</th></tr></thead><tbody>{''.join(finding_html)}</tbody></table>
<footer><p>DRAFT · SYNTHETIC · release_eligible = false</p><p>Snapshot SHA-256: {_e(payload.get('snapshot_sha256', ''))}</p><p>Build ID: {_e(validation.get('build_provenance', {}).get('build_id', 'not recorded'))}</p><p>{_e(tr('ไม่มีการลงนาม ไม่มีการอนุมัติ ไม่มีระบบบันทึกการพิมพ์ เอกสารสมมติจากต้นแบบในเครื่อง', 'Unsigned; no release or print audit. Synthetic artifact from a local prototype.'))}</p></footer>
</main></body></html>"""
