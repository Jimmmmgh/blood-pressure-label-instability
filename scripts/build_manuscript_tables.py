"""Create manuscript-ready aggregate tables from frozen project outputs."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRIVATE_ROOT = PROJECT_ROOT / "analysis" / "private"
TABLE_ROOT = PROJECT_ROOT / "tables"
RESULT_ROOT = PROJECT_ROOT / "results"

SOURCES = {
    "sicdb": "SICdb",
    "mimic_iv": "MIMIC-IV",
    "eicu": "eICU",
}


def sex_is_female(source: str, value: object) -> bool:
    if source == "sicdb":
        return value == 736
    if source == "mimic_iv":
        return value == "F"
    return value == "Female"


def fmt_n_pct(n: int, denominator: int) -> str:
    return f"{n} ({100 * n / denominator:.1f}%)"


def fmt_ci(estimate: float, low: float, high: float, scale: float = 100) -> str:
    return f"{estimate * scale:.1f} ({low * scale:.1f} to {high * scale:.1f})"


def build_table1() -> pd.DataFrame:
    rows = []
    for source, label in SOURCES.items():
        pairs = pd.read_parquet(PRIVATE_ROOT / f"{source}_primary_pairs_v1.parquet")
        people = (
            pairs.groupby("person_key_hash", observed=True)
            .agg(age=("age", "first"), sex=("sex", "first"), pairs=("ccd", "size"))
            .reset_index()
        )
        female = int(people["sex"].map(lambda value: sex_is_female(source, value)).sum())
        unknown = 0
        if source == "sicdb":
            unknown = int((people["sex"] == 737).sum())
        elif source == "eicu":
            unknown = int((~people["sex"].isin(["Male", "Female"])).sum())
        age_q = people["age"].quantile([0.25, 0.5, 0.75])
        pair_q = people["pairs"].quantile([0.25, 0.5, 0.75])
        outcome_flow = json.loads(
            (PROJECT_ROOT / "audit" / "outcome_flow" / f"{source}_locked_outcome_flow_v2.json").read_text(
                encoding="utf-8"
            )
        )
        rows.append(
            {
                "Source": label,
                "Independent people": len(people),
                "Paired observations": len(pairs),
                "Age, median (IQR), y": f"{age_q.loc[0.5]:.0f} ({age_q.loc[0.25]:.0f}-{age_q.loc[0.75]:.0f})",
                "Female, n (%)": fmt_n_pct(female, len(people)),
                "Unknown sex, n (%)": fmt_n_pct(unknown, len(people)),
                "Pairs/person, median (IQR)": f"{pair_q.loc[0.5]:.0f} ({pair_q.loc[0.25]:.0f}-{pair_q.loc[0.75]:.0f})",
                "24-h landmark people": outcome_flow["landmark_people"],
                "Subsequent hospital deaths": fmt_n_pct(
                    outcome_flow["hospital_deaths"], outcome_flow["landmark_people"]
                ),
            }
        )
    table = pd.DataFrame(rows)
    table.to_csv(TABLE_ROOT / "Table_1_cohort_characteristics.csv", index=False)
    return table


def build_table2() -> pd.DataFrame:
    primary = json.loads((RESULT_ROOT / "measurement_primary_v2.json").read_text(encoding="utf-8"))
    burden = json.loads((RESULT_ROOT / "policy_burden_shifts_v2.json").read_text(encoding="utf-8"))["sources"]
    rows = []
    for source in primary["sources"]:
        key = source["source"]
        e = source["estimands"]
        agreement = source["agreement"]
        rows.append(
            {
                "Source": source["source_label"],
                "People": source["people"],
                "Pairs": source["pairs"],
                "CCD, % (95% CI)": fmt_ci(**{
                    "estimate": e["ccd_fraction"]["estimate"],
                    "low": e["ccd_fraction"]["ci_low"],
                    "high": e["ccd_fraction"]["ci_high"],
                }),
                "Threshold discordance, %": f"{100 * e['threshold_discordant_fraction']['estimate']:.1f}",
                "Absolute cuff-arterial difference >=10 mmHg, %": f"{100 * e['large_discordance_fraction']['estimate']:.1f}",
                "Review/indeterminate, %": f"{100 * e['review_fraction']['estimate']:.1f}",
                "Mean bias, cuff-arterial, mmHg": f"{agreement['mean_bias']['estimate']:.1f}",
                "Descriptive pair-level 95% dispersion limits, mmHg": f"{agreement['lower_loa']['estimate']:.1f} to {agreement['upper_loa']['estimate']:.1f}",
                "Patients with >=10-point burden shift, %": f"{100 * burden[key]['fraction_absolute_burden_shift_at_least_010']:.1f}",
                "Stable-policy coverage, %": f"{100 * burden[key]['stable_coverage']:.1f}",
            }
        )
    table = pd.DataFrame(rows)
    table.to_csv(TABLE_ROOT / "Table_2_measurement_results.csv", index=False)
    return table


def build_table3() -> pd.DataFrame:
    models = json.loads((RESULT_ROOT / "locked_outcome_models_v2.json").read_text(encoding="utf-8"))["models"]
    policy_labels = {
        "arterial_only": "Arterial only",
        "cuff_only": "Cuff only",
        "any_sensor": "Any sensor",
        "concordant_only": "Concordant only",
    }
    model_labels = {"age_sex": "Age/sex", "age_sex_severity": "Age/sex + severity"}
    rows = []
    for source in SOURCES:
        for policy in policy_labels:
            for model_name in model_labels:
                record = next(
                    item
                    for item in models
                    if item["source"] == source
                    and item["policy"] == policy
                    and item["model"] == model_name
                )
                value = record["intervals"]["average_marginal_risk_difference"]
                rows.append(
                    {
                        "Source": SOURCES[source],
                        "Policy": policy_labels[policy],
                        "Adjustment": model_labels[model_name],
                        "People": record["people"],
                        "Deaths": record["deaths"],
                        "AMRD per ~10-point burden increase, percentage points (95% CI)": fmt_ci(
                            value["estimate"], value["ci_low"], value["ci_high"]
                        ),
                        "AUROC": f"{record['performance']['auroc']:.3f}",
                        "Brier score": f"{record['performance']['brier']:.3f}",
                    }
                )
    table = pd.DataFrame(rows)
    table.to_csv(TABLE_ROOT / "Supplementary_Table_outcome_models.csv", index=False)
    compact = (
        table.pivot_table(
            index=["Source", "Policy"],
            columns="Adjustment",
            values="AMRD per ~10-point burden increase, percentage points (95% CI)",
            aggfunc="first",
        )
        .reset_index()
        .rename(
            columns={
                "Age/sex": "Age/sex-adjusted AMRD, percentage points (95% CI)",
                "Age/sex + severity": "Severity-adjusted AMRD, percentage points (95% CI)",
            }
        )
    )
    source_order = {label: index for index, label in enumerate(SOURCES.values())}
    policy_order = {label: index for index, label in enumerate(policy_labels.values())}
    compact["_source_order"] = compact["Source"].map(source_order)
    compact["_policy_order"] = compact["Policy"].map(policy_order)
    compact = compact.sort_values(["_source_order", "_policy_order"]).drop(
        columns=["_source_order", "_policy_order"]
    )
    compact.to_csv(TABLE_ROOT / "Table_3_outcome_sensitivity.csv", index=False)
    return compact


def markdown_table(frame: pd.DataFrame) -> str:
    headers = [str(column) for column in frame.columns]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in frame.itertuples(index=False, name=None):
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(lines)


def main() -> int:
    TABLE_ROOT.mkdir(parents=True, exist_ok=True)
    table1 = build_table1()
    table2 = build_table2()
    table3 = build_table3()
    output = [
        "**Table 1. Source-specific cohort characteristics**",
        "",
        markdown_table(table1),
        "",
        "**Table 1 legend.** The first eligible adult ICU stay/case per person with at least three valid first-day pairs was retained. Landmark counts precede the exclusion of two eICU participants with unknown sex from adjusted models; the resulting common-adjustment population included 7,292 participants and 1,071 deaths.",
        "",
        "**Table 2. Measurement-source instability**",
        "",
        markdown_table(table2),
        "",
        "**Table 2 legend.** CCD denotes clinically consequential discordance: exactly one modality below 65 mmHg plus an absolute inter-modality difference >=10 mmHg. Proportions are equal-person weighted. Stable-policy coverage is the proportion outside the review/indeterminate state. Dispersion limits are the pair-level mean cuff-arterial difference +/-1.96 SD, with the patient as the bootstrap resampling unit; they are not controlled repeated-measures agreement estimates.",
        "",
        "**Table 3. Policy-specific mortality association sensitivity**",
        "",
        markdown_table(table3),
        "",
        "**Table 3 legend.** AMRD is the standardized average marginal risk difference from adding 0.10 to each patient's burden, capped at 1.0; the mean realized increment was approximately 0.09-0.10. Severity scores were SAPS 3, APS III, and APACHE IVa in SICdb, MIMIC-IV, and eICU. All values are prognostic associations, not causal effects.",
    ]
    (TABLE_ROOT / "MAIN_TABLES.md").write_text("\n".join(output) + "\n", encoding="utf-8")
    print("Wrote three manuscript tables")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
