"""Shared, outcome-blind measurement definitions for the frozen v1.0 study."""

from __future__ import annotations

import hashlib
from typing import Iterable

import numpy as np
import polars as pl


MAP_LOW = 20.0
MAP_HIGH = 200.0
HYPOTENSION_THRESHOLD = 65.0
LARGE_DIFFERENCE = 10.0
SEED = 20260812


def hash_identifier(source: str, value: object) -> str:
    """Return a deterministic project-local pseudonym without retaining raw IDs."""
    return hashlib.sha256(f"bp-label-v1|{source}|{value}".encode("utf-8")).hexdigest()[:24]


def add_measurement_states(frame: pl.DataFrame) -> pl.DataFrame:
    """Apply the exact frozen MAP and discordance definitions."""
    return frame.with_columns(
        (pl.col("cuff_map") - pl.col("arterial_map")).alias(
            "delta_cuff_minus_arterial"
        ),
        (pl.col("cuff_map") - pl.col("arterial_map")).abs().alias("abs_delta"),
        (pl.col("arterial_map") < HYPOTENSION_THRESHOLD).alias("arterial_low_65"),
        (pl.col("cuff_map") < HYPOTENSION_THRESHOLD).alias("cuff_low_65"),
    ).with_columns(
        (pl.col("arterial_low_65") != pl.col("cuff_low_65")).alias(
            "threshold_discordant"
        ),
        (pl.col("abs_delta") >= LARGE_DIFFERENCE).alias("large_discordance_10"),
    ).with_columns(
        (pl.col("threshold_discordant") & pl.col("large_discordance_10")).alias(
            "ccd"
        )
    )


def validate_core_frame(frame: pl.DataFrame) -> None:
    required = {
        "source",
        "person_key_hash",
        "unit_key_hash",
        "pair_time_relative",
        "arterial_map",
        "cuff_map",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    if frame.is_empty():
        raise ValueError("Measurement frame is empty")
    for column in ("arterial_map", "cuff_map"):
        invalid = frame.filter(
            pl.col(column).is_null()
            | ~pl.col(column).is_finite()
            | ~pl.col(column).is_between(MAP_LOW, MAP_HIGH)
        ).height
        if invalid:
            raise ValueError(f"{invalid} invalid values in {column}")
    if frame.select(pl.col("person_key_hash").str.len_chars().n_unique()).item() != 1:
        raise ValueError("Pseudonym lengths are inconsistent")


def patient_level_fractions(frame: pl.DataFrame) -> pl.DataFrame:
    """Create equal-person measurement summaries from a classified pair table."""
    return (
        frame.group_by("person_key_hash")
        .agg(
            pl.col("unit_key_hash").first(),
            pl.len().alias("n_pairs"),
            pl.col("ccd").mean().alias("ccd_fraction"),
            pl.col("threshold_discordant").mean().alias(
                "threshold_discordant_fraction"
            ),
            pl.col("large_discordance_10").mean().alias(
                "large_discordance_fraction"
            ),
            (
                pl.col("ccd")
                & pl.col("cuff_low_65")
                & ~pl.col("arterial_low_65")
            )
            .mean()
            .alias("ccd_cuff_low_fraction"),
            (
                pl.col("ccd")
                & pl.col("arterial_low_65")
                & ~pl.col("cuff_low_65")
            )
            .mean()
            .alias("ccd_arterial_low_fraction"),
            (
                pl.col("threshold_discordant") | pl.col("large_discordance_10")
            )
            .mean()
            .alias("review_fraction"),
            pl.col("delta_cuff_minus_arterial").mean().alias("mean_delta"),
            pl.col("delta_cuff_minus_arterial").median().alias("median_delta"),
            pl.col("abs_delta").median().alias("median_abs_delta"),
        )
        .sort("person_key_hash")
    )


def bootstrap_mean_ci(
    values: Iterable[float], replicates: int = 2_000, seed: int = SEED
) -> tuple[float, float, float]:
    """Percentile CI for the equal-person mean, reproducibly resampling people."""
    array = np.asarray(list(values), dtype=np.float64)
    array = array[np.isfinite(array)]
    if array.size == 0:
        raise ValueError("No finite values for bootstrap")
    rng = np.random.default_rng(seed)
    results = np.empty(replicates, dtype=np.float64)
    chunk = min(250, replicates)
    offset = 0
    while offset < replicates:
        count = min(chunk, replicates - offset)
        indices = rng.integers(0, array.size, size=(count, array.size))
        results[offset : offset + count] = array[indices].mean(axis=1)
        offset += count
    lower, upper = np.quantile(results, [0.025, 0.975])
    return float(array.mean()), float(lower), float(upper)
