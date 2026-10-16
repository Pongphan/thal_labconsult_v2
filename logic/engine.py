"""Deterministic screening support; clinical wording and weights live in JSON."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
import hashlib
import json
import math
import numpy as np
import pandas as pd
from .rules import load_rules
from .validation import SCREENING_COLUMNS, is_missing, safe_num, normalize_call, normalize_threshold_sex, yn, validate_screening
from utils.csv_io import MAX_ROWS
from utils.build_provenance import capture_build_provenance
from .clinical_grouping import group_screening_findings

DEFAULT_THRESHOLDS = load_rules()["thresholds"].copy()


def _age_limit(age: float, field_name: str, default: float, config: dict) -> float:
    if not math.isfinite(age):
        return np.nan
    for upper, value in config["age_thresholds"][field_name]:
        if age < upper:
            return float(value)
    return default


def _anemia_limit(age: float, sex: str | None, pregnant: Any, name: str, config: dict) -> float:
    if isinstance(age, (bool, np.bool_)):
        return np.nan
    age = safe_num(age)
    age_low, age_high, _ = config["validation"]["ranges"]["age"]
    if not math.isfinite(age) or not age_low <= age <= age_high:
        return np.nan
    adult = config["adult_thresholds"][name]
    sex_context = normalize_threshold_sex(sex)
    if pregnant is True:
        # A contradictory or unspecified threshold context must be reviewed;
        # pregnancy must not silently override the selected sex context.
        return adult["pregnant"] if sex_context == "Female" else np.nan
    sex_key = sex_context.lower() if sex_context is not None else None
    # Age-only childhood rules remain usable. A sex-dependent female threshold
    # requires explicit nonpregnancy; unknown must not silently mean False.
    adult_limit = adult[sex_key] if sex_key and (sex_key == "male" or pregnant is False) else np.nan
    return _age_limit(age, name, adult_limit, config)


def anemia_threshold(age: float, sex: str | None = None, pregnant: bool | None = None) -> float:
    return _anemia_limit(age, sex, pregnant, "hb_g_dl", load_rules())


def hct_threshold(age: float, sex: str | None = None, pregnant: bool | None = None) -> float:
    return _anemia_limit(age, sex, pregnant, "hct_percent", load_rules())


def mcv_threshold(age: float) -> float:
    config = load_rules()
    return _age_limit(safe_num(age), "mcv_fl", config["thresholds"]["mcv_microcytosis"], config)


def mch_threshold(age: float) -> float:
    config = load_rules()
    return _age_limit(safe_num(age), "mch_pg", config["thresholds"]["mch_hypochromia"], config)


def clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(value))) if math.isfinite(value) else lo


def derived_indices(row: dict[str, Any] | pd.Series) -> dict[str, float]:
    hb, rbc, mcv, mch, rdw, hct = [safe_num(row.get(k)) for k in
        ("hb_g_dl", "rbc_10e12_l", "mcv_fl", "mch_pg", "rdw_percent", "hct_percent")]
    values = {
        "mentzer_index": mcv / rbc if rbc > 0 else np.nan,
        "rdwi": mcv * rdw / rbc if rbc > 0 else np.nan,
        "shine_lal_index": mcv ** 2 * mch / 100,
        "england_fraser_index": mcv - rbc - 5 * hb - 3.4,
        "green_king_index": mcv ** 2 * rdw / (100 * hb) if hb > 0 else np.nan,
        "calculated_mchc": hb * 100 / hct if hct > 0 else np.nan,
    }
    return {key: round(value, 2) if math.isfinite(value) else np.nan for key, value in values.items()}


def assess_partner_screening(patient_oft: Any, patient_dcip: Any, partner_oft: Any,
                             partner_dcip: Any, *, rules: dict | None = None) -> dict[str, Any]:
    config = rules or load_rules()
    calls = [normalize_call(v) for v in (patient_oft, patient_dcip, partner_oft, partner_dcip)]
    complete = all(value in {"Positive", "Negative"} for value in calls)
    positive = ["Positive" in calls[:2], "Positive" in calls[2:]]
    status = "incomplete" if not complete else "both_positive" if all(positive) else "one_positive" if any(positive) else "negative"
    return {"status": status, "complete": complete,
            "interpretation": config["partner_screening"][status],
            "recommendations": list(config["partner_screening"]["recommendations"])}


@dataclass
class ScreeningResult:
    sample_id: str
    top_pattern: str
    consult_risk: str
    consult_score: float
    beta_trait_score: float
    alpha_trait_score: float
    hbe_score: float
    iron_deficiency_score: float
    severe_anemia_flag: bool
    microcytosis: bool | None
    hypochromia: bool | None
    anemia: bool | None
    evidence: list[str]
    recommendations: list[str]
    caveats: list[str]
    derived: dict[str, float]
    normalized: dict[str, Any]
    validation_errors: list[str] = field(default_factory=list)
    validation_warnings: list[str] = field(default_factory=list)
    counseling: list[str] = field(default_factory=list)
    suspected_genotypes: list[str] = field(default_factory=list)
    rule_ids: list[str] = field(default_factory=list)
    ruleset_version: str = ""
    ruleset_hash: str = ""
    confidence_note: str = ""
    thresholds_used: dict[str, float | None] = field(default_factory=dict)
    ee_assessment: dict[str, Any] = field(default_factory=dict)
    partner_screening: dict[str, Any] = field(default_factory=dict)
    input_origin: str = "unknown"
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone(timedelta(hours=7))).isoformat(timespec="seconds"))
    clinical_grouping: dict[str, Any] = field(default_factory=dict)
    build_provenance: dict[str, Any] = field(default_factory=capture_build_provenance)
    clinical_use_status: str = "draft_not_clinically_validated"

    def to_flat_dict(self) -> dict[str, Any]:
        out = {key: value for key, value in vars(self).items()
               if key not in {"derived", "normalized", "thresholds_used", "ee_assessment", "partner_screening", "clinical_grouping", "build_provenance"}}
        out = {key: " | ".join(value) if isinstance(value, list) else value for key, value in out.items()}
        out.update(self.derived)
        out.update(self.normalized)
        out["thresholds_used"] = json.dumps(self.thresholds_used, ensure_ascii=False, allow_nan=False)
        out["ee_applicable"] = self.ee_assessment.get("applicable", False)
        out["ee_score"] = self.ee_assessment.get("score")
        out["ee_interpretation"] = self.ee_assessment.get("interpretation", "")
        out["partner_status"] = self.partner_screening.get("status", "incomplete")
        out["partner_complete"] = self.partner_screening.get("complete", False)
        out["partner_interpretation"] = self.partner_screening.get("interpretation", "")
        out["partner_recommendations"] = " | ".join(self.partner_screening.get("recommendations", []))
        out["clinical_grouping"] = json.dumps(self.clinical_grouping, ensure_ascii=False, allow_nan=False)
        out["clinical_group_labels"] = " | ".join(self.clinical_grouping.get("group_labels", []))
        out["build_provenance"] = json.dumps(self.build_provenance, ensure_ascii=False, allow_nan=False)
        return out


def _matches(rule: dict, signals: dict[str, bool]) -> bool:
    return (all(signals[k] for k in rule.get("all", []))
            and (not rule.get("any") or any(signals[k] for k in rule["any"]))
            and not any(signals[k] for k in rule.get("none", [])))


def analyze_screening(row: dict[str, Any] | pd.Series, thresholds: dict[str, float] | None = None,
                      *, input_origin: str = "unknown") -> ScreeningResult:
    config = load_rules()
    return _analyze_screening(row, thresholds, config=config, digest=_rules_digest(config), input_origin=input_origin)


def _rules_digest(config: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(config, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")).hexdigest()


def _analyze_screening(row: dict[str, Any] | pd.Series, thresholds: dict[str, float] | None,
                       *, config: dict[str, Any], digest: str, input_origin: str = "unknown") -> ScreeningResult:
    """Analyze with one validated configuration snapshot, shared across a batch."""
    checked = validate_screening(row, rules=config)
    n, errors, warnings = checked.normalized, checked.errors, checked.warnings
    t = config["thresholds"].copy()
    overrides = thresholds or {}
    for key, value in overrides.items():
        number = safe_num(value)
        if key not in t or not math.isfinite(number) or number <= 0 or isinstance(value, (bool, np.bool_)):
            errors.append(f"เกณฑ์ {key} ไม่ถูกต้อง กรุณาให้ผู้ดูแลตรวจสอบ")
        else:
            t[key] = number
    if t["ferritin_deficient"] >= t["ferritin_borderline"] or t["hba2_beta_trait"] >= t["hba2_review_upper"] or t["hbf_elevated"] >= t["hbf_review"]:
        errors.append("ลำดับเกณฑ์ที่ปรับไม่สอดคล้องกัน กรุณาให้ผู้ดูแลตรวจสอบโปรไฟล์")
    if "mcv_microcytosis" not in overrides:
        t["mcv_microcytosis"] = _age_limit(n["age"], "mcv_fl", t["mcv_microcytosis"], config)
    if "mch_hypochromia" not in overrides:
        t["mch_hypochromia"] = _age_limit(n["age"], "mch_pg", t["mch_hypochromia"], config)
    t["anemia_hb"] = _anemia_limit(n["age"], n["sex"], n["pregnant"], "hb_g_dl", config)
    t["anemia_hct"] = _anemia_limit(n["age"], n["sex"], n["pregnant"], "hct_percent", config)
    d = derived_indices(n)
    hb, mcv, mch = n["hb_g_dl"], n["mcv_fl"], n["mch_pg"]
    hba2, hbf, hbe, ferritin = (n[k] for k in ("hba2_percent", "hbf_percent", "hbe_percent", "ferritin_ng_ml"))
    severe = math.isfinite(hb) and hb < t["severe_hb"]
    micro = mcv < t["mcv_microcytosis"] if math.isfinite(mcv) and math.isfinite(t["mcv_microcytosis"]) else None
    hypo = mch < t["mch_hypochromia"] if math.isfinite(mch) and math.isfinite(t["mch_hypochromia"]) else None
    anemia_checks = [value < cutoff for value, cutoff in ((hb, t["anemia_hb"]), (n["hct_percent"], t["anemia_hct"]))
                     if math.isfinite(value) and math.isfinite(cutoff)]
    anemia = any(anemia_checks) if anemia_checks else None
    msg, metadata = config["messages"], config["metadata"]
    evidence, recommendations, caveats, counseling, genotypes, rule_ids = [], [], [metadata["disclaimer_th"]], [], [], []
    if severe:
        evidence.append(msg["urgent"])
        recommendations.append(msg["urgent"])
    if n["transfusion_recent"] is True:
        caveats.append(msg["transfusion"])
    if math.isfinite(n["age"]) and n["age"] < 18:
        caveats.append(msg["age_caveat"])
    known_age = math.isfinite(n["age"])
    eligible_age = known_age and n["age"] >= t["hb_fraction_min_age_years"]
    signals = {
        "eligible_age": eligible_age, "infant": known_age and not eligible_age,
        "micro": bool(micro), "hypo": bool(hypo), "high_rbc": n["rbc_10e12_l"] >= t["rbc_high"],
        "mentzer_beta_like": d["mentzer_index"] < t["mentzer_beta_like"],
        "rdw_high": n["rdw_percent"] > t["rdw_high"], "ferritin_low": ferritin < t["ferritin_deficient"],
        "ferritin_border_only": t["ferritin_deficient"] <= ferritin < t["ferritin_borderline"],
        "hba2_high": eligible_age and hba2 >= t["hba2_beta_trait"],
        "hba2_not_high": eligible_age and hba2 < t["hba2_beta_trait"],
        "hbf_high": eligible_age and hbf > t["hbf_elevated"],
        "hbf_review": eligible_age and hbf > t["hbf_review"],
        "hbe_present": hbe >= t["hbe_present"], "hbe_detected": hbe > 0,
        "of_pos": n["oft"] == "Positive", "dcip_pos": n["dcip"] == "Positive",
        "hbh_pos": n["hbh_inclusion"] == "Positive", "family": n["family_history"] is True,
        "rbc_not_high": n["rbc_10e12_l"] < t["rbc_high"],
        "mentzer_iron_like": d["mentzer_index"] >= t["mentzer_beta_like"],
        "alpha_variant": any(n[key] > 0 for key in ("bart_percent", "hbh_percent", "hbcs_percent")),
        "combined_present": math.isfinite(n["hba2e_percent"]),
        "hba2_within_trait_range": hba2 <= t["hba2_review_upper"],
        "hba2_very_high": eligible_age and hba2 > t["hba2_review_upper"], "transfusion": n["transfusion_recent"] is True,
    }
    scores = {key: round(clamp(sum(weight for name, weight in weights.items() if signals[name])), 1)
              for key, weights in config["scores"].items()}
    top_pattern, consult_score = msg["no_pattern"], max(scores.values())
    matched = sorted((rule for rule in config["rules"] if _matches(rule, signals)), key=lambda rule: rule["priority"], reverse=True)
    if errors:
        top_pattern, consult_score = msg["invalid_pattern"], np.nan
        scores = {key: np.nan for key in scores}
        # Invalid input cannot retain apparently normal classification flags.
        # The independent low-Hb alert above remains visible for review.
        micro = hypo = anemia = None
        recommendations.append(msg["invalid_recommendation"])
        risk = "Critical review" if severe else "Invalid / incomplete"
    else:
        context = {**n, **t}
        for name, flag in (("micro", micro), ("hypo", hypo), ("anemia", anemia), ("hba2_high", signals["hba2_high"]), ("hbf_high", signals["hbf_high"])):
            if flag:
                evidence.append(msg[name].format(**context))
        for rule in matched:
            rule_ids.append(rule["id"])
            evidence.extend(rule["evidence"])
            recommendations.extend(rule["tests"])
            counseling.extend(rule["counseling"])
            if eligible_age:
                genotypes.extend(rule["genotypes"])
            consult_score = max(consult_score, rule["score_floor"])
        if matched:
            top_pattern = matched[0]["pattern"]
        if signals["ferritin_low"]:
            caveats.append(msg["iron_caveat"])
        if signals["transfusion"]:
            recommendations.append(msg["transfusion"])
        risk = "Critical review" if severe else "High" if consult_score >= config["risk"]["high_score"] else "Moderate" if consult_score >= config["risk"]["moderate_score"] else "Low / inconclusive"
    if not evidence:
        evidence.append(top_pattern)
    if not recommendations:
        recommendations.append(msg["default_recommendation"])
    counseling.append(msg["default_counseling"])
    if not genotypes:
        genotypes.append(msg["unresolved_genotype"])
    unique = lambda values: list(dict.fromkeys(values))
    return ScreeningResult(
        sample_id=n["sample_id"], top_pattern=top_pattern, consult_risk=risk, consult_score=consult_score,
        **scores, severe_anemia_flag=severe, microcytosis=micro, hypochromia=hypo, anemia=anemia,
        evidence=unique(evidence), recommendations=unique(recommendations), caveats=unique(caveats),
        derived=d, normalized=n, validation_errors=errors, validation_warnings=warnings,
        counseling=unique(counseling), suspected_genotypes=unique(genotypes), rule_ids=rule_ids,
        ruleset_version=metadata["version"], ruleset_hash=digest,
        confidence_note=metadata["confidence_note_th"], thresholds_used={key: value if math.isfinite(value) else None for key, value in t.items()},
        ee_assessment={"applicable": False, "score": None, "interpretation": config["ee_score"]["interpretation"]},
        partner_screening=assess_partner_screening(n["oft"], n["dcip"], n["partner_oft"], n["partner_dcip"], rules=config),
        input_origin=input_origin if isinstance(input_origin, str) and input_origin in {"manual", "demo", "csv"} else "unknown",
        clinical_grouping=group_screening_findings(
            n, rule_ids, errors, severe=severe, anemia=anemia,
            microcytosis=micro, hypochromia=hypo,
        ),
    )


def analyze_dataframe(df: pd.DataFrame, thresholds: dict[str, float] | None = None,
                      *, input_origin: str = "unknown") -> pd.DataFrame:
    """Preserve input row order, including duplicate indices and invalid cases."""
    if len(df) > MAX_ROWS:
        raise ValueError(f"ประเมินได้ไม่เกิน {MAX_ROWS} แถวต่อครั้ง กรุณาแบ่งชุดข้อมูล")
    if df.columns.duplicated().any():
        raise ValueError("พบชื่อคอลัมน์ซ้ำ กรุณาแก้ไขก่อนประเมินชุดข้อมูล")
    config = load_rules()
    digest = _rules_digest(config)
    rows = []
    identifiers = df["sample_id"] if "sample_id" in df.columns else pd.Series(dtype=object)
    duplicates = set(identifiers.dropna().astype(str)[identifiers.dropna().astype(str).duplicated(keep=False)])
    for position, source in enumerate(df.to_dict(orient="records"), start=1):
        if is_missing(source.get("sample_id")):
            source["sample_id"] = f"CASE-{position:03d}"
        result = _analyze_screening(source, thresholds, config=config, digest=digest, input_origin=input_origin)
        if result.sample_id in duplicates:
            result.validation_warnings.append("รหัสตัวอย่างซ้ำในชุดข้อมูล กรุณาทบทวนการระบุแถวก่อนใช้หรือส่งออกรายงาน")
        rows.append(result.to_flat_dict())
    if not rows:
        return pd.DataFrame(columns=_analyze_screening({}, thresholds, config=config, digest=digest).to_flat_dict().keys())
    return pd.DataFrame(rows)
