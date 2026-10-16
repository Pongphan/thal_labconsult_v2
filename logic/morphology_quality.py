"""Review recorded manual observations and specimen quality, without image AI."""

from __future__ import annotations

from typing import Any, Mapping

from .hematology_common import ReviewResult, finish_review, rule_text, start_review


def analyze_morphology_quality(data: Mapping[str, Any]) -> ReviewResult:
    result, rules = start_review("morphology_quality", data)
    n = result.normalized
    text = lambda key, **values: rule_text(rules, key, **values)
    holds = []
    for field, expected, message in (
        ("specimen_clot", "yes", "clot"), ("specimen_hemolysis", "yes", "hemolysis"),
        ("edta_fill_status", "outside", "fill"), ("smear_quality", "unacceptable", "smear_bad"),
    ):
        if n[field] == expected:
            holds.append(field)
            result.findings.append(text(message))
            result.recommendations.append(text(message))
            result.rules_used.append("MQ_" + field.upper())

    age, limit = n["sample_age_hours"], n["local_max_age_hours"]
    timing_complete = n["timing_limit_validated"] == "yes" and age is not None and limit is not None
    if timing_complete:
        result.thresholds_used["local_max_age_hours"] = limit
        result.rules_used.append("MQ_LOCAL_SPECIMEN_STABILITY")
        if age > limit:
            holds.append("sample_age_hours")
            result.findings.append(text("timing_exceeded", age=age, limit=limit))
        else:
            result.rationale.append(text("timing_review", age=age, limit=limit))
    else:
        result.validation_warnings.append(text("timing_missing"))
    quality_complete = (timing_complete and n["specimen_clot"] == "no"
        and n["specimen_hemolysis"] == "no" and n["edta_fill_status"] == "acceptable"
        and n["smear_quality"] == "acceptable" and n["smear_reviewed"] == "yes")

    observed_sets: dict[str, set[str]] = {}
    for field in ("rbc_morphology", "wbc_morphology"):
        selected = set(n[field])
        observed = selected - {"none", "unknown"}
        observed_sets[field] = observed
        if (observed and selected & {"none", "unknown"}) or {"none", "unknown"} <= selected:
            result.validation_errors.append(text("selection_conflict", label=result.field_labels[field]))
        if observed:
            names = [result.value_labels[field][value] for value in n[field] if value in observed]
            if field == "rbc_morphology":
                result.findings.append(text("rbc_observed", items=", ".join(names),
                    grade=result.value_labels["rbc_grade"][n["rbc_grade"]]))
                result.recommendations.append(text("rbc_action"))
            else:
                result.findings.append(text("wbc_observed", items=", ".join(names)))
                result.recommendations.append(text("wbc_action"))
            result.rules_used.append("MQ_RECORDED_" + field.upper())

    count_fields = rules["thresholds"]["differential_fields"]
    any_counts = any(n[field] is not None for field in count_fields)
    reported_total = n["diff_total_reported"]
    for field in [*count_fields, "diff_total_reported", "nrbc_count"]:
        if n[field] is not None and not n[field].is_integer():
            result.validation_errors.append(text("counts_integer", label=result.field_labels[field]))
    count_blasts = n["diff_blasts"]
    blast_reported = n["blast_observation"] in {"suspected", "confirmed"} or (count_blasts is not None and count_blasts > 0)
    if blast_reported:
        result.alerts.append(text("blast_alert"))
        result.recommendations.append(text("blast_action"))
        result.rules_used.append("MQ_REPORTED_BLAST_REVIEW")
    if count_blasts is not None and count_blasts > 0 and n["blast_observation"] == "not_seen":
        result.validation_errors.append(text("blast_conflict"))

    schistocytes = n["schistocyte_percent"]
    if schistocytes is not None:
        result.findings.append(text("schisto_value", value=schistocytes))
        result.limitations.append(text("schisto_limit"))
        population = n["population"]
        upper = rules["thresholds"]["schistocyte_percent_upper"].get(population)
        if upper is None:
            result.validation_warnings.append(text("schisto_scope"))
        else:
            result.thresholds_used["schistocyte_percent_upper"] = upper
            result.thresholds_used["schistocyte_population"] = population
            result.rules_used.append("MQ_SCHISTOCYTE_POPULATION_REFERENCE")
            if schistocytes > upper:
                if population in {"adult", "term_neonate"}:
                    result.alerts.append(text("schisto_high", value=schistocytes, limit=upper))
                    result.recommendations.append(text("schisto_high", value=schistocytes, limit=upper))
                else:
                    result.findings.append(text("schisto_preterm", value=schistocytes, limit=upper))
                    result.recommendations.append(text("schisto_preterm", value=schistocytes, limit=upper))
    if n["platelet_clumps"] == "yes":
        holds.append("platelet_clumps")
        result.findings.append(text("clumps"))
        result.recommendations.append(text("clumps_action"))
        result.rules_used.append("MQ_PLATELET_CLUMP_REVIEW")

    observation_present = (blast_reported or schistocytes is not None or n["platelet_clumps"] == "yes"
        or any(observed_sets.values()) or any_counts)
    if n["smear_reviewed"] == "no" and observation_present:
        result.validation_errors.append(text("observation_unreviewed"))
    elif n["smear_reviewed"] != "yes":
        result.validation_warnings.append(text("review_missing"))

    result.calculated["manual_differential_total"] = None
    result.calculated["manual_differential_percent"] = {}
    if any_counts or reported_total is not None or n["nrbc_count"] is not None:
        complete_counts = all(n[field] is not None for field in count_fields)
        result.limitations.append(text("counts_arithmetic"))
        if not complete_counts:
            result.validation_warnings.append(text("counts_incomplete"))
        elif not result.validation_errors:
            total = sum(n[field] for field in count_fields)
            if total <= 0:
                result.validation_errors.append(text("counts_zero"))
            elif reported_total is not None and total != reported_total:
                result.validation_errors.append(text("counts_mismatch", total=total, reported=reported_total))
            else:
                result.calculated["manual_differential_total"] = int(total)
                result.calculated["manual_differential_percent"] = {
                    field.removeprefix("diff_"): round(n[field] / total * 100, 3) for field in count_fields
                }
                result.findings.append(text("counts_ready", total=total))
                result.rules_used.append("MQ_MANUAL_DIFFERENTIAL_ARITHMETIC")
                if n["nrbc_count"] is not None:
                    result.calculated["nrbc_per_100_wbc_counted"] = round(n["nrbc_count"] / total * 100, 3)
                    result.rationale.append(text("nrbc_note"))

    if holds:
        result.calculated["quality_gate"] = "hold_for_review"
        result.findings.append(text("quality_hold"))
        result.recommendations.append(text("quality_action"))
    elif result.validation_errors:
        result.calculated["quality_gate"] = "invalid_data"
        result.validation_warnings.append(text("quality_unknown"))
    elif quality_complete:
        result.calculated["quality_gate"] = "eligible_for_professional_review"
        result.findings.append(text("quality_review"))
    else:
        result.calculated["quality_gate"] = "incomplete"
        result.validation_warnings.append(text("quality_unknown"))
    result.calculated["quality_holds"] = holds
    result.calculated["report_authorized"] = False
    result.rules_used.append("MQ_QUALITY_GATE")
    if holds or observation_present or quality_complete:
        result.status = "review"
    if (quality_complete and not holds and not blast_reported and schistocytes in (None, 0)
            and n["blast_observation"] == "not_seen" and n["platelet_clumps"] == "no"
            and n["rbc_morphology"] == ["none"] and n["wbc_morphology"] == ["none"]):
        result.findings.append(text("no_abnormal_reported"))
    return finish_review(result)
