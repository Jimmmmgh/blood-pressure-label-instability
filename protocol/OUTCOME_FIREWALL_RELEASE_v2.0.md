# Outcome firewall release v2.0

- released_at_utc: 2026-08-12T14:36:22.551680Z
- effective_protocol: v2.0 pre-result restart
- measurement_gate: PASS
- flagship_viability_gate: PASS
- decision: RELEASE
- evidence: `results/measurement_gate_report_v2.json`
- evidence_sha256: `32e6efdde89118a184ee5341fe5cd1387c7a63a6eef8336a857e4b4ce0aa6d6d`
- released_by: deterministic local QA workflow

## Completed checks

- v2.0 frozen-manifest validation passed with no modified input.
- Boundary tests for MAP 65 mmHg, absolute difference 10 mmHg, and XOR classification passed.
- SICdb, MIMIC-IV, and eICU capacity thresholds passed.
- The SICdb primary event estimate exceeded 5%, and both external lower 95% confidence limits exceeded 2%.
- Retained extracts had at least three pairs per person, no nonfinite or out-of-range core values, and no locked outcome column.
- 1,000-versus-2,000 replicate bootstrap endpoints differed by at most 0.061 percentage points.
- Range, first-six-hour, minimum-one-pair, full-stay, hospital leave-one-out, and interpretable calendar-stratum checks preserved the qualitative finding.
- No eICU hospital contributed more than 4.35% of people; leave-one-hospital-out estimates remained 13.19%-13.47%.
- VitalDB remains a selected raw-waveform technical substudy and is excluded from prevalence estimates. INSPIRE remains a quantization stress test and is excluded from continuous mmHg inference.

## Release scope

Only the locked subsequent hospital-mortality landmark analysis may now be extracted. No other outcome, organ-injury endpoint, treatment effect, causal contrast, or post hoc outcome definition is authorized by this release.

The frozen base firewall remains unchanged for auditability; this separate signed release record is the operative v2.0 authorization.
