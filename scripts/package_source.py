"""Create a reproducible source snapshot from reviewed application paths only."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = (
    "app.py", "requirements.txt", "requirements-lock-win-py312.txt", "run.cmd",
    "run.ps1", ".gitignore", "README.md", "CHANGELOG.md", ".streamlit/config.toml",
    "requirements-dev.txt", "pyproject.toml", ".github/workflows/quality.yml",
    ".github/required-checks.ruleset.json",
    "requirements-dev-lock-win-py312.txt",
)
SOURCE_FOLDERS = ("logic", "ui", "utils", "thalab", "pages", "tests")
DATA_FILES = (
    "allele_panel.json", "cbc_rules.json", "clinical_rules.json", "modules.json",
    "learning_modules.json", "white_cells_rules.json", "marrow_malignancies_rules.json",
    "platelets_bleeding_rules.json", "thrombosis_rules.json", "transfusion_rules.json",
    "morphology_quality_rules.json", "example_pcr_panel.csv", "example_screening.csv",
)
DOC_FILES = (
    "TEST_RESULTS.md", "CLINICAL_REVIEW.md", "HEMATOLOGY_PLATFORM.md", "LOCAL_SETUP.md",
    "RULE_REVIEW_TEMPLATE.md", "SOURCES_WHITE_MARROW.md", "SOURCES_HEMOSTASIS.md",
    "SOURCES_TRANSFUSION_MORPHOLOGY.md", "USER_ACCEPTANCE_TESTS.md",
    "EXPERT_REVIEW_UAT.md", "RULE_INVENTORY.csv", "QUALITY_REMEDIATION.md", "CI_SETUP.md",
    "REPORTING_DESIGN.md",
    "REVIEW_FIXES.md",
)


def source_snapshot() -> dict[str, bytes]:
    """Read each file once so the hashes describe precisely what is archived."""
    paths = [ROOT / name for name in ROOT_FILES]
    paths.extend(ROOT / "data" / name for name in DATA_FILES)
    paths.extend(ROOT / "docs" / name for name in DOC_FILES)
    for folder in SOURCE_FOLDERS:
        paths.extend((ROOT / folder).glob("*.py"))
    for suffix in ("*.py", "*.ps1", "*.cmd"):
        paths.extend((ROOT / "scripts").glob(suffix))
    snapshot = {}
    for path in sorted(set(paths)):
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise ValueError(f"Source path must remain inside the project: {path}")
        if not path.is_file():
            raise FileNotFoundError(f"Required delivery source is missing: {path}")
        snapshot[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    return snapshot


def manifest_bytes(snapshot: dict[str, bytes]) -> bytes:
    manifest = {
        "schema_version": 1,
        "project": "thal_labconsult",
        "files": [
            {"path": name, "size_bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
            for name, content in sorted(snapshot.items())
        ],
    }
    return (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def complete_source_bytes(snapshot: dict[str, bytes]) -> bytes:
    """The readable delivery and ZIP describe the same captured sources."""
    lines = [
        "# ThalLink — complete source snapshot", "",
        "Generated from the same source snapshot as `thal_labconsult_source.zip` and `SOURCE_MANIFEST.json`.",
        "Use the ZIP for installation. Test evidence and pending user acceptance are documented in `docs/TEST_RESULTS.md` and `docs/USER_ACCEPTANCE_TESTS.md`.",
        "", f"Includes {len(snapshot)} allowlisted files. Local environments, uploaded data and generated deliveries are excluded.", "",
    ]
    languages = {".py": "python", ".json": "json", ".toml": "toml", ".md": "markdown", ".ps1": "powershell", ".cmd": "bat", ".csv": "csv"}
    for name, content in sorted(snapshot.items()):
        source = content.decode("utf-8-sig")
        fence = "````"
        while fence in source:
            fence += "`"
        lines.extend([f"## {name}", "", f"{fence}{languages.get(Path(name).suffix, 'text')}", source.rstrip("\r\n"), fence, ""])
    return ("\n".join(lines) + "\n").encode("utf-8")


def write_archive(path: Path, snapshot: dict[str, bytes], manifest: bytes) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, content in sorted({**snapshot, "SOURCE_MANIFEST.json": manifest}.items()):
            # Stable timestamps/permissions keep identical source snapshots reproducible.
            entry = zipfile.ZipInfo(f"thal_labconsult/{name}", date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, content, compresslevel=9)
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError("Archive CRC verification failed")
        for name, content in snapshot.items():
            if archive.read(f"thal_labconsult/{name}") != content:
                raise ValueError(f"Archive content mismatch: {name}")
        if archive.read("thal_labconsult/SOURCE_MANIFEST.json") != manifest:
            raise ValueError("Archive manifest mismatch")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true", help="Write ZIP, readable source and manifest to deliverables/; default only checks the allowlist")
    parser.add_argument("--check", action="store_true", help="Explicitly check the source allowlist without writing artifacts")
    args = parser.parse_args()
    if args.build and args.check:
        parser.error("--build and --check are mutually exclusive")
    snapshot = source_snapshot()
    manifest = manifest_bytes(snapshot)
    print(f"Verified {len(snapshot)} source/rule/example/documentation files ({sum(map(len, snapshot.values())):,} bytes).")
    if not args.build:
        print("No artifacts written. Use --build to create the source ZIP and SHA-256 manifest.")
        return 0
    output = ROOT / "deliverables"
    if not output.resolve().is_relative_to(ROOT) or output.is_symlink():
        raise ValueError("Delivery directory must remain inside the project")
    output.mkdir(exist_ok=True)
    archive_path = output / "thal_labconsult_source.zip"
    staging_path = output / "thal_labconsult_source.zip.tmp"
    manifest_path = output / "SOURCE_MANIFEST.json"
    readable_path = output / "COMPLETE_SOURCE.md"
    for target in (archive_path, staging_path, manifest_path, readable_path):
        if target.is_symlink() or not target.resolve().is_relative_to(ROOT):
            raise ValueError(f"Delivery file must remain inside the project: {target}")
    write_archive(staging_path, snapshot, manifest)
    staging_path.replace(archive_path)
    manifest_path.write_bytes(manifest)
    readable_path.write_bytes(complete_source_bytes(snapshot))
    print(f"Source ZIP: {archive_path}")
    print(f"Archive SHA-256: {hashlib.sha256(archive_path.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
