# Statistical Analysis Plan v1.0

## Administrative record

- Parent protocol: `PROTOCOL_v1.0.md`
- Version/date: 1.0 / 2026-08-12
- Analysis state: written before project-level pressure-difference and outcome analysis
- Two-sided alpha: 0.05
- Confidence level: 95%
- Random seed: 20260812
- Bootstrap replicates: 2,000 for final inference; 200 permitted only for pipeline smoke tests and never for manuscript numbers

## Analysis populations

1. `eligible_all_pairs`: first eligible adult stay/case per patient, at least one valid pair.
2. `primary_three_plus`: first eligible adult stay/case per patient, at least three valid pairs in the first 24 hours. This is the primary analysis population.
3. `all_stays_sensitivity`: every eligible stay, with patient-level clustered resampling.
4. `landmark_outcome`: members of `primary_three_plus` alive and under observation at 24 hours with a determinable subsequent hospital outcome.

Every table must show people, stays/cases, pairs, excluded records, and reasons. Pair counts are never described as sample size without the corresponding independent-unit count.

## Deterministic preprocessing

1. Read only the source fields listed in the variable contract.
2. Normalize units to mmHg; no unit conversion is expected for the selected MAP fields.
3. Reduce within-modality duplicates at a timestamp by median unless the protocol specifies byte-identity checking.
4. Pair only at the exact source-specific time key. No nearest-neighbor matching is allowed in the primary analysis.
5. Apply the inclusive plausible range 20-200 mmHg to both modalities.
6. Calculate `delta = cuff_map - arterial_map`, `abs_delta`, modality-specific low-MAP flags, threshold XOR, and CCD exactly as specified in the protocol.
7. Sort eligible stays chronologically and retain the first eligible stay per person. A later stay cannot replace it based on its observed discordance.
8. Write a cohort-flow ledger before inferential summaries.

## Primary analysis

Within each patient `i`, let `p_i` be CCD pairs divided by valid pairs. In SICdb estimate `mean(p_i)`. Obtain the 95% percentile interval by resampling patients with replacement 2,000 times. Report:

- number of independent patients;
- number and median/IQR of pairs per patient;
- mean patient-level CCD fraction and bootstrap interval;
- median/IQR and full empirical distribution of patient-level CCD fractions;
- pair-weighted CCD fraction as a clearly labeled secondary quantity.

Repeat without model refitting in MIMIC-IV and eICU. Present source-specific estimates and absolute differences from SICdb with bootstrap intervals. A random-effects summary may be shown only as exploratory because three semantically heterogeneous sources provide unstable heterogeneity estimation. Row-level pooling is prohibited.

## Precision rationale

The design is census-based: all locally available eligible records are used, so no data-dependent sample-size stopping rule applies. The prospective gate of at least 2,000 independent people per source gives a worst-case simple-binomial 95% half-width of approximately 2.2 percentage points and about 1.0 percentage point when prevalence is 5%; final uncertainty is cluster-bootstrap based and may be wider. No post-hoc observed power will be reported. If estimates are imprecise, confidence intervals and the minimum detectable difference under the realized independent-unit count will be reported.

## Agreement and distribution summaries

Agreement summaries do not designate a reference truth.

- Signed difference: `cuff - arterial`.
- Report mean bias, SD, median, IQR, median absolute difference, RMSE, and 2.5th/97.5th percentiles.
- Repeated-measures limits of agreement are mean difference plus/minus 1.96 times the SD of pair differences; patient-cluster bootstrap intervals are required. Because this is routine-care data rather than a controlled validation protocol, these values must not be presented as AAMI/ISO device certification.
- Plot hexbin/density distributions rather than overplotted raw scatter; show MAP-dependent smooths with patient-cluster bootstrap bands.
- Inspect heteroscedasticity with residual-versus-mean plots and Breusch-Pagan as a descriptive diagnostic. If strong, retain raw-scale results and add log/relative-difference sensitivity only where pressures are positive; do not replace the prespecified analysis.
- Normality tests on millions of pairs will not determine method choice. Distribution plots and robust summaries take priority.

## Secondary measurement analyses

The following finite confirmatory family uses Holm correction within each source:

1. threshold discordance;
2. `abs(delta) >= 10`;
3. cuff-low/arterial-not-low CCD;
4. arterial-low/cuff-not-low CCD;
5. review-state coverage.

Report risk differences/proportions and 95% intervals whether or not corrected p-values cross 0.05. Other subgroup tests are exploratory and use Benjamini-Hochberg false-discovery-rate control at 5% within a named family.

## Prespecified heterogeneity

- MIMIC-IV: age groups 18-44, 45-64, 65-79, and at least 80; sex; first 6 versus 6-24 hours; calendar era if dates permit.
- eICU: the same person-level strata plus hospital. Report hospital estimates only for hospitals with at least 50 eligible people; use hierarchical shrinkage or Wilson intervals and leave-one-hospital-out summaries. Do not rank named hospitals.
- SICdb: age group, sex, SAPS 3 quartile, sepsis-at-admission flag, admission urgency, and first 6 versus 6-24 hours.

Subgroup interaction estimates with intervals are required; within-subgroup significance/no-significance comparisons are forbidden.

## Sensitivity analyses

1. Plausible MAP ranges 30-160 and 40-130 mmHg.
2. At least 1, 5, and 10 pairs per patient.
3. First 6 hours and full stay.
4. Thresholds 60, 65, and 70 mmHg.
5. Large-difference cutoffs 5, 10, and 15 mmHg, with 10 primary.
6. Pair-weighted rather than equal-patient-weighted prevalence.
7. All eligible stays with patient-cluster resampling.
8. Source-specific duplicate exclusion rather than median reduction.
9. SICdb offsets shifted by plus/minus 1 and plus/minus 5 minutes to quantify sensitivity to alignment.
10. MIMIC-IV and eICU analyses restricted to stays with at least one pair in each of two different hours.
11. eICU leave-one-hospital-out and calendar-era splits.
12. Between-person permutation within source and broad MAP stratum as an alignment falsification analysis; because blood pressure is autocorrelated, time shifts are not interpreted as a pure null.

Sensitivity conclusions are based on magnitude and interval overlap, not a vote count of p-values.

## VitalDB raw-waveform technical substudy

For every high-specificity cuff-update proxy:

1. Extract raw arterial pressure from 30 seconds before through 30 seconds after the proxy time.
2. Require at least 80% of expected samples and a valid sampling frequency.
3. Flag the window if more than 5% of samples are outside 20-250 mmHg, if the 95th-5th percentile amplitude is below 10 or above 150 mmHg, if at least 95% of adjacent differences have magnitude below 0.1 mmHg, or if any nonfinite run exceeds 5 seconds.
4. Define waveform-derived MAP as the time-weighted mean of retained raw pressure samples; compare it with median numeric arterial MAP in the same window.
5. Primary technical concordance requires absolute waveform-derived versus numeric arterial MAP difference no greater than 5 mmHg.
6. Re-estimate CCD only among quality-passing, technically concordant windows and report how many selected cuff-update proxies remain. This is a selected technical quantity, not population prevalence.

If the monitor's raw track scale or sample semantics fail a manual trace QA, stop the waveform claim and retain a feasibility report only.

## INSPIRE quantization sensitivity

The public values are not treated as continuous measured mmHg. If documented category boundaries can be deterministically mapped, use interval arithmetic:

- `definitely low` only if the category upper bound is below 65;
- `definitely not low` only if the lower bound is at least 65;
- `definitely >=10 apart` only if the minimum distance between modality intervals is at least 10;
- otherwise `indeterminate`.

Report coverage and guaranteed discordance bounds. Do not replace category values by midpoints for the primary or validation estimand. If bounds cannot be reconstructed from public metadata, report paired-operation capacity only.

## Measurement-stage model (exploratory)

Only after the primary source-specific estimates are complete, fit transparent source-specific models for CCD risk to characterize context, not to identify truth. Candidate predictors are the mean of paired MAP values, time since admission, recent within-modality variability, age, sex, source-specific severity, vasopressor exposure, and hospital random effect where available. Continuous predictors use restricted cubic splines with prespecified knots at empirical 5th, 35th, 65th, and 95th percentiles computed in the development source.

- Development: SICdb.
- Locked external evaluation: MIMIC-IV and eICU using only harmonizable predictors.
- Split by person, never by pair.
- Report calibration-in-the-large, calibration slope, Brier score, AUROC, AUPRC, and decision/review coverage; bootstrap confidence intervals by person.
- A model does not support a clinical deployment claim. If external calibration is poor, report failure without post hoc threshold tuning.

## Outcome-stage analysis

The outcome stage begins only after firewall release.

For each source separately, fit a logistic model for subsequent hospital mortality after the 24-hour landmark. The exposure is each policy-specific first-day hypotension fraction, modeled with a restricted cubic spline. Minimum common adjustment is age and sex. A source-specific severity score measured at or near admission is added in a prespecified sensitivity model if its construction does not incorporate post-landmark information.

Report standardized absolute risk at burden values 0%, 10%, 25%, and 50%, and the average marginal risk difference for a 10-percentage-point burden increase, with bootstrap intervals. Also report Brier score, calibration slope/intercept, AUROC, and policy coverage. Do not compare raw odds-ratio magnitude across differently selected samples without standardization.

The primary downstream question is whether the direction or clinically material magnitude of the association changes across measurement policies. No causal wording, mediation, treatment recommendation, or claim that one sensor is ground truth is permitted.

## Missingness

- Core measurement values, time keys, source identifiers, and outcomes are never imputed.
- Report missingness by source before modeling.
- For adjusted outcome models, complete-case analysis is primary when every covariate is under 5% missing.
- If any covariate has 5-40% missing, use multiple imputation by chained equations as sensitivity, with at least 20 imputations and all model variables included. Compare with complete cases.
- If a required covariate exceeds 40% missing, omit that covariate/source-specific adjusted model rather than extrapolate silently.
- Sex coded as unknown is reported as observed; it is not inferred.

## Assumption and diagnostic checks

- Verify bootstrap stability by comparing 1,000 versus 2,000 replicate endpoints.
- Inspect influential patients by leave-one-percent-out and pairs-per-person strata.
- For logistic models, check separation, nonlinearity, calibration, influential observations, and effective events per parameter.
- Check collinearity with variance inflation factors; merge or remove redundant predictors before locked external evaluation, documenting the action.
- Use cluster-robust or hierarchical methods for hospital/site structure.
- Report violations and robust alternatives. A very small p-value in a large dataset is never treated as evidence of clinical importance without an effect size and interval.

## Output controls

Every final statistical table must include the estimand, independent-unit count, observation count, point estimate, 95% interval, and analysis population. Exact p-values are reported to three decimals when at least .001 and as `<.001` otherwise. All prespecified analyses, including null and adverse results, remain in the supplement.

Primary result files are generated by code from frozen extracts. Manual edits to numeric results are prohibited. Each result artifact receives a SHA-256 checksum and provenance entry.
