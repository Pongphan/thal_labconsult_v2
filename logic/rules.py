"""Load a reviewable, declarative ruleset without evaluating executable expressions."""
from __future__ import annotations

import json
import math
import string
from pathlib import Path
from typing import Any

RULES_PATH = Path(__file__).resolve().parents[1] / "data" / "clinical_rules.json"
SIGNALS = frozenset({
    "micro", "hypo", "high_rbc", "mentzer_beta_like", "rdw_high", "ferritin_low",
    "ferritin_border_only", "hba2_high", "hba2_not_high", "hbf_high", "hbf_review",
    "hbe_present", "hbe_detected", "of_pos", "dcip_pos", "hbh_pos", "family",
    "rbc_not_high", "mentzer_iron_like", "alpha_variant", "combined_present",
    "hba2_within_trait_range", "hba2_very_high", "transfusion", "eligible_age", "infant",
})


def _require(condition: bool, message: str = "invalid ruleset") -> None:
    if not condition:
        raise ValueError(message)


def _number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in values, "duplicate JSON key")
        values[key] = value
    return values


def _reject_constant(value: str) -> None:
    raise ValueError("non-finite JSON number")


def load_rules(path: Path | str | None = None) -> dict[str, Any]:
    """Reject malformed rulesets; do not silently fall back to a different SOP."""
    try:
        config = json.loads(Path(path or RULES_PATH).read_text(encoding="utf-8-sig"),
                            object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)
        _require(isinstance(config, dict))
        for section in ("metadata", "thresholds", "age_thresholds", "adult_thresholds",
                        "validation", "scores", "risk", "messages", "ee_score", "partner_screening"):
            _require(isinstance(config[section], dict), section)
        for key in ("version", "status", "description_th", "disclaimer_th", "confidence_note_th"):
            _require(isinstance(config['metadata'][key], str) and config['metadata'][key], key)
        _require(isinstance(config['metadata']['sources'], list) and bool(config['metadata']['sources']), 'sources')
        for source in config['metadata']['sources']:
            _require(isinstance(source['title'], str) and source['title'])
            _require(isinstance(source['url'], str) and source['url'].startswith('https://'))
        thresholds = config["thresholds"]
        required = {"mcv_microcytosis", "mch_hypochromia", "hba2_beta_trait", "hbf_elevated",
                    "hbf_review", "hbe_present", "ferritin_deficient", "ferritin_borderline",
                    "rbc_high", "mentzer_beta_like", "rdw_high", "severe_hb", "hba2_review_upper",
                    "hb_fraction_min_age_years"}
        _require(required == thresholds.keys(), 'thresholds')
        _require(all((type(v) in (int, float) and math.isfinite(v) and (v > 0) for v in thresholds.values())), 'invalid ruleset')
        _require(thresholds['ferritin_deficient'] < thresholds['ferritin_borderline'], 'invalid ruleset')
        _require(thresholds['hba2_beta_trait'] < thresholds['hba2_review_upper'])
        _require(thresholds['hbf_elevated'] < thresholds['hbf_review'])
        numeric_fields = {'age', 'hb_g_dl', 'rbc_10e12_l', 'hct_percent', 'mcv_fl', 'mch_pg',
                          'mchc_g_dl', 'rdw_percent', 'retic_percent', 'ferritin_ng_ml',
                          'hba_percent', 'hba2_percent', 'hba2e_percent', 'hbf_percent',
                          'hbe_percent', 'bart_percent', 'hbh_percent', 'hbcs_percent'}
        _require(set(config['validation']['ranges']) == numeric_fields)
        for bounds in config["validation"]["ranges"].values():
            _require(isinstance(bounds, list) and len(bounds) == 3, 'invalid bounds')
            _require(all(_number(v) for v in bounds[:2]), 'invalid bounds')
            _require(bounds[0] < bounds[1] and isinstance(bounds[2], str) and bool(bounds[2].strip()), 'invalid bounds')
        _require(isinstance(config['validation']['required'], list))
        _require(set(config['validation']['required']) <= config['validation']['ranges'].keys(), 'invalid ruleset')
        _require(_number(config['validation']['fraction_sum_max']) and 100 <= config['validation']['fraction_sum_max'] <= 110, 'invalid ruleset')
        for field in ("mcv_fl", "mch_pg", "hb_g_dl", "hct_percent"):
            rows = config["age_thresholds"][field]
            _require(isinstance(rows, list) and bool(rows), 'invalid age thresholds')
            _require(all(isinstance(r, list) and len(r) == 2 and all(_number(v) and v > 0 for v in r) for r in rows), 'invalid age thresholds')
            _require(all((a[0] < b[0] for a, b in zip(rows, rows[1:]))), 'invalid ruleset')
        for field in ("hb_g_dl", "hct_percent"):
            _require(all(_number(config['adult_thresholds'][field][k]) and config['adult_thresholds'][field][k] > 0
                         for k in ('male', 'female', 'pregnant')))
        _require(set(config['scores']) == {'beta_trait_score', 'alpha_trait_score', 'hbe_score', 'iron_deficiency_score'}, 'invalid ruleset')
        for weights in config["scores"].values():
            _require(set(weights) <= SIGNALS, 'invalid ruleset')
            _require(all((type(v) in (int, float) and math.isfinite(v) for v in weights.values())), 'invalid ruleset')
        _require(all(_number(config['risk'][key]) for key in ('moderate_score', 'high_score')), 'invalid risk scores')
        _require(0 <= config['risk']['moderate_score'] <= config['risk']['high_score'] <= 100, 'invalid ruleset')
        _require(all((isinstance(v, str) for v in config['messages'].values())), 'invalid ruleset')
        required_messages = {'no_pattern', 'invalid_pattern', 'urgent', 'micro', 'hypo', 'anemia',
                             'hba2_high', 'hbf_high', 'combined', 'resolved_and_combined', 'transfusion', 'iron_caveat',
                             'age_caveat', 'default_recommendation', 'default_counseling',
                             'invalid_recommendation', 'unresolved_genotype'}
        _require(required_messages <= config['messages'].keys())
        for message in config['messages'].values():
            for _, name, spec, conversion in string.Formatter().parse(message):
                _require(name is None or (name in numeric_fields | required and spec in {'', 'g'} and conversion is None))
        _require(config['ee_score']['applicable'] is False, 'EE model has no validated protocol')
        _require(isinstance(config['ee_score']['interpretation'], str))
        for key in ('incomplete', 'both_positive', 'one_positive', 'negative'):
            _require(isinstance(config['partner_screening'][key], str))
        _require(isinstance(config['partner_screening']['recommendations'], list))
        _require(all(isinstance(v, str) for v in config['partner_screening']['recommendations']))
        _require(isinstance(config['rules'], list) and bool(config['rules']))
        rule_ids = set()
        for rule in config["rules"]:
            _require(isinstance(rule['id'], str) and rule['id'] not in rule_ids, 'invalid ruleset')
            rule_ids.add(rule["id"])
            _require(isinstance(rule['pattern'], str) and rule['pattern'], 'invalid ruleset')
            _require(type(rule['priority']) is int and _number(rule['score_floor']) and 0 <= rule['score_floor'] <= 100, 'invalid ruleset')
            _require(any((rule.get(k) for k in ('all', 'any'))), 'empty condition')
            for key in ("all", "any", "none"):
                _require(isinstance(rule.get(key, []), list) and set(rule.get(key, [])) <= SIGNALS, 'invalid ruleset')
            for key in ("evidence", "tests", "genotypes", "counseling"):
                _require(isinstance(rule[key], list) and all((isinstance(v, str) for v in rule[key])), 'invalid ruleset')
        json.dumps(config, ensure_ascii=False, allow_nan=False)
        return config
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError, OverflowError) as exc:
        raise ValueError("ไฟล์กฎไม่ผ่านการตรวจสอบ โครงสร้างหรือค่ากฎไม่ถูกต้อง กรุณาให้ผู้ดูแลทบทวนก่อนใช้งาน") from exc
