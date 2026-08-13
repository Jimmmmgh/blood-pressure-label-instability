"""Run the frozen, outcome-blind primary measurement analysis."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

import numpy as np
import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRIVATE_ROOT = PROJECT_ROOT / "analysis" / "private"
RESULTS_ROOT = PROJECT_ROOT / "results"
TABLES_ROOT = PROJECT_ROOT / "tables"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from measurement_core import (  # noqa: E402
    SEED,
    bootstrap_mean_ci,
    patient_level_fractions,
    validate_core_frame,
)


SOURCES = ("sicdb", "mimic_iv", "eicu")
SOURCE_LABELS = {
    "sicdb": "SICdb",
    "mimic_iv": "MIMIC-IV",
    "eicu": "eICU",
}
FRACTION_METRICS = (
    "ccd_fraction",
    "threshold_discordant_fraction",
    "large_discordance_fraction",
    "ccd_cuff_low_fraction",
    "ccd_arterial_low_fraction",
    "review_fraction",
)


def quantiles(values: pl.Series) -> dict[str, float]:
    clean = values.drop_nulls().cast(pl.Float64)
    return {
        "p25": float(clean.quantile(0.25, interpolation="linear")),
        "median": float(clean.quantile(0.50, interpolation="linear")),
        "p75": float(clean.quantile(0.75, interpolation="linear")),
        "p90": float(clean.quantile(0.90, interpolation="linear")),
    }


def bootstrap_cluster_agreement(
    frame: pl.DataFrame, replicates: int = 2_000
) -> dict[str, dict[str, float]]:
    aggregates = (
        frame.group_by("person_key_hash")
        .agg(
            pl.len().cast(pl.Float64).alias("n"),
            pl.col("delta_cuff_minus_arterial").sum().alias("sum"),
            (pl.col("delta_cuff_minus_arterial") ** 2).sum().alias("sumsq"),
        )
        .sort("person_key_hash")
    )
    n = aggregates["n"].to_numpy()
    sums = aggregates["sum"].to_numpy()
    sumsqs = aggregates["sumsq"].to_numpy()
    total_n = n.sum()
    mean = sums.sum() / total_n
    variance = (sumsqs.sum() - total_n * mean**2) / (total_n - 1)
    sd = float(np.sqrt(max(variance, 0.0)))
    observed = {
        "mean_bias": float(mean),
        "lower_loa": float(mean - 1.96 * sd),
        "upper_loa": float(mean + 1.96 * sd),
        "rmse": float(np.sqrt(sumsqs.sum() / total_n)),
    }
    rng = np.random.default_rng(SEED)
    bootstrap = {name: np.empty(replicates) for name in observed}
    people = len(n)
    for start in range(0, replicates, 200):
        count = min(200, replicates - start)
        indices = rng.integers(0, people, size=(count, people))
        bn = n[indices].sum(axis=1)
        bs = sums[indices].sum(axis=1)
        bss = sumsqs[indices].sum(axis=1)
        bmean = bs / bn
        bvar = (bss - bn * bmean**2) / np.maximum(bn - 1, 1)
        bsd = np.sqrt(np.maximum(bvar, 0.0))
        bootstrap["mean_bias"][start : start + count] = bmean
        bootstrap["lower_loa"][start : start + count] = bmean - 1.96 * bsd
        bootstrap["upper_loa"][start : start + count] = bmean + 1.96 * bsd
        bootstrap["rmse"][start : start + count] = np.sqrt(bss / bn)
    return {
        name: {
            "estimate": value,
            "ci_low": float(np.quantile(bootstrap[name], 0.025)),
            "ci_high": float(np.quantile(bootstrap[name], 0.975)),
        }
        for name, value in observed.items()
    }


def patient_median_ci(frame: pl.DataFrame, column: str) -> dict[str, float]:
    medians = (
        frame.group_by("person_key_hash")
        .agg(pl.col(column).median().alias("value"))
        .sort("person_key_hash")["value"]
        .to_numpy()
    )
    rng = np.random.default_rng(SEED)
    estimates = np.empty(2_000)
    for start in range(0, 2_000, 200):
        count = min(200, 2_000 - start)
        idx = rng.integers(0, len(medians), size=(count, len(medians)))
        estimates[start : start + count] = np.median(medians[idx], axis=1)
    return {
        "estimate": float(np.median(medians)),
        "ci_low": float(np.quantile(estimates, 0.025)),
        "ci_high": float(np.quantile(estimates, 0.975)),
    }


def source_summary(source: str) -> tuple[dict[str, Any], pl.DataFrame]:
    path = PRIVATE_ROOT / f"{source}_primary_pairs_v1.parquet"
    frame = pl.read_parquet(path)
    validate_core_frame(frame)
    people = patient_level_fractions(frame)
    if people.filter(pl.col("n_pairs") < 3).height:
        raise AssertionError(f"{source}: primary population contains <3-pair people")
    estimands: dict[str, dict[str, float]] = {}
    for metric in FRACTION_METRICS:
        estimate, low, high = bootstrap_mean_ci(people[metric], replicates=2_000)
        estimands[metric] = {
            "estimate": estimate,
            "ci_low": low,
            "ci_high": high,
        }
    estimands["pair_weighted_ccd_fraction"] = {
        "estimate": float(frame["ccd"].mean()),
        "ci_low": float("nan"),
        "ci_high": float("nan"),
    }
    summary = {
        "source": source,
        "source_label": SOURCE_LABELS[source],
        "people": people.height,
        "units": frame["unit_key_hash"].n_unique(),
        "pairs": frame.height,
        "pairs_per_person": quantiles(people["n_pairs"]),
        "estimands": estimands,
        "agreement": bootstrap_cluster_agreement(frame),
        "equal_person_median_delta": patient_median_ci(
            frame, "delta_cuff_minus_arterial"
        ),
        "equal_person_median_abs_delta": patient_median_ci(frame, "abs_delta"),
    }
    people = people.with_columns(pl.lit(source).alias("source"))
    if source == "eicu":
        sites = frame.select("person_key_hash", "hospital_key_hash").unique()
        people = people.join(sites, on="person_key_hash", how="left")
    return summary, people


def external_differences(
    patient_tables: dict[str, pl.DataFrame], replicates: int = 2_000
) -> dict[str, dict[str, float]]:
    anchor = patient_tables["sicdb"]["ccd_fraction"].to_numpy()
    rng = np.random.default_rng(SEED)
    output: dict[str, dict[str, float]] = {}
    for source in ("mimic_iv", "eicu"):
        external = patient_tables[source]["ccd_fraction"].to_numpy()
        values = np.empty(replicates)
        for start in range(0, replicates, 200):
            count = min(200, replicates - start)
            anchor_idx = rng.integers(0, len(anchor), size=(count, len(anchor)))
            external_idx = rng.integers(
                0, len(external), size=(count, len(external))
            )
            values[start : start + count] = external[external_idx].mean(axis=1) - anchor[
                anchor_idx
            ].mean(axis=1)
        output[source] = {
            "estimate": float(external.mean() - anchor.mean()),
            "ci_low": float(np.quantile(values, 0.025)),
            "ci_high": float(np.quantile(values, 0.975)),
        }
    return output


def eicu_site_diagnostics(people: pl.DataFrame) -> dict[str, Any]:
    sites = (
        people.group_by("hospital_key_hash")
        .agg(
            pl.len().alias("people"),
            pl.col("ccd_fraction").mean().alias("mean_ccd_fraction"),
        )
        .sort("people", descending=True)
    )
    eligible = sites.filter(pl.col("people") >= 50)
    total_sum = float((sites["people"] * sites["mean_ccd_fraction"]).sum())
    total_n = int(sites["people"].sum())
    leave_one_out = eligible.with_columns(
        (
            (total_sum - pl.col("people") * pl.col("mean_ccd_fraction"))
            / (total_n - pl.col("people"))
        ).alias("leave_one_hospital_out_mean")
    )
    return {
        "all_hospitals": sites.height,
        "hospitals_with_at_least_50_people": eligible.height,
        "largest_hospital_people": int(sites["people"].max()),
        "largest_hospital_fraction_of_people": float(sites["people"].max() / total_n),
        "eligible_hospital_ccd_range": [
            float(eligible["mean_ccd_fraction"].min()),
            float(eligible["mean_ccd_fraction"].max()),
        ],
        "leave_one_hospital_out_overall_range": [
            float(leave_one_out["leave_one_hospital_out_mean"].min()),
            float(leave_one_out["leave_one_hospital_out_mean"].max()),
        ],
    }


def flat_estimand_table(summaries: list[dict[str, Any]]) -> pl.DataFrame:
    rows = []
    for summary in summaries:
        for name, values in summary["estimands"].items():
            rows.append(
                {
                    "source": summary["source_label"],
                    "estimand": name,
                    "independent_people": summary["people"],
                    "pairs": summary["pairs"],
                    **values,
                }
            )
    return pl.DataFrame(rows)


def main() -> int:
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    TABLES_ROOT.mkdir(parents=True, exist_ok=True)
    summaries = []
    patient_tables: dict[str, pl.DataFrame] = {}
    for source in SOURCES:
        summary, people = source_summary(source)
        summaries.append(summary)
        patient_tables[source] = people
        people.write_parquet(
            PRIVATE_ROOT / f"{source}_patient_measurement_summary_v2.parquet",
            compression="zstd",
        )
    external = external_differences(patient_tables)
    eicu_site = eicu_site_diagnostics(patient_tables["eicu"])
    gate = {
        "v2_capacity_gate": (
            summaries[0]["people"] >= 1_500
            and summaries[1]["people"] >= 2_000
            and summaries[2]["people"] >= 2_000
        ),
        "sicdb_primary_ccd_at_least_005": (
            summaries[0]["estimands"]["ccd_fraction"]["estimate"] >= 0.05
        ),
        "both_external_ccd_lower_ci_above_002": all(
            summary["estimands"]["ccd_fraction"]["ci_low"] > 0.02
            for summary in summaries[1:]
        ),
        "site_and_sensitivity_gate": "pending",
        "flagship_viability_gate": "pending",
        "outcome_firewall": "locked",
    }
    output = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "protocol_version": "2.0 pre-result restart",
        "outcomes_read": False,
        "bootstrap_replicates": 2_000,
        "seed": SEED,
        "sources": summaries,
        "external_minus_sicdb_ccd_difference": external,
        "eicu_site_diagnostics": eicu_site,
        "gates": gate,
    }
    (RESULTS_ROOT / "measurement_primary_v2.json").write_text(
        json.dumps(output, indent=2, allow_nan=True) + "\n", encoding="utf-8"
    )
    flat_estimand_table(summaries).write_csv(
        TABLES_ROOT / "measurement_estimands_v2.csv"
    )
    pl.DataFrame(
        [
            {
                "source": item["source_label"],
                "people": item["people"],
                "units": item["units"],
                "pairs": item["pairs"],
                "pairs_p25": item["pairs_per_person"]["p25"],
                "pairs_median": item["pairs_per_person"]["median"],
                "pairs_p75": item["pairs_per_person"]["p75"],
                "pairs_p90": item["pairs_per_person"]["p90"],
            }
            for item in summaries
        ]
    ).write_csv(TABLES_ROOT / "measurement_cohort_summary_v2.csv")
    print(json.dumps(output, indent=2, allow_nan=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
