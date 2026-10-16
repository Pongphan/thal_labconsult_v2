"""Capture the evaluated workspace build; exports must reuse this snapshot.

Hashes identify source and dependencies, not an electronic signature or clinical
approval. Restart the app after installing packages or changing application code.
"""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from hashlib import sha256
from importlib import metadata
import json
from pathlib import Path
import platform
import re
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE_FOLDERS = ("logic", "ui", "utils", "thalab", "pages")
LOCK_FILES = ("requirements-lock-win-py312.txt", "requirements-dev-lock-win-py312.txt")


def _digest(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


@lru_cache(maxsize=8)
def _installed_versions(names: tuple[str, ...]) -> dict[str, str]:
    versions = {}
    for name in names:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = "not-installed"
    return versions


@lru_cache(maxsize=16)
def _capture(manifest: tuple[tuple[str, str], ...], packages: tuple[str, ...]) -> dict[str, Any]:
    sources, locks = {}, {}
    for name, digest in manifest:
        if name.endswith(".py"):
            sources[name] = digest
        else:
            locks[name] = digest
    environment = {
        "python": platform.python_version(),
        "platform": platform.system(),
        "packages": _installed_versions(packages),
    }
    return {
        "schema_version": 1,
        "application": "thal_labconsult",
        "source_sha256": _digest(sources),
        "source_files": sources,
        "lock_sha256": locks,
        "environment_sha256": _digest(environment),
        "environment": environment,
        "build_id": _digest({"sources": sources, "locks": locks, "environment": environment}),
        "capture_scope": "workspace_source_at_evaluation",
        "clinical_approval": False,
    }


def capture_build_provenance(root: Path = ROOT) -> dict[str, Any]:
    """Return a detached snapshot keyed by bytes, never file timestamps alone."""
    root = Path(root).resolve()
    paths = [root / "app.py"]
    for folder in SOURCE_FOLDERS:
        paths.extend((root / folder).rglob("*.py"))
    paths.extend(root / name for name in LOCK_FILES if (root / name).is_file())
    manifest, packages = [], set()
    for path in sorted(set(paths)):
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError("Build source must remain inside the application")
        name = path.relative_to(root).as_posix()
        content = path.read_bytes()
        manifest.append((name, sha256(content).hexdigest()))
        # Parse the same lock bytes that were hashed; ignore hash continuations.
        if name == LOCK_FILES[0]:
            packages.update(re.findall(r"^([A-Za-z0-9_.-]+)==", content.decode("utf-8-sig"), re.MULTILINE))
    return deepcopy(_capture(tuple(manifest), tuple(sorted(packages))))
