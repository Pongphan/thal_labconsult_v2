"""Integrate documented hematopathology evidence without final disease assignment."""
from __future__ import annotations

import math
from typing import Any, Mapping

from logic.hematology_common import ReviewResult, finish_review, rule_text, start_review


def analyze_marrow_malignancies(data: Mapping[str, Any]) -> ReviewResult:
    result, rules = start_review("marrow_malignancies", data)
    n, t = result.normalized, rules["thresholds"]
    if set(t) != {"high_blast_review_percent", "multiple_cytopenia_lineages"} or any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0 for value in t.values()):
        raise ValueError("เกณฑ์ทบทวนไขกระดูกไม่ครบหรือไม่ถูกต้อง กรุณาตรวจไฟล์กฎ")
    if t["high_blast_review_percent"] > 100 or not 2 <= t["multiple_cytopenia_lineages"] <= 3:
        raise ValueError("เกณฑ์ทบทวนไขกระดูกอยู่นอกช่วงที่รองรับ")

    def text(key: str, **values: Any) -> str:
        return rule_text(rules, key, **values)

    labels = {field["key"]: field["label"] for field in rules["fields"]}
    units = {field["key"]: field.get("unit", "") for field in rules["fields"]}
    option_labels = {field["key"]: {option["value"]: option["label"] for option in field["options"]} for field in rules["fields"] if "options" in field}
    result.thresholds_used = dict(t)
    evidence: list[dict[str, Any]] = []
    numeric_evidence = ("hb_g_dl", "wbc_10e9_l", "anc_10e9_l", "platelets_10e9_l", "pb_blasts_percent", "bm_blasts_percent", "bm_plasma_cells_percent")
    qualitative_evidence = ("clinician_cytopenias", "prior_myeloid_neoplasm", "blast_increase_observed", "apl_morphology", "marrow_dysplasia", "marrow_cellularity", "marrow_fibrosis", "flow_lineage", "flow_clonality", "pml_rara", "bcr_abl1", "jak2", "calr", "mpl", "npm1", "aml_rearrangement", "monoclonal_protein", "tissue_pathology")
    for key in numeric_evidence:
        if n[key] is not None:
            evidence.append({"field": key, "label": labels[key], "value": n[key], "unit": units[key]})
            result.findings.append(text("measured", label=labels[key], value=n[key], unit=units[key]))
    for key in qualitative_evidence:
        if n[key] != "unknown":
            label = option_labels[key][n[key]]
            evidence.append({"field": key, "label": labels[key], "value": n[key], "display": label})
            result.findings.append(text("observed", label=labels[key], value=label))
    result.calculated["documented_evidence"] = evidence
    result.calculated["unassessed_tests"] = [labels[key] for key in qualitative_evidence if n[key] == "unknown"]

    local_cytopenias: list[str] = []
    local_limits: dict[str, Any] = {}
    for field, lower, lineage in (("hb_g_dl", "hb_low", "erythroid/Hb"), ("anc_10e9_l", "anc_low", "neutrophils"), ("platelets_10e9_l", "platelets_low", "platelets")):
        value, bound = n[field], n[lower]
        if value is None:
            continue
        if bound is None:
            result.validation_warnings.append(text("missing_range", label=labels[field]))
            continue
        local_limits[field] = {"low": bound, "unit": units[field]}
        if value < bound:
            local_cytopenias.append(lineage)
            result.rationale.append(text("local_low", label=labels[field], value=value, bound=bound, unit=units[field]))
    result.thresholds_used["local_lower_limits"] = local_limits
    result.calculated["cytopenias"] = {"local_lineages": local_cytopenias, "local_count": len(local_cytopenias), "clinician_observation": n["clinician_cytopenias"]}
    if local_cytopenias:
        result.findings.append(text("cytopenia_summary", count=len(local_cytopenias), lineages=", ".join(local_cytopenias)))
        result.rules_used.append("MARROW_LOCAL_CYTOPENIA_REVIEW")
        if n["clinician_cytopenias"] == "none":
            result.validation_warnings.append(text("cytopenia_conflict"))
    cytopenia = bool(local_cytopenias or n["clinician_cytopenias"] in {"one", "multiple"})
    multiple = len(local_cytopenias) >= t["multiple_cytopenia_lineages"] or n["clinician_cytopenias"] == "multiple"

    hypotheses: list[dict[str, Any]] = []

    def hypothesis(code: str, message: str, keys: list[str], confirmations: list[str]) -> None:
        observed = [{"field": key, "value": n[key]} for key in keys if n.get(key) is not None and n.get(key) != "unknown"]
        statement = text(message)
        hypotheses.append({"group_id": code, "review_hypothesis": statement, "supporting_inputs": observed, "confirmation_paths": [text(key) for key in confirmations]})
        result.findings.append(statement)
        result.recommendations.extend(text(key) for key in confirmations)
        result.rules_used.append("MARROW_" + code.upper())

    pb, bm = n["pb_blasts_percent"], n["bm_blasts_percent"]
    high_blasts = any(value is not None and value >= t["high_blast_review_percent"] for value in (pb, bm))
    peripheral_blasts = pb is not None and pb > 0
    marrow_above_local = bm is not None and n["bm_blasts_high"] is not None and bm > n["bm_blasts_high"]
    if bm is not None and n["bm_blasts_high"] is not None:
        result.thresholds_used["marrow_blast_upper_limit"] = n["bm_blasts_high"]
        if marrow_above_local:
            result.rationale.append(text("marrow_blast_local_above", value=bm, bound=n["bm_blasts_high"]))
            result.rules_used.append("MARROW_BLASTS_ABOVE_LOCAL_BOUND")
    blast_evidence = peripheral_blasts or high_blasts or marrow_above_local or n["blast_increase_observed"] == "yes"
    if pb is not None or bm is not None:
        result.rationale.append(text("blast_context"))
    if high_blasts:
        result.alerts.append(text("high_blast_alert", cutoff=t["high_blast_review_percent"]))
        result.rules_used.append("MARROW_HIGH_BLAST_REVIEW_ALERT")
    elif peripheral_blasts:
        result.alerts.append(text("pb_blast_alert"))
        result.rules_used.append("MARROW_PB_BLAST_REVIEW_ALERT")

    apl = n["pml_rara"] == "detected" or n["apl_morphology"] == "yes"
    if apl:
        result.alerts.insert(0, text("apl_alert"))
        hypothesis("apl_urgent_path", "apl_path", ["pml_rara", "apl_morphology", "pb_blasts_percent", "bm_blasts_percent"], ["apl_confirm"])
        if n["pml_rara"] == "not_detected" and n["apl_morphology"] == "yes":
            result.validation_warnings.append(text("apl_negative"))

    lineage = n["flow_lineage"]
    genetic_myeloid = n["npm1"] == "detected" or n["aml_rearrangement"] not in {"unknown", "not_detected"}
    if genetic_myeloid:
        hypothesis("myeloid_genetic_path", "genetic_path", ["npm1", "aml_rearrangement", "flow_lineage", "pb_blasts_percent", "bm_blasts_percent"], ["generic_confirm"])
    if lineage == "myeloid_blast" and not apl:
        hypothesis("myeloid_blast_path", "myeloid_path", ["flow_lineage", "pb_blasts_percent", "bm_blasts_percent"], ["generic_confirm"])
    elif lineage in {"b_lymphoblast", "t_lymphoblast"}:
        hypothesis("lymphoblastic_path", "lymphoblast_path", ["flow_lineage", "flow_clonality", "pb_blasts_percent", "bm_blasts_percent"], ["generic_confirm"])
    elif lineage == "ambiguous":
        hypothesis("ambiguous_lineage_path", "ambiguous_path", ["flow_lineage", "pb_blasts_percent", "bm_blasts_percent"], ["generic_confirm"])
    elif blast_evidence and lineage in {"unknown", "no_aberrant", "mature_b", "mature_t", "plasma_cell"} and not apl:
        hypothesis("unassigned_blast_path", "blasts_unassigned", ["blast_increase_observed", "pb_blasts_percent", "bm_blasts_percent", "bm_blasts_high", "flow_lineage"], ["generic_confirm"])
    if n["bcr_abl1"] == "detected":
        hypothesis("bcr_abl1_path", "bcr_path", ["bcr_abl1", "flow_lineage", "prior_myeloid_neoplasm", "pb_blasts_percent", "bm_blasts_percent"], ["bcr_confirm"])
    if any(n[key] == "detected" for key in ("jak2", "calr", "mpl")) or n["marrow_fibrosis"] == "yes":
        hypothesis("mpn_clonal_myeloid_path", "mpn_path", ["jak2", "calr", "mpl", "marrow_fibrosis", "marrow_cellularity"], ["mpn_confirm"])
    if cytopenia and n["marrow_dysplasia"] == "yes":
        hypothesis("cytopenia_dysplasia_path", "dysplasia_path", ["clinician_cytopenias", "marrow_dysplasia", "hb_g_dl", "anc_10e9_l", "platelets_10e9_l"], ["generic_confirm"])
    if cytopenia and n["marrow_cellularity"] == "hypocellular":
        hypothesis("hypocellular_cytopenia_path", "hypocellular_path", ["clinician_cytopenias", "marrow_cellularity", "hb_g_dl", "anc_10e9_l", "platelets_10e9_l"], ["generic_confirm"])
    elif multiple:
        hypothesis("multiple_cytopenia_path", "cytopenia_path", ["clinician_cytopenias", "hb_g_dl", "anc_10e9_l", "platelets_10e9_l"], ["generic_confirm"])
    if lineage in {"mature_b", "mature_t"} or n["tissue_pathology"] == "lymphoid_suspicious":
        hypothesis("mature_lymphoid_path", "mature_lymphoid_path", ["flow_lineage", "flow_clonality", "tissue_pathology"], ["tissue_confirm"])
    plasma = n["monoclonal_protein"] == "detected" or lineage == "plasma_cell" or n["tissue_pathology"] == "plasma_cell_clonal"
    if plasma:
        hypothesis("plasma_cell_path", "plasma_path", ["monoclonal_protein", "bm_plasma_cells_percent", "flow_lineage", "flow_clonality", "tissue_pathology"], ["plasma_confirm"])
    if lineage == "no_aberrant" and n["flow_clonality"] == "detected":
        result.validation_warnings.append(text("inconsistent_flow"))
    if n["tissue_pathology"] == "myeloid_suspicious" and not any(item["group_id"] == "myeloid_blast_path" for item in hypotheses):
        hypothesis("tissue_myeloid_path", "myeloid_path", ["tissue_pathology", "flow_lineage"], ["tissue_confirm", "generic_confirm"])

    organs = [item for item in n["organ_findings"] if item != "unknown"]
    if organs:
        result.findings.append(text("organ_caveat", items=", ".join(option_labels["organ_findings"][item] for item in organs)))
        if "unknown" in n["organ_findings"]:
            result.validation_warnings.append(text("unknown_mixed"))
    result.calculated["hypothesis_groups"] = hypotheses
    if evidence or organs:
        result.status = "review"
        if not hypotheses:
            result.findings.append(text("no_route"))
        if lineage == "unknown" and (blast_evidence or genetic_myeloid or apl):
            result.recommendations.append(text("missing_flow"))
        if bm is None and n["marrow_cellularity"] == "unknown" and (hypotheses or cytopenia):
            result.recommendations.append(text("missing_marrow"))
        if any(n[key] == "not_detected" for key in ("pml_rara", "bcr_abl1", "jak2", "calr", "mpl", "npm1", "aml_rearrangement", "monoclonal_protein")):
            result.limitations.append(text("negative_panel"))
        result.recommendations.append(text("generic_confirm"))
    else:
        result.findings.append(text("empty"))
    return finish_review(result)
