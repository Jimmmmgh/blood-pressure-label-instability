"""Audit all pre-outcome gates and create a machine-readable release decision."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import polars as pl


ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "analysis" / "private"
RESULTS = ROOT / "results"
PROTOCOL = ROOT / "protocol"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_primary_measurements import query_frame  # noqa: E402
from measurement_core import (  # noqa: E402
    add_measurement_states,
    bootstrap_mean_ci,
    hash_identifier,
    patient_level_fractions,
    validate_core_frame,
)


OUTCOME_COLUMNS = {
    "dischargestate",
    "hospitaldischargetype",
    "hospitaldischargeday",
    "offsetofdeath",
    "hospital_expire_flag",
    "deathtime",
    "dischtime",
    "hospitaldischargestatus",
    "hospitaldischargeoffset",
    "unitdischargestatus",
    "unitdischargeoffset",
}


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def manifest_valid() -> tuple[bool, list[dict[str, Any]]]:
    manifest = json.loads(
        (PROTOCOL / "FROZEN_CONTRACT_v2.0.sha256.json").read_text(encoding="utf-8")
    )
    failures = []
    for expected in manifest["files"]:
        path = ROOT / expected["relative_path"]
        observed = (
            {
                "relative_path": expected["relative_path"],
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            if path.is_file()
            else None
        )
        if observed != expected:
            failures.append({"expected": expected, "observed": observed})
    return not failures, failures


def boundary_tests() -> bool:
    frame = pl.DataFrame(
        {
            "arterial_map": [64.0, 65.0, 64.0, 64.0, 75.0],
            "cuff_map": [74.0, 55.0, 73.0, 60.0, 65.0],
        }
    )
    observed = add_measurement_states(frame)
    return (
        observed["threshold_discordant"].to_list()
        == [True, True, True, False, False]
        and observed["large_discordance_10"].to_list()
        == [True, True, False, False, True]
        and observed["ccd"].to_list() == [True, True, False, False, False]
    )


def source_quality(source: str) -> dict[str, Any]:
    path = PRIVATE / f"{source}_primary_pairs_v1.parquet"
    frame = pl.read_parquet(path)
    validate_core_frame(frame)
    people = patient_level_fractions(frame)
    estimate_1k = bootstrap_mean_ci(people["ccd_fraction"], replicates=1_000)
    estimate_2k = bootstrap_mean_ci(people["ccd_fraction"], replicates=2_000)
    overlap = sorted(OUTCOME_COLUMNS.intersection({name.lower() for name in frame.columns}))
    return {
        "people": people.height,
        "pairs": frame.height,
        "minimum_pairs": int(people["n_pairs"].min()),
        "nonfinite_or_out_of_range_rows": frame.filter(
            ~pl.col("arterial_map").is_finite()
            | ~pl.col("cuff_map").is_finite()
            | ~pl.col("arterial_map").is_between(20, 200)
            | ~pl.col("cuff_map").is_between(20, 200)
        ).height,
        "outcome_columns_found": overlap,
        "bootstrap_1000": list(estimate_1k),
        "bootstrap_2000": list(estimate_2k),
        "bootstrap_max_endpoint_difference": float(
            max(abs(a - b) for a, b in zip(estimate_1k, estimate_2k))
        ),
    }


def calendar_mapping(source: str) -> pl.DataFrame:
    if source == "mimic_iv":
        raw = query_frame(
            "mimic",
            "SELECT stay_id, EXTRACT(YEAR FROM intime)::integer AS calendar_year "
            "FROM mimiciv_icu.icustays",
        )
        return raw.with_columns(
            pl.col("stay_id")
            .map_elements(
                lambda value: hash_identifier("mimic_iv", f"unit:{value}"),
                return_dtype=pl.String,
            )
            .alias("unit_key_hash")
        ).select("unit_key_hash", "calendar_year")
    if source == "eicu":
        raw = query_frame(
            "eicu",
            "SELECT patientunitstayid, hospitaldischargeyear::integer AS calendar_year "
            "FROM eicu_crd.patient",
        )
        return raw.with_columns(
            pl.col("patientunitstayid")
            .map_elements(
                lambda value: hash_identifier("eicu", f"unit:{value}"),
                return_dtype=pl.String,
            )
            .alias("unit_key_hash")
        ).select("unit_key_hash", "calendar_year")
    frame = pl.read_parquet(PRIVATE / "sicdb_primary_pairs_v1.parquet")
    return frame.select(
        "unit_key_hash", pl.col("admission_year").alias("calendar_year")
    ).unique()


def calendar_diagnostics(source: str) -> dict[str, Any]:
    if source == "mimic_iv":
        return {
            "status": "not_interpretable",
            "reason": (
                "MIMIC-IV dates are shifted independently by patient; displayed years "
                "cannot define a between-person calendar stratum. Calendar heterogeneity "
                "is therefore not claimed for this source."
            ),
        }
    frame = pl.read_parquet(PRIVATE / f"{source}_primary_pairs_v1.parquet")
    people = patient_level_fractions(frame)
    mapping = calendar_mapping(source)
    people = people.join(mapping, on="unit_key_hash", how="left")
    missing = people["calendar_year"].null_count()
    years = (
        people.drop_nulls("calendar_year")
        .group_by("calendar_year")
        .agg(
            pl.len().alias("people"),
            pl.col("ccd_fraction").mean().alias("mean_ccd_fraction"),
        )
        .sort("calendar_year")
    )
    total_n = int(years["people"].sum())
    total_sum = float((years["people"] * years["mean_ccd_fraction"]).sum())
    loo = years.with_columns(
        pl.when(pl.col("people") < total_n)
        .then(
            (total_sum - pl.col("people") * pl.col("mean_ccd_fraction"))
            / (total_n - pl.col("people"))
        )
        .otherwise(None)
        .alias("leave_one_year_out_mean")
    )
    return {
        "missing_year_people": missing,
        "year_strata": years.to_dicts(),
        "largest_year_fraction": float(years["people"].max() / total_n),
        "year_specific_ccd_range": [
            float(years["mean_ccd_fraction"].min()),
            float(years["mean_ccd_fraction"].max()),
        ],
        "leave_one_year_out_range": [
            float(loo["leave_one_year_out_mean"].drop_nulls().min()),
            float(loo["leave_one_year_out_mean"].drop_nulls().max()),
        ],
    }


def main() -> int:
    primary = json.loads(
        (RESULTS / "measurement_primary_v2.json").read_text(encoding="utf-8")
    )
    sensitivity = json.loads(
        (RESULTS / "measurement_sensitivity_v2.json").read_text(encoding="utf-8")
    )
    extended = json.loads(
        (RESULTS / "measurement_extended_sensitivity_v2.json").read_text(
            encoding="utf-8"
        )
    )
    manifest_pass, manifest_failures = manifest_valid()
    quality = {source: source_quality(source) for source in ("sicdb", "mimic_iv", "eicu")}
    calendars = {
        source: calendar_diagnostics(source)
        for source in ("sicdb", "mimic_iv", "eicu")
    }
    source_results = {item["source"]: item for item in primary["sources"]}
    capacity_pass = (
        source_results["sicdb"]["people"] >= 1_500
        and source_results["mimic_iv"]["people"] >= 2_000
        and source_results["eicu"]["people"] >= 2_000
    )
    primary_signal_pass = (
        source_results["sicdb"]["estimands"]["ccd_fraction"]["estimate"] >= 0.05
        and source_results["mimic_iv"]["estimands"]["ccd_fraction"]["ci_low"] > 0.02
        and source_results["eicu"]["estimands"]["ccd_fraction"]["ci_low"] > 0.02
    )
    qa_pass = all(
        not item["outcome_columns_found"]
        and item["minimum_pairs"] >= 3
        and item["nonfinite_or_out_of_range_rows"] == 0
        and item["bootstrap_max_endpoint_difference"] <= 0.0025
        for item in quality.values()
    )
    site = primary["eicu_site_diagnostics"]
    site_pass = (
        site["largest_hospital_fraction_of_people"] < 0.10
        and site["leave_one_hospital_out_overall_range"][0] > 0.02
    )
    calendar_pass = all(
        calendars[source]["missing_year_people"] == 0
        and calendars[source]["leave_one_year_out_range"][0] > 0.02
        for source in ("sicdb", "eicu")
    )
    extended_pass = all(
        extended["sources"][source][analysis]["ci_low"] > 0.02
        for source in ("sicdb", "mimic_iv", "eicu")
        for analysis in ("first24_min1", "fullstay_min3")
    )
    gates = {
        "v2_manifest": manifest_pass,
        "classification_boundary_tests": boundary_tests(),
        "capacity": capacity_pass,
        "primary_signal": primary_signal_pass,
        "core_qa_and_bootstrap_stability": qa_pass,
        "range_and_timing_sensitivity": sensitivity[
            "primary_conclusion_preserved_across_range_and_timing"
        ],
        "minimum_one_pair_and_full_stay_sensitivity": extended_pass,
        "eicu_site_concentration": site_pass,
        "calendar_concentration": calendar_pass,
    }
    pass_all = all(gates.values())
    output = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "outcomes_read": False,
        "protocol_version": "2.0 pre-result restart",
        "gates": gates,
        "measurement_gate_pass": pass_all,
        "flagship_viability_gate_pass": pass_all,
        "outcome_firewall_decision": "RELEASE" if pass_all else "LOCKED",
        "quality": quality,
        "calendar_diagnostics": calendars,
        "eicu_site_diagnostics": site,
        "manifest_failures": manifest_failures,
        "implementation_deviation": (
            "Calendar-year fields were omitted from VARIABLE_CONTRACT_v1.0 despite "
            "calendar heterogeneity being prespecified in the protocol. Only deidentified "
            "year was read for this gate; it was not used to alter the cohort or estimand."
        ),
    }
    path = RESULTS / "measurement_gate_report_v2.json"
    path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))
    return 0 if pass_all else 4


if __name__ == "__main__":
    raise SystemExit(main())
