from __future__ import annotations

import numpy as np
import pandas as pd

from .core import derived_indices, is_missing, safe_num

ML_FEATURE_COLUMNS = [
    "hb_g_dl",
    "rbc_10e12_l",
    "mcv_fl",
    "mch_pg",
    "rdw_percent",
    "ferritin_ng_ml",
    "hba2_percent",
    "hbf_percent",
    "hbe_percent",
    "mentzer_index",
]

# Interpretable laboratory prototypes. These are not a substitute for a locally
# trained classifier; they provide a safe ML-shaped baseline for UI validation,
# feature export, and later replacement by a fitted model.
PHENOTYPE_PROTOTYPES = {
    "คล้ายรูปแบบ β-thalassemia trait": {
        "hb_g_dl": 11.5,
        "rbc_10e12_l": 5.6,
        "mcv_fl": 67.0,
        "mch_pg": 21.0,
        "rdw_percent": 14.0,
        "ferritin_ng_ml": 80.0,
        "hba2_percent": 5.0,
        "hbf_percent": 1.2,
        "hbe_percent": 0.0,
        "mentzer_index": 12.0,
    },
    "คล้ายรูปแบบพาหะ α-thalassemia": {
        "hb_g_dl": 12.0,
        "rbc_10e12_l": 5.5,
        "mcv_fl": 70.0,
        "mch_pg": 22.0,
        "rdw_percent": 13.5,
        "ferritin_ng_ml": 90.0,
        "hba2_percent": 2.5,
        "hbf_percent": 0.6,
        "hbe_percent": 0.0,
        "mentzer_index": 12.8,
    },
    "คล้ายรูปแบบ HbE / structural variant": {
        "hb_g_dl": 12.0,
        "rbc_10e12_l": 5.2,
        "mcv_fl": 74.0,
        "mch_pg": 23.0,
        "rdw_percent": 14.0,
        "ferritin_ng_ml": 80.0,
        "hba2_percent": 3.8,
        "hbf_percent": 0.8,
        "hbe_percent": 24.0,
        "mentzer_index": 14.0,
    },
    "คล้ายรูปแบบภาวะขาดธาตุเหล็ก": {
        "hb_g_dl": 9.8,
        "rbc_10e12_l": 4.2,
        "mcv_fl": 72.0,
        "mch_pg": 22.0,
        "rdw_percent": 18.5,
        "ferritin_ng_ml": 8.0,
        "hba2_percent": 2.5,
        "hbf_percent": 0.4,
        "hbe_percent": 0.0,
        "mentzer_index": 17.0,
    },
    "คล้ายรูปแบบอ้างอิงทั่วไป": {
        "hb_g_dl": 13.5,
        "rbc_10e12_l": 4.8,
        "mcv_fl": 88.0,
        "mch_pg": 29.0,
        "rdw_percent": 13.0,
        "ferritin_ng_ml": 75.0,
        "hba2_percent": 2.7,
        "hbf_percent": 0.5,
        "hbe_percent": 0.0,
        "mentzer_index": 18.0,
    },
}

_FEATURE_SCALE = {
    "hb_g_dl": 2.5,
    "rbc_10e12_l": 1.1,
    "mcv_fl": 12.0,
    "mch_pg": 4.0,
    "rdw_percent": 4.0,
    "ferritin_ng_ml": 60.0,
    "hba2_percent": 2.0,
    "hbf_percent": 2.0,
    "hbe_percent": 14.0,
    "mentzer_index": 5.0,
}


def _first_num(row: pd.Series, names: list[str]) -> float:
    for name in names:
        if name in row.index:
            value = safe_num(row.get(name))
            if not np.isnan(value):
                return value
    return np.nan


def ml_feature_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Return a clean, explicit feature table for downstream ML deployment."""
    rows: list[dict[str, float | str]] = []
    for _, row in df.iterrows():
        sample_id = row.get("sample_id", "")
        record: dict[str, float | str] = {
            "sample_id": str(sample_id) if not is_missing(sample_id) else f"CASE-{len(rows)+1:03d}"
        }
        record["hb_g_dl"] = _first_num(row, ["hb_g_dl", "Hb", "hb"])
        record["rbc_10e12_l"] = _first_num(row, ["rbc_10e12_l", "RBC", "rbc"])
        record["mcv_fl"] = _first_num(row, ["mcv_fl", "MCV", "mcv"])
        record["mch_pg"] = _first_num(row, ["mch_pg", "MCH", "mch"])
        record["rdw_percent"] = _first_num(row, ["rdw_percent", "RDW", "rdw"])
        record["ferritin_ng_ml"] = _first_num(row, ["ferritin_ng_ml", "Ferritin", "ferritin"])
        record["hba2_percent"] = _first_num(row, ["hba2_percent", "HbA2", "hba2"])
        record["hbf_percent"] = _first_num(row, ["hbf_percent", "HbF", "hbf"])
        record["hbe_percent"] = _first_num(row, ["hbe_percent", "HbE", "hbe"])
        derived = derived_indices(record)
        record["mentzer_index"] = derived.get("mentzer_index", np.nan)
        rows.append(record)
    return pd.DataFrame(rows, columns=["sample_id", *ML_FEATURE_COLUMNS])


def phenotype_similarity(df: pd.DataFrame) -> pd.DataFrame:
    """Prototype-based phenotype similarity for demo ML workflows.

    The returned score is a similarity measure from 0 to 100, not a calibrated
    probability. Replace this function with a locally trained and validated model
    when molecular-confirmed labels are available.
    """
    features = ml_feature_matrix(df)
    out_rows: list[dict[str, float | str]] = []
    for _, row in features.iterrows():
        available = sum(np.isfinite(safe_num(row.get(col))) for col in ML_FEATURE_COLUMNS)
        if available < 5:
            out_rows.append({"sample_id": row["sample_id"], "ml_prototype_pattern": "ข้อมูลไม่เพียงพอสำหรับเปรียบเทียบ",
                             "ml_similarity_score": np.nan, "ml_runner_up": "", "ml_runner_up_score": np.nan,
                             "ml_note": "ต้องมีอย่างน้อย 5 คุณลักษณะ การเปรียบเทียบนี้เป็นเครื่องมือทดลอง ไม่ใช่การวินิจฉัย"})
            continue
        distances: dict[str, float] = {}
        for label, proto in PHENOTYPE_PROTOTYPES.items():
            parts = []
            for col in ML_FEATURE_COLUMNS:
                value = safe_num(row.get(col))
                if np.isnan(value):
                    continue
                parts.append(((value - proto[col]) / _FEATURE_SCALE[col]) ** 2)
            distances[label] = float(np.sqrt(np.mean(parts))) if parts else np.inf
        best_label = min(distances, key=distances.get)
        best_distance = distances[best_label]
        similarity = 0.0 if not np.isfinite(best_distance) else 100.0 / (1.0 + best_distance)
        sorted_labels = sorted(distances, key=distances.get)
        second_label = sorted_labels[1] if len(sorted_labels) > 1 else ""
        second_similarity = 0.0 if not second_label or not np.isfinite(distances[second_label]) else 100.0 / (1.0 + distances[second_label])
        out_rows.append(
            {
                "sample_id": row["sample_id"],
                "ml_prototype_pattern": best_label,
                "ml_similarity_score": round(similarity, 1),
                "ml_runner_up": second_label,
                "ml_runner_up_score": round(second_similarity, 1),
                "ml_note": "ความคล้ายคลึงกับข้อมูลสมมติเท่านั้น ไม่ใช่ความน่าจะเป็นหรือผลวินิจฉัย",
            }
        )
    return pd.DataFrame(out_rows, columns=["sample_id", "ml_prototype_pattern", "ml_similarity_score",
                                          "ml_runner_up", "ml_runner_up_score", "ml_note"])
