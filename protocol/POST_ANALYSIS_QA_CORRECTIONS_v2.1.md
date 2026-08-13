# Post-analysis QA corrections v2.1

## Administrative record

- Date: 2026-08-13
- Trigger: structured peer-review-style audit after the complete v2.0 package had passed initial technical preflight
- Primary CCD endpoint, thresholds, cohort pairing, measurement values, and outcome firewall: unchanged
- Status: post-result correction and completion of prespecified sensitivity work; not a pre-result protocol amendment

## Correction 1: MIMIC-IV age at ICU admission

The initial MIMIC-IV extraction used `patients.anchor_age` directly. MIMIC-IV defines this age in `anchor_year`; age at ICU admission should be calculated as:

`anchor_age + year(icustays.intime) - anchor_year`

Among the 4,171 primary MIMIC-IV participants, 1,118 ages changed by 1-15 years, the median changed from 65 to 66 years, and 191 participants changed prespecified age stratum. The primary paired MAP values, cohort membership, CCD classifications, and primary measurement estimate do not depend on age and were unchanged. MIMIC-IV descriptive age, age-subgroup results, and outcome adjustment were regenerated from the corrected age.

This required reading `patients.anchor_year`, which was omitted from `VARIABLE_CONTRACT_v1.0.json`. The frozen contract was not overwritten; this correction file records the post-analysis field addition.

## Correction 2: eICU severity-score missingness sensitivity

APACHE IVa was missing in approximately 11% of the eICU landmark outcome cohort. The frozen SAP required multiple imputation when a required covariate had 5%-40% missingness. The initial package reported complete-case severity models only. Version 2.1 adds a 20-imputation sensitivity analysis that includes outcome, age, sex, the policy-specific burden, and auxiliary observed first-day variables in the imputation model. The complete-case models remain the prespecified main severity analysis; the imputed analysis tests missing-data sensitivity.

## Reporting corrections

- Descriptive mean plus/minus 1.96 SD summaries are labeled descriptive pair-level 95% dispersion limits with patient-cluster bootstrap uncertainty, not repeated-measures limits of agreement or device-validation estimates.
- “External-minus-anchor absolute differences” is corrected to “signed external-minus-anchor differences” because the reported contrasts retain direction.
- The supplement explicitly lists completed falsification analyses and any remaining prespecified analyses not executed.
- The protocol is described as locally frozen and hash-audited, not externally preregistered or independently time-stamped.

All regenerated outputs receive fresh package checksums and Word-native QA after these corrections.
