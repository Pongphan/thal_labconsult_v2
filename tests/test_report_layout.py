"""Export security and immutable draft constraints of the synthetic designer."""
from copy import deepcopy
from html.parser import HTMLParser
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest
from ui.navigation import navigation_key

from logic.reporting import PANEL_FIELDS, TEST_CATALOG, demo_rows, validate_report
from utils.report_layout import (
    ReportTemplate, SYNTHETIC_HEADER, build_report_payload, json_bytes,
    render_report_html, template_payload,
)


class ParsedHTML(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.tags = []
        self.attributes = []
        self.text = []
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attributes.extend(attrs)

    def handle_data(self, data):
        self.text.append(data)


def bundle(panel="cbc", **settings):
    rows = demo_rows(panel)
    return build_report_payload(rows, TEST_CATALOG, validate_report(rows, panel=panel), ReportTemplate(panel=panel, **settings))


@pytest.mark.parametrize("panel", tuple(PANEL_FIELDS))
@pytest.mark.parametrize("language", ("th", "en", "bilingual"))
def test_every_panel_language_remains_synthetic_draft_without_fabricated_ranges(panel, language):
    payload = bundle(panel, language=language)
    html = render_report_html(payload)
    assert payload["release_eligible"] is False
    assert payload["reference_intervals"] is None
    assert payload["patient_specimen"] == SYNTHETIC_HEADER
    assert payload["validation"]["decision"] == "HOLD"
    assert len(payload["rows"]) == len(PANEL_FIELDS[panel])
    assert "DRAFT · SYNTHETIC" in html
    assert "release_eligible = false" in html
    assert ("ยังไม่กำหนด" if language == "th" else "Not configured") in html
    assert "@page { size: A4; margin: 15mm; }" in html
    assert "SYNTHETIC-PATIENT-001" in html


def test_all_variable_content_is_escaped_and_has_no_network_or_active_content():
    attack = '</td><script>alert("x")</script><img src="https://example.invalid/a" onerror="alert(1)">'
    rows = demo_rows("cbc")
    rows[0]["unit"] = attack
    catalog = deepcopy(TEST_CATALOG)
    catalog["hb_g_dl"]["name_en"] = attack
    validation = validate_report(rows, panel="cbc")
    validation["findings"][0]["message"] = attack
    validation["findings"][0]["evidence"] = {"user_content": attack}
    payload = build_report_payload(rows, catalog, validation, ReportTemplate(institution=attack[:160], version='<svg/onload="x">', language="en"))
    html = render_report_html(payload)
    parsed = ParsedHTML(html)
    assert not {"script", "img", "svg", "iframe", "object", "embed", "link"}.intersection(parsed.tags)
    assert not any(key.startswith("on") or key in {"src", "href", "srcdoc"} for key, _ in parsed.attributes)
    assert "&lt;script&gt;" in html
    assert attack in "".join(parsed.text)
    assert payload["validation"]["decision"] == "REJECT"
    assert "DRAFT · SYNTHETIC" in html


@pytest.mark.parametrize("changes", [
    {"margin_mm": '15; } </style><script>x</script>'},
    {"margin_mm": 9}, {"margin_mm": 31}, {"margin_mm": True},
    {"language": 'en" onload="x'}, {"panel": "other"},
    {"version": ""},
])
def test_template_rejects_unsafe_or_unsupported_layout_configuration(changes):
    with pytest.raises(ValueError):
        ReportTemplate(**changes)


@pytest.mark.parametrize("decision,eligible", [("PASS", False), ("HOLD", True), ("RELEASED", True), ("HOLD", None)])
def test_release_is_rejected_at_both_export_boundaries(decision, eligible):
    payload = bundle()
    validation = {**payload["validation"], "decision": decision, "release_eligible": eligible}
    with pytest.raises(ValueError):
        build_report_payload(demo_rows("cbc"), TEST_CATALOG, validation, ReportTemplate())
    payload["validation"] = validation
    with pytest.raises(ValueError):
        render_report_html(payload)


def test_snapshot_hash_changes_with_current_values_template_and_validation_context():
    initial = bundle()
    rows = demo_rows("cbc")
    rows[0]["result"] = -1.0
    changed = build_report_payload(rows, TEST_CATALOG, validate_report(rows, panel="cbc"), ReportTemplate())
    tolerance = {"index_abs": {"mcv_fl": 0.5}}
    configured = build_report_payload(demo_rows("cbc"), TEST_CATALOG, validate_report(demo_rows("cbc"), panel="cbc", tolerances=tolerance), ReportTemplate(), validation_context={"specimen_flags": [], "tolerances": tolerance, "previous_comparable": False})
    assert len({initial["snapshot_sha256"], changed["snapshot_sha256"], bundle(margin_mm=20)["snapshot_sha256"], configured["snapshot_sha256"]}) == 4
    exported = json.loads(json_bytes(changed))
    assert exported["rows"][0]["result"] == -1.0
    assert exported["validation"]["decision"] == "REJECT"
    assert exported["validation"]["raw_rows"][0]["result"] == -1.0
    assert "-1.0" in render_report_html(changed)


def test_template_export_contains_settings_but_no_person_or_result_values():
    payload = template_payload(ReportTemplate(show_comments=False, show_trend=True))
    assert payload["document_status"] == "DRAFT"
    assert payload["data_origin"] == "synthetic"
    assert payload["release_eligible"] is False
    assert "rows" not in payload
    assert "patient_specimen" not in payload
    assert payload["template"]["show_trend"] is True


def test_optional_sections_cannot_remove_the_draft_notice_or_invent_morphology():
    html = render_report_html(bundle(show_previous=False, show_comments=False, show_morphology=True, show_trend=True))
    assert "DRAFT · SYNTHETIC" in html
    assert "Placeholder only — no smear assessment performed" in html
    assert "Two synthetic time points" in html
    assert "Clinical comparability is not established" in html
    assert "12.8 → 7.2" in html
    assert "<th>ผลก่อนหน้า" not in html


def test_nonfinite_invalid_input_exports_strict_json_and_keeps_validator_evidence():
    rows = demo_rows("cbc")
    rows[0]["result"] = float("inf")
    validation = validate_report(rows, panel="cbc")
    payload = build_report_payload(rows, TEST_CATALOG, validation, ReportTemplate())
    exported = json.loads(json_bytes(payload), parse_constant=lambda value: pytest.fail(f"Invalid JSON constant: {value}"))
    assert exported["rows"][0]["result"] is None
    assert exported["validation"]["decision"] == "REJECT"
    assert exported["validation"]["raw_rows"][0]["result"] == {"nonfinite": "inf"}


def test_payload_does_not_alias_mutable_inputs():
    rows = demo_rows("cbc")
    validation = validate_report(rows, panel="cbc")
    payload = build_report_payload(rows, TEST_CATALOG, validation, ReportTemplate())
    rows[0]["result"] = 99
    validation["findings"][0]["message"] = "changed"
    assert payload["rows"][0]["result"] == 7.2
    assert payload["validation"]["findings"][0]["message"] != "changed"


def test_export_refuses_stale_validation_for_different_current_rows():
    rows = demo_rows("cbc")
    old_validation = validate_report(rows, panel="cbc")
    rows[0]["result"] = 14.0
    with pytest.raises(ValueError, match="snapshot"):
        build_report_payload(rows, TEST_CATALOG, old_validation, ReportTemplate())


@pytest.mark.parametrize("area", ["row", "template", "validation", "catalog", "hash"])
def test_html_renderer_rejects_payload_changes_after_snapshot_binding(area):
    payload = bundle()
    if area == "row":
        payload["rows"][0]["result"] = 14.0
    elif area == "template":
        payload["template"]["institution"] = "Other laboratory"
    elif area == "validation":
        payload["validation"]["findings"][0]["message"] = "changed after evaluation"
    elif area == "catalog":
        payload["catalog"]["hb_g_dl"]["unit"] = "unexpected"
    else:
        payload.pop("snapshot_sha256")
    with pytest.raises(ValueError, match="snapshot"):
        render_report_html(payload)


def test_snapshot_digest_survives_json_roundtrip_and_mapping_key_reordering():
    payload = bundle()
    reordered = json.loads(json.dumps(payload, sort_keys=True, ensure_ascii=False))
    assert render_report_html(reordered) == render_report_html(payload)


def test_html_uses_bound_synthetic_header_not_later_global_defaults(monkeypatch):
    payload = bundle()
    before = render_report_html(payload)
    monkeypatch.setitem(SYNTHETIC_HEADER, "patient_name", "A later synthetic fixture")
    assert render_report_html(payload) == before


def test_export_refuses_validation_from_another_panel():
    rows = demo_rows("cbc")
    validation = validate_report(rows, panel="cbc")
    with pytest.raises(ValueError, match="panel"):
        build_report_payload(rows, TEST_CATALOG, validation, ReportTemplate(panel="combined"))


@pytest.mark.parametrize("context", [
    {"specimen_flags": ["clotted"], "tolerances": {}, "previous_comparable": False},
    {"specimen_flags": [], "tolerances": {"index_abs": {"mcv_fl": 99}}, "previous_comparable": False},
    {"specimen_flags": [], "tolerances": {}, "previous_comparable": True},
])
def test_export_refuses_context_that_was_not_evaluated(context):
    rows = demo_rows("cbc")
    validation = validate_report(rows, panel="cbc")
    with pytest.raises(ValueError, match="context"):
        build_report_payload(rows, TEST_CATALOG, validation, ReportTemplate(), validation_context=context)


@pytest.mark.parametrize("missing", ["raw_rows", "validation_context"])
def test_export_refuses_validation_without_input_provenance(missing):
    rows = demo_rows("cbc")
    validation = validate_report(rows, panel="cbc")
    validation.pop(missing)
    with pytest.raises(ValueError, match="snapshot|context"):
        build_report_payload(rows, TEST_CATALOG, validation, ReportTemplate())


def test_editor_changes_revalidate_and_export_the_current_snapshot_then_reset():
    page = Path(__file__).resolve().parents[1] / "pages" / "10_Reporting.py"
    with patch("ui.reporting.render_report_html", wraps=render_report_html) as render:
        app = AppTest.from_file(str(page), default_timeout=30).run()
        assert not app.exception
        initial = render.call_args.args[0]
        app.session_state["reporting_editor_cbc_0"] = {
            "edited_rows": {0: {"result": -1.0}}, "deleted_rows": [], "added_rows": [],
        }
        app.run()
        assert not app.exception
        changed = render.call_args.args[0]
        assert changed["rows"][0]["result"] == -1.0
        assert changed["validation"]["raw_rows"][0]["result"] == -1.0
        assert changed["validation"]["decision"] == "REJECT"
        assert changed["snapshot_sha256"] != initial["snapshot_sha256"]
        assert any("REJECT" in item.value for item in app.error)
        app.run()
        assert render.call_args.args[0]["snapshot_sha256"] == changed["snapshot_sha256"]
        app.button(key="reporting_reset").click().run()
        assert not app.exception
        restored = render.call_args.args[0]
        assert restored["rows"][0]["result"] == 7.2
        assert restored["validation"]["decision"] == "HOLD"
        assert restored["snapshot_sha256"] == initial["snapshot_sha256"]


def test_reporting_preview_and_downloads_survive_iframe_without_alt():
    import streamlit as st

    root = Path(__file__).resolve().parents[1]
    native_iframe = st.iframe
    rendered = []

    def iframe_without_alt(src, *, height, width, tab_index):
        rendered.append((src, height, width, tab_index))
        return native_iframe(src, height=height, width=width, tab_index=tab_index)

    with patch.object(st, "iframe", iframe_without_alt), patch(
        "ui.reporting.render_report_html", wraps=render_report_html
    ) as render:
        app = AppTest.from_file(str(root / "app.py"), default_timeout=30).run()
        app.switch_page("pages/10_Reporting.py").run()
        assert not app.exception
        assert len(rendered) == 1
        assert rendered[0] == (render_report_html(render.call_args.args[0]), 850, "stretch", 0)
        assert any("รายงานสมมติฉบับเดียวกับไฟล์ HTML" in item.value for item in app.caption)
        labels = {item.label for item in app.get("download_button")}
        assert {"HTML · DRAFT", "Template · JSON", "Validation · JSON"} <= labels


def test_switching_panels_uses_current_schema_and_explicit_demo_tolerances():
    page = Path(__file__).resolve().parents[1] / "pages" / "10_Reporting.py"
    with patch("ui.reporting.render_report_html", wraps=render_report_html) as render:
        app = AppTest.from_file(str(page), default_timeout=30).run()
        app.checkbox(key="reporting_use_tolerances").check().run()
        configured = render.call_args.args[0]
        assert configured["validation_context"]["tolerances"]["index_abs"]["mcv_fl"] == 0.5
        assert any(item["rule_id"] == "INDEX_MCV_FL" and item["status"] == "PASS" for item in configured["validation"]["findings"])
        for panel in PANEL_FIELDS:
            app.selectbox(key="reporting_panel").set_value(panel).run()
            assert not app.exception
            current = render.call_args.args[0]
            assert current["template"]["panel"] == panel
            assert [row["code"] for row in current["rows"]] == list(PANEL_FIELDS[panel])
            assert current["validation"]["panel"] == panel
            assert current["release_eligible"] is False
            assert not app.sidebar.button


def test_designer_draft_survives_panel_switch_and_navigation_round_trip():
    root = Path(__file__).resolve().parents[1]

    def navigate(app, path):
        app.button(key=f"top_{navigation_key(path)}").click().run()
        assert not app.exception
        assert app.session_state["_platform_current_page"] == path
        app.switch_page(path)

    with patch("ui.reporting.render_report_html", wraps=render_report_html) as render:
        app = AppTest.from_file(str(root / "app.py"), default_timeout=30).run()
        navigate(app, "pages/10_Reporting.py")
        app.text_input(key="reporting_institution").set_value("Synthetic laboratory B").run()
        app.selectbox(key="reporting_language").set_value("en").run()
        app.slider(key="reporting_margin").set_value(20).run()
        app.checkbox(key="reporting_show_morphology").check().run()
        app.checkbox(key="reporting_use_tolerances").check().run()
        app.number_input(key="reporting_tolerance_mcv_fl").set_value(1.2).run()
        app.session_state["reporting_editor_cbc_0"] = {
            "edited_rows": {0: {"result": 8.2}}, "deleted_rows": [], "added_rows": [],
        }
        app.run()
        before = render.call_args.args[0]
        assert before["rows"][0]["result"] == 8.2
        app.selectbox(key="reporting_panel").set_value("coagulation").run()
        app.selectbox(key="reporting_panel").set_value("cbc").run()
        assert render.call_args.args[0]["snapshot_sha256"] == before["snapshot_sha256"]
        navigate(app, "app.py")
        navigate(app, "pages/10_Reporting.py")
        after = render.call_args.args[0]
        assert app.text_input(key="reporting_institution").value == "Synthetic laboratory B"
        assert app.selectbox(key="reporting_language").value == "en"
        assert app.slider(key="reporting_margin").value == 20
        assert app.checkbox(key="reporting_show_morphology").value is True
        assert app.number_input(key="reporting_tolerance_mcv_fl").value == 1.2
        assert after["snapshot_sha256"] == before["snapshot_sha256"]
        assert after["rows"][0]["result"] == after["validation"]["raw_rows"][0]["result"] == 8.2
