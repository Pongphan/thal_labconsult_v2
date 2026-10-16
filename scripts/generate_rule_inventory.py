"""Generate a deterministic, review-only inventory; never execute clinical rules.

The inventory intentionally exposes source-mapping gaps. A module bibliography is
not evidence that every cutoff, score, or branch has been clinically validated.
"""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import io
import json
from itertools import product
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path("docs/RULE_INVENTORY.csv")
SPECS = {
    "thalassemia": ("data/clinical_rules.json", ("logic/engine.py", "logic/validation.py", "logic/clinical_grouping.py")),
    "cbc_anemia": ("data/cbc_rules.json", ("logic/cbc.py",)),
    **{name: (f"data/{name}_rules.json", (f"logic/{name}.py",)) for name in (
        "white_cells", "marrow_malignancies", "platelets_bleeding", "thrombosis",
        "transfusion", "morphology_quality")},
    "pcr_genetics": ("data/allele_panel.json", ("thalab/genetics.py",)),
    "shared_validation": (None, ("logic/hematology_common.py", "logic/units.py")),
    "reporting_prototype": (None, ("logic/reporting.py",)),
}
COLUMNS = (
    "module", "entry_kind", "rule_id", "clinical_rationale", "condition_or_operator",
    "thresholds_or_parameters", "source_guideline", "source_mapping", "output",
    "implementation", "review_status", "source_sha256",
)
PENDING = "REVIEW_REQUIRED — ยังไม่ผ่านการรับรองโดยผู้เชี่ยวชาญ/หน่วยงาน"
UNMAPPED = "MODULE_BIBLIOGRAPHY_ONLY; rule-to-section/page mapping not established"


def compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def string_patterns(node: ast.AST) -> list[str]:
    """Describe emitted IDs without eval; '*' explicitly denotes a dynamic family."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.IfExp):
        return sorted(set(string_patterns(node.body) + string_patterns(node.orelse)))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return sorted({a + b for a in string_patterns(node.left) for b in string_patterns(node.right)})
    return ["*"]


def emitted_rule_calls(tree: ast.AST) -> list[ast.Call]:
    calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or node.func.attr != "append" or not node.args:
            continue
        receiver = node.func.value
        name = receiver.attr if isinstance(receiver, ast.Attribute) else receiver.id if isinstance(receiver, ast.Name) else ""
        if name == "rules_used":
            calls.append(node)
    return sorted(calls, key=lambda node: node.lineno)


def expand_rule_family(pattern: str, config: dict[str, Any], tree: ast.AST) -> list[str]:
    """Enumerate current bounded families; fail closed if a new family is added."""
    domains = {
        "CBC_MCV_*": [("MICRO", "NORMO", "MACRO")],
        "CBC_LAB_REFERENCE_*_*": [[key.upper() for key in config.get("validation", {}).get("reference_fields", [])], ("LOW", "HIGH", "WITHIN")],
        "WBC_LOCAL_RANGE_*_*": [("WBC", "ANC", "ALC", "AMC", "AEC", "ABC"), ("LOW", "HIGH", "WITHIN")],
        "PLATELET_LOCAL_REFERENCE_*": [("LOW", "HIGH", "WITHIN")],
        "COAG_PATTERN_*": [("BOTH_PROLONGED", "ISOLATED_PT", "ISOLATED_APTT", "NEITHER_PROLONGED")],
        "VTE_PRETEST_*": [("INTERMEDIATE", "HIGH")],
        "MQ_*": [("SPECIMEN_CLOT", "SPECIMEN_HEMOLYSIS", "EDTA_FILL_STATUS", "SMEAR_QUALITY")],
        "MQ_RECORDED_*": [("RBC_MORPHOLOGY", "WBC_MORPHOLOGY")],
        "MARROW_*": [[str(node.args[0].value).upper() for node in ast.walk(tree)
                       if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                       and node.func.id == "hypothesis" and node.args and isinstance(node.args[0], ast.Constant)]],
    }
    if "*" not in pattern:
        return [pattern]
    if pattern not in domains or any(not values for values in domains[pattern]):
        raise ValueError(f"Unmapped rule family {pattern}; extend the review inventory explicitly")
    result = []
    for choices in product(*domains[pattern]):
        identifier = pattern
        for choice in choices:
            identifier = identifier.replace("*", choice, 1)
        result.append(identifier)
    return sorted(set(result))


def message_keys(node: ast.AST, messages: dict[str, Any]) -> dict[str, Any]:
    """Resolve literal template keys; dynamic templates remain in the text rows."""
    keys = {item.value for item in ast.walk(node) if isinstance(item, ast.Constant) and isinstance(item.value, str)}
    return {key: messages[key] for key in sorted(keys & messages.keys())}


def direct_branch_outputs(node: ast.If | ast.IfExp) -> str:
    """Retain untemplated PCR status text and direct state/validation changes."""
    if isinstance(node, ast.IfExp):
        return ast.unparse(node)
    outputs = {}
    for label, statements in (("when_true", node.body), ("when_false", node.orelse)):
        direct = [ast.unparse(statement) for statement in statements
                  if isinstance(statement, (ast.Assign, ast.AnnAssign, ast.Expr, ast.Return, ast.Raise))]
        if direct:
            outputs[label] = direct
    return compact(outputs) if outputs else "Control-flow branch; subordinate decision rows give its outputs"


def build_rows(root: Path = ROOT) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    paths = {path for config_path, code_paths in SPECS.values() for path in (*code_paths, config_path) if path}
    snapshot = {path: (root / path).read_bytes() for path in sorted(paths)}
    hashes = {path: hashlib.sha256(content).hexdigest() for path, content in snapshot.items()}
    for module, (config_path, code_paths) in SPECS.items():
        config = json.loads(snapshot[config_path].decode("utf-8-sig")) if config_path else {}
        metadata = config.get("metadata", {})
        sources = compact(metadata.get("sources", []))
        scope = metadata.get("scope", metadata.get("description_th", config.get("description", "Shared input validation and result finalization; engineering policy")))
        messages = config.get("messages", {})
        parameters = {key: config[key] for key in ("thresholds", "age_thresholds", "adult_thresholds", "scores", "risk", "ee_score") if key in config}
        if module == "pcr_genetics":
            sources = "No primer/SOP validation source in allele_panel.json; background only: docs/CLINICAL_REVIEW.md; https://www.ncbi.nlm.nih.gov/sites/books/NBK1435/"
        if module == "shared_validation":
            sources = "Application data contract; not a clinical guideline"

        def add(kind: str, rule_id: str, rationale: str, condition: str, thresholds: Any,
                output: str, path: str, line: int | None = None) -> None:
            rows.append(dict(zip(COLUMNS, (
                module, kind, rule_id, rationale, condition,
                compact(thresholds) if not isinstance(thresholds, str) else thresholds,
                sources, UNMAPPED, output, f"{path}:{line}" if line else path,
                PENDING, hashes[path],
            ))))

        add("source_reference", "SOURCE:" + module, "Existing module bibliography; not per-rule validation",
            "Use the source's actual edition and section; expert must record a precise rule mapping", {},
            sources, config_path or code_paths[0])
        sources = "SOURCE:" + module
        if config_path:
            add("configuration", "CONFIG:" + module, scope,
                "Exact stored configuration; bounds are input plausibility limits, not normal ranges",
                {**parameters, "validation": config.get("validation"), "fields": config.get("fields")},
                "Scope: " + scope, config_path)
            for rule in config.get("rules", []):
                add("declared_rule", rule["id"], " | ".join(rule.get("evidence", [])),
                    compact({key: rule[key] for key in ("all", "any", "none", "priority") if key in rule}),
                    {**parameters, "score_floor": rule.get("score_floor")},
                    compact({key: rule[key] for key in ("pattern", "tests", "genotypes", "counseling") if key in rule}), config_path)
            for key, message in sorted(messages.items()):
                add("output_template", "TEXT:" + key, "Existing output wording; clinical appropriateness requires review",
                    "Referenced by code; placeholders are filled from the evaluated input", {}, compact(message), config_path)
            for allele in config.get("alleles", []):
                add("demonstration_target", "PCR_TARGET:" + allele["target_code"], allele["interpretation"],
                    "abs(observed_bp - expected_bp) <= tolerance_bp only after valid operator call and passing controls",
                    allele, "Band agreement in demonstration panel; no genotype confirmation", config_path)

        for code_path in code_paths:
            source = snapshot[code_path].decode("utf-8-sig")
            tree = ast.parse(source)
            parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
            if code_path == "logic/clinical_grouping.py":
                constants = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
                             if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                             and node.targets[0].id in {"RULE_GROUPS", "GROUP_LABELS", "GROUP_ACTIONS", "SOURCES", "POLICY_VERSION"}}
                for code, label in sorted(constants["GROUP_LABELS"].items()):
                    ids = [rule_id for rule_id, group in constants["RULE_GROUPS"].items() if group == code]
                    add("clinical_group", "GROUP:" + code, "Additive workflow proposal; no new diagnostic cutoff",
                        compact({"existing_rule_ids": ids, "fallback_or_overlay": not bool(ids)}),
                        {"policy_version": constants["POLICY_VERSION"], "sources": constants["SOURCES"]},
                        compact({"label": label, "action": constants["GROUP_ACTIONS"][code]}), code_path)

            def guards(node: ast.AST) -> str:
                found = []
                child = node
                while child in parents:
                    ancestor = parents[child]
                    if isinstance(ancestor, ast.If):
                        predicate = ast.unparse(ancestor.test)
                        found.append(f"not ({predicate})" if child in ancestor.orelse else predicate)
                    child = ancestor
                return " AND ".join(reversed(found)) or "Unconditional at this source location; inspect helper call sites"

            for call in emitted_rule_calls(tree):
                ancestor: ast.AST = call
                while ancestor in parents and not isinstance(ancestor, (ast.If, ast.FunctionDef)):
                    ancestor = parents[ancestor]
                outputs = message_keys(ancestor, messages)
                for identifier in sorted({identifier for pattern in string_patterns(call.args[0])
                                          for identifier in expand_rule_family(pattern, config, tree)}):
                    add("emitted_rule", identifier,
                        compact(outputs) if outputs else scope,
                        guards(call) + "; emitted ID expression: " + ast.unparse(call.args[0]),
                        "See CONFIG:" + module + "; predicates/formulas below resolve local variables and operators",
                        compact(outputs) if outputs else "See output templates and source branch; no invented clinical rationale",
                        code_path, call.lineno)
            # Some marrow IDs are emitted through a helper; include the concrete call-site IDs.
            for call in sorted((node for node in ast.walk(tree) if isinstance(node, ast.Call)
                                and isinstance(node.func, ast.Name) and node.func.id == "hypothesis"), key=lambda n: n.lineno):
                if call.args and isinstance(call.args[0], ast.Constant):
                    outputs = message_keys(call, messages)
                    add("emitted_rule", "MARROW_" + str(call.args[0].value).upper(), compact(outputs),
                        guards(call), "See CONFIG:" + module, compact(outputs), code_path, call.lineno)
            # Include untagged gates, fallback branches, PCR decisions and comparisons.
            # These are source-location IDs, not runtime rule IDs or a formal path proof.
            nodes = sorted((node for node in ast.walk(tree) if isinstance(node, (ast.If, ast.IfExp))),
                           key=lambda n: (n.lineno, n.col_offset))
            for index, node in enumerate(nodes, 1):
                predicate = ast.unparse(node.test)
                outputs = message_keys(node, messages)
                add("decision", f"DECISION:{Path(code_path).stem}:{index:03d}",
                    "Implementation gate / branch; review clinical rationale where applicable", predicate,
                    "See CONFIG:" + module, compact(outputs) if outputs else direct_branch_outputs(node),
                    code_path, node.lineno)
            # Preserve exact assignments for signal dictionaries and derived thresholds.
            # The source hash also detects changes to calculations without a comparison.
            for node in sorted((item for item in ast.walk(tree) if isinstance(item, (ast.Assign, ast.AnnAssign))), key=lambda n: (n.lineno, n.col_offset)):
                if node.value is not None and any(isinstance(item, (ast.Compare, ast.BoolOp)) for item in ast.walk(node.value)):
                    add("predicate_formula", f"FORMULA:{Path(code_path).stem}:{node.lineno}",
                        "Implementation formula; cutoffs and inclusive/exclusive operators are copied without modification",
                        ast.unparse(node), "See CONFIG:" + module, "Named intermediate used by decisions/rule IDs", code_path, node.lineno)
    return rows


def render_inventory(root: Path = ROOT) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(build_rows(root))
    return output.getvalue().encode("utf-8-sig")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if the checked-in inventory differs from current source")
    args = parser.parse_args()
    content = render_inventory()
    destination = ROOT / OUTPUT
    if args.check:
        if not destination.exists() or destination.read_bytes() != content:
            print("STALE: run python scripts/generate_rule_inventory.py and review the inventory diff")
            return 1
        print("PASS: rule inventory matches current source")
    else:
        destination.write_bytes(content)
        print(f"Wrote {OUTPUT.as_posix()} ({len(build_rows())} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
