from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from itertools import product
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd

from utils.csv_io import CSVInputError, MAX_ROWS, read_csv_table
from utils.build_provenance import capture_build_provenance

ALLELE_PANEL_PATH = Path(__file__).resolve().parents[1] / "data" / "allele_panel.json"


def load_allele_panel(path: str | Path = ALLELE_PANEL_PATH) -> dict[str, Any]:
    """Validate editable demonstration reference data; never read patient files."""
    try:
        panel = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        if not isinstance(panel, dict) or panel.get("status") != "demonstration":
            raise ValueError("invalid panel metadata")
        panel_id = panel.get("panel_id")
        if not isinstance(panel_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", panel_id):
            raise ValueError("invalid panel identifier")
        entries = panel.get("alleles")
        if not isinstance(entries, list) or not entries or len(entries) > 500:
            raise ValueError("invalid target list")
        fields = {"system", "target_code", "common_name", "gene", "variant_class", "hgvs", "method", "interpretation", "expected_bp", "clinical_weight"}
        text_fields = fields - {"expected_bp", "clinical_weight"}
        seen = set()
        clean_entries = []
        for entry in entries:
            if not isinstance(entry, dict) or not fields <= set(entry):
                raise ValueError("invalid target fields")
            if any(not isinstance(entry[field], str) or not entry[field].strip() for field in text_fields):
                raise ValueError("invalid target text")
            code = entry["target_code"]
            if not re.fullmatch(r"[A-Z0-9_]{1,40}", code) or code in seen or entry["system"] not in {"alpha", "beta"}:
                raise ValueError("invalid or duplicate target")
            seen.add(code)
            for field, upper in [("expected_bp", 10000), ("clinical_weight", 100)]:
                value = entry[field]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or not 0 < value <= upper:
                    raise ValueError("invalid target numeric value")
            clean_entries.append({field: entry[field] for field in ["system", "target_code", "common_name", "gene", "variant_class", "hgvs", "method", "expected_bp", "clinical_weight", "interpretation"]})
        return {"panel_id": panel_id, "status": "demonstration", "alleles": clean_entries}
    except (OSError, UnicodeError, ValueError, TypeError):
        raise ValueError("ไฟล์ฐานข้อมูล allele panel ไม่ผ่านการตรวจสอบ กรุณาทบทวนรหัสเป้าหมายที่ไม่ซ้ำ ระบบ globin และขนาดแถบสาธิตก่อนใช้งาน") from None


_PANEL = load_allele_panel()
PANEL_ID = _PANEL["panel_id"]
ALLELES = _PANEL["alleles"]


def allele_dataframe() -> pd.DataFrame:
    return pd.DataFrame(ALLELES).copy()

def pcr_template() -> pd.DataFrame:
    return pd.DataFrame([
        {"sample_id":"PARENT-A","target_code":"SEA_DEL","observed_bp":728,"result":"Positive","lane":"A1"},
        {"sample_id":"PARENT-A","target_code":"A37_DEL","observed_bp":"","result":"Negative","lane":"A2"},
        {"sample_id":"PARENT-A","target_code":"CS","observed_bp":"","result":"Negative","lane":"A3"},
        {"sample_id":"PARENT-A","target_code":"HBE","observed_bp":399,"result":"Positive","lane":"B1"},
        {"sample_id":"PARENT-B","target_code":"SEA_DEL","observed_bp":"","result":"Negative","lane":"A4"},
        {"sample_id":"PARENT-B","target_code":"A37_DEL","observed_bp":2026,"result":"Positive","lane":"A5"},
        {"sample_id":"PARENT-B","target_code":"CD41_42","observed_bp":302,"result":"Positive","lane":"B2"},
        {"sample_id":"PARENT-B","target_code":"HBE","observed_bp":"","result":"Negative","lane":"B3"},
    ])

PCR_INPUT_COLUMNS = ["sample_id", "target_code", "observed_bp", "result", "lane"]


def read_pcr_csv(payload: bytes) -> tuple[pd.DataFrame, list[str]]:
    """Validate every CSV column before selecting fields and replacing identities."""
    frame, notes = read_csv_table(
        payload, PCR_INPUT_COLUMNS, required_columns=("sample_id", "target_code"),
    )
    work = prepare_pcr_calls(frame, pseudonymize=True)
    notes.append("แทนรหัสตัวอย่างเดิมและช่องแถบในหน่วยความจำแล้ว ผลที่ไม่รู้จักคงสถานะไม่ทราบ")
    return work, notes


def _to_float(value: Any) -> float:
    try:
        number = float(value)
        return number if np.isfinite(number) else np.nan
    except Exception:
        return np.nan

def normalize_pcr_call(value: Any) -> str:
    """Keep an unavailable or unrecognized qualitative call unresolved."""
    token = str(value).strip().lower()
    if token in {"positive", "pos", "+", "detected", "present", "yes", "y", "true", "1", "1.0", "บวก"}:
        return "Positive"
    if token in {"negative", "neg", "-", "not detected", "absent", "no", "n", "false", "0", "0.0", "ลบ"}:
        return "Negative"
    return "Unknown"


def prepare_pcr_calls(pcr_df: pd.DataFrame, pseudonymize: bool = False) -> pd.DataFrame:
    """Whitelist input fields and optionally replace imported identifiers in memory."""
    if pcr_df.columns.duplicated().any():
        raise CSVInputError("พบชื่อคอลัมน์ PCR ซ้ำ กรุณาเลือกผลต้นฉบับเพียงหนึ่งคอลัมน์")
    if len(pcr_df) > MAX_ROWS:
        raise CSVInputError("ประเมินได้ไม่เกิน 200 แถวต่อครั้ง กรุณาแบ่งไฟล์")
    missing = {"sample_id", "target_code"} - set(pcr_df.columns)
    if missing:
        raise ValueError("ตาราง PCR ต้องมีคอลัมน์ sample_id และ target_code")
    work = pcr_df.reindex(columns=PCR_INPUT_COLUMNS).copy()
    work["result"] = work["result"].map(normalize_pcr_call)
    def valid_band_size(value: Any) -> float:
        if value is None or pd.isna(value) or (isinstance(value, str) and not value.strip()):
            return np.nan
        number = _to_float(value)
        if np.isnan(number) or number <= 0 or number > 10000:
            raise ValueError("ขนาดแถบต้องเป็นตัวเลขมากกว่า 0 ถึง 10000 bp หรือเว้นว่างเมื่อไม่มีข้อมูล")
        return number

    work["observed_bp"] = work["observed_bp"].map(valid_band_size)
    work["target_code"] = work["target_code"].fillna("").astype(str).str.strip().str.upper()
    if pseudonymize:
        identifiers = work["sample_id"].fillna("").astype(str).str.strip()
        identifiers = pd.Series([("present", value) if value else ("missing", i)
                                 for i, value in enumerate(identifiers)], index=work.index)
        mapping = {value: f"PCR-{i+1:03d}" for i, value in enumerate(identifiers.unique())}
        work["sample_id"] = identifiers.map(mapping)
        known_targets = set(allele_dataframe()["target_code"])
        work.loc[~work["target_code"].isin(known_targets), "target_code"] = "UNKNOWN"
        work["lane"] = [f"L{i+1}" for i in range(len(work))]
    else:
        work["sample_id"] = work["sample_id"].fillna("").astype(str)
        work["lane"] = [f"L{i+1}" if pd.isna(value) or not str(value).strip() else str(value)
                        for i, value in enumerate(work["lane"])]
    return work


def match_pcr_bands(
    pcr_df: pd.DataFrame,
    tolerance_bp: float = 25,
    controls_status: str = "not_confirmed",
) -> pd.DataFrame:
    """Compare a demonstration panel with calls after explicit run-control review.

    ``confidence`` is retained for legacy chart compatibility. It is a band-size
    similarity on a 0–1 scale, never a probability or diagnostic confidence.
    An unresolved call has detected=False and must be interpreted using call/status.
    """
    tolerance = _to_float(tolerance_bp)
    if np.isnan(tolerance) or tolerance <= 0:
        raise ValueError("ค่าความคลาดเคลื่อนขนาดแถบต้องเป็นจำนวนบวกที่มีค่าจำกัด")
    if controls_status not in {"not_confirmed", "pass", "fail"}:
        raise ValueError("สถานะ controls ต้องเป็น not_confirmed, pass หรือ fail")
    work = prepare_pcr_calls(pcr_df)
    # The reference and its fingerprint describe the exact evaluated snapshot,
    # even if the editable panel file changes before a report is downloaded.
    panel = {"panel_id": PANEL_ID, "status": "demonstration", "alleles": deepcopy(ALLELES)}
    panel_hash = sha256(json.dumps(panel, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
    evaluated_at = datetime.now(timezone(timedelta(hours=7))).isoformat(timespec="seconds")
    reference = pd.DataFrame(panel["alleles"])
    db = reference.set_index("target_code")
    out = []
    for _, record in work.iterrows():
        row = record.to_dict()
        code = row["target_code"]
        observed = _to_float(row["observed_bp"])
        operator_call = row["result"]
        known = code in db.index
        if known:
            row.update(db.loc[code].to_dict())
        else:
            row.update({"expected_bp": np.nan, "common_name": "เป้าหมายที่ไม่อยู่ในชุดตรวจ",
                        "system": "unknown", "variant_class": "unknown"})
        expected = _to_float(row["expected_bp"])
        valid_band = np.isfinite(observed) and observed > 0
        delta = abs(observed - expected) if valid_band and known else np.nan
        band_match = bool(np.isfinite(delta) and delta <= tolerance)
        score = max(0.0, 1.0 - delta / tolerance) if np.isfinite(delta) else 0.0
        call, status = "unresolved", "Unresolved: qualitative call unavailable"
        note = "ผลเชิงคุณภาพขาดหายหรือไม่รู้จัก ต้องทบทวนก่อนแปลผล"
        if not known:
            status, note = "Unresolved: unknown target", "ไม่พบรหัสเป้าหมายในฐานข้อมูลชุดตรวจสาธิต"
        elif np.isfinite(observed) and observed <= 0:
            status, note = "Needs review: invalid band size", "ขนาดแถบต้องมากกว่า 0 bp หรือเว้นว่างเมื่อไม่มีข้อมูล"
        elif operator_call == "Negative" and band_match:
            status, note = "Needs review: negative call with matched band", "ผู้ตรวจระบุผลลบ แต่ขนาดแถบตรงเป้าหมาย ต้องทบทวนความขัดแย้ง"
        elif operator_call == "Positive" and valid_band and not band_match:
            status, note = "Needs review: positive call with mismatched band", "ผู้ตรวจระบุผลบวก แต่ขนาดแถบอยู่นอกช่วงที่กำหนด ต้องทบทวน"
        elif operator_call == "Positive" and not valid_band:
            status, note = "Unresolved: positive call without band size", "ผลบวกยังไม่มีขนาดแถบที่ใช้ตรวจสอบ ต้องทบทวนหลักฐาน"
        elif operator_call == "Positive" and band_match:
            call, status = "detected", "Detected: band-size matched"
            note = "ผลผู้ตรวจและขนาดแถบสอดคล้องกับเป้าหมายสาธิต ไม่ยืนยัน genotype หรือการวินิจฉัย"
        elif operator_call == "Negative":
            call, status = "not_detected", "Not detected in selected assay"
            note = "ผู้ตรวจระบุผลลบและไม่มีแถบตรงเป้าหมาย ไม่ตัดความเป็นไปได้ของ variant นอกชุดตรวจ"
        evidence_status = {"Detected: band-size matched": "Evidence: positive call and band agree",
                           "Not detected in selected assay": "Evidence: negative call without target band"}.get(status, status)
        if controls_status != "pass":
            call, status = "unresolved", "Unresolved: run controls not passed"
            note = "ระงับการแปลผล: controls ของ run ยังไม่ยืนยันผ่านหรือไม่ผ่าน"
        row.update({"match_status": status, "evidence_status": evidence_status,
                    "controls_status": controls_status, "call": call,
                    "confidence": round(float(score), 3), "match_score": round(float(score) * 100, 1),
                    "delta_bp": round(float(delta), 1) if np.isfinite(delta) else np.nan,
                    "detected": call == "detected", "interpretation": note})
        out.append(row)
    columns = list(dict.fromkeys(PCR_INPUT_COLUMNS + list(reference.columns) + [
        "match_status", "evidence_status", "controls_status", "call", "confidence", "match_score",
        "delta_bp", "detected", "interpretation"]))
    result = pd.DataFrame(out, columns=columns)
    result.attrs["evaluation"] = {
        "panel_id": panel["panel_id"], "panel_sha256": panel_hash,
        "build_provenance": capture_build_provenance(),
        "evaluated_at": evaluated_at, "controls_status": controls_status,
        "tolerance_bp": float(tolerance),
    }
    return result

ALPHA_GENOTYPES = {"αα/αα — อ้างอิง":["αα","αα"],"-α/αα — พาหะแฝง":["-α","αα"],"-α/-α — α+ trait":["-α","-α"],"--SEA/αα — α0 trait":["--SEA","αα"],"--THAI/αα — α0 trait":["--THAI","αα"],"--SEA/-α — genotype ที่สัมพันธ์กับ HbH":["--SEA","-α"],"αCSα/αα — พาหะ Constant Spring":["αCSα","αα"],"--SEA/αCSα — genotype ที่สัมพันธ์กับ HbH-CS":["--SEA","αCSα"]}
BETA_GENOTYPES = {"βA/βA — อ้างอิง":["βA","βA"],"βA/βE — พาหะ HbE":["βA","βE"],"βA/β0 — พาหะ β-thal":["βA","β0"],"βA/β+ — พาหะ β-thal":["βA","β+"],"βE/βE — homozygous HbE":["βE","βE"],"β0/βE — HbE/β0-thalassemia":["β0","βE"],"β+/βE — HbE/β+-thalassemia":["β+","βE"],"β0/β0 — ความเสี่ยง β-thalassemia":["β0","β0"],"β+/β+ — ความเสี่ยง β-thalassemia ที่มีความรุนแรงแปรผัน":["β+","β+"]}

def _alpha_loss(hap: str) -> int:
    if hap == "αα": return 0
    if hap in {"-α","αCSα"}: return 1
    if hap.startswith("--"): return 2
    return 0

def classify_alpha(h1: str, h2: str) -> tuple[str, str, int]:
    loss = _alpha_loss(h1) + _alpha_loss(h2); nondeletional = "CS" in h1 or "CS" in h2
    if loss >= 4: return "ความเสี่ยง phenotype Hb Bart hydrops fetalis", "critical", loss
    if loss == 3 and nondeletional: return "ความเสี่ยง phenotype HbH / HbH-Constant Spring", "high", loss
    if loss == 3: return "ความเสี่ยง phenotype HbH", "high", loss
    if loss == 2 and nondeletional: return "ความเสี่ยง phenotype nondeletional α-thalassemia; ความรุนแรงแปรผัน", "moderate", loss
    if loss == 2: return "รูปแบบ genotype ที่สัมพันธ์กับ α-thalassemia trait", "moderate", loss
    if loss == 1: return "รูปแบบพาหะ α-thalassemia ในแบบจำลอง", "low", loss
    return "ไม่พบ allele ผิดปกติในแบบจำลอง α ที่เลือก", "minimal", loss

def classify_beta(a1: str, a2: str) -> tuple[str, str]:
    alleles = sorted([a1, a2]); s = set(alleles)
    if s in [{"β0"}, {"β0", "βE"}]: return "ความเสี่ยง phenotype β-thalassemia / HbE-β-thalassemia; ความรุนแรงแปรผัน", "critical"
    if s in [{"β+", "βE"}, {"β+", "β0"}, {"β+"}]: return "ความเสี่ยง phenotype β-thalassemia / HbE-β-thalassemia; ต้องประเมินเพิ่มเติม", "high"
    if alleles == ["βE", "βE"]: return "รูปแบบ genotype homozygous HbE ในแบบจำลอง", "moderate"
    if "β0" in alleles or "β+" in alleles or "βE" in alleles: return "รูปแบบพาหะ / β-globin variant ในแบบจำลอง", "low"
    return "ไม่พบ allele ผิดปกติในแบบจำลอง β ที่เลือก", "minimal"

def punnett(parent1: list[str], parent2: list[str], system: str) -> pd.DataFrame:
    if system not in {"alpha", "beta"}:
        raise ValueError("ระบบ globin ต้องเป็น alpha หรือ beta")
    if len(parent1) != 2 or len(parent2) != 2:
        raise ValueError("แบบจำลองต้องมี 2 alleles/haplotypes ต่อบุคคล")
    allowed = {allele for pair in (ALPHA_GENOTYPES if system == "alpha" else BETA_GENOTYPES).values() for allele in pair}
    if any(allele not in allowed for allele in parent1 + parent2):
        raise ValueError("พบ allele ที่แบบจำลองยังไม่รองรับ")
    rows = []
    for g1, g2 in product(parent1, parent2):
        genotype = "/".join(sorted([g1, g2]))
        if system == "alpha":
            phenotype, severity, burden = classify_alpha(g1, g2); rows.append({"parent1_gamete":g1,"parent2_gamete":g2,"offspring_genotype":genotype,"phenotype":phenotype,"severity":severity,"allele_burden":burden,"probability":25.0})
        else:
            phenotype, severity = classify_beta(g1, g2); rows.append({"parent1_gamete":g1,"parent2_gamete":g2,"offspring_genotype":genotype,"phenotype":phenotype,"severity":severity,"allele_burden":np.nan,"probability":25.0})
    df = pd.DataFrame(rows)
    return df.groupby(["offspring_genotype", "phenotype", "severity", "allele_burden"], dropna=False, as_index=False).agg(
        probability=("probability", "sum"),
        parent1_gamete=("parent1_gamete", lambda values: " / ".join(sorted(set(values)))),
        parent2_gamete=("parent2_gamete", lambda values: " / ".join(sorted(set(values)))),
    )

def summarize_risk(punnett_df: pd.DataFrame) -> dict[str, float]:
    return {str(r["severity"]): float(r["probability"]) for _, r in punnett_df.groupby("severity", as_index=False)["probability"].sum().iterrows()}
