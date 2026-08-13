"""Quantify patient-level hypotension phenotyping shifts between modalities."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import polars as pl


ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "analysis" / "private"
RESULTS = ROOT / "results"
TABLES = ROOT / "tables"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from measurement_core import bootstrap_mean_ci  # noqa: E402


def main() -> int:
    rows = []
    output = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "outcomes_read": False,
        "sources": {},
    }
    for source in ("sicdb", "mimic_iv", "eicu"):
        frame = pl.read_parquet(PRIVATE / f"{source}_primary_pairs_v1.parquet")
        people = (
            frame.group_by("person_key_hash")
            .agg(
                pl.len().alias("pairs"),
                pl.col("arterial_low_65").mean().alias("arterial_burden"),
                pl.col("cuff_low_65").mean().alias("cuff_burden"),
                (~(pl.col("threshold_discordant") | pl.col("large_discordance_10")))
                .mean()
                .alias("stable_coverage"),
            )
            .sort("person_key_hash")
            .with_columns(
                (pl.col("cuff_burden") - pl.col("arterial_burden")).alias(
                    "burden_delta_cuff_minus_arterial"
                )
            )
        )
        mean, low, high = bootstrap_mean_ci(
            people["burden_delta_cuff_minus_arterial"], replicates=2_000
        )
        stable_mean, stable_low, stable_high = bootstrap_mean_ci(
            people["stable_coverage"], replicates=2_000
        )
        summary = {
            "people": people.height,
            "mean_burden_delta": mean,
            "mean_burden_delta_ci_low": low,
            "mean_burden_delta_ci_high": high,
            "median_burden_delta": float(
                people["burden_delta_cuff_minus_arterial"].median()
            ),
            "people_absolute_burden_shift_at_least_010": int(
                people.filter(
                    pl.col("burden_delta_cuff_minus_arterial").abs() >= 0.10
                ).height
            ),
            "fraction_absolute_burden_shift_at_least_010": float(
                (people["burden_delta_cuff_minus_arterial"].abs() >= 0.10).mean()
            ),
            "fraction_cuff_higher_by_at_least_010": float(
                (people["burden_delta_cuff_minus_arterial"] >= 0.10).mean()
            ),
            "fraction_arterial_higher_by_at_least_010": float(
                (people["burden_delta_cuff_minus_arterial"] <= -0.10).mean()
            ),
            "stable_coverage": stable_mean,
            "stable_coverage_ci_low": stable_low,
            "stable_coverage_ci_high": stable_high,
        }
        output["sources"][source] = summary
        rows.append({"source": source, **summary})
    (RESULTS / "policy_burden_shifts_v2.json").write_text(
        json.dumps(output, indent=2) + "\n", encoding="utf-8"
    )
    pl.DataFrame(rows).write_csv(TABLES / "policy_burden_shifts_v2.csv")
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
