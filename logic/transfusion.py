"""Component-specific review gates; never a blood-release authorization."""

from __future__ import annotations

from typing import Any, Mapping

from .hematology_common import ReviewResult, finish_review, rule_text, start_review


ABO_GROUPS = {"O", "A", "B", "AB"}


def analyze_transfusion(data: Mapping[str, Any]) -> ReviewResult:
    result, rules = start_review("transfusion", data)
    n = result.normalized
    text = lambda key, **values: rule_text(rules, key, **values)
    result.calculated.update({"patient_abo_for_review": None, "abo_table_match": None,
                              "compatibility_review_ready": False, "release_authorized": False})
    result.recommendations.append(text("release_limit"))

    symptoms = set(n["reaction_symptoms"])
    observed_symptoms = symptoms - {"none", "unknown"}
    if (observed_symptoms and symptoms & {"none", "unknown"}) or {"none", "unknown"} <= symptoms:
        result.validation_errors.append(text("multiselect_conflict"))
    reaction = n["reaction_suspected"] == "yes" or bool(observed_symptoms)
    if reaction:
        result.alerts.append(text("reaction_alert"))
        result.recommendations.extend(text(key) for key in
            ("reaction_abc", "reaction_iv", "reaction_check", "reaction_samples"))
        result.limitations.append(text("reaction_no_classify"))
        result.rationale.append(text("reaction_only"))
        result.rules_used.append("TF_REACTION_ESCALATION")
        if observed_symptoms and n["reaction_suspected"] == "no":
            result.validation_warnings.append(text("reaction_conflict"))

    controls_ready = True
    for key in ("identity_verified", "specimen_valid", "independent_type_verified"):
        if n[key] != "yes":
            controls_ready = False
            result.validation_warnings.append(text("control_missing", label=result.field_labels[key]))
    result.rules_used.append("TF_IDENTITY_SPECIMEN_TYPE_GATES")

    forward, reverse, record = n["forward_abo"], n["reverse_abo"], n["verified_patient_abo"]
    if record in ABO_GROUPS and n["record_verified"] != "yes":
        controls_ready = False
        result.validation_warnings.append(text("control_missing", label=result.field_labels["record_verified"]))
    patient = None
    discrepancy = forward in ABO_GROUPS and reverse in ABO_GROUPS and forward != reverse
    if n["abo_basis"] == "forward_reverse" and forward in ABO_GROUPS and forward == reverse:
        patient = forward
    elif n["abo_basis"] == "verified_record" and n["record_verified"] == "yes" and record in ABO_GROUPS:
        patient = record
    if n["record_verified"] == "yes" and record in ABO_GROUPS:
        discrepancy |= any(group in ABO_GROUPS and group != record for group in (forward, reverse))
    if discrepancy:
        patient = None
        result.alerts.append(text("abo_discrepancy"))
        result.recommendations.append(text("abo_discrepancy_action"))
        result.rules_used.append("TF_ABO_DISCREPANCY")
    elif patient is None:
        result.validation_warnings.append(text("abo_missing"))
    result.calculated["patient_abo_for_review"] = patient

    component, donor = n["component"], n["donor_abo"]
    abo_match = None
    if component not in {"rbc", "plasma"}:
        result.validation_warnings.append(text("component_missing"))
    elif patient is not None and donor in ABO_GROUPS:
        choices = rules["thresholds"]["abo_compatibility"][component][patient]
        result.thresholds_used["abo_component_table"] = rules["thresholds"]["abo_compatibility"][component]
        abo_match = donor in choices
        result.status = "review"
        result.rationale.append(text("abo_review", patient=patient, donor=donor,
                                     component=result.value_labels["component"][component]))
        result.rules_used.append("TF_ABO_RBC" if component == "rbc" else "TF_ABO_PLASMA")
        if not abo_match:
            result.alerts.append(text("abo_mismatch"))
            result.recommendations.append(text("abo_mismatch_action"))
        if controls_ready:
            result.calculated["abo_table_match"] = abo_match
    else:
        result.validation_warnings.append(text("abo_missing"))

    component_ready = component == "plasma"
    if component == "plasma":
        result.rationale.append(text("plasma_scope"))
        result.rules_used.append("TF_PLASMA_NO_RHD_GATE")
    elif component == "rbc":
        component_ready = True
        if n["patient_rhd"] == "unknown" or n["donor_rhd"] == "unknown":
            component_ready = False
            result.validation_warnings.append(text("rhd_missing"))
        elif n["patient_rhd"] == "negative" and n["donor_rhd"] == "positive":
            component_ready = False
            result.findings.append(text("rhd_exception"))
            result.recommendations.append(text("rhd_exception"))
        result.rules_used.append("TF_RBC_RHD_REVIEW")

        if n["antibody_screen"] not in {"negative", "positive"} or n["antibody_history"] == "unknown":
            component_ready = False
            result.validation_warnings.append(text("screen_missing"))
        antibody_risk = n["antibody_screen"] == "positive" or n["antibody_history"] == "yes"
        if antibody_risk:
            result.findings.append(text("antibody_special"))
            result.recommendations.append(text("antibody_special"))
            result.rules_used.append("TF_ANTIBODY_HISTORY_IAT_GATE")
            if not (n["antibody_workup_reviewed"] == "yes" and n["antigen_negative_verified"] == "yes" and n["crossmatch_method"] == "iat"):
                component_ready = False
                result.validation_warnings.append(text("antibody_gate"))
        if not (n["crossmatch_result"] == "compatible" and n["crossmatch_process_validated"] == "yes"
                and n["crossmatch_method"] in {"iat", "electronic", "immediate_spin"}):
            component_ready = False
            result.validation_warnings.append(text("crossmatch_missing"))
        if n["crossmatch_result"] == "incompatible":
            result.alerts.append(text("crossmatch_bad"))
        result.rules_used.append("TF_RBC_CROSSMATCH_GATE")

    reaction_reviewed = n["reaction_suspected"] == "no" and not reaction
    if n["reaction_suspected"] == "unknown" and not reaction:
        result.validation_warnings.append(text("reaction_unknown"))
    ready = bool(controls_ready and abo_match is True and component_ready and reaction_reviewed
                 and not result.validation_errors and not discrepancy)
    result.calculated["compatibility_review_ready"] = ready
    if ready:
        result.status = "review"
        result.findings.extend([text("abo_pattern_only"), text("ready")])
        result.rules_used.append("TF_REVIEW_ONLY_NOT_RELEASE")
    else:
        result.findings.append(text("not_ready"))
    return finish_review(result)
