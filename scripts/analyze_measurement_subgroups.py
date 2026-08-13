"""Run prespecified, outcome-blind subgroup analyses of CCD prevalence.

All estimands are equal-person weighted.  Subgroup contrasts are risk
differences versus a named reference level and use patient-level bootstrap
resampling.  They characterize heterogeneity; they do not identify a true
measurement modality or a causal effect.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRIVATE_ROOT = PROJECT_ROOT / "analysis" / "private"
RESULTS_ROOT = PROJECT_ROOT / "results"
TABLES_ROOT = PROJECT_ROOT / "tables"
SEED = 20260812
REPLICATES = 2_000

SOURCE_FILES = {
    "sicdb": "sicdb_primary_pairs_v1.parquet",
    "mimic_iv": "mimic_iv_primary_pairs_v1.parquet",
    "eicu": "eicu_primary_pairs_v1.parquet",
}


def percentile_interval(values: np.ndarray) -> tuple[float, float]:
    return tuple(float(x) for x in np.quantile(values, [0.025, 0.975]))


def bootstrap_group_mean(
    values: np.ndarray, rng: np.random.Generator
) -> tuple[float, float, float, np.ndarray]:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) < 2:
        return float(np.mean(values)), float("nan"), float("nan"), np.full(REPLICATES, np.nan)
    draws = np.empty(REPLICATES, dtype=float)
    for start in range(0, REPLICATES, 200):
        count = min(200, REPLICATES - start)
        idx = rng.integers(0, len(values), size=(count, len(values)))
        draws[start : start + count] = values[idx].mean(axis=1)
    low, high = percentile_interval(draws)
    return float(values.mean()), low, high, draws


def add_age_group(frame: pd.DataFrame) -> None:
    frame["age_group"] = pd.cut(
        frame["age"],
        bins=[18, 45, 65, 80, np.inf],
        right=False,
        labels=["18-44", "45-64", "65-79", ">=80"],
    ).astype("object")


def normalize_sex(source: str, values: pd.Series) -> pd.Series:
    if source == "sicdb":
        return values.map({735: "Male", 736: "Female", 737: "Unknown"}).fillna("Unknown")
    if source == "mimic_iv":
        return values.map({"M": "Male", "F": "Female"}).fillna("Unknown")
    return values.where(values.isin(["Male", "Female"]), "Unknown")


def patient_table(source: str, frame: pd.DataFrame) -> pd.DataFrame:
    metadata = ["age", "sex"]
    if source == "sicdb":
        metadata += ["saps3", "sepsis_at_admission", "admission_urgency"]
    conflict = frame.groupby("person_key_hash", observed=True)[metadata].nunique(dropna=False).max()
    if (conflict > 1).any():
        raise AssertionError(f"{source}: patient metadata changes within person: {conflict.to_dict()}")
    people = (
        frame.groupby("person_key_hash", observed=True)
        .agg(ccd_fraction=("ccd", "mean"), n_pairs=("ccd", "size"), **{c: (c, "first") for c in metadata})
        .reset_index()
    )
    people["sex_group"] = normalize_sex(source, people["sex"])
    add_age_group(people)
    if source == "sicdb":
        people["sepsis_group"] = people["sepsis_at_admission"].map(
            {738: "No", 739: "Unknown", 740: "Yes"}
        ).fillna("Unknown")
        people["urgency_group"] = people["admission_urgency"].map(
            {3136: "Unknown", 3137: "Urgent", 3138: "Elective"}
        ).fillna("Unknown")
        valid_saps = people["saps3"].dropna().astype(float)
        edges = np.unique(np.quantile(valid_saps, [0, 0.25, 0.5, 0.75, 1]))
        if len(edges) != 5:
            raise AssertionError("SICdb SAPS 3 quartile boundaries are not unique")
        edges[0] = -np.inf
        edges[-1] = np.inf
        people["saps3_quartile"] = pd.cut(
            people["saps3"], edges, include_lowest=True, labels=["Q1", "Q2", "Q3", "Q4"]
        ).astype("object")
        people.attrs["saps3_edges"] = [float(x) if np.isfinite(x) else str(x) for x in edges]
    return people


def bh_adjust(p_values: list[float]) -> list[float]:
    values = np.asarray(p_values, dtype=float)
    finite = np.isfinite(values)
    result = np.full_like(values, np.nan)
    if not finite.any():
        return result.tolist()
    p = values[finite]
    order = np.argsort(p)
    ranked = p[order]
    adjusted = ranked * len(ranked) / np.arange(1, len(ranked) + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    restored = np.empty_like(adjusted)
    restored[order] = np.minimum(adjusted, 1.0)
    result[finite] = restored
    return result.tolist()


def contrast_p_value(draws: np.ndarray) -> float:
    draws = draws[np.isfinite(draws)]
    if not len(draws):
        return float("nan")
    return float(min(1.0, 2 * min(np.mean(draws <= 0), np.mean(draws >= 0))))


def categorical_family(
    source: str,
    people: pd.DataFrame,
    variable: str,
    levels: list[str],
    reference: str,
    rng: np.random.Generator,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    draws_by_level: dict[str, np.ndarray] = {}
    for level in levels:
        values = people.loc[people[variable] == level, "ccd_fraction"].to_numpy(float)
        if not len(values):
            continue
        estimate, low, high, draws = bootstrap_group_mean(values, rng)
        draws_by_level[level] = draws
        rows.append(
            {
                "source": source,
                "family": variable,
                "level": level,
                "reference": reference,
                "people": int(len(values)),
                "estimate": estimate,
                "ci_low": low,
                "ci_high": high,
                "contrast_vs_reference": 0.0 if level == reference else None,
                "contrast_ci_low": 0.0 if level == reference else None,
                "contrast_ci_high": 0.0 if level == reference else None,
                "p_value": None,
            }
        )
    if reference not in draws_by_level:
        raise AssertionError(f"{source}/{variable}: missing reference {reference}")
    reference_estimate = next(row["estimate"] for row in rows if row["level"] == reference)
    for row in rows:
        if row["level"] == reference:
            continue
        contrast_draws = draws_by_level[row["level"]] - draws_by_level[reference]
        row["contrast_vs_reference"] = row["estimate"] - reference_estimate
        row["contrast_ci_low"], row["contrast_ci_high"] = percentile_interval(contrast_draws)
        row["p_value"] = contrast_p_value(contrast_draws)
    return rows


def time_family(
    source: str, frame: pd.DataFrame, rng: np.random.Generator
) -> list[dict[str, Any]]:
    working = frame[["person_key_hash", "pair_time_relative", "ccd"]].copy()
    working["pair_time_relative"] = pd.to_numeric(working["pair_time_relative"], errors="coerce")
    working["time_group"] = np.where(working["pair_time_relative"] < 360, "0-<6 h", "6-24 h")
    wide = (
        working.groupby(["person_key_hash", "time_group"], observed=True)["ccd"]
        .mean()
        .unstack("time_group")
        .reindex(columns=["0-<6 h", "6-24 h"])
    )
    observed = wide.mean(axis=0, skipna=True)
    draws = {level: np.empty(REPLICATES, dtype=float) for level in wide.columns}
    contrast = np.empty(REPLICATES, dtype=float)
    array = wide.to_numpy(float)
    for start in range(0, REPLICATES, 200):
        count = min(200, REPLICATES - start)
        idx = rng.integers(0, len(array), size=(count, len(array)))
        sampled = array[idx]
        means = np.nanmean(sampled, axis=1)
        for column_index, level in enumerate(wide.columns):
            draws[level][start : start + count] = means[:, column_index]
        contrast[start : start + count] = means[:, 0] - means[:, 1]
    rows: list[dict[str, Any]] = []
    for level in wide.columns:
        low, high = percentile_interval(draws[level])
        is_reference = level == "6-24 h"
        rows.append(
            {
                "source": source,
                "family": "time_group",
                "level": level,
                "reference": "6-24 h",
                "people": int(wide[level].notna().sum()),
                "estimate": float(observed[level]),
                "ci_low": low,
                "ci_high": high,
                "contrast_vs_reference": 0.0 if is_reference else float(observed["0-<6 h"] - observed["6-24 h"]),
                "contrast_ci_low": 0.0 if is_reference else percentile_interval(contrast)[0],
                "contrast_ci_high": 0.0 if is_reference else percentile_interval(contrast)[1],
                "p_value": None if is_reference else contrast_p_value(contrast),
            }
        )
    return rows


def source_analysis(source: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    frame = pd.read_parquet(PRIVATE_ROOT / SOURCE_FILES[source])
    people = patient_table(source, frame)
    rng = np.random.default_rng(SEED + {"sicdb": 1, "mimic_iv": 2, "eicu": 3}[source])
    rows: list[dict[str, Any]] = []
    rows += categorical_family(
        source, people, "age_group", ["18-44", "45-64", "65-79", ">=80"], "65-79", rng
    )
    rows += categorical_family(
        source, people, "sex_group", ["Female", "Male", "Unknown"], "Female", rng
    )
    rows += time_family(source, frame, rng)
    metadata: dict[str, Any] = {
        "people": int(len(people)),
        "pairs": int(len(frame)),
        "unavailable_prespecified_fields": [],
    }
    if source == "sicdb":
        rows += categorical_family(
            source, people, "saps3_quartile", ["Q1", "Q2", "Q3", "Q4"], "Q1", rng
        )
        rows += categorical_family(
            source, people, "sepsis_group", ["No", "Yes", "Unknown"], "No", rng
        )
        rows += categorical_family(
            source, people, "urgency_group", ["Elective", "Urgent", "Unknown"], "Elective", rng
        )
        metadata["saps3_quartile_edges"] = people.attrs["saps3_edges"]
        metadata["unavailable_prespecified_fields"] = ["vasopressor exposure"]
    else:
        metadata["unavailable_prespecified_fields"] = [
            "source-specific severity in measurement extract",
            "vasopressor exposure",
        ]
        if source == "mimic_iv":
            metadata["calendar_time_note"] = "Not interpretable because MIMIC-IV dates are shifted per patient."
        else:
            metadata["calendar_time_note"] = "Calendar year was not retained in the frozen measurement extract."
    return rows, metadata


def main() -> int:
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    TABLES_ROOT.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict[str, Any]] = []
    metadata: dict[str, Any] = {}
    for source in SOURCE_FILES:
        rows, source_metadata = source_analysis(source)
        all_rows.extend(rows)
        metadata[source] = source_metadata
    table = pd.DataFrame(all_rows)
    for source in SOURCE_FILES:
        mask = (table["source"] == source) & table["p_value"].notna()
        table.loc[mask, "bh_q_value"] = bh_adjust(table.loc[mask, "p_value"].tolist())
    table.to_csv(TABLES_ROOT / "measurement_subgroups_v2.csv", index=False)
    payload = {
        "analysis_version": "2.0",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "independent_unit": "person",
        "estimand": "equal-person mean clinically consequential discordance fraction",
        "bootstrap_replicates": REPLICATES,
        "contrast_definition": "percentage-point difference versus named reference level",
        "multiplicity": "Benjamini-Hochberg within each source across non-reference contrasts",
        "metadata": metadata,
        "rows": table.where(pd.notna(table), None).to_dict(orient="records"),
    }
    (RESULTS_ROOT / "measurement_subgroups_v2.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(table.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
