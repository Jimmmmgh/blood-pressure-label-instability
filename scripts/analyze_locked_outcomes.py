"""Run the released 24-hour-landmark mortality sensitivity analysis."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import patsy
import polars as pl
from scipy.special import expit, logit
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
)


ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "analysis" / "private"
RESULTS = ROOT / "results"
TABLES = ROOT / "tables"
POLICIES = {
    "arterial_only": "arterial_burden",
    "cuff_only": "cuff_burden",
    "any_sensor": "any_sensor_burden",
    "concordant_only": "concordant_only_burden",
}
BURDEN_LEVELS = (0.0, 0.10, 0.25, 0.50)


def stable_seed(label: str) -> int:
    digest = hashlib.sha256(label.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def fit_weighted_logistic(
    design: np.ndarray,
    outcome: np.ndarray,
    weights: np.ndarray,
    initial: np.ndarray | None = None,
    max_iter: int = 60,
) -> tuple[np.ndarray, bool]:
    columns = design.shape[1]
    if initial is None:
        beta = np.zeros(columns, dtype=np.float64)
        prevalence = np.average(outcome, weights=weights)
        beta[0] = logit(np.clip(prevalence, 1e-5, 1 - 1e-5))
    else:
        beta = initial.astype(np.float64, copy=True)

    def log_likelihood(value: np.ndarray) -> float:
        linear = np.clip(design @ value, -40, 40)
        return float(np.sum(weights * (outcome * linear - np.logaddexp(0, linear))))

    for _ in range(max_iter):
        linear = np.clip(design @ beta, -40, 40)
        probability = expit(linear)
        score = design.T @ (weights * (outcome - probability))
        working = weights * probability * (1 - probability)
        information = design.T @ (design * working[:, None])
        information.flat[:: columns + 1] += 1e-8
        try:
            step = np.linalg.solve(information, score)
        except np.linalg.LinAlgError:
            step = np.linalg.lstsq(information, score, rcond=None)[0]
        current_ll = log_likelihood(beta)
        scale = 1.0
        candidate = beta + step
        while scale > 1 / 256 and log_likelihood(candidate) < current_ll:
            scale /= 2
            candidate = beta + scale * step
        beta = candidate
        if np.max(np.abs(scale * step)) < 1e-8:
            return beta, True
    return beta, False


def calibration_intercept_slope(outcome: np.ndarray, prediction: np.ndarray) -> tuple[float, float]:
    linear = logit(np.clip(prediction, 1e-6, 1 - 1e-6))
    design = np.column_stack([np.ones(len(linear)), linear])
    beta, _ = fit_weighted_logistic(
        design, outcome, np.ones(len(outcome), dtype=np.float64)
    )
    return float(beta[0]), float(beta[1])


def prepare_data(source: str, policy: str, severity_adjusted: bool) -> tuple[pd.DataFrame, str]:
    path = PRIVATE / f"{source}_locked_landmark_outcome_v2.parquet"
    frame = pl.read_parquet(path)
    burden_column = POLICIES[policy]
    columns = ["person_key_hash", "hospital_mortality", burden_column, "age", "sex"]
    if severity_adjusted:
        columns.append("severity_score")
    data = (
        frame.select(columns)
        .sort("person_key_hash")
        .rename({burden_column: "burden"})
        .to_pandas()
    )
    data = data.dropna(subset=["hospital_mortality", "burden", "age", "sex"])
    if severity_adjusted:
        data = data.dropna(subset=["severity_score"])
    if source == "sicdb":
        data["male"] = (data["sex"] == 735).astype(float)
        data["sex_unknown"] = 0.0
    elif source == "mimic_iv":
        data["male"] = (data["sex"] == "M").astype(float)
    else:
        data = data[data["sex"].isin(["Male", "Female"])].copy()
        data["male"] = (data["sex"] == "Male").astype(float)
    data["age10"] = (data["age"].astype(float) - data["age"].astype(float).mean()) / 10.0
    formula = "cr(burden, df=3, constraints='center') + age10 + male"
    if severity_adjusted:
        severity = data["severity_score"].astype(float)
        data["severity_z"] = (severity - severity.mean()) / severity.std(ddof=0)
        formula += " + severity_z"
    return data.reset_index(drop=True), formula


def design_variants(data: pd.DataFrame, formula: str) -> tuple[np.ndarray, dict[str, np.ndarray], np.ndarray, patsy.DesignInfo]:
    design_frame = patsy.dmatrix(formula, data, return_type="dataframe")
    design_info = design_frame.design_info
    variants: dict[str, np.ndarray] = {}
    for level in BURDEN_LEVELS:
        counterfactual = data.copy()
        counterfactual["burden"] = level
        variants[f"risk_{level:.2f}"] = np.asarray(
            patsy.build_design_matrices([design_info], counterfactual)[0],
            dtype=np.float64,
        )
    incremented = data.copy()
    incremented["burden"] = np.minimum(data["burden"].to_numpy() + 0.10, 1.0)
    increment_design = np.asarray(
        patsy.build_design_matrices([design_info], incremented)[0], dtype=np.float64
    )
    return np.asarray(design_frame, dtype=np.float64), variants, increment_design, design_info


def run_model(task: tuple[str, str, bool, int]) -> dict[str, Any]:
    source, policy, severity_adjusted, replicates = task
    data, formula = prepare_data(source, policy, severity_adjusted)
    outcome = data["hospital_mortality"].to_numpy(dtype=np.float64)
    design, variants, increment_design, _ = design_variants(data, formula)
    weights = np.ones(len(data), dtype=np.float64)
    beta, converged = fit_weighted_logistic(design, outcome, weights)
    prediction = expit(design @ beta)
    risk_points = {
        name: float(expit(matrix @ beta).mean()) for name, matrix in variants.items()
    }
    incremented_prediction = expit(increment_design @ beta)
    amrd = float(np.mean(incremented_prediction - prediction))
    mean_increment = float(
        np.mean(np.minimum(data["burden"].to_numpy() + 0.10, 1.0) - data["burden"])
    )
    calibration_intercept, calibration_slope = calibration_intercept_slope(
        outcome, prediction
    )

    rng = np.random.default_rng(stable_seed(f"{source}|{policy}|{severity_adjusted}"))
    names = [*variants, "average_marginal_risk_difference"]
    boot = {name: np.empty(replicates, dtype=np.float64) for name in names}
    failed = 0
    for iteration in range(replicates):
        sample = rng.integers(0, len(data), size=len(data))
        sample_weights = np.bincount(sample, minlength=len(data)).astype(np.float64)
        fitted, ok = fit_weighted_logistic(
            design, outcome, sample_weights, initial=beta
        )
        if not ok or not np.all(np.isfinite(fitted)):
            failed += 1
            for name in names:
                boot[name][iteration] = np.nan
            continue
        denominator = sample_weights.sum()
        base_prediction = expit(design @ fitted)
        for name, matrix in variants.items():
            boot[name][iteration] = float(
                np.sum(sample_weights * expit(matrix @ fitted)) / denominator
            )
        boot["average_marginal_risk_difference"][iteration] = float(
            np.sum(
                sample_weights
                * (expit(increment_design @ fitted) - base_prediction)
            )
            / denominator
        )

    intervals = {}
    points = {**risk_points, "average_marginal_risk_difference": amrd}
    for name, point in points.items():
        valid = boot[name][np.isfinite(boot[name])]
        intervals[name] = {
            "estimate": point,
            "ci_low": float(np.quantile(valid, 0.025)),
            "ci_high": float(np.quantile(valid, 0.975)),
        }
    return {
        "source": source,
        "policy": policy,
        "model": "age_sex_severity" if severity_adjusted else "age_sex",
        "people": len(data),
        "deaths": int(outcome.sum()),
        "event_fraction": float(outcome.mean()),
        "burden_mean": float(data["burden"].mean()),
        "burden_p05": float(data["burden"].quantile(0.05)),
        "burden_median": float(data["burden"].median()),
        "burden_p95": float(data["burden"].quantile(0.95)),
        "mean_realized_increment_for_amrd": mean_increment,
        "design_columns": design.shape[1],
        "design_condition_number": float(np.linalg.cond(design)),
        "original_fit_converged": converged,
        "bootstrap_replicates": replicates,
        "bootstrap_failures": failed,
        "intervals": intervals,
        "performance": {
            "brier": float(brier_score_loss(outcome, prediction)),
            "auroc": float(roc_auc_score(outcome, prediction)),
            "auprc": float(average_precision_score(outcome, prediction)),
            "calibration_intercept": calibration_intercept,
            "calibration_slope": calibration_slope,
        },
        "interpretation": (
            "Association under a measurement policy; not a causal effect or device-truth comparison."
        ),
    }


def flatten(results: list[dict[str, Any]]) -> pl.DataFrame:
    rows = []
    for item in results:
        for estimand, values in item["intervals"].items():
            rows.append(
                {
                    "source": item["source"],
                    "policy": item["policy"],
                    "model": item["model"],
                    "people": item["people"],
                    "deaths": item["deaths"],
                    "estimand": estimand,
                    **values,
                }
            )
    return pl.DataFrame(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replicates", type=int, default=2_000)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    tasks = [
        (source, policy, severity, args.replicates)
        for source in ("sicdb", "mimic_iv", "eicu")
        for policy in POLICIES
        for severity in (False, True)
    ]
    results = []
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(run_model, task): task for task in tasks}
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda item: (item["source"], item["policy"], item["model"]))
    output = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "protocol_version": "2.0 pre-result restart",
        "outcome": "subsequent hospital mortality after 24-hour ICU landmark",
        "causal_claim": False,
        "models": results,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    TABLES.mkdir(parents=True, exist_ok=True)
    (RESULTS / "locked_outcome_models_v2.json").write_text(
        json.dumps(output, indent=2) + "\n", encoding="utf-8"
    )
    flatten(results).write_csv(TABLES / "locked_outcome_estimands_v2.csv")
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
