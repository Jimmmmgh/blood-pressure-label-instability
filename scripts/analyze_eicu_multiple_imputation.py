"""Complete the prespecified eICU severity-score missing-data sensitivity."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd
import patsy
import polars as pl
from scipy.special import expit
from scipy.stats import t as student_t
from sklearn.experimental import enable_iterative_imputer  # noqa: F401
from sklearn.impute import IterativeImputer
from sklearn.linear_model import BayesianRidge
from sklearn.metrics import brier_score_loss, roc_auc_score


ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "analysis" / "private"
RESULTS = ROOT / "results"
TABLES = ROOT / "tables"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_locked_outcomes import (  # noqa: E402
    POLICIES,
    design_variants,
    fit_weighted_logistic,
    stable_seed,
)


def rubin_interval(points: np.ndarray, within_variances: np.ndarray) -> dict[str, float]:
    imputations = len(points)
    estimate = float(points.mean())
    within = float(within_variances.mean())
    between = float(points.var(ddof=1))
    total = within + (1.0 + 1.0 / imputations) * between
    if between > 0:
        ratio = within / ((1.0 + 1.0 / imputations) * between)
        degrees_freedom = float((imputations - 1) * (1 + ratio) ** 2)
        critical = float(student_t.ppf(0.975, degrees_freedom))
    else:
        degrees_freedom = float("inf")
        critical = 1.96
    standard_error = float(np.sqrt(max(total, 0.0)))
    return {
        "estimate": estimate,
        "ci_low": estimate - critical * standard_error,
        "ci_high": estimate + critical * standard_error,
        "within_imputation_variance": within,
        "between_imputation_variance": between,
        "total_variance": total,
        "degrees_freedom": degrees_freedom,
    }


def prepare(policy: str) -> tuple[pd.DataFrame, list[str]]:
    burden_column = POLICIES[policy]
    frame = pl.read_parquet(PRIVATE / "eicu_locked_landmark_outcome_v2.parquet")
    columns = [
        "person_key_hash",
        "hospital_mortality",
        "burden",
        "age",
        "sex",
        "severity_score",
        "n_pairs",
        "ccd_fraction",
        "arterial_burden",
        "cuff_burden",
        "any_sensor_burden",
        "stable_coverage",
    ]
    data = (
        frame.with_columns(pl.col(burden_column).alias("burden"))
        .select(columns)
        .sort("person_key_hash")
        .to_pandas()
    )
    data = data[data["sex"].isin(["Male", "Female"])].copy()
    data = data.dropna(subset=["hospital_mortality", "burden", "age", "sex"])
    data["male"] = (data["sex"] == "Male").astype(float)
    data["age10"] = (data["age"].astype(float) - data["age"].astype(float).mean()) / 10.0
    data["log_n_pairs"] = np.log1p(data["n_pairs"].astype(float))
    imputation_columns = [
        "severity_score",
        "age",
        "male",
        "hospital_mortality",
        "burden",
        "log_n_pairs",
        "ccd_fraction",
        "arterial_burden",
        "cuff_burden",
        "any_sensor_burden",
        "stable_coverage",
    ]
    return data.reset_index(drop=True), imputation_columns


def analyze_policy(task: tuple[str, int, int]) -> dict[str, Any]:
    policy, imputations, bootstraps = task
    data, imputation_columns = prepare(policy)
    outcome = data["hospital_mortality"].to_numpy(dtype=np.float64)
    missing = int(data["severity_score"].isna().sum())
    observed_min = float(data["severity_score"].min())
    observed_max = float(data["severity_score"].max())

    points = []
    within_variances = []
    aurocs = []
    briers = []
    failures = []
    for imputation in range(imputations):
        seed = stable_seed(f"eicu|mi|{policy}|{imputation}")
        imputer = IterativeImputer(
            estimator=BayesianRidge(),
            max_iter=20,
            sample_posterior=True,
            skip_complete=True,
            min_value=observed_min,
            max_value=observed_max,
            random_state=seed,
        )
        imputed = imputer.fit_transform(data[imputation_columns])
        completed = data.copy()
        completed["severity_score"] = imputed[:, 0]
        severity = completed["severity_score"].astype(float)
        completed["severity_z"] = (severity - severity.mean()) / severity.std(ddof=0)
        formula = "cr(burden, df=3, constraints='center') + age10 + male + severity_z"
        design, _, increment_design, _ = design_variants(completed, formula)
        beta, converged = fit_weighted_logistic(
            design, outcome, np.ones(len(completed), dtype=np.float64)
        )
        if not converged:
            raise RuntimeError(f"Original imputation fit did not converge: {policy}, {imputation}")
        prediction = expit(design @ beta)
        incremented = expit(increment_design @ beta)
        points.append(float(np.mean(incremented - prediction)))
        aurocs.append(float(roc_auc_score(outcome, prediction)))
        briers.append(float(brier_score_loss(outcome, prediction)))

        rng = np.random.default_rng(seed + 1)
        bootstrap_values = np.empty(bootstraps, dtype=np.float64)
        failed = 0
        for iteration in range(bootstraps):
            sample = rng.integers(0, len(completed), size=len(completed))
            weights = np.bincount(sample, minlength=len(completed)).astype(np.float64)
            fitted, ok = fit_weighted_logistic(design, outcome, weights, initial=beta)
            if not ok or not np.all(np.isfinite(fitted)):
                bootstrap_values[iteration] = np.nan
                failed += 1
                continue
            base = expit(design @ fitted)
            bootstrap_values[iteration] = float(
                np.sum(weights * (expit(increment_design @ fitted) - base))
                / weights.sum()
            )
        valid = bootstrap_values[np.isfinite(bootstrap_values)]
        if len(valid) < max(50, int(0.9 * bootstraps)):
            raise RuntimeError(f"Too many bootstrap failures: {policy}, {imputation}")
        within_variances.append(float(valid.var(ddof=1)))
        failures.append(failed)

    combined = rubin_interval(np.asarray(points), np.asarray(within_variances))
    base = json.loads((RESULTS / "locked_outcome_models_v2.json").read_text(encoding="utf-8"))
    complete_case = next(
        item for item in base["models"]
        if item["source"] == "eicu"
        and item["policy"] == policy
        and item["model"] == "age_sex_severity"
    )["intervals"]["average_marginal_risk_difference"]
    return {
        "source": "eicu",
        "policy": policy,
        "people": len(data),
        "deaths": int(outcome.sum()),
        "severity_missing": missing,
        "severity_missing_fraction": missing / len(data),
        "imputations": imputations,
        "bootstrap_replicates_per_imputation": bootstraps,
        "bootstrap_failures_total": int(sum(failures)),
        "imputation_model": (
            "Bayesian-ridge chained-equation draw including outcome, age, sex, "
            "policy burden, pair count, CCD, source burdens, and stable coverage"
        ),
        "amrd": combined,
        "complete_case_amrd": complete_case,
        "difference_from_complete_case": combined["estimate"] - complete_case["estimate"],
        "performance_mean": {
            "auroc": float(np.mean(aurocs)),
            "brier": float(np.mean(briers)),
        },
        "interpretation": "Missing-data sensitivity; association, not causal effect.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--imputations", type=int, default=20)
    parser.add_argument("--bootstraps", type=int, default=2000)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.imputations < 20:
        raise ValueError("Final analysis requires at least 20 imputations")
    tasks = [(policy, args.imputations, args.bootstraps) for policy in POLICIES]
    results = []
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(analyze_policy, task): task for task in tasks}
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda item: item["policy"])
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "analysis_version": "2.1 post-analysis QA completion",
        "source": "eicu",
        "method": "20-imputation sensitivity combined with Rubin's rules",
        "results": results,
    }
    RESULTS.mkdir(exist_ok=True)
    TABLES.mkdir(exist_ok=True)
    (RESULTS / "eicu_multiple_imputation_outcome_sensitivity_v2_1.json").write_text(
        json.dumps(payload, indent=2, allow_nan=True) + "\n", encoding="utf-8"
    )
    rows = []
    for item in results:
        rows.append({
            "source": "eICU",
            "policy": item["policy"],
            "people": item["people"],
            "deaths": item["deaths"],
            "severity_missing": item["severity_missing"],
            "severity_missing_percent": 100 * item["severity_missing_fraction"],
            "imputations": item["imputations"],
            "bootstrap_replicates_per_imputation": item["bootstrap_replicates_per_imputation"],
            "mi_amrd_percentage_points": 100 * item["amrd"]["estimate"],
            "mi_ci_low_percentage_points": 100 * item["amrd"]["ci_low"],
            "mi_ci_high_percentage_points": 100 * item["amrd"]["ci_high"],
            "complete_case_amrd_percentage_points": 100 * item["complete_case_amrd"]["estimate"],
            "difference_mi_minus_complete_case_percentage_points": 100 * item["difference_from_complete_case"],
            "mean_auroc": item["performance_mean"]["auroc"],
            "mean_brier": item["performance_mean"]["brier"],
        })
    pl.DataFrame(rows).write_csv(TABLES / "eicu_multiple_imputation_outcome_sensitivity_v2_1.csv")
    print(json.dumps(payload, indent=2, allow_nan=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
