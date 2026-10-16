"""Check CI gates and reporting behavior, without needing a GitHub account."""
from pathlib import Path
import json
import os
import subprocess
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import pytest
import yaml
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from scripts.ci_summary import summary
from scripts import check_environment

ROOT = Path(__file__).resolve().parents[1]


def test_ci_runs_required_gates_for_all_changes():
    workflow = yaml.load((ROOT / ".github/workflows/quality.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert {"push", "pull_request", "merge_group"} <= workflow["on"].keys()
    assert workflow["permissions"] == {"contents": "read"}
    job = workflow["jobs"]["quality"]
    assert job["name"] == "thallink-quality"
    scripts = "\n".join(step.get("run", "") for step in job["steps"])
    for gate in ("--locked", "--development", "--require-hashes", "--only-binary=:all:", "requirements-dev-lock-win-py312.txt", "ruff check", "generate_rule_inventory.py --check", "--cov", "--junitxml", "package_source.py --check", "playwright install chromium", "scripts/browser_smoke.py"):
        assert gate in scripts
    assert "continue-on-error" not in job
    assert not any("continue-on-error" in step for step in job["steps"])
    assert all("paths" not in (config or {}) for config in workflow["on"].values())


def test_ci_summary_reports_failures_and_coverage(tmp_path):
    root = ET.Element("testsuites")
    ET.SubElement(root, "testsuite", tests="10", failures="1", errors="0", skipped="2")
    ET.ElementTree(root).write(tmp_path / "junit.xml")
    (tmp_path / "coverage.json").write_text(json.dumps({"totals": {"percent_covered": 81.23}}), encoding="utf-8")
    text = summary(tmp_path)
    assert "failures: 1" in text and "skipped: 2" in text and "81.23%" in text


def test_missing_reports_are_not_reported_as_pass(tmp_path):
    assert "This is not a pass" in summary(tmp_path)


def test_complete_hashed_locks_include_runtime_and_every_direct_development_tool():
    runtime = check_environment.read_requirements(ROOT / "requirements-lock-win-py312.txt", hashed=True)
    development = check_environment.read_requirements(ROOT / "requirements-dev-lock-win-py312.txt", hashed=True)
    versions = {canonicalize_name(item.name): str(item.specifier) for item in development}
    assert len(versions) == len(development)
    for item in runtime + check_environment.read_requirements(ROOT / "requirements-dev.txt"):
        assert versions[canonicalize_name(item.name)] == str(item.specifier)
    assert {"coverage", "pluggy", "iniconfig", "pygments", "colorama", "greenlet", "pyee"} <= versions.keys()


@pytest.mark.parametrize("line", ["sample>=1", "sample==1", "sample==1 --hash=sha256:broken", "sample==1.* --hash=sha256:" + "a" * 64])
def test_exact_lock_rejects_unpinned_or_unhashed_packages(tmp_path, line):
    path = tmp_path / "invalid-lock.txt"
    path.write_text(line, encoding="utf-8")
    with pytest.raises(ValueError):
        check_environment.read_requirements(path, hashed=True)


def test_dependency_check_detects_drift_and_missing_transitive_lock(monkeypatch):
    packages = {
        "parent": SimpleNamespace(version="1", requires=["child>=1"]),
        "child": SimpleNamespace(version="2", requires=[]),
    }
    monkeypatch.setattr(check_environment.metadata, "distribution", packages.__getitem__)
    errors, checked = check_environment.verify_dependencies([Requirement("parent==1")], locked_names={"parent"})
    assert errors == ["Dependency missing from exact lock: child"]
    assert checked == {"parent", "child"}
    errors, _ = check_environment.verify_dependencies([Requirement("child==1")], locked_names={"child"})
    assert errors == ["child 2 does not satisfy child==1"]


def test_requested_extras_are_checked_in_parent_context(monkeypatch):
    packages = {
        "parent": SimpleNamespace(version="1", requires=['optional>=2; extra == "qa"']),
        "optional": SimpleNamespace(version="1", requires=[]),
    }
    monkeypatch.setattr(check_environment.metadata, "distribution", packages.__getitem__)
    errors, _ = check_environment.verify_dependencies([Requirement("parent[qa]==1")], locked_names={"parent"})
    assert "Dependency missing from exact lock: optional" in errors
    assert "optional 1 does not satisfy optional>=2" in errors


@pytest.mark.skipif(os.name != "nt", reason="Windows activation helper")
@pytest.mark.parametrize("origin", [None, "https://github.com/example/intended.git", "git@github.com:example/intended.git"])
def test_activation_prepares_explicit_target_without_changing_git(tmp_path, origin):
    project = tmp_path / "project"
    (project / "scripts").mkdir(parents=True)
    (project / ".github").mkdir()
    script = project / "scripts/prepare_ci_activation.ps1"
    script.write_bytes((ROOT / "scripts/prepare_ci_activation.ps1").read_bytes())
    (project / ".github/required-checks.ruleset.json").write_bytes((ROOT / ".github/required-checks.ruleset.json").read_bytes())
    subprocess.run(["git", "init", str(project)], check=True, capture_output=True)
    if origin:
        subprocess.run(["git", "-C", str(project), "remote", "add", "origin", origin], check=True)
    config = (project / ".git/config").read_bytes()
    output = tmp_path / "prepared"
    result = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Repository", "example/intended", "-Branch", "release/test", "-OutputDirectory", str(output)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (project / ".git/config").read_bytes() == config
    record = json.loads((output / "ACTIVATION_STATUS.json").read_text(encoding="utf-8"))
    assert record["status"] == "prepared_only_not_activated"
    assert record["hosted_run_url"] is None
    ruleset = json.loads((output / "required-checks.ruleset.json").read_text(encoding="utf-8"))
    assert ruleset["conditions"]["ref_name"]["include"] == ["refs/heads/release/test"]
    if origin:
        result = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Repository", "other/wrong", "-Branch", "main", "-OutputDirectory", str(tmp_path / "wrong")], capture_output=True, text=True)
        assert result.returncode != 0
        assert not (tmp_path / "wrong").exists()
