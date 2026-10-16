"""Code changes must be traceable independently of rule-configuration hashes."""
from copy import deepcopy
import json
import os
from unittest.mock import patch

import pytest

from logic.cbc import analyze_cbc
from logic.engine import analyze_screening
from logic.hematology import analyze_domain
from logic.reporting import TEST_CATALOG, demo_rows, validate_report
from utils.build_provenance import capture_build_provenance
from utils.domain_reporting import report_json, report_metadata
from utils.report_layout import ReportTemplate, build_report_payload, render_report_html
from utils.reporting import screening_report_csv, screening_report_markdown, to_json_bytes


def test_python_change_changes_build_without_changing_rule_configuration(tmp_path):
    (tmp_path / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "requirements-lock-win-py312.txt").write_text("numpy==2.5.3\n", encoding="utf-8")
    original = capture_build_provenance(tmp_path)
    (tmp_path / "app.py").write_text("VALUE = 222\n", encoding="utf-8")
    changed = capture_build_provenance(tmp_path)
    assert original["build_id"] != changed["build_id"]
    assert original["source_sha256"] != changed["source_sha256"]
    assert original["lock_sha256"] == changed["lock_sha256"]
    assert original["environment_sha256"] == changed["environment_sha256"]


@pytest.mark.parametrize("relative", ["app.py", "logic/nested/helper.py", "requirements-lock-win-py312.txt"])
def test_same_size_preserved_timestamp_edit_changes_content_snapshot(tmp_path, relative):
    (tmp_path / "app.py").write_text("pass\n", encoding="utf-8")
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")
    stat = target.stat()
    before = capture_build_provenance(tmp_path)
    target.write_text("VALUE = 2\n", encoding="utf-8")
    os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert target.stat().st_size == stat.st_size
    assert target.stat().st_mtime_ns == stat.st_mtime_ns
    after = capture_build_provenance(tmp_path)
    assert after["build_id"] != before["build_id"]
    assert after["source_files" if relative.endswith(".py") else "lock_sha256"][relative] != before["source_files" if relative.endswith(".py") else "lock_sha256"][relative]


def test_lock_change_changes_build_and_snapshot_is_detached(tmp_path):
    (tmp_path / "app.py").write_text("pass\n", encoding="utf-8")
    lock = tmp_path / "requirements-lock-win-py312.txt"
    lock.write_text("numpy==2.5.3\n", encoding="utf-8")
    original = capture_build_provenance(tmp_path)
    original["source_files"].clear()
    unchanged = capture_build_provenance(tmp_path)
    assert unchanged["source_files"]
    lock.write_text("numpy==2.5.3\n# reviewed snapshot\n", encoding="utf-8")
    changed = capture_build_provenance(tmp_path)
    assert unchanged["build_id"] != changed["build_id"]
    assert unchanged["source_sha256"] == changed["source_sha256"]


@pytest.mark.parametrize("module", ["white_cells", "marrow_malignancies", "platelets_bleeding", "thrombosis", "transfusion", "morphology_quality"])
def test_domain_export_preserves_evaluated_build(module):
    result = analyze_domain(module, {})
    original = deepcopy(result.build_provenance)
    assert len(original["build_id"]) == 64
    payload = json.loads(report_json(result, report_metadata(module, "demo")))
    assert payload["result"]["build_provenance"] == original
    assert result.build_provenance == original


def test_screening_all_exports_keep_build_and_unapproved_score_status():
    result = analyze_screening({"age": 30, "hb_g_dl": 12, "mcv_fl": 70, "mch_pg": 22})
    build_id = result.build_provenance["build_id"]
    for output in (screening_report_csv(result).decode("utf-8-sig"), screening_report_markdown(result), to_json_bytes(result).decode("utf-8")):
        assert build_id in output
        assert "draft_not_clinically_validated" in output
    assert json.loads(result.to_flat_dict()["build_provenance"]) == result.build_provenance


def test_saved_exports_never_recapture_build_at_download():
    screening = analyze_screening({"age": 30, "hb_g_dl": 12, "mcv_fl": 70, "mch_pg": 22})
    domain = analyze_domain("white_cells", {})
    cbc = analyze_cbc({"age": 30, "hb_g_dl": 12})
    rows = demo_rows("cbc")
    validation = validate_report(rows, panel="cbc")
    from ui.cbc import cbc_report_csv, cbc_report_payload
    from utils.domain_reporting import report_csv
    metadata = report_metadata("white_cells", "demo")
    cbc_metadata = {**metadata, "report_id": "CBC-SYNTHETIC"}
    with patch("utils.build_provenance._capture", side_effect=AssertionError("Export recaptured current build")):
        outputs = [screening_report_csv(screening), screening_report_markdown(screening), to_json_bytes(screening),
                   report_csv(domain, metadata), report_json(domain, metadata), cbc_report_csv(cbc, cbc_metadata),
                   to_json_bytes(cbc_report_payload(cbc, cbc_metadata)),
                   render_report_html(build_report_payload(rows, TEST_CATALOG, validation, ReportTemplate()))]
    assert all(outputs)


def test_cbc_and_synthetic_report_capture_build_at_evaluation():
    result = analyze_cbc({"age": 30, "hb_g_dl": 12})
    assert result.to_dict()["build_provenance"] == result.build_provenance
    rows = demo_rows("cbc")
    validation = validate_report(rows, panel="cbc")
    payload = build_report_payload(rows, TEST_CATALOG, validation, ReportTemplate())
    assert payload["validation"]["build_provenance"] == validation["build_provenance"]
    assert validation["build_provenance"]["build_id"] in render_report_html(payload)
    assert validation["build_provenance"]["clinical_approval"] is False


def test_pcr_snapshot_keeps_build_in_evaluation_attributes():
    import pandas as pd
    from thalab.genetics import match_pcr_bands

    result = match_pcr_bands(pd.DataFrame([{"sample_id": "SYNTHETIC-1", "target_code": "UNKNOWN", "result": "Positive", "observed_bp": 100}]))
    # The PCR engine retains the exact reference and build in its existing attrs.
    assert result.attrs["evaluation"]["build_provenance"]["clinical_approval"] is False
