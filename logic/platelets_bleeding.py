"""Review platelet and coagulation measurements after specimen/context gates."""
from __future__ import annotations

from typing import Any, Mapping
from .hematology_common import ReviewResult, start_review, finish_review, rule_text


def analyze_platelets_bleeding(data: Mapping[str, Any]) -> ReviewResult:
    result, rules = start_review("platelets_bleeding", data)
    n = result.normalized
    text = lambda key, **values: rule_text(rules, key, **values)
    ratio_limit = rules["thresholds"].get("prolonged_ratio")
    if type(ratio_limit) not in (int, float) or ratio_limit != 1:
        raise ValueError("เกณฑ์อัตราส่วนต้องเป็น 1 สำหรับการเทียบขอบเขตบนของวิธีตรวจ")
    if n["bleeding_severity"] == "major" or n["hemodynamic_instability"] == "yes":
        result.alerts.append(text("major_bleed"))
        result.rules_used.append("BLEEDING_URGENT_SYMPTOMS")
    count, low, high = (n[k] for k in ("platelets_10e9_l", "platelet_ref_low", "platelet_ref_high"))
    critical = n["platelet_critical_low"]
    if count is not None and critical is not None and count < critical:
        result.alerts.append(text("plt_critical", value=count, threshold=critical))
        result.thresholds_used["platelet_critical_low"] = critical
        result.rules_used.append("PLATELET_LOCAL_CRITICAL_VERIFY")
    if low is not None and high is not None and low >= high:
        result.validation_errors.append(text("invalid_ranges"))
    if result.validation_errors:
        result.recommendations.append(text("invalid"))
        return finish_review(result)

    platelet_low = False
    if count is not None:
        if n["cbc_sample_quality"] != "acceptable" or n["platelet_clumps"] != "no":
            result.validation_warnings.append(text("plt_artifact"))
            result.recommendations.append(text("plt_repeat"))
            result.rules_used.append("PLATELET_ARTIFACT_GATE")
        elif low is None and high is None:
            result.validation_warnings.append(text("plt_refs"))
        else:
            result.status = "review"
            if low is not None:
                result.thresholds_used["platelet_ref_low"] = low
            if high is not None:
                result.thresholds_used["platelet_ref_high"] = high
            platelet_low = low is not None and count < low
            direction = "low" if platelet_low else "high" if high is not None and count > high else "within"
            message = text("plt_" + direction, value=count, threshold=low if direction == "low" else high)
            result.findings.append(message)
            result.rationale.append(message)
            result.rules_used.append("PLATELET_LOCAL_REFERENCE_" + direction.upper())
            if direction != "within":
                result.recommendations.append(text("plt_review"))

    coag_values = any(n[k] is not None for k in ("pt_seconds", "aptt_seconds", "fibrinogen_g_l"))
    prolonged: dict[str, bool] = {}
    fibrinogen_low = False
    if coag_values and n["coag_sample_quality"] != "acceptable":
        result.validation_warnings.append(text("coag_quality"))
        result.recommendations.append(text("coag_repeat"))
        result.rules_used.append("COAGULATION_SPECIMEN_GATE")
    elif coag_values:
        for key, label in (("pt", "PT"), ("aptt", "aPTT")):
            value, uln = n[key + "_seconds"], n[key + "_uln_seconds"]
            if value is None or uln is None:
                result.validation_warnings.append(text("missing_" + key))
                continue
            ratio = value / uln
            result.calculated[key + "_to_uln_ratio"] = round(ratio, 4)
            result.thresholds_used[key + "_uln_seconds"] = uln
            result.rationale.append(text("ratio", label=label, ratio=ratio))
            prolonged[key] = value > uln
            result.status = "review"
        if len(prolonged) == 2:
            pattern = "both_prolonged" if all(prolonged.values()) else "isolated_pt" if prolonged["pt"] else "isolated_aptt" if prolonged["aptt"] else "neither_prolonged"
            result.findings.append(text(pattern))
            result.rules_used.append("COAG_PATTERN_" + pattern.upper())
            result.calculated["coagulation_pattern"] = pattern
            if any(prolonged.values()):
                if n["anticoagulant"] == "none" and n["recent_factor_or_transfusion"] == "no":
                    result.recommendations.append(text("mixing"))
                else:
                    result.validation_warnings.append(text("confounder"))
                    result.recommendations.append(text("drug_review"))
                    result.rules_used.append("COAGULATION_INTERFERENCE_GATE")
            elif n["bleeding_severity"] in {"minor", "major"}:
                result.recommendations.append(text("bleeding_normal_tests"))
                result.rules_used.append("BLEEDING_WITH_UNPROLONGED_PT_APTT")
        fibrinogen, fib_low = n["fibrinogen_g_l"], n["fibrinogen_ref_low"]
        if fibrinogen is not None:
            if fib_low is None:
                result.validation_warnings.append(text("fibrinogen_missing"))
            else:
                result.thresholds_used["fibrinogen_ref_low"] = fib_low
                fibrinogen_low = fibrinogen < fib_low
                result.calculated["fibrinogen_below_local_lower_limit"] = fibrinogen_low
                result.status = "review"
                if fibrinogen_low:
                    result.findings.append(text("fibrinogen_low", value=fibrinogen, threshold=fib_low))
                    result.rules_used.append("FIBRINOGEN_LOCAL_LOW")
    if n["ddimer_lab_call"] != "unknown":
        result.limitations.append(text("ddimer"))
    if platelet_low and len(prolonged) == 2 and all(prolonged.values()) and fibrinogen_low and n["ddimer_lab_call"] == "increased":
        result.findings.append(text("combined_abnormal"))
        result.recommendations.append(text("combined_abnormal"))
        result.rules_used.append("MULTIPLE_HEMOSTASIS_ABNORMALITIES_NO_DIC_DIAGNOSIS")
    if n["bleeding_pattern"] == "mucocutaneous" and n["bleeding_severity"] in {"minor", "major"}:
        result.recommendations.append(text("mucosal"))
    if n["antiplatelet_use"] in {"yes", "unknown"} and n["bleeding_severity"] in {"minor", "major"}:
        result.recommendations.append(text("drug_review"))
    if not result.findings:
        result.recommendations.append(text("missing"))
    return finish_review(result)
