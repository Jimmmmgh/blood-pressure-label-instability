"""Create publication-ready, source-backed figures for the manuscript."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
from PIL import Image
import polars as pl


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
TABLES = ROOT / "tables"
PRIVATE = ROOT / "analysis" / "private"
FIGURES = ROOT / "figures"
SOURCE_DATA = FIGURES / "source_data"

COLORS = {
    "sicdb": "#0072B2",
    "mimic_iv": "#E69F00",
    "eicu": "#009E73",
    "arterial_only": "#0072B2",
    "cuff_only": "#E69F00",
    "any_sensor": "#009E73",
    "concordant_only": "#CC79A7",
    "neutral": "#555555",
    "fail": "#D55E00",
}
LABELS = {"sicdb": "SICdb", "mimic_iv": "MIMIC-IV", "eicu": "eICU"}
POLICY_LABELS = {
    "arterial_only": "Arterial only",
    "cuff_only": "Cuff only",
    "any_sensor": "Any sensor",
    "concordant_only": "Concordant only",
}


def configure() -> None:
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "DejaVu Sans"],
            "font.size": 7.5,
            "axes.labelsize": 8,
            "axes.titlesize": 8,
            "xtick.labelsize": 6.5,
            "ytick.labelsize": 6.5,
            "legend.fontsize": 6.5,
            "axes.linewidth": 0.7,
            "lines.linewidth": 1.2,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "savefig.transparent": False,
        }
    )


def clean_axis(axis: plt.Axes) -> None:
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.tick_params(width=0.6, length=3)


def label_panel(axis: plt.Axes, letter: str) -> None:
    axis.text(
        -0.12,
        1.06,
        letter,
        transform=axis.transAxes,
        fontsize=10,
        fontweight="bold",
        va="top",
    )


def save(fig: plt.Figure, stem: str) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES / f"{stem}.pdf", bbox_inches="tight")
    fig.savefig(FIGURES / f"{stem}.svg", bbox_inches="tight")
    png = FIGURES / f"{stem}.png"
    fig.savefig(png, dpi=600, bbox_inches="tight")
    with Image.open(png) as image:
        image.convert("L").save(FIGURES / f"{stem}_grayscale_qa.png", dpi=(300, 300))
    plt.close(fig)


def figure2() -> None:
    primary = json.loads((RESULTS / "measurement_primary_v2.json").read_text())
    shifts = json.loads((RESULTS / "policy_burden_shifts_v2.json").read_text())
    by_source = {item["source"]: item for item in primary["sources"]}
    order = ["sicdb", "mimic_iv", "eicu"]
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.4), constrained_layout=True)
    ax_a, ax_b, ax_c, ax_d = axes.ravel()

    rows = []
    for y, source in enumerate(order[::-1]):
        values = by_source[source]["estimands"]["ccd_fraction"]
        x = 100 * values["estimate"]
        low = 100 * values["ci_low"]
        high = 100 * values["ci_high"]
        ax_a.errorbar(
            x,
            y,
            xerr=[[x - low], [high - x]],
            fmt="o",
            color=COLORS[source],
            capsize=2.5,
            markersize=5,
        )
        ax_a.text(high + 0.25, y, f"{x:.1f}%", va="center", fontsize=6.5)
        rows.append(
            {
                "source": LABELS[source],
                "people": by_source[source]["people"],
                "pairs": by_source[source]["pairs"],
                "estimate_percent": x,
                "ci_low_percent": low,
                "ci_high_percent": high,
            }
        )
    ax_a.set_yticks(range(3), [LABELS[item] for item in order[::-1]])
    ax_a.set_xlim(0, 18)
    ax_a.set_xlabel("Clinically consequential discordance (%)")
    ax_a.axvline(5, color="#999999", linestyle="--", linewidth=0.8)
    ax_a.text(5.15, 2.35, "predefined 5% gate", color="#666666", fontsize=6)
    clean_axis(ax_a)
    label_panel(ax_a, "A")
    pl.DataFrame(rows).write_csv(SOURCE_DATA / "figure2a_primary_ccd.csv")

    metrics = [
        ("threshold_discordant_fraction", "Threshold discordance", "o"),
        ("large_discordance_fraction", "|Difference| ≥10 mmHg", "s"),
        ("review_fraction", "Review / indeterminate", "^"),
    ]
    rows = []
    offsets = [-0.18, 0, 0.18]
    for xbase, source in enumerate(order):
        for offset, (metric, label, marker) in zip(offsets, metrics):
            values = by_source[source]["estimands"][metric]
            estimate = 100 * values["estimate"]
            low = 100 * values["ci_low"]
            high = 100 * values["ci_high"]
            ax_b.errorbar(
                xbase + offset,
                estimate,
                yerr=[[estimate - low], [high - estimate]],
                fmt=marker,
                color=COLORS[source],
                markerfacecolor="white" if metric != "review_fraction" else COLORS[source],
                capsize=2,
                markersize=4.5,
            )
            rows.append(
                {
                    "source": LABELS[source],
                    "estimand": label,
                    "estimate_percent": estimate,
                    "ci_low_percent": low,
                    "ci_high_percent": high,
                }
            )
    ax_b.set_xticks(range(3), [LABELS[item] for item in order])
    ax_b.set_ylabel("Patient-weighted paired observations (%)")
    ax_b.set_ylim(0, 55)
    ax_b.legend(
        [
            Line2D([0], [0], marker=marker, color="#555555", linestyle="none", markerfacecolor="white" if i < 2 else "#555555")
            for i, (_, _, marker) in enumerate(metrics)
        ],
        [label for _, label, _ in metrics],
        frameon=False,
        loc="upper left",
    )
    clean_axis(ax_b)
    label_panel(ax_b, "B")
    pl.DataFrame(rows).write_csv(SOURCE_DATA / "figure2b_secondary_states.csv")

    rows = []
    for y, source in enumerate(order[::-1]):
        agreement = by_source[source]["agreement"]
        mean = agreement["mean_bias"]["estimate"]
        lower = agreement["lower_loa"]["estimate"]
        upper = agreement["upper_loa"]["estimate"]
        ax_c.hlines(y, lower, upper, color=COLORS[source], linewidth=3, alpha=0.75)
        ax_c.plot(mean, y, "o", color="black", markersize=4)
        rows.append(
            {
                "source": LABELS[source],
                "mean_bias": mean,
                "lower_pair_level_dispersion_limit": lower,
                "upper_pair_level_dispersion_limit": upper,
            }
        )
    ax_c.axvline(0, color="#777777", linestyle="--", linewidth=0.8)
    ax_c.set_yticks(range(3), [LABELS[item] for item in order[::-1]])
    ax_c.set_xlabel("Cuff minus arterial MAP (mmHg)")
    ax_c.set_xlim(-65, 55)
    ax_c.text(-63, 2.3, "line: pair-level 95% dispersion limits\npoint: mean bias", fontsize=6)
    clean_axis(ax_c)
    label_panel(ax_c, "C")
    pl.DataFrame(rows).write_csv(SOURCE_DATA / "figure2c_agreement.csv")

    rows = []
    x = np.arange(3)
    width = 0.32
    absolute = [
        100 * shifts["sources"][source]["fraction_absolute_burden_shift_at_least_010"]
        for source in order
    ]
    stable = [100 * shifts["sources"][source]["stable_coverage"] for source in order]
    ax_d.bar(
        x - width / 2,
        absolute,
        width,
        color=[COLORS[s] for s in order],
        edgecolor="black",
        linewidth=0.4,
        label="|Burden shift| ≥10 percentage points",
    )
    ax_d.bar(
        x + width / 2,
        stable,
        width,
        color="white",
        edgecolor=[COLORS[s] for s in order],
        linewidth=1.2,
        hatch="///",
        label="Stable-policy coverage",
    )
    for index, source in enumerate(order):
        rows.append(
            {
                "source": LABELS[source],
                "absolute_burden_shift_ge_10pp_percent": absolute[index],
                "stable_policy_coverage_percent": stable[index],
            }
        )
    ax_d.set_xticks(x, [LABELS[s] for s in order])
    ax_d.set_ylim(0, 65)
    ax_d.set_ylabel("Patients or paired observations (%)")
    ax_d.legend(frameon=False, loc="upper right")
    clean_axis(ax_d)
    label_panel(ax_d, "D")
    pl.DataFrame(rows).write_csv(SOURCE_DATA / "figure2d_policy_impact.csv")
    save(fig, "Figure_2_measurement_instability")


def figure3() -> None:
    table = pl.read_csv(TABLES / "measurement_sensitivity_v2.csv")
    extended = pl.read_csv(TABLES / "measurement_extended_sensitivity_v2.csv")
    fig = plt.figure(figsize=(7.2, 5.0), constrained_layout=True)
    grid = fig.add_gridspec(2, 2, height_ratios=[1.15, 1])
    ax_a = fig.add_subplot(grid[0, :])
    ax_b = fig.add_subplot(grid[1, 0])
    ax_c = fig.add_subplot(grid[1, 1])

    specifications = [
        ("plausible_range", "20-200", "Range\n20-200"),
        ("plausible_range", "30-160", "Range\n30-160"),
        ("plausible_range", "40-130", "Range\n40-130"),
        ("minimum_pairs", "3", "Pairs\n≥3"),
        ("minimum_pairs", "5", "Pairs\n≥5"),
        ("minimum_pairs", "10", "Pairs\n≥10"),
        ("time_window_minutes", "0-360", "Window\n0-6 h"),
        ("time_window_minutes", "0-1440", "Window\n0-24 h"),
        ("hypotension_threshold", "60", "MAP\n<60"),
        ("hypotension_threshold", "65", "MAP\n<65"),
        ("hypotension_threshold", "70", "MAP\n<70"),
        ("large_difference_cutoff", "5", "|Δ|\n≥5"),
        ("large_difference_cutoff", "10", "|Δ|\n≥10"),
        ("large_difference_cutoff", "15", "|Δ|\n≥15"),
    ]
    matrix = np.zeros((3, len(specifications)))
    rows = []
    for row_index, source in enumerate(["sicdb", "mimic_iv", "eicu"]):
        for column_index, (family, level, label) in enumerate(specifications):
            match = table.filter(
                (pl.col("source") == source)
                & (pl.col("family") == family)
                & (pl.col("level").cast(pl.String) == level)
            )
            value = 100 * float(match["estimate"][0])
            matrix[row_index, column_index] = value
            rows.append(
                {
                    "source": LABELS[source],
                    "family": family,
                    "level": level,
                    "estimate_percent": value,
                }
            )
    image = ax_a.imshow(matrix, aspect="auto", cmap="cividis", vmin=5, vmax=22)
    for row_index in range(matrix.shape[0]):
        for column_index in range(matrix.shape[1]):
            color = "white" if matrix[row_index, column_index] < 10 else "black"
            ax_a.text(
                column_index,
                row_index,
                f"{matrix[row_index, column_index]:.1f}",
                ha="center",
                va="center",
                fontsize=5.5,
                color=color,
            )
    ax_a.set_yticks(range(3), ["SICdb", "MIMIC-IV", "eICU"])
    ax_a.set_xticks(range(len(specifications)), [item[2] for item in specifications])
    ax_a.tick_params(axis="x", length=0)
    ax_a.tick_params(axis="y", length=0)
    colorbar = fig.colorbar(image, ax=ax_a, pad=0.01, shrink=0.85)
    colorbar.set_label("CCD (%)", fontsize=7)
    label_panel(ax_a, "A")
    pl.DataFrame(rows).write_csv(SOURCE_DATA / "figure3a_sensitivity_heatmap.csv")

    eicu = pl.read_parquet(PRIVATE / "eicu_patient_measurement_summary_v2.parquet")
    sites = (
        eicu.group_by("hospital_key_hash")
        .agg(
            pl.len().alias("people"),
            (100 * pl.col("ccd_fraction").mean()).alias("ccd_percent"),
        )
        .filter(pl.col("people") >= 50)
        .sort("people")
    )
    ax_b.scatter(
        sites["people"],
        sites["ccd_percent"],
        s=np.sqrt(sites["people"].to_numpy()) * 2.2,
        color=COLORS["eicu"],
        alpha=0.65,
        edgecolor="black",
        linewidth=0.3,
    )
    overall = 100 * float(eicu["ccd_fraction"].mean())
    ax_b.axhline(overall, color="#333333", linestyle="--", linewidth=0.8)
    ax_b.set_xlabel("Eligible people per hospital")
    ax_b.set_ylabel("Hospital mean CCD (%)")
    ax_b.set_ylim(0, 24)
    ax_b.text(55, overall + 0.7, f"overall {overall:.1f}%", fontsize=6)
    clean_axis(ax_b)
    label_panel(ax_b, "B")
    sites.write_csv(SOURCE_DATA / "figure3b_eicu_hospitals.csv")

    rows = []
    analyses = ["first24_min1", "fullstay_min3"]
    markers = ["o", "s"]
    offsets = [-0.1, 0.1]
    for y, source in enumerate(["eicu", "mimic_iv", "sicdb"]):
        for analysis, marker, offset in zip(analyses, markers, offsets):
            match = extended.filter(
                (pl.col("source") == source) & (pl.col("analysis") == analysis)
            )
            estimate = 100 * float(match["ccd_fraction"][0])
            low = 100 * float(match["ci_low"][0])
            high = 100 * float(match["ci_high"][0])
            ax_c.errorbar(
                estimate,
                y + offset,
                xerr=[[estimate - low], [high - estimate]],
                fmt=marker,
                color=COLORS[source],
                markerfacecolor="white" if analysis == "first24_min1" else COLORS[source],
                capsize=2,
            )
            rows.append(
                {
                    "source": LABELS[source],
                    "analysis": analysis,
                    "estimate_percent": estimate,
                    "ci_low_percent": low,
                    "ci_high_percent": high,
                    "people": int(match["people"][0]),
                }
            )
    ax_c.set_yticks(range(3), ["eICU", "MIMIC-IV", "SICdb"])
    ax_c.set_xlim(10, 17)
    ax_c.set_xlabel("CCD (%)")
    ax_c.legend(
        [
            Line2D([0], [0], marker="o", color="#555555", markerfacecolor="white", linestyle="none"),
            Line2D([0], [0], marker="s", color="#555555", markerfacecolor="#555555", linestyle="none"),
        ],
        ["First 24 h, ≥1 pair", "Full stay, ≥3 pairs"],
        frameon=False,
        loc="lower right",
    )
    clean_axis(ax_c)
    label_panel(ax_c, "C")
    pl.DataFrame(rows).write_csv(SOURCE_DATA / "figure3c_extended_sensitivity.csv")
    save(fig, "Figure_3_robustness")


def figure4() -> None:
    outcomes = json.loads((RESULTS / "locked_outcome_models_v2.json").read_text())
    models = outcomes["models"]
    fig, axes = plt.subplots(2, 3, figsize=(7.2, 5.0), sharex=True, constrained_layout=True)
    sources = ["sicdb", "mimic_iv", "eicu"]
    policies = ["arterial_only", "cuff_only", "any_sensor", "concordant_only"]
    rows = []
    for row_index, model_name in enumerate(["age_sex", "age_sex_severity"]):
        for column_index, source in enumerate(sources):
            axis = axes[row_index, column_index]
            for y, policy in enumerate(policies[::-1]):
                item = next(
                    value
                    for value in models
                    if value["source"] == source
                    and value["policy"] == policy
                    and value["model"] == model_name
                )
                values = item["intervals"]["average_marginal_risk_difference"]
                estimate = 100 * values["estimate"]
                low = 100 * values["ci_low"]
                high = 100 * values["ci_high"]
                axis.errorbar(
                    estimate,
                    y,
                    xerr=[[estimate - low], [high - estimate]],
                    fmt="o",
                    color=COLORS[policy],
                    capsize=2,
                    markersize=4.5,
                )
                rows.append(
                    {
                        "source": LABELS[source],
                        "model": model_name,
                        "policy": POLICY_LABELS[policy],
                        "people": item["people"],
                        "deaths": item["deaths"],
                        "risk_difference_percentage_points": estimate,
                        "ci_low": low,
                        "ci_high": high,
                    }
                )
            axis.axvline(0, color="#777777", linestyle="--", linewidth=0.8)
            axis.set_xlim(-1.6, 3.1)
            axis.set_yticks(range(4), [POLICY_LABELS[item] for item in policies[::-1]] if column_index == 0 else [])
            if row_index == 0:
                axis.set_title(LABELS[source], fontweight="bold")
            clean_axis(axis)
    axes[0, 0].set_ylabel("Age/sex adjusted")
    axes[1, 0].set_ylabel("Age/sex + severity adjusted")
    label_panel(axes[0, 0], "A")
    label_panel(axes[1, 0], "B")
    fig.supxlabel("Mortality risk difference (percentage points)", fontsize=8)
    pl.DataFrame(rows).write_csv(SOURCE_DATA / "figure4_outcome_policy_models.csv")
    save(fig, "Figure_4_outcome_sensitivity")


def figure5() -> None:
    data = json.loads((RESULTS / "vitaldb_waveform_substudy_v2.json").read_text())
    fig = plt.figure(figsize=(7.2, 4.2), constrained_layout=True)
    grid = fig.add_gridspec(2, 2, width_ratios=[1.05, 1])
    ax_a = fig.add_subplot(grid[:, 0])
    ax_b = fig.add_subplot(grid[0, 1])
    ax_c = fig.add_subplot(grid[1, 1])

    flow = [
        ("One operation per subject", data["tasks"]),
        ("Aligned cuff triplet", data["triplet_aligned_cases"]),
        ("Plausible update proxy", data["cases_with_any_plausible_state_change"]),
        ("≥3 coverage-eligible windows", data["cases_with_at_least_three_coverage_eligible_windows"]),
        ("Technical subset", data["technical_subset_people"]),
    ]
    y = np.arange(len(flow))[::-1]
    values = [item[1] for item in flow]
    ax_a.barh(y, values, color="#56B4E9", edgecolor="black", linewidth=0.4)
    ax_a.set_yticks(y, [item[0] for item in flow])
    ax_a.set_xlabel("Operations / people")
    ax_a.set_xlim(0, 3000)
    for position, value in zip(y, values):
        ax_a.text(value + 35, position, f"{value:,}", va="center", fontsize=6.5)
    clean_axis(ax_a)
    label_panel(ax_a, "A")

    failures = data["quality_failure_counts_among_coverage_eligible"]
    failure_rows = [
        ("Out-of-range >5%", failures["outside_fraction_above_005"]),
        ("Amplitude >150 mmHg", failures["amplitude_above_150"]),
        ("Amplitude <10 mmHg", failures["amplitude_below_10"]),
        ("Missing run >5 s", failures["missing_run_above_5_seconds"]),
        ("Flat adjacent ≥95%", failures["flat_adjacent_fraction_at_least_095"]),
    ]
    percentages = [100 * value / data["coverage_eligible_windows"] for _, value in failure_rows]
    y = np.arange(len(failure_rows))[::-1]
    ax_b.barh(y, percentages, color=COLORS["fail"], alpha=0.8)
    ax_b.set_yticks(y, [item[0] for item in failure_rows])
    ax_b.set_xlabel("Coverage-eligible windows failing criterion (%)")
    ax_b.set_xlim(0, 55)
    clean_axis(ax_b)
    label_panel(ax_b, "B")

    pass_percent = 100 * data["quality_pass_fraction_among_coverage_eligible"]
    ccd_values = data["selected_equal_person_ccd_fraction"]
    ax_c.bar([0], [pass_percent], width=0.45, color="#999999", edgecolor="black")
    ax_c.axhline(80, color=COLORS["fail"], linestyle="--", linewidth=1)
    ax_c.text(0.25, 81.5, "predefined 80% gate", color=COLORS["fail"], fontsize=6)
    ax_c.set_xlim(-0.5, 1.6)
    ax_c.set_ylim(0, 100)
    ax_c.set_xticks([0, 1], ["Waveform QA\npass", "Selected\nCCD"])
    ax_c.set_ylabel("Percent")
    ccd_est = 100 * ccd_values["estimate"]
    ccd_low = 100 * ccd_values["ci_low"]
    ccd_high = 100 * ccd_values["ci_high"]
    ax_c.errorbar(
        1,
        ccd_est,
        yerr=[[ccd_est - ccd_low], [ccd_high - ccd_est]],
        fmt="o",
        color=COLORS["sicdb"],
        capsize=3,
    )
    ax_c.text(0, pass_percent + 3, f"{pass_percent:.1f}%\nNO-GO", ha="center", fontsize=7, fontweight="bold")
    ax_c.text(1, ccd_high + 3, f"{ccd_est:.1f}%", ha="center", fontsize=7)
    clean_axis(ax_c)
    ax_c.text(
        -0.12,
        1.15,
        "C",
        transform=ax_c.transAxes,
        fontsize=10,
        fontweight="bold",
        va="top",
    )

    pl.DataFrame(
        [{"stage": label, "count": value} for label, value in flow]
    ).write_csv(SOURCE_DATA / "figure5a_vitaldb_flow.csv")
    pl.DataFrame(
        [
            {
                "failure_criterion": label,
                "count": count,
                "percent": percent,
            }
            for (label, count), percent in zip(failure_rows, percentages)
        ]
    ).write_csv(SOURCE_DATA / "figure5b_vitaldb_failures.csv")
    pl.DataFrame(
        [
            {
                "quality_pass_percent": pass_percent,
                "quality_gate_percent": 80.0,
                "selected_ccd_percent": ccd_est,
                "selected_ccd_ci_low": ccd_low,
                "selected_ccd_ci_high": ccd_high,
            }
        ]
    ).write_csv(SOURCE_DATA / "figure5c_vitaldb_selected.csv")
    save(fig, "Figure_5_vitaldb_waveform_no_go")


def main() -> int:
    configure()
    SOURCE_DATA.mkdir(parents=True, exist_ok=True)
    figure2()
    figure3()
    figure4()
    figure5()
    print(f"Figures written to {FIGURES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
