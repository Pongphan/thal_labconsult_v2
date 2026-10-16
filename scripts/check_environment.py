"""Verify the active interpreter, application imports, and dependency constraints."""
from __future__ import annotations

import argparse
import importlib
import importlib.metadata as metadata
import platform
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def read_requirements(path: Path, *, hashed: bool = False):
    """Read our pinned requirements format, including pip hash continuations."""
    from packaging.requirements import Requirement

    text = path.read_text(encoding="utf-8").replace("\\\n", " ")
    requirements = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = re.split(r"\s+--hash=", line)
        requirement = Requirement(parts[0])
        hashes = ["--hash=" + value.strip() for value in parts[1:]]
        if any(not re.fullmatch(r"--hash=sha256:[a-f0-9]{64}", value) for value in hashes):
            raise ValueError(f"Unsupported lock option in {path.name}: {requirement.name}")
        if hashed:
            pins = list(requirement.specifier)
            if (not hashes or len(pins) != 1 or pins[0].operator != "=="
                    or "*" in pins[0].version or requirement.url or requirement.marker):
                raise ValueError(f"Expected an exact version and SHA-256 hashes in {path.name}: {requirement.name}")
        requirements.append(requirement)
    return requirements


def verify_dependencies(requirements, *, locked_names: set[str] | None = None):
    """Check metadata constraints, requested extras, and complete lock coverage."""
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

    errors: list[str] = []
    pending = list(requirements)
    checked: set[tuple[str, str]] = set()
    names: set[str] = set()
    while pending:
        requirement = pending.pop()
        if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
            continue
        name = canonicalize_name(requirement.name)
        if locked_names is not None and name not in locked_names:
            errors.append(f"Dependency missing from exact lock: {requirement.name}")
        try:
            installed = metadata.distribution(requirement.name)
        except metadata.PackageNotFoundError:
            errors.append(f"Missing dependency: {requirement}")
            continue
        if installed.version not in requirement.specifier:
            errors.append(f"{requirement.name} {installed.version} does not satisfy {requirement}")
        names.add(name)
        for extra in {"", *requirement.extras}:
            if (name, extra) in checked:
                continue
            checked.add((name, extra))
            for item in installed.requires or []:
                child = Requirement(item)
                if not child.marker or child.marker.evaluate({"extra": extra}):
                    # Marker was evaluated in its parent's extra context.
                    child.marker = None
                    pending.append(child)
    return errors, names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--locked", action="store_true", help="Require the tested Windows/Python 3.12 dependency snapshot")
    parser.add_argument("--dependencies-only", action="store_true", help="Check runtime packages without importing application rules")
    parser.add_argument("--development", action="store_true", help="Also verify the complete development dependency lock when --locked")
    args = parser.parse_args()
    errors: list[str] = []
    print(f"Python {platform.python_version()} ({platform.system()} {platform.machine()})")
    print(f"Interpreter: {sys.executable}")
    if sys.version_info < (3, 10):
        errors.append("Python 3.10 or newer is required.")
    if args.locked and (sys.version_info[:2] != (3, 12) or sys.platform != "win32" or sys.maxsize <= 2**32):
        errors.append("The exact snapshot targets CPython 3.12 on 64-bit Windows.")
    try:
        from packaging.utils import canonicalize_name
    except ImportError:
        print("FAIL: dependencies are missing. Run scripts/setup.ps1.")
        return 1

    try:
        requirements = read_requirements(ROOT / "requirements.txt")
        if args.development:
            requirements.extend(read_requirements(ROOT / "requirements-dev.txt"))
        locked_names = None
        if args.locked:
            lock_name = "requirements-dev-lock-win-py312.txt" if args.development else "requirements-lock-win-py312.txt"
            locked = read_requirements(ROOT / lock_name, hashed=True)
            locked_names = {canonicalize_name(item.name) for item in locked}
            if len(locked_names) != len(locked):
                raise ValueError(f"Duplicate package in {lock_name}")
            requirements.extend(locked)
        dependency_errors, checked = verify_dependencies(requirements, locked_names=locked_names)
        errors.extend(dependency_errors)
    except (OSError, ValueError) as exc:
        print(f"FAIL: cannot read dependency specification: {exc}")
        return 1

    modules = ["streamlit", "pandas", "numpy", "plotly"]
    if not args.dependencies_only:
        modules.extend(("logic.engine", "ui.navigation"))
    for module in modules:
        try:
            loaded = importlib.import_module(module)
            if hasattr(loaded, "__version__"):
                print(f"{module}: {loaded.__version__}")
        except Exception as exc:
            errors.append(f"Cannot import {module}: {exc}")
    if errors:
        for error in dict.fromkeys(errors):
            print(f"FAIL: {error}")
        return 1
    print(f"PASS: imports and {len(checked)} dependency versions verified" + (" against the complete exact lockfile (artifact hashes are enforced at installation)." if args.locked else "."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
