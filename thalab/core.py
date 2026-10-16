"""Backward-compatible imports; clinical logic now lives in logic."""
from logic.engine import (
    DEFAULT_THRESHOLDS, ScreeningResult, analyze_dataframe, analyze_screening,
    anemia_threshold, assess_partner_screening, clamp, derived_indices, hct_threshold,
    mch_threshold, mcv_threshold,
)
from logic.examples import example_screening_dataframe
from logic.validation import (
    SCREENING_COLUMNS, ValidationResult, is_missing, normalize_call, safe_num,
    validate_screening, yn,
)

__all__ = [
    "DEFAULT_THRESHOLDS", "SCREENING_COLUMNS", "ScreeningResult", "ValidationResult",
    "analyze_dataframe", "analyze_screening", "anemia_threshold", "assess_partner_screening",
    "clamp", "derived_indices", "example_screening_dataframe", "hct_threshold",
    "is_missing", "mch_threshold", "mcv_threshold", "normalize_call", "safe_num",
    "validate_screening", "yn",
]
