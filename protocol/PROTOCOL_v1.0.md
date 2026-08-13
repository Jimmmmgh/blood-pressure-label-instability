# Protocol v1.0

## Administrative record

- Protocol title: Blood pressure is not a single label: cross-system transportability of measurement-source discordance across operating rooms and intensive care units
- Protocol version: 1.0
- Freeze date: 2026-08-12, Asia/Taipei
- Design: retrospective, multi-database measurement-method and phenotyping-robustness study
- State at freeze: pressure differences and clinical outcomes have not been analyzed in this project
- Reporting frameworks: STROBE for observational cohorts, GRRAS principles for agreement/reliability reporting, and TRIPOD-AI principles only for any explicitly exploratory prediction component

## Rationale and novelty boundary

Invasive arterial and oscillometric cuff blood pressure are not interchangeable observations, yet retrospective studies frequently collapse them into one mean arterial pressure (MAP) label. Prior studies already show wide agreement limits and greater cuff error at low invasive MAP. Therefore, this study will not claim novelty for the generic statement that cuff pressure is inaccurate during hypotension, will not treat either modality as universal ground truth, and will not build another generic cuffless blood-pressure benchmark.

The new target is measurement-policy robustness: quantify how often a clinically important hypotension label changes with measurement source, determine whether that instability transports across heterogeneous public data systems, examine whether obvious arterial-waveform failure explains it in a raw-signal substudy, and estimate how alternative measurement policies alter downstream prognostic associations.

## Objectives

### Primary objective

Estimate, in the SICdb anchor cohort, the equal-patient-weighted prevalence of clinically consequential MAP discordance during the first 24 hours of the first eligible adult ICU case.

### External-validation objective

Estimate the same source-specific quantity in MIMIC-IV and eICU using their closest documented time-alignment proxies, while explicitly preserving the differences in acquisition semantics.

### Engineering objective

In VitalDB, determine whether clinically consequential discordance persists after a prespecified raw arterial-waveform quality screen and after checking concordance between waveform-derived MAP and the bedside monitor's numeric arterial MAP. Because cuff values are carried forward and identical repeated cuff results cannot be recovered, VitalDB is a technical substudy and not a prevalence cohort.

### Phenotyping objective

After the measurement-stage gate passes, compare first-day hypotension exposure and hospital-mortality associations under arterial-only, cuff-only, concordant-only, and review/indeterminate measurement policies. These are prognostic sensitivity analyses, not causal effects.

### Discretization objective

Use non-overlapping INSPIRE operations only as a stress test of what remains identifiable after public-release quantization. No continuous mmHg difference will be reconstructed or imputed from quantized values.

## Data-source roles

| Source | Setting | Role | Pairing semantics | Primary continuous estimand eligible? |
|---|---|---|---|---|
| SICdb 1.0.8 | Single-center ICU | Anchor cohort | Minute values deserialized from paired 60-float hourly blobs | Yes |
| MIMIC-IV | Single-center ICU | External validation | Same `charttime`; documentation-time coincidence, not guaranteed device synchronization | Yes, source-specific |
| eICU-CRD | 187-hospital ICU network | External validation and site heterogeneity | Same offset; invasive value is a five-minute median and cuff is an irregular event | Yes, source-specific |
| VitalDB | Operating room | Raw-waveform technical substudy | High-specificity cuff state-change proxy aligned to waveform/numeric arterial windows | No prevalence claim |
| INSPIRE 1.4.2 | Operating room | Quantization sensitivity | Five-minute medians, categorized into 5-percentile values; VitalDB-linked cases excluded | No continuous-difference claim |
| MIMIC-IV Waveform | ICU | Optional small technical stress test | Only clinically linked, checksum-verified local records | No; feasibility permitting |

No row-level pooled estimate across sources will be presented as if the databases shared an identical acquisition mechanism.

## Population and independent unit

The independent inferential unit is a person. The primary analysis retains the first eligible stay/case/operation for each person. Repeated measurements within that unit contribute to a person-level proportion; they are never counted as independent people.

Common criteria:

1. Age at admission at least 18 years. If age is top-coded, a value known to be at least 18 is eligible.
2. At least three valid paired MAP observations during the prespecified observation window for the primary analysis.
3. Both modalities have numeric MAP in 20-200 mmHg after source-specific deduplication.
4. No imputation of MAP, modality, timestamp, pair membership, or waveform quality.
5. When several stays are eligible for one person, retain the chronologically first eligible stay; all-stay analyses are sensitivity analyses with person-clustered uncertainty.

Source-specific rules:

- SICdb: use `CaseID` linked to `PatientID`; retain measurements from `ICUOffset` through the earlier of `ICUOffset + 86,400 seconds` and end of stay. Use DataID 703 for arterial MAP and 706 for noninvasive MAP. Deserialize each valid `rawdata` blob as 60 little-endian float32 values at `Offset + i*60` seconds. If duplicate rows at the same case/offset/modality are not byte-identical, exclude that hour and report it.
- MIMIC-IV: link `chartevents` to `icustays` and `patients`; use itemid 220052 for arterial MAP and 220181 for cuff MAP. Retain `charttime` from ICU `intime` through `intime + 24 hours`; within modality and timestamp, use the median of duplicate numeric entries. Do not use the coalesced derived `mbp` field.
- eICU: link `vitalperiodic.systemicmean` to `vitalaperiodic.noninvasivemean` at equal `patientunitstayid` and `observationoffset`, restricted to offsets 0-1440 minutes. Retain the first eligible unit stay per `uniquePid`. Duplicate cuff rows at one offset are reduced by median. Hospital is retained for cluster and heterogeneity analyses.
- VitalDB: retain one operation per subject, require raw `SNUADC/ART`, numeric `Solar8000/ART_MBP`, and the aligned NIBP triplet. A change in any of NIBP SBP/DBP/MAP defines a high-specificity cuff-update proxy; the first state is not considered an observed update. This misses identical consecutive cuff results and therefore cannot estimate prevalence.
- INSPIRE: restrict measurements to `orin_time` through `orout_time`, exclude operations with non-null `case_id`, and retain one operation per `subject_id`. Use only interval/ordinal statements that are guaranteed by documented category bounds. If category bounds are unavailable, report coverage only.

## Observation windows

- ICU primary window: first 24 hours after ICU entry.
- ICU sensitivity windows: first 6 hours and entire eligible ICU stay.
- Operating-room window: documented intraoperative interval.
- For outcome analysis, use a 24-hour landmark: include only patients alive and still observed at 24 hours, and predict subsequent hospital mortality. This prevents exposure information after the prediction origin and avoids labeling early deaths with incomplete exposure windows.

## Measurement states

Let `A` be arterial MAP, `C` be cuff MAP, and `D = C - A`, all in mmHg. The clinical threshold is MAP below 65 mmHg.

- Arterial hypotension: `A < 65`.
- Cuff hypotension: `C < 65`.
- Threshold discordance: exactly one of `A < 65` and `C < 65` is true.
- Large magnitude discordance: `abs(D) >= 10`.
- Clinically consequential discordance (CCD): threshold discordance and large magnitude discordance are both true.
- Concordant hypotension: both modalities are below 65.
- Concordant normotension: both modalities are at least 65.
- Review/indeterminate state: threshold discordance or large magnitude discordance.

The primary event is symmetric. Signed differences are descriptive and do not imply that arterial MAP is true.

## Primary estimand

For each eligible patient, calculate the fraction of paired observations in the first 24 hours meeting CCD. The primary estimand is the arithmetic mean of those patient-level fractions in SICdb, so every patient receives equal weight regardless of monitoring frequency. Report the point estimate and a percentile 95% confidence interval from 2,000 patient-level bootstrap resamples with seed 20260812.

MIMIC-IV and eICU repeat the estimand as prespecified external validations. Their estimates are not required to be numerically homogeneous with SICdb because acquisition and documentation differ.

## Secondary measurement estimands

1. Equal-patient-weighted prevalence of threshold discordance without the 10-mmHg condition.
2. Equal-patient-weighted prevalence of `abs(D) >= 10`.
3. Direction-specific CCD: cuff-low/arterial-not-low and arterial-low/cuff-not-low.
4. Patient-weighted median signed difference, median absolute difference, root-mean-square difference, and repeated-measures Bland-Altman mean bias and 95% limits of agreement, all with patient-cluster bootstrap intervals.
5. Coverage of stable hypotension, stable normotension, and review/indeterminate policies.
6. Source, hospital, calendar-time, severity, vasopressor, and baseline-MAP heterogeneity, labeled secondary or exploratory as specified in the SAP.

## Outcome-stage estimands

Outcome data remain closed until the firewall gate is signed. In each eligible ICU source, construct four person-level first-day burdens from the same paired timestamps:

1. arterial-only hypotension fraction;
2. cuff-only hypotension fraction;
3. any-sensor hypotension fraction;
4. concordant-only hypotension fraction, with review states excluded and coverage reported.

The outcome is subsequent hospital mortality after the 24-hour landmark. The main downstream quantity is the adjusted absolute risk difference for a 10-percentage-point increase in hypotension burden, estimated separately for each measurement policy and source. Discrimination and calibration are descriptive. This analysis evaluates sensitivity of prognostic inference to label policy; it does not estimate the effect of hypotension or a device on mortality.

## Go/no-go gates

### Measurement-stage gate

Proceed to primary measurement analysis only if:

- the frozen-file hash manifest validates;
- at least 2,000 independent people are eligible in SICdb and in at least two external continuous sources;
- source semantics and deduplication checks show no unresolved contradiction;
- all output contains only minimum necessary deidentified identifiers; and
- unit tests for pairing, XOR classification, thresholds, and bootstrap reproducibility pass.

### Flagship viability gate

Proceed to the outcome stage only if all conditions hold:

- SICdb primary CCD estimate is at least 5%;
- at least two external continuous sources have a CCD lower 95% confidence limit above 2%;
- at least 80% of the planned eligible units survive core QA in every source used for confirmatory claims;
- no single hospital or calendar stratum alone explains the eICU result; and
- timing/range sensitivities do not reverse the qualitative conclusion that measurement source changes the hypotension label.

The 5% and 2% thresholds are prospective workflow-relevance gates, not tests of statistical significance. Failure leads to a transparent negative measurement paper or termination of the 10-20 target, not definition changes.

### Raw-waveform gate

VitalDB supports an engineering claim only if at least 1,000 independent operations have at least three cuff-update proxies with at least 80% waveform coverage and at least 80% of retained windows pass waveform quality checks. Otherwise it remains feasibility-only.

### Outcome gate

Open outcomes only after a signed `OUTCOME_FIREWALL.md` records passed measurement gates, frozen hashes, completed measurement tables/figures, and zero outcome columns in measurement-stage extracts.

## Bias and interpretation safeguards

- Paired monitoring is selected: patients with arterial lines and cuff checks are not representative of all ICU or surgical patients.
- Timestamp equality is a database alignment proxy in MIMIC-IV and eICU, not proof of simultaneous acquisition.
- Arterial lines can be damped, resonant, malpositioned, or zeroed incorrectly; cuff measurements can be affected by size, site, movement, perfusion, rhythm, and device algorithms.
- Cuff site/size, arterial site/leveling, calibration, and clinician adjudication are incompletely observed.
- Clinical actions between readings and documentation artifacts may influence values.
- INSPIRE quantization prevents ordinary mmHg agreement analysis.
- VitalDB cuff update detection is selected against repeated identical readings.
- The study estimates label instability and association robustness, not physiological truth, causality, or deployment benefit.

## Data governance and reproducibility

Raw credentialed data stay local. Public-release code must contain no credentials, row-level protected data, or reconstructable dates/identifiers. Reproducibility artifacts will include source versions, checksums where available, cohort flow counts, variable contracts, environment versions, deterministic seeds, aggregate tables, and scripts that users with authorized access can rerun.

## Amendments

After the freeze manifest is written, this file is immutable. Any change requires a dated amendment file stating whether it was made before or after the affected result was inspected. Confirmatory results will always be reported under v1.0 as frozen, with amended analyses labeled sensitivity or exploratory.
