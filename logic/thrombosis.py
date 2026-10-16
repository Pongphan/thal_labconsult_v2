"""Context-gated VTE workup review, without automated disease exclusion or dosing."""
from __future__ import annotations

from typing import Any, Mapping
from .hematology_common import ReviewResult, start_review, finish_review, rule_text


def analyze_thrombosis(data: Mapping[str, Any]) -> ReviewResult:
    result, rules = start_review("thrombosis", data)
    n = result.normalized
    text = lambda key, **values: rule_text(rules, key, **values)
    adult_min = rules["thresholds"].get("adult_min_years")
    if type(adult_min) not in (int, float) or not 18 <= adult_min <= 120:
        raise ValueError("เกณฑ์อายุของโมดูล VTE ต้องจำกัดผู้ใหญ่และอยู่ในช่วงที่รองรับ")
    result.calculated["vte_excluded_by_tool"] = False
    result.calculated["ddimer_interpretation"] = "not_interpretable"
    result.thresholds_used["adult_min_years"] = adult_min
    if n["unstable"] == "yes":
        result.alerts.append(text("urgent"))
        result.rules_used.append("VTE_URGENT_SYMPTOMS")
    imaging = n["imaging_status"]
    if imaging == "positive":
        result.alerts.append(text("imaging_positive"))
        result.findings.append(text("imaging_positive"))
        result.rules_used.append("VTE_REPORTED_POSITIVE_IMAGING")
    if result.validation_errors:
        result.recommendations.append(text("invalid"))
        return finish_review(result)

    adult_scope = n["age"] is not None and n["age"] >= adult_min and n["pregnant"] == "no" and n["suspected_site"] in {"dvt_leg", "pe"}
    if not adult_scope:
        result.validation_warnings.append(text("scope"))
    pretest = n["pretest_probability"]
    if pretest == "unknown":
        result.recommendations.append(text("pretest_missing"))
    elif pretest in {"high", "intermediate"}:
        result.findings.append(text("high_pretest" if pretest == "high" else "intermediate"))
        result.rules_used.append("VTE_PRETEST_" + pretest.upper())
        if adult_scope and imaging != "positive":
            result.recommendations.append(text("imaging_dvt" if n["suspected_site"] == "dvt_leg" else "imaging_pe"))
        result.status = "review"
    if imaging == "negative":
        result.findings.append(text("imaging_negative"))
        result.status = "review"
    elif imaging in {"pending", "not_performed", "inconclusive"}:
        result.findings.append(text("imaging_unresolved"))
    if pretest == "high" and imaging in {"negative", "inconclusive"}:
        result.recommendations.append(text("imaging_discordant"))
        result.rules_used.append("VTE_DISCORDANT_IMAGING_REVIEW")

    value, cutoff = n["ddimer_value"], n["ddimer_cutoff"]
    complete = value is not None and cutoff is not None and all(n[k] != "unknown" for k in ("ddimer_unit", "cutoff_unit", "ddimer_basis", "cutoff_basis"))
    matching = n["ddimer_unit"] == n["cutoff_unit"] and n["ddimer_basis"] == n["cutoff_basis"]
    if value is not None or cutoff is not None:
        if not complete:
            result.validation_warnings.append(text("units_missing"))
            result.rules_used.append("DDIMER_MISSING_ASSAY_GATE")
        elif not matching:
            result.validation_warnings.append(text("units_mismatch"))
            result.rules_used.append("DDIMER_UNIT_BASIS_GATE")
        elif n["cutoff_validated"] != "yes":
            result.validation_warnings.append(text("assay_unconfirmed"))
            result.rules_used.append("DDIMER_CUTOFF_GATE")
        else:
            ratio = value / cutoff
            result.calculated["ddimer_to_cutoff_ratio"] = round(ratio, 6)
            result.thresholds_used.update({"ddimer_cutoff": cutoff, "ddimer_unit": n["cutoff_unit"], "ddimer_basis": n["cutoff_basis"]})
            result.rationale.append(text("ratio", ratio=ratio))
            result.status = "review"
            low_pathway = (adult_scope and pretest == "low" and n["unstable"] == "no"
                           and n["symptoms_current"] == "yes" and n["recurrent_vte"] == "no"
                           and n["anticoagulant_use"] == "no" and n["high_sensitivity_assay"] == "yes"
                           and imaging != "positive")
            if value >= cutoff:
                result.findings.append(text("above"))
                result.calculated["ddimer_interpretation"] = "at_or_above_cutoff"
                result.rules_used.append("DDIMER_ABOVE_NOT_DIAGNOSTIC")
                if adult_scope and imaging != "positive":
                    result.recommendations.append(text("imaging_dvt" if n["suspected_site"] == "dvt_leg" else "imaging_pe"))
            elif low_pathway:
                result.findings.append(text("below_eligible"))
                result.calculated["ddimer_interpretation"] = "below_cutoff_requires_pathway_review"
                result.rules_used.append("DDIMER_LOW_PRETEST_PATHWAY_REVIEW")
            else:
                result.findings.append(text("below_not_eligible"))
                result.calculated["ddimer_interpretation"] = "not_used_for_exclusion"
                result.rules_used.append("DDIMER_EXCLUSION_BLOCKED")
    if n["anticoagulant_use"] != "no":
        result.validation_warnings.append(text("anticoagulant"))
    if n["recurrent_vte"] == "yes":
        result.recommendations.append(text("recurrence"))
    if n["thrombophilia_requested"] == "yes":
        result.recommendations.append(text("thrombophilia"))
        result.rules_used.append("THROMBOPHILIA_INDICATION_REVIEW")
        result.status = "review"
        if n["acute_event"] != "no" or n["anticoagulant_use"] != "no" or n["pregnant"] != "no":
            result.validation_warnings.append(text("thrombophilia_interference"))
            result.rules_used.append("THROMBOPHILIA_INTERFERENCE_GATE")
    if not result.findings:
        result.recommendations.append(text("missing"))
    return finish_review(result)
