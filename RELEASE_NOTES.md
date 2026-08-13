# Version 2.1.1

Maintenance release for the cross-database critical-care blood-pressure label-instability study. It adds deterministic LF checkout rules so that `MANIFEST.sha256` verifies after a Windows clone; scientific content is unchanged from package version 2.1.

This release includes frozen protocols, deterministic post-extraction analysis code, code-level tests, aggregate results, figure source data, publication figures, environment metadata, and sanitized audit records. It excludes every patient-level or protected source record, identifier, credential, database connection helper, and local absolute path.

Scientific package version 2.1 records the corrected MIMIC-IV admission-age calculation, completed eICU multiple-imputation sensitivity, remaining cohort-rule sensitivities, and row-order-independent deterministic verification. These corrections did not change cohort membership, paired measurements, discordance classifications, or primary measurement estimates.
