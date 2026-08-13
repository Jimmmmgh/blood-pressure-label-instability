# Blood-pressure label instability in critical care

This repository contains the disclosure-screened reproducibility materials for:

> Measurement-source instability of ICU hypotension phenotypes: a cross-database retrospective measurement-method study

Authors: Chaoyuan Jin, Sucheng Mu, Qingxia Dai, Xingxing Ren, and Jie Shen.

## What is included

- Frozen and dated analysis contracts, including the outcome firewall and version 2.1 post-analysis correction record.
- Deterministic post-extraction analysis code and boundary tests.
- Sanitized aggregate results, tables, figure source data, and publication figures.
- Analysis-environment metadata and file-level checksums.
- Audit records for the MIMIC-IV age correction, deterministic rerun, and corrected package gate.

## Data-governance boundary

No patient-level data, person or stay identifiers, timestamps, blood-pressure records, outcomes, derived row-level cohorts, credentials, database connection helpers, or local absolute paths are included. Source data must be obtained independently from their custodians and used under the applicable access terms.

SICdb 1.0.8, MIMIC-IV 3.1, eICU-CRD 2.0, and VitalDB 1.0.0 are available through PhysioNet subject to the conditions shown on each resource page. This repository does not redistribute those databases or confer access rights.

## Main finding and inference boundary

Across 14,698 people and 234,958 paired observations, arterial- and cuff-specific definitions yielded different clinically consequential hypotension labels in approximately 13%-15% of equal-person-weighted observations. The work establishes retrospective phenotype instability. It does not determine which modality is correct, certify device accuracy, identify a causal effect, or demonstrate deployment benefit.

## Reproduction

Create a Python 3.13 environment and install the pinned packages listed in `requirements-lock.txt`. Run code-level tests that do not require protected extracts with:

```text
python -m pytest scripts/test_measurement_core.py -q
```

After independently constructing the protected local extracts specified in `protocol/VARIABLE_CONTRACT_v1.0.json`, run the post-extraction workflow in this order:

```text
python scripts/analyze_primary_measurements.py
python scripts/run_measurement_sensitivities.py
python scripts/analyze_measurement_subgroups.py
python scripts/analyze_locked_outcomes.py
python scripts/analyze_eicu_multiple_imputation.py
python scripts/summarize_policy_burden_shifts.py
python scripts/build_manuscript_tables.py
python scripts/create_publication_figures.py
python scripts/verify_analysis_determinism_v2_1.py
```

The raw-source extraction and local database-connection layer is intentionally excluded because it contains infrastructure-specific logic and could expose protected resources. The frozen field contract documents the required variables and source semantics.

## Version 2.1.1

Version 2.1.1 contains scientific package version 2.1 and adds deterministic LF checkout rules so that the file manifest verifies after a Windows clone. Scientific package version 2.1 corrects MIMIC-IV age at ICU admission to `anchor_age + year(intime) - anchor_year`, completes the prespecified eICU APACHE IVa multiple-imputation sensitivity, completes remaining cohort-rule sensitivities, and makes deterministic comparison independent of anonymous patient row order. The correction changed age-derived summaries and adjusted models but did not change cohort membership, paired measurements, discordance classifications, or primary measurement estimates.

## License and citation

Analysis code is released under the MIT License. The license does not apply to source datasets. Cite the repository using `CITATION.cff` and cite the eventual article when its bibliographic record becomes available.
