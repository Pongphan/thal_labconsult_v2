"""Publish aggregate synthetic-test evidence; never include clinical input rows."""
from __future__ import annotations

import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET


def summary(folder: Path) -> str:
    lines = ["## ThalLink software quality", ""]
    junit = folder / "junit.xml"
    if junit.is_file():
        root = ET.parse(junit).getroot()
        suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
        totals = {key: sum(int(item.get(key, "0")) for item in suites)
                  for key in ("tests", "failures", "errors", "skipped")}
        lines.append("JUnit entries (including subtests): {tests}; failures: {failures}; errors: {errors}; skipped: {skipped}.".format(**totals))
    else:
        lines.append("Test report unavailable: inspect earlier job steps. This is not a pass.")
    coverage = folder / "coverage.json"
    if coverage.is_file():
        totals = json.loads(coverage.read_text(encoding="utf-8"))["totals"]
        lines.append(f"Application statement/branch coverage: {totals['percent_covered']:.2f}% (required >=80%).")
    else:
        lines.append("Coverage report unavailable; no coverage claim.")
    lines.extend(["", "Software tests do not constitute clinical validation or expert/UAT sign-off.", ""])
    return "\n".join(lines)


if __name__ == "__main__":
    report = summary(Path("artifacts"))
    destination = os.environ.get("GITHUB_STEP_SUMMARY")
    if destination:
        with Path(destination).open("a", encoding="utf-8") as stream:
            stream.write(report)
    print(report)
