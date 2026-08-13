# Protocol v2.0: pre-result capacity restart

## Status of v1.0

Protocol v1.0 was frozen at 2026-08-12T14:22:05Z and then used only to build outcome-blind cohort extracts. Its measurement-stage requirement of at least 2,000 eligible people in the SICdb anchor was not met: 1,510 independent people had at least three valid first-day pairs after the adult and first-eligible-case rules. MIMIC-IV had 4,171 and eICU had 9,017.

Version 1.0 is therefore closed as `NO-GO_CAPACITY` before any source-level pressure difference, clinically consequential discordance prevalence, subgroup contrast, clinical outcome, or association result was summarized or inspected. Extract files mechanically contain the frozen classification flags, but no aggregate of those flags was calculated or displayed before this restart.

## Effective v2.0 contract

Protocol v2.0 prospectively incorporates every definition, population rule, estimand, sensitivity analysis, outcome firewall, claim boundary, and analysis method in:

- `PROTOCOL_v1.0.md`
- `SAP_v1.0.md`
- `VARIABLE_CONTRACT_v1.0.json`
- `OUTCOME_FIREWALL.md`

There is exactly one replacement:

> In the measurement-stage gate, replace "at least 2,000 independent people are eligible in SICdb and in at least two external continuous sources" with "at least 1,500 independent people are eligible in SICdb and at least 2,000 independent people are eligible in each of MIMIC-IV and eICU."

The source hierarchy remains SICdb as the minute-level anchor, MIMIC-IV and eICU as semantically distinct continuous external validations, VitalDB as a selected raw-waveform technical substudy, and INSPIRE as a quantization stress test.

## Rationale independent of the measurement result

The original 2,000-person threshold was an arbitrary round-number feasibility rule, not a sample-size calculation. With 1,500 independent people, a simple-binomial 95% half-width is approximately 2.5 percentage points at the worst-case prevalence of 50% and approximately 1.1 percentage points at the prespecified flagship threshold of 5%. The final patient-level cluster-bootstrap interval may be wider and will determine interpretation. The two external cohorts remain well above 2,000.

No endpoint threshold, pairing rule, minimum-pair rule, time window, source role, statistical method, flagship viability threshold, or outcome rule changes. This restart is driven only by blinded eligibility counts and occurs before primary measurement analysis.

## Freeze rule

The v2.0 manifest hashes the v1.0 base contract, this restart document, and the three outcome-blind cohort-flow files. After the v2.0 freeze, no further confirmatory definition change is permitted. Any subsequent deviation is exploratory and must be labeled as such.
