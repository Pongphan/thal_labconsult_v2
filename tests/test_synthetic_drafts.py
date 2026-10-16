"""Synthetic work files are explicit, bounded and isolated from clinical state."""
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from logic.reporting import PANEL_FIELDS, demo_rows
from ui.drafts import _restore_uploaded_draft
from utils.drafts import (
    MAX_DRAFT_BYTES, capture_synthetic_draft, read_synthetic_draft,
    restore_synthetic_draft, synthetic_draft_bytes, validate_synthetic_draft,
)


def populated_state():
    state = {
        "reporting_panel": "combined", "reporting_language": "en",
        "reporting_institution": "Synthetic laboratory B", "reporting_version": "2.3",
        "reporting_margin": 20, "reporting_show_previous": False,
        "reporting_show_morphology": True, "reporting_show_comments": False,
        "reporting_show_trend": True, "reporting_specimen_flags": ["clotted"],
        "reporting_previous_comparable": True, "reporting_use_tolerances": True,
        "reporting_tolerance_mcv_fl": 0.1, "reporting_tolerance_mch_pg": 0.2,
        "reporting_tolerance_mchc_g_dl": 0.3,
        "platform_learning_module": "cbc_anemia", "platform_show_thal_demo": True,
        "platform_learning_demo_cbc_anemia": True,
        "cbc_result": {"secret": "DO NOT EXPORT"}, "_auth": "DO NOT EXPORT",
    }
    for panel in PANEL_FIELDS:
        state[f"reporting_rows_{panel}"] = demo_rows(panel)
    state["reporting_rows_combined"][0]["result"] = -1.0
    state["reporting_rows_cbc"][0]["result"] = None
    return state


def test_all_controls_and_per_panel_numeric_drafts_round_trip_without_saved_results():
    original = capture_synthetic_draft(populated_state())
    encoded = synthetic_draft_bytes(original)
    assert b"DO NOT EXPORT" not in encoded
    assert len(encoded) < MAX_DRAFT_BYTES
    decoded = read_synthetic_draft(encoded)
    restored = {"cbc_result": {"keep": True}, "screening_single_result": "unchanged", "_auth": "unchanged"}
    restore_synthetic_draft(restored, decoded)
    assert capture_synthetic_draft(restored) == original
    assert restored["cbc_result"] == {"keep": True}
    assert restored["screening_single_result"] == "unchanged"
    assert restored["_auth"] == "unchanged"
    assert restored["reporting_rows_combined"][0]["result"] == -1.0
    assert restored["reporting_rows_cbc"][0]["result"] is None
    assert "validation" not in decoded["reporting"]


@pytest.mark.parametrize("field,value", [
    ("schema_version", True), ("schema_version", 99),
    ("release_eligible", True), ("document_status", "APPROVED"),
    ("data_policy", "deidentified_patient"), ("patient_id", "someone"),
])
def test_non_draft_or_extra_top_level_fields_are_rejected(field, value):
    draft = capture_synthetic_draft({})
    draft[field] = value
    with pytest.raises(ValueError):
        validate_synthetic_draft(draft)


@pytest.mark.parametrize("field,value", [
    ("result", True), ("result", "7.2"), ("result", float("inf")),
    ("result", float("nan")), ("previous_result", False),
    ("previous_days", {"value": 7}), ("unit", "mg/dL"),
    ("code", "unknown_code"), ("patient_name", "someone"),
])
def test_result_schema_rejects_unsupported_values_units_and_identifiers(field, value):
    draft = capture_synthetic_draft({})
    draft["reporting"]["rows_by_panel"]["cbc"][0][field] = value
    with pytest.raises(ValueError):
        validate_synthetic_draft(draft)


@pytest.mark.parametrize("field,value", [
    ("show_comments", "true"), ("margin_mm", True), ("margin_mm", 40),
    ("panel", "not_a_panel"), ("language", []), ("specimen_flags", ["clotted", "clotted"]),
    ("specimen_flags", ["unknown"]), ("institution", "x" * 161),
    ("index_tolerances", {"mcv_fl": True, "mch_pg": 0.1, "mchc_g_dl": 0.1}),
    ("index_tolerances", {"mcv_fl": -1.0, "mch_pg": 0.1, "mchc_g_dl": 0.1}),
    ("arbitrary_session_key", "no"),
])
def test_controls_are_server_validated(field, value):
    draft = capture_synthetic_draft({})
    draft["reporting"]["controls"][field] = value
    with pytest.raises(ValueError):
        validate_synthetic_draft(draft)


@pytest.mark.parametrize("data", [
    b'{"schema_version":1,"schema_version":1}', b'{"x":NaN}', b'{"x":Infinity}',
    b'{"x":-Infinity}', b'{"nested":{"x":1,"x":2}}', b'not json', b'\xff',
    b'[' * 2000 + b']' * 2000, b' ' * (MAX_DRAFT_BYTES + 1),
], ids=["duplicate", "nan", "infinity", "negative_infinity", "nested_duplicate", "not_json", "bad_utf8", "too_deep", "oversized"])
def test_untrusted_json_is_bounded_and_rejects_duplicates_constants_and_malformed_bytes(data):
    with pytest.raises(ValueError):
        read_synthetic_draft(data)


def test_restore_is_atomic_and_replaces_only_explicit_simulation_state():
    state = {**populated_state(), "reporting_editor_epoch": 5,
             "reporting_editor_combined_5": {"edited_rows": {0: {"result": 99}}},
             "reporting_editor_base_combined": ["old base"], "reporting_unrelated": "keep"}
    before = deepcopy(state)
    invalid = capture_synthetic_draft({})
    invalid["reporting"]["rows_by_panel"]["cbc"].reverse()
    with pytest.raises(ValueError):
        restore_synthetic_draft(state, invalid)
    assert state == before
    restore_synthetic_draft(state, capture_synthetic_draft({}))
    assert state["reporting_editor_epoch"] == 6
    assert "reporting_editor_combined_5" not in state
    assert "reporting_editor_base_combined" not in state
    assert "reporting_rows_combined" not in state
    assert state["reporting_unrelated"] == "keep"
    assert state["cbc_result"] == before["cbc_result"]


def test_import_callback_validates_then_restores_without_reusing_imported_results():
    draft = capture_synthetic_draft(populated_state())
    state = {"synthetic_work_draft_upload": BytesIO(synthetic_draft_bytes(draft)), "cbc_result": "keep"}
    with patch("ui.drafts.st", SimpleNamespace(session_state=state)):
        _restore_uploaded_draft()
    assert state["synthetic_work_draft_notice"][0] == "success"
    assert state["cbc_result"] == "keep"
    assert capture_synthetic_draft(state) == draft
    state["synthetic_work_draft_upload"] = BytesIO(b'{"release_eligible":true}')
    before = capture_synthetic_draft(state)
    with patch("ui.drafts.st", SimpleNamespace(session_state=state)):
        _restore_uploaded_draft()
    assert state["synthetic_work_draft_notice"][0] == "error"
    assert capture_synthetic_draft(state) == before


def test_restored_draft_is_freshly_validated_when_reporting_page_renders():
    root = Path(__file__).resolve().parents[1]
    app = AppTest.from_file(str(root / "pages" / "10_Reporting.py"), default_timeout=30)
    # Restore before widgets render, as the uploader's on_click callback does.
    restore_synthetic_draft(app.session_state, capture_synthetic_draft(populated_state()))
    app.run()
    assert not app.exception
    assert app.selectbox(key="reporting_panel").value == "combined"
    assert app.text_input(key="reporting_institution").value == "Synthetic laboratory B"
    assert app.session_state["reporting_rows_combined"][0]["result"] == -1.0
    assert any("REJECT" in item.value for item in app.error)
    assert app.checkbox(key="reporting_show_morphology").value is True
    assert app.number_input(key="reporting_tolerance_mcv_fl").value == 0.1


def test_input_object_and_restored_state_never_alias_the_draft():
    draft = capture_synthetic_draft({})
    state = {}
    restore_synthetic_draft(state, draft)
    state["reporting_rows_cbc"][0]["result"] = 99
    assert draft["reporting"]["rows_by_panel"]["cbc"][0]["result"] == 7.2
    assert json.loads(synthetic_draft_bytes(draft))["reporting"]["rows_by_panel"]["cbc"][0]["result"] == 7.2
