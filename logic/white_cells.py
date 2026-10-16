"""Evidence-aware leukocyte review with measured/derived counts kept distinct."""
from __future__ import annotations

import math
from typing import Any, Mapping

from logic.hematology_common import ReviewResult, finish_review, rule_text, start_review


DIFFERENTIAL_FIELDS = (
    "neutrophils_percent", "lymphocytes_percent", "monocytes_percent", "eosinophils_percent",
    "basophils_percent", "immature_granulocytes_percent", "blasts_percent",
)
ABSOLUTE_MAP = (
    ("anc", "ANC", "neutrophils_percent"), ("alc", "Lymphocytes", "lymphocytes_percent"),
    ("amc", "Monocytes", "monocytes_percent"), ("aec", "Eosinophils", "eosinophils_percent"),
    ("abc", "Basophils", "basophils_percent"),
)


def analyze_white_cells(data: Mapping[str, Any]) -> ReviewResult:
    result, rules = start_review("white_cells", data)
    n, t = result.normalized, rules["thresholds"]
    required = {"adult_min_age", "differential_total", "differential_tolerance_percent", "absolute_conflict_relative", "absolute_conflict_floor", "severe_anc_10e9_l", "fever_single_c", "fever_sustained_c", "fever_sustained_hours"}
    if set(t) != required or any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0 for value in t.values()):
        raise ValueError("เกณฑ์เม็ดเลือดขาวไม่ครบหรือไม่ถูกต้อง กรุณาทบทวนไฟล์กฎ")
    # These constants define units and the explicit assertion in the input field.
    if (t["differential_total"] != 100 or t["fever_sustained_c"] != 38
            or t["fever_sustained_hours"] != 1
            or t["fever_single_c"] < t["fever_sustained_c"]
            or t["differential_tolerance_percent"] >= t["differential_total"]):
        raise ValueError("ลำดับเกณฑ์เม็ดเลือดขาวไม่ถูกต้อง กรุณาทบทวนไฟล์กฎ")

    def text(key: str, **values: Any) -> str:
        return rule_text(rules, key, **values)

    result.thresholds_used = dict(t)
    wbc = n["wbc_10e9_l"]
    adult = n["age"] is not None and n["age"] >= t["adult_min_age"]
    if not adult:
        result.validation_warnings.append(text("age_scope", age=t["adult_min_age"]))
    known = {field: n[field] for field in DIFFERENTIAL_FIELDS if n[field] is not None}
    total = sum(known.values())
    complete = len(known) == len(DIFFERENTIAL_FIELDS)
    differential_ok = total <= t["differential_total"] + t["differential_tolerance_percent"]
    if complete and abs(total - t["differential_total"]) > t["differential_tolerance_percent"]:
        differential_ok = False
    if known:
        result.calculated["differential"] = {"known_total_percent": total, "reported_categories": len(known), "required_categories": len(DIFFERENTIAL_FIELDS), "complete": complete, "consistent": differential_ok}
        result.findings.append(text("total", sum=total, known=len(known), total=len(DIFFERENTIAL_FIELDS)))
        if not complete:
            result.validation_warnings.append(text("partial", sum=total, known=len(known), total=len(DIFFERENTIAL_FIELDS)))
        if not differential_ok:
            result.validation_errors.append(text("total_invalid", sum=total))
            result.rules_used.append("WBC_DIFFERENTIAL_INCONSISTENT")
    if known and wbc is None:
        result.validation_warnings.append(text("no_wbc"))

    absolutes: dict[str, dict[str, Any]] = {}
    for short, label, percentage_field in ABSOLUTE_MAP:
        measured = n[short + "_10e9_l"]
        percentage = n[percentage_field]
        derived = wbc * percentage / t["differential_total"] if wbc is not None and percentage is not None and differential_ok else None
        effective = measured if measured is not None else derived
        if effective is None:
            continue
        source = "measured" if measured is not None else "calculated"
        conflict = False
        if measured is not None and derived is not None:
            margin = max(t["absolute_conflict_floor"], abs(measured) * t["absolute_conflict_relative"])
            conflict = abs(measured - derived) > margin
            if conflict:
                result.validation_warnings.append(text("conflict", name=label, measured=measured, derived=derived))
                result.rules_used.append("WBC_MEASURED_DERIVED_CONFLICT")
        absolutes[short] = {"measured": measured, "derived": derived, "effective": effective, "source": source, "conflict": conflict, "unit": "10^9/L"}
        result.findings.append(text("absolute", name=label, value=effective, source=text("measured_source" if source == "measured" else "calculated_source")))
        if derived is not None:
            result.rationale.append(text("calculation", name=label, wbc=wbc, percent=percentage, value=derived))
            result.rules_used.append("WBC_ABSOLUTE_CALCULATION")
        if measured is not None and wbc is not None and measured > wbc + t["absolute_conflict_floor"]:
            result.validation_errors.append(text("absolute_exceeds", name=label))
    # Sum one effective value per non-overlapping category. Summing only measured
    # values misses impossible mixed measured/calculated differentials; summing
    # both representations of a category would count the same cells twice.
    components = {short: {"value": item["effective"], "source": item["source"]}
                  for short, item in absolutes.items()}
    if wbc is not None and differential_ok:
        for short, field in (("ig", "immature_granulocytes_percent"), ("blasts", "blasts_percent")):
            if n[field] is not None:
                components[short] = {"value": wbc * n[field] / t["differential_total"], "source": "calculated"}
    # A partial sum is a lower bound, not evidence that missing categories are 0.
    effective_sum = math.fsum(item["value"] for item in components.values()) if components else None
    absolute_complete = len(components) == len(DIFFERENTIAL_FIELDS)
    consistent = None
    if effective_sum is not None and wbc is not None:
        lower, upper = wbc - t["absolute_conflict_floor"], wbc + t["absolute_conflict_floor"]
        # Accommodate arithmetic roundoff at an inclusive tolerance boundary.
        below_upper = effective_sum <= upper or math.isclose(effective_sum, upper, rel_tol=0, abs_tol=1e-12)
        above_lower = effective_sum >= lower or math.isclose(effective_sum, lower, rel_tol=0, abs_tol=1e-12)
        consistent = below_upper and (not absolute_complete or above_lower)
    result.calculated["absolute_total"] = {
        "known_total_10e9_l": effective_sum, "wbc_10e9_l": wbc,
        "components": components, "reported_categories": len(components),
        "required_categories": len(DIFFERENTIAL_FIELDS), "complete": absolute_complete,
        "tolerance_10e9_l": t["absolute_conflict_floor"], "consistent": consistent,
    }
    if consistent is False:
        if absolute_complete:
            result.validation_errors.append(text("absolute_total_mismatch", sum=effective_sum, wbc=wbc, tolerance=t["absolute_conflict_floor"]))
            result.rules_used.append("WBC_ABSOLUTE_TOTAL_MISMATCH")
        else:
            result.validation_errors.append(text("absolute_total_exceeds", sum=effective_sum, wbc=wbc, tolerance=t["absolute_conflict_floor"]))
        result.rules_used.append("WBC_ABSOLUTE_TOTAL_INCONSISTENT")
    result.calculated["absolute_counts"] = absolutes
    local_ranges: dict[str, Any] = {}
    count_map = {"wbc": ("WBC", wbc), **{short: (label, absolutes.get(short, {}).get("effective")) for short, label, _ in ABSOLUTE_MAP}}
    for short, (label, value) in count_map.items():
        low, high = n[short + "_low"], n[short + "_high"]
        if low is not None and high is not None and low >= high:
            result.validation_errors.append(text("range_invalid", name=label))
            continue
        if value is None:
            continue
        if low is None and high is None:
            result.validation_warnings.append(text("no_range", name=label))
            continue
        local_ranges[short] = {"low": low, "high": high, "unit": "10^9/L"}
        direction = "low" if low is not None and value < low else "high" if high is not None and value > high else "within"
        result.findings.append(text("range_" + direction, name=label, value=value, bound=low if direction == "low" else high))
        result.rules_used.append("WBC_LOCAL_RANGE_" + short.upper() + "_" + direction.upper())
    result.thresholds_used["local_reference_intervals"] = local_ranges

    anc = absolutes.get("anc", {}).get("effective")
    fever = (n["temperature_c"] is not None and n["temperature_c"] >= t["fever_single_c"]) or n["fever_38_for_hour"] == "yes"
    result.calculated["fever_criterion_present"] = True if fever else False if n["temperature_c"] is not None and n["fever_38_for_hour"] == "no" else None
    if anc is not None and anc < t["severe_anc_10e9_l"]:
        if adult:
            result.findings.append(text("low_anc", anc=anc, cutoff=t["severe_anc_10e9_l"]))
            result.rules_used.append("WBC_ADULT_SEVERE_ANC_REVIEW")
        if fever:
            result.alerts.append(text("fever_anc_alert", anc=anc, cutoff=t["severe_anc_10e9_l"]) if adult else text("unscoped_alert"))
            result.rules_used.append("WBC_FEVER_LOW_ANC_ALERT")
        elif n["temperature_c"] is None or n["fever_38_for_hour"] == "unknown":
            result.validation_warnings.append(text("fever_unknown"))

    observed_blasts = n["smear_blasts"] == "yes" or (n["blasts_percent"] is not None and n["blasts_percent"] > 0)
    if n["instrument_blast_flag"] == "yes":
        result.findings.append(text("instrument"))
        result.rules_used.append("WBC_INSTRUMENT_FLAG_REVIEW")
        result.recommendations.append(text("followup_blasts"))
    if observed_blasts:
        result.findings.append(text("smear"))
        result.alerts.append(text("blast_alert"))
        result.recommendations.append(text("followup_blasts"))
        result.rules_used.append("WBC_PERIPHERAL_BLAST_REVIEW")
    if n["smear_blasts"] == "no" and n["blasts_percent"] is not None and n["blasts_percent"] > 0:
        result.validation_warnings.append(text("smear_conflict"))
    if n["smear_blasts"] == "no" or n["instrument_blast_flag"] == "no":
        result.limitations.append(text("not_excluded"))
    has_evidence = bool(wbc is not None or absolutes or known or n["smear_blasts"] != "unknown" or n["instrument_blast_flag"] != "unknown")
    if has_evidence:
        result.status = "review"
        result.recommendations.append(text("followup_counts"))
    else:
        result.findings.append(text("empty"))
    return finish_review(result)
