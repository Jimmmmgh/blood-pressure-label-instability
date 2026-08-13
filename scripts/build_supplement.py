from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "tables"
RESULTS = ROOT / "results"
OUT = ROOT / "manuscript" / "SUPPLEMENTARY_MATERIAL.md"


SOURCE_LABEL = {"sicdb": "SICdb", "mimic_iv": "MIMIC-IV", "eicu": "eICU"}


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def md_table(headers: list[str], body: list[list[object]]) -> str:
    def clean(value: object) -> str:
        if value is None:
            return ""
        return str(value).replace("|", "\\|").replace("\n", " ")

    lines = [
        "| " + " | ".join(map(clean, headers)) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    lines.extend("| " + " | ".join(clean(v) for v in row) + " |" for row in body)
    return "\n".join(lines)


def pct(value: str | float, digits: int = 1) -> str:
    return f"{100 * float(value):.{digits}f}%"


def ci_pct(est: str, low: str, high: str) -> str:
    return f"{pct(est)} ({pct(low)}-{pct(high)})"


def q_value(value: str) -> str:
    if value == "":
        return "Reference"
    x = float(value)
    return "<0.001" if x < 0.001 else f"{x:.3f}"


def main() -> None:
    sensitivity = rows(TABLES / "measurement_sensitivity_v2.csv")
    extended = rows(TABLES / "measurement_extended_sensitivity_v2.csv")
    remaining = rows(TABLES / "remaining_prespecified_sensitivities_v2_1.csv")
    subgroups = rows(TABLES / "measurement_subgroups_v2.csv")
    outcome = rows(TABLES / "Supplementary_Table_outcome_models.csv")
    eicu_mi = rows(TABLES / "eicu_multiple_imputation_outcome_sensitivity_v2_1.csv")
    gate = json.loads((RESULTS / "measurement_gate_report_v2.json").read_text(encoding="utf-8"))
    vital = json.loads((RESULTS / "vitaldb_waveform_substudy_v2.json").read_text(encoding="utf-8"))

    sensitivity_table = []
    for r in sensitivity:
        sensitivity_table.append([
            SOURCE_LABEL[r["source"]],
            r["family"].replace("_", " "),
            r["level"],
            f'{int(r["people"]):,}',
            f'{int(r["pairs"]):,}',
            ci_pct(r["estimate"], r["ci_low"], r["ci_high"]),
            pct(r["pair_weighted"]),
        ])

    extended_table = []
    for r in extended:
        extended_table.append([
            SOURCE_LABEL[r["source"]],
            r["analysis"].replace("_", " "),
            f'{int(r["people"]):,}',
            f'{int(r["pairs"]):,}',
            ci_pct(r["ccd_fraction"], r["ci_low"], r["ci_high"]),
            pct(r["pair_weighted_ccd"]),
            f'{float(r["pairs_per_person_median"]):.0f} ({float(r["pairs_per_person_p25"]):.0f}-{float(r["pairs_per_person_p75"]):.0f})',
        ])

    remaining_labels = {
        "all_eligible_stays_first24": "All eligible first-day stays",
        "exclude_duplicate_timestamps": "Exclude duplicate timestamps",
        "pairs_in_at_least_two_hours": "Pairs span >=2 hours",
    }
    remaining_table = []
    for r in remaining:
        stays = r.get("stays", "")
        remaining_table.append([
            SOURCE_LABEL[r["source"]],
            remaining_labels.get(r["analysis"], r["analysis"].replace("_", " ")),
            f'{int(r["people"]):,}',
            f'{int(float(stays)):,}' if stays else "-",
            f'{int(r["pairs"]):,}',
            ci_pct(r["ccd_fraction"], r["ci_low"], r["ci_high"]),
            pct(r["pair_weighted_ccd"]),
        ])

    subgroup_table = []
    for r in subgroups:
        contrast = "Reference"
        contrast_ci = ""
        if r["contrast_vs_reference"] != "0.0" or r["level"] != r["reference"]:
            if r["contrast_vs_reference"]:
                contrast = f'{100 * float(r["contrast_vs_reference"]):+.1f} pp'
                contrast_ci = (
                    f'{100 * float(r["contrast_ci_low"]):+.1f} to '
                    f'{100 * float(r["contrast_ci_high"]):+.1f} pp'
                )
        subgroup_table.append([
            SOURCE_LABEL[r["source"]],
            r["family"].replace("_", " "),
            r["level"],
            r["reference"],
            f'{int(r["people"]):,}',
            ci_pct(r["estimate"], r["ci_low"], r["ci_high"]),
            contrast,
            contrast_ci,
            q_value(r["bh_q_value"]),
        ])

    outcome_headers = list(outcome[0].keys())
    outcome_table = [[r[h] for h in outcome_headers] for r in outcome]

    policy_labels = {
        "arterial_only": "Arterial only",
        "cuff_only": "Cuff only",
        "any_sensor": "Any sensor",
        "concordant_only": "Concordant only",
    }
    mi_table = []
    for r in eicu_mi:
        mi_table.append([
            policy_labels[r["policy"]],
            f'{int(r["people"]):,}',
            f'{int(r["severity_missing"]):,} ({float(r["severity_missing_percent"]):.1f}%)',
            f'{int(r["imputations"])} x {int(r["bootstrap_replicates_per_imputation"]):,}',
            (
                f'{float(r["mi_amrd_percentage_points"]):.2f} '
                f'({float(r["mi_ci_low_percentage_points"]):.2f} to '
                f'{float(r["mi_ci_high_percentage_points"]):.2f})'
            ),
            f'{float(r["complete_case_amrd_percentage_points"]):.2f}',
            f'{float(r["difference_mi_minus_complete_case_percentage_points"]):+.2f}',
        ])

    calendar_rows = []
    for source, data in gate["calendar_diagnostics"].items():
        if data.get("status") == "not_interpretable":
            calendar_rows.append([SOURCE_LABEL[source], "Not interpretable", "-", data["reason"]])
            continue
        for item in data["year_strata"]:
            calendar_rows.append([
                SOURCE_LABEL[source],
                item["calendar_year"],
                f'{item["people"]:,}',
                pct(item["mean_ccd_fraction"]),
            ])

    site = gate["eicu_site_diagnostics"]
    failure_counts = vital["quality_failure_counts_among_coverage_eligible"]
    vital_rows = [
        ["Tasks attempted", f'{vital["tasks"]:,}'],
        ["Tasks loaded successfully", f'{vital["load_success"]:,}'],
        ["Cases with aligned cuff triplet", f'{vital["triplet_aligned_cases"]:,}'],
        ["Plausible cuff state-change episodes", f'{vital["plausible_state_change_episodes"]:,}'],
        ["Coverage-eligible waveform windows", f'{vital["coverage_eligible_windows"]:,}'],
        ["Cases with at least three coverage-eligible windows", f'{vital["cases_with_at_least_three_coverage_eligible_windows"]:,}'],
        ["Waveform-quality-pass windows", f'{vital["waveform_quality_pass_windows"]:,}'],
        ["Quality-pass fraction", pct(vital["quality_pass_fraction_among_coverage_eligible"])],
        ["Prespecified pass threshold", "80.0%"],
        ["Raw-waveform gate", "NO-GO"],
        ["Numeric-waveform-concordant windows", f'{vital["numeric_waveform_concordant_windows"]:,}'],
        ["Selected technical-subset windows", f'{vital["technical_subset_windows"]:,}'],
        ["Selected technical-subset people", f'{vital["technical_subset_people"]:,}'],
        ["Selected equal-person CCD", ci_pct(
            vital["selected_equal_person_ccd_fraction"]["estimate"],
            vital["selected_equal_person_ccd_fraction"]["ci_low"],
            vital["selected_equal_person_ccd_fraction"]["ci_high"],
        )],
    ]
    failure_rows = [
        ["More than 5% of samples outside 20-250 mmHg", f'{failure_counts["outside_fraction_above_005"]:,}'],
        ["95th-5th percentile amplitude below 10 mmHg", f'{failure_counts["amplitude_below_10"]:,}'],
        ["95th-5th percentile amplitude above 150 mmHg", f'{failure_counts["amplitude_above_150"]:,}'],
        ["At least 95% adjacent differences below 0.1 mmHg", f'{failure_counts["flat_adjacent_fraction_at_least_095"]:,}'],
        ["Nonfinite run longer than 5 seconds", f'{failure_counts["missing_run_above_5_seconds"]:,}'],
    ]

    strobe = [
        ["1", "Title and abstract", "Title; structured abstract"],
        ["2-3", "Background and objectives", "Background; final paragraph states four aims"],
        ["4", "Study design", "Methods: Study design, protocol, and reporting"],
        ["5", "Setting", "Methods: Data sources and roles"],
        ["6", "Participants", "Methods: Population and pairing; Figure 2A"],
        ["7", "Variables", "Methods: Measurement states and estimands; protocol variable contract"],
        ["8", "Data sources/measurement", "Methods: Data sources and roles; Supplementary Methods S1"],
        ["9", "Bias", "Methods: symmetric event, equal-person estimand, outcome firewall; Discussion: Limitations"],
        ["10", "Study size", "Methods: protocol restart and census design; Supplementary Methods S2"],
        ["11", "Quantitative variables", "Methods: thresholds, burdens, splines, and sensitivity ranges"],
        ["12", "Statistical methods", "Methods: uncertainty, heterogeneity, sensitivity, and outcome analyses"],
        ["13", "Participant flow", "Results: Cohort construction; Figure 2A"],
        ["14", "Descriptive data", "Table 1"],
        ["15", "Outcome data", "Results: Outcome association sensitivity; Table 3"],
        ["16", "Main results", "Results: Primary measurement findings; Tables 2-3"],
        ["17", "Other analyses", "Figures 3-5; Supplementary Tables S1-S8"],
        ["18", "Key results", "Discussion: Principal findings"],
        ["19", "Limitations", "Discussion: Limitations"],
        ["20", "Interpretation", "Discussion: Interpretation and implications"],
        ["21", "Generalizability", "Discussion: Strengths and limitations"],
        ["22", "Funding", "Declarations: Funding"],
    ]

    text = f"""# Supplementary material

## Blood pressure is not a single label: a cross-database retrospective measurement-method study of hypotension phenotype instability in critical care

**Authors:** Chaoyuan Jin, Sucheng Mu, Qingxia Dai, Xingxing Ren, and Jie Shen  
**Equal contribution:** Chaoyuan Jin, Sucheng Mu, and Qingxia Dai contributed equally.  
**Co-corresponding authors:** Xingxing Ren and Jie Shen

**Version:** 2.1  
**Analysis freeze date:** 12 August 2026  
**Post-analysis QA correction date:** 13 August 2026  
**Random seed:** 20260812  
**Bootstrap replicates used for manuscript inference:** 2,000  

This supplement accompanies the main manuscript. It preserves source-specific acquisition semantics, negative results, protocol deviations and post-analysis corrections, completed prespecified sensitivity analyses, and the raw-waveform No-Go decision. Paired observations are repeated measurements; the person is the independent inferential unit throughout. The protocol package was locally frozen and hash-audited, but it was not externally preregistered or independently time-stamped.

## Supplementary Methods S1. Source-specific measurement semantics

| Source | Role | Arterial MAP | Cuff MAP | Primary alignment | Important interpretation boundary |
| --- | --- | --- | --- | --- | --- |
| SICdb 1.0.8 | Anchor | DataID 703, 60 float32 minute values per hourly blob | DataID 706, same serialization | Exact reconstructed minute | Routine-care values; not synchronized device-validation measurements |
| MIMIC-IV 3.1 | Single-center external validation | itemid 220052 | itemid 220181 | Exact charttime after within-modality median duplicate reduction | Equal charttime is an alignment proxy; age at ICU admission uses anchor_age + year(intime) - anchor_year |
| eICU-CRD 2.0 | Multicenter external validation | vitalperiodic.systemicmean, stored as a five-minute median | vitalaperiodic.noninvasivemean, irregular event | Exact patient-stay offset | Nominal offset does not make the underlying acquisition mechanisms identical |
| VitalDB 1.0.0 | Raw-waveform technical substudy | SNUADC/ART raw waveform plus Solar8000/ART_MBP numeric | State changes in the NIBP systolic/diastolic/MAP triplet | 60-second waveform window around a plausible cuff update | Identical repeated cuff states are unobservable; the quality gate failed |
| INSPIRE 1.4.2 | Quantization capacity stress | Public quantized MAP category | Public quantized MAP category | Non-overlapping operating-room bins | Category boundaries were not locally verified; continuous mmHg inference was prohibited |

Within each source, both modalities had to lie between 20 and 200 mmHg. The first eligible adult stay per person and first 24 hours were retained; at least three paired observations were required. No MAP value, timestamp, modality, pair membership, or outcome was imputed.

## Supplementary Methods S2. Protocol chronology and deviations

1. Version 1.0 of the protocol, statistical analysis plan, variable contract, and outcome firewall was locally frozen and hash-audited before aggregate pressure differences, CCD prevalence, subgroup contrasts, or outcomes were inspected. This was not external preregistration.
2. The original arbitrary SICdb feasibility gate required 2,000 eligible people. Outcome-blind extraction produced 1,510 people, so version 1.0 was closed as `NO-GO_CAPACITY`.
3. Before any source-level difference or outcome was summarized, a dated pre-result restart changed only the SICdb capacity threshold to 1,500. Endpoints, clinical thresholds, inclusion rules, bootstrap plan, and external-source gates were unchanged. Both manifests and hashes remain in the audit directory.
4. A post-analysis quality audit found that MIMIC-IV age had initially been read as `anchor_age` rather than advanced from `anchor_year` to ICU admission year. Version 2.1 uses `anchor_age + year(intime) - anchor_year`. Among 4,171 participants, 1,118 ages and 191 prespecified age strata changed; no participant, paired MAP value, CCD classification, or primary measurement estimate changed. The original frozen variable contract was preserved, and the addition of `anchor_year` is recorded in the dated correction file.
5. The initial eICU severity model used complete cases although APACHE IVa was 11.0% missing. Version 2.1 completed the prespecified multiple-imputation sensitivity with 20 imputations and 2,000 bootstraps per imputation; the complete-case model remains the main severity analysis.
6. Calendar year was prespecified but omitted from the original variable-contract JSON. Deidentified year alone was subsequently read for the calendar concentration gate; it did not change cohort construction or any estimand.
7. The statistical plan named Holm correction for a finite secondary measurement family. Tests against a zero prevalence were not performed because zero was clinically non-informative with these census-sized cohorts; effect estimates and patient-bootstrap intervals are reported instead. Exploratory subgroup contrasts use Benjamini-Hochberg control as prespecified.
8. The exploratory CCD-risk model was not pursued. The strongest candidate predictor, paired mean MAP, is computed from the same two measurements that define CCD, so a risk model would be partly circular and could be misread as a deployment model. This post-primary decision does not alter the confirmatory cohort, endpoint, uncertainty, sensitivity, or outcome analyses.
9. Residual-versus-mean, Breusch-Pagan, and conditional relative-difference diagnostics specified for agreement characterization were not performed. Their omission is a reported post-primary deviation; raw-scale signed and robust distribution summaries remain available, and no claim depends on homoscedasticity.
10. The VitalDB raw-waveform quality gate failed. The selected technical-subset estimate is retained only for auditability and is not promoted to validation or prevalence.

## Supplementary Methods S3. Outcome firewall and modeling

Outcome fields were physically absent from measurement-stage extracts. The firewall was released only after frozen hashes, deterministic boundary tests, capacity and signal gates, finite-value checks, bootstrap stability, sensitivity preservation, eICU site concentration, and interpretable calendar concentration all passed. Outcome models began at a 24-hour ICU landmark and modeled subsequent in-hospital mortality. Each source-policy combination used logistic regression with a restricted cubic spline for first-day hypotension burden. Common adjustment was age and sex; sensitivity models added SAPS 3, APS III, or APACHE IVa. Reported marginal risk differences are standardized associations and are not causal effects.

APACHE IVa was missing for 802 of 7,292 eICU participants in common-adjustment models. The version 2.1 missing-data sensitivity used 20 posterior Bayesian-ridge chained-equation imputations. The imputation model included subsequent mortality, age, sex, policy-specific burden, number of pairs, CCD, arterial-only burden, cuff-only burden, any-sensor burden, and stable-policy coverage. Each imputed dataset used 2,000 patient-bootstrap resamples; estimates were combined with Rubin's rules. Across four policies, 160,000 bootstrap model fits completed without failure. This sensitivity did not impute MAP, timestamps, modality, pair membership, sex, or outcome.

## Supplementary Table S1. Complete threshold and range sensitivity analyses

{md_table(["Source", "Family", "Level", "People", "Pairs", "Equal-person CCD, % (95% CI)", "Pair-weighted CCD"], sensitivity_table)}

## Supplementary Table S2. Expanded-population and full-stay sensitivity analyses

{md_table(["Source", "Analysis", "People", "Pairs", "Equal-person CCD, % (95% CI)", "Pair-weighted CCD", "Pairs/person, median (IQR)"], extended_table)}

The `first24 min1` analysis retains at least one first-day pair; `fullstay min3` extends the observation window while retaining at least three pairs. These populations were re-extracted and were not inferred from the primary cohort.

## Supplementary Table S3. Remaining prespecified cohort-rule sensitivities completed in version 2.1

{md_table(["Source", "Analysis", "People", "Stays", "Pairs", "Equal-person CCD, % (95% CI)", "Pair-weighted CCD"], remaining_table)}

For the all-stays analysis, multiple eligible stays were retained while the patient remained the resampling unit. The duplicate-exclusion analysis removes duplicated timestamps rather than relying on within-modality reduction. The two-hour analysis requires eligible pairs in at least two distinct clock hours; it was applied to all three sources as a conservative extension of the frozen requirement for MIMIC-IV and eICU.

## Supplementary Table S4. Prespecified subgroup analyses

{md_table(["Source", "Family", "Level", "Reference", "People", "CCD, % (95% CI)", "Contrast", "Contrast 95% CI", "BH q"], subgroup_table)}

Contrasts are percentage-point differences from the named reference. A q value is descriptive evidence within the source-specific exploratory family; comparisons of significance across subgroups are not made.

## Supplementary Table S5. Calendar and site concentration checks

{md_table(["Source", "Calendar stratum", "People", "Equal-person CCD or status"], calendar_rows)}

For eICU, {site["all_hospitals"]} hospitals contributed to the primary analytic cohort. {site["hospitals_with_at_least_50_people"]} hospitals had at least 50 eligible people. The largest hospital contributed {pct(site["largest_hospital_fraction_of_people"], 2)} of people. Among hospitals with at least 50 people, CCD estimates ranged from {pct(site["eligible_hospital_ccd_range"][0])} to {pct(site["eligible_hospital_ccd_range"][1])}; leave-one-hospital-out overall estimates ranged from {pct(site["leave_one_hospital_out_overall_range"][0])} to {pct(site["leave_one_hospital_out_overall_range"][1])}. Hospitals are deliberately unnamed and unranked.

## Supplementary Table S6. Full outcome model summary

{md_table(outcome_headers, outcome_table)}

AMRD is the standardized average marginal risk difference for adding 0.10 to each person's observed burden, capped at 1.0. Concordant-only models have lower coverage because observations in the review/indeterminate state are omitted. All models converged in all 2,000 patient-bootstrap resamples; the two eICU records with unknown sex were excluded from the common-adjustment model. Associations do not compare device truth and do not identify treatment effects.

## Supplementary Table S7. eICU multiple-imputation sensitivity for APACHE IVa missingness

{md_table(["Policy", "People", "APACHE IVa missing", "Imputations x bootstraps", "MI AMRD, percentage points (95% CI)", "Complete-case AMRD", "MI minus complete-case"], mi_table)}

The multiple-imputation estimates were close to the complete-case estimates and all intervals included zero. Rubin-rule intervals include both within- and between-imputation uncertainty. The analysis is a missing-data sensitivity, not a causal model or an external validation.

## Supplementary Table S8. VitalDB raw-waveform gate

{md_table(["Metric", "Value"], vital_rows)}

### Overlapping waveform-quality failure flags

{md_table(["Failure criterion", "Windows"], failure_rows)}

Failure flags overlap and therefore do not sum to the number of failing windows. The selected technical-subset estimate is conditioned on coverage, quality, and numeric-waveform concordance, as well as on observable cuff state changes. It is not a fourth prevalence estimate.

## Supplementary Result S1. INSPIRE quantization stress test

There were 166,581 non-overlapping, non-VitalDB-linked intraoperative paired bins in 30,992 operations. The public values were quantized categories, and locally available metadata did not provide verified category bounds. The prespecified interval-arithmetic analysis was therefore not estimable. No midpoint reconstruction, continuous agreement estimate, or threshold-discordance prevalence was produced.

## Supplementary Result S2. Negative and falsification evidence

- The primary pattern persisted under MAP ranges of 30-160 and 40-130 mmHg, minimum pair-count changes, first-six-hour restriction, full-stay extension, hypotension thresholds of 60 and 70 mmHg, and large-difference cutoffs of 5 and 15 mmHg.
- Equal-person and pair-weighted estimands differed in magnitude but did not reverse the cross-source conclusion.
- Retaining all eligible first-day stays yielded CCD estimates of 15.1%, 13.2%, and 13.4% in SICdb, MIMIC-IV, and eICU; duplicate exclusion yielded 15.0%, 13.2%, and 13.3%; requiring pairs in at least two hours yielded 15.4%, 13.1%, and 13.2%.
- SICdb +/-1-minute and +/-5-minute shifts and source-stratified between-person cuff-sequence permutations changed magnitude but did not eliminate discordance. These are alignment falsifications, not physiological null models.
- SICdb year-specific CCD ranged from {pct(gate["calendar_diagnostics"]["sicdb"]["year_specific_ccd_range"][0])} to {pct(gate["calendar_diagnostics"]["sicdb"]["year_specific_ccd_range"][1])}. eICU 2014 and 2015 estimates were {pct(gate["calendar_diagnostics"]["eicu"]["year_strata"][0]["mean_ccd_fraction"])} and {pct(gate["calendar_diagnostics"]["eicu"]["year_strata"][1]["mean_ccd_fraction"])}, respectively.
- MIMIC-IV calendar-year heterogeneity was not tested because patient-specific date shifting makes displayed years unsuitable for between-person calendar strata.
- The MIMIC-IV age correction changed descriptive and covariate-derived outputs but left all measurement rows and CCD classifications unchanged; the corrected age gradient remained descriptive and did not supply a mechanism.
- eICU multiple imputation moved severity-adjusted AMRDs by only +0.07 to +0.19 percentage points relative to complete cases and preserved null-compatible intervals.
- The raw-waveform gate failed despite complete loading of all {vital["tasks"]:,} planned VitalDB tasks, preventing a favorable selected subset from being described as validation.

### Prespecified or planned analyses not executed

- The exploratory measurement-stage CCD-risk model was not fitted because its strongest candidate predictor, paired mean MAP, is constructed from the same measurements that define CCD. This is a documented post-primary deviation and prevents circular performance claims.
- Residual-versus-mean, Breusch-Pagan, and conditional log/relative-difference agreement diagnostics were not performed. The raw-scale signed difference distribution, robust summaries, and explicit database-semantic limitations are retained; no claim depends on homoscedasticity.
- MIMIC-IV calendar-era analysis was not estimable because dates are shifted independently by patient. INSPIRE continuous agreement was not estimable because verified category boundaries were unavailable. VitalDB prevalence validation was prohibited by the failed quality gate.

## Supplementary Figure legends

**Supplementary Figure QA-1. Grayscale rendering check for Figure 2.** Automated grayscale conversion used only to verify separability; it is not a scientific result.

**Supplementary Figure QA-2. Grayscale rendering check for Figure 3.** Automated grayscale conversion used only to verify separability; it is not a scientific result.

**Supplementary Figure QA-3. Grayscale rendering check for Figure 4.** Automated grayscale conversion used only to verify separability; it is not a scientific result.

**Supplementary Figure QA-4. Grayscale rendering check for Figure 5.** Automated grayscale conversion used only to verify separability; it is not a scientific result.

## Reproducibility and data governance

All classifications are generated from locally hash-audited source-specific extracts by deterministic code. The original version 2.0 manifest is retained unchanged; the version 2.1 post-analysis record identifies corrected age-derived outputs, missing-data sensitivity, completed cohort-rule analyses, and regenerated checksums. The public release excludes protected source data, row-level extracts, credentials, access tokens, and absolute local paths. It includes protocols, source-field contracts, scripts, aggregate results, figure source data, figures, tables, tests, environment metadata, and checksums. Database access remains subject to the original data-use agreements. The public GitHub repository is https://github.com/Jimmmmgh/blood-pressure-label-instability, and the manuscript version is archived as release v2.1.0.

## STROBE checklist

{md_table(["Item", "Recommendation", "Location"], strobe)}

"""

    OUT.write_text(text, encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
