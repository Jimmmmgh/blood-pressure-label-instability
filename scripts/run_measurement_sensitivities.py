"""Prespecified outcome-blind sensitivity and falsification analyses."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import polars as pl


ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "analysis" / "private"
RESULTS = ROOT / "results"
TABLES = ROOT / "tables"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from measurement_core import SEED, bootstrap_mean_ci  # noqa: E402


SOURCES = ("sicdb", "mimic_iv", "eicu")


def classify(frame: pl.DataFrame, threshold: float, difference: float) -> pl.DataFrame:
    return frame.with_columns(
        (
            ((pl.col("arterial_map") < threshold) != (pl.col("cuff_map") < threshold))
            & ((pl.col("cuff_map") - pl.col("arterial_map")).abs() >= difference)
        ).alias("event")
    )


def summarize(
    frame: pl.DataFrame,
    *,
    threshold: float = 65.0,
    difference: float = 10.0,
    minimum_pairs: int = 3,
) -> dict[str, float | int]:
    classified = classify(frame, threshold, difference)
    people = (
        classified.group_by("person_key_hash")
        .agg(pl.len().alias("n_pairs"), pl.col("event").mean().alias("fraction"))
        .filter(pl.col("n_pairs") >= minimum_pairs)
        .sort("person_key_hash")
    )
    if people.is_empty():
        return {
            "people": 0,
            "pairs": 0,
            "estimate": float("nan"),
            "ci_low": float("nan"),
            "ci_high": float("nan"),
            "pair_weighted": float("nan"),
        }
    retained = classified.join(
        people.select("person_key_hash"), on="person_key_hash", how="inner"
    )
    estimate, low, high = bootstrap_mean_ci(people["fraction"], replicates=2_000)
    return {
        "people": people.height,
        "pairs": retained.height,
        "estimate": estimate,
        "ci_low": low,
        "ci_high": high,
        "pair_weighted": float(retained["event"].mean()),
    }


def sensitivity_rows(source: str, frame: pl.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def add(family: str, level: str, subset: pl.DataFrame, **kwargs: Any) -> None:
        rows.append(
            {
                "source": source,
                "family": family,
                "level": level,
                **summarize(subset, **kwargs),
            }
        )

    for low, high in ((20, 200), (30, 160), (40, 130)):
        add(
            "plausible_range",
            f"{low}-{high}",
            frame.filter(
                pl.col("arterial_map").is_between(low, high)
                & pl.col("cuff_map").is_between(low, high)
            ),
        )
    for minimum in (3, 5, 10):
        add("minimum_pairs", str(minimum), frame, minimum_pairs=minimum)
    for end in (360, 1_440):
        add(
            "time_window_minutes",
            f"0-{end}",
            frame.filter(pl.col("pair_time_relative").is_between(0, end)),
        )
    for threshold in (60, 65, 70):
        add("hypotension_threshold", str(threshold), frame, threshold=threshold)
    for difference in (5, 10, 15):
        add("large_difference_cutoff", str(difference), frame, difference=difference)
    return rows


def sicdb_time_shift(frame: pl.DataFrame, shift_minutes: int) -> dict[str, Any]:
    arterial = frame.select(
        "person_key_hash", "pair_time_relative", "arterial_map"
    )
    cuff = frame.select(
        "person_key_hash",
        (pl.col("pair_time_relative") - shift_minutes).alias("pair_time_relative"),
        "cuff_map",
    )
    shifted = arterial.join(
        cuff, on=["person_key_hash", "pair_time_relative"], how="inner"
    )
    return {"shift_minutes": shift_minutes, **summarize(shifted)}


def stratified_between_person_permutation(frame: pl.DataFrame) -> dict[str, Any]:
    work = frame.with_columns(
        pl.when(pl.col("arterial_map") < 55)
        .then(pl.lit("lt55"))
        .when(pl.col("arterial_map") < 65)
        .then(pl.lit("55_64"))
        .when(pl.col("arterial_map") < 75)
        .then(pl.lit("65_74"))
        .when(pl.col("arterial_map") < 90)
        .then(pl.lit("75_89"))
        .otherwise(pl.lit("ge90"))
        .alias("arterial_stratum")
    ).with_row_index("row_index")
    rng = np.random.default_rng(SEED)
    permuted_parts = []
    for stratum in work["arterial_stratum"].unique().sort().to_list():
        part = work.filter(pl.col("arterial_stratum") == stratum)
        cuffs = part["cuff_map"].to_numpy().copy()
        people = part["person_key_hash"].to_numpy()
        # Rotate after random ordering until most cuffs are assigned across people.
        order = rng.permutation(len(part))
        rotated = np.roll(order, max(1, len(part) // 3))
        assigned = cuffs[rotated]
        donor_people = people[rotated]
        if len(part) > 1:
            same = donor_people == people
            assigned[same] = np.roll(assigned, 1)[same]
        permuted_parts.append(part.with_columns(pl.Series("cuff_map", assigned)))
    permuted = pl.concat(permuted_parts).sort("row_index")
    return summarize(permuted)


def main() -> int:
    rows: list[dict[str, Any]] = []
    permutations: dict[str, Any] = {}
    frames: dict[str, pl.DataFrame] = {}
    for source in SOURCES:
        frame = pl.read_parquet(PRIVATE / f"{source}_primary_pairs_v1.parquet")
        frames[source] = frame
        rows.extend(sensitivity_rows(source, frame))
        permutations[source] = stratified_between_person_permutation(frame)
    shifts = [sicdb_time_shift(frames["sicdb"], value) for value in (-5, -1, 1, 5)]
    table = pl.DataFrame(rows)
    table.write_csv(TABLES / "measurement_sensitivity_v2.csv")

    core = table.filter(
        pl.col("family").is_in(["plausible_range", "time_window_minutes"])
    )
    per_source = (
        core.group_by("source")
        .agg(
            pl.col("estimate").min().alias("min_estimate"),
            pl.col("estimate").max().alias("max_estimate"),
            pl.col("ci_low").min().alias("min_ci_low"),
            pl.col("people").min().alias("min_people"),
        )
        .sort("source")
    )
    output = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "protocol_version": "2.0 pre-result restart",
        "outcomes_read": False,
        "bootstrap_replicates": 2_000,
        "core_range_and_timing_summary": per_source.to_dicts(),
        "sicdb_time_shift_falsification": shifts,
        "between_person_stratified_permutation": permutations,
        "primary_conclusion_preserved_across_range_and_timing": bool(
            per_source.filter(pl.col("min_ci_low") <= 0.02).is_empty()
        ),
        "notes": [
            "Minimum-pair 1 and full-stay sensitivities require separate all-pair extracts and are not represented by this primary-population file.",
            "Permutation is stratified on broad arterial-MAP bands and is a falsification analysis, not a physiological null model.",
        ],
    }
    (RESULTS / "measurement_sensitivity_v2.json").write_text(
        json.dumps(output, indent=2, allow_nan=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(output, indent=2, allow_nan=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
