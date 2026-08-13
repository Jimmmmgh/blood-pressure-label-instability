# Outcome firewall

## Purpose

This file prevents outcome-informed changes to the measurement definitions. Clinical outcomes must not be queried, extracted, opened, summarized, or modeled for this project until every required item below is complete.

## Locked outcome

Subsequent hospital mortality among patients alive and still observed at the 24-hour landmark. This outcome is locked now but remains unopened.

## Forbidden before release

- mortality, discharge status, discharge destination, length of stay, organ injury, treatment escalation, or any other clinical endpoint;
- outcome-stratified pair distributions or cohort counts;
- feature selection using an outcome;
- changes to MAP 65 mmHg, the 10-mmHg magnitude rule, first-24-hour window, at-least-three-pair rule, or first-eligible-stay rule based on results.

## Release checklist

- [ ] `FROZEN_CONTRACT.sha256.json` exists and validates all protocol inputs.
- [ ] Source-specific extraction and classification unit tests pass.
- [ ] SICdb, MIMIC-IV, and eICU cohort flow tables are complete.
- [ ] Primary and prespecified measurement-stage results are complete.
- [ ] Measurement-stage result files contain no outcome columns.
- [ ] Measurement-stage gate in `PROTOCOL_v1.0.md` passes.
- [ ] Flagship viability gate in `PROTOCOL_v1.0.md` passes.
- [ ] Timing, range, minimum-pair, and eICU site sensitivities are reviewed.
- [ ] VitalDB and INSPIRE limitations are correctly labeled and do not inflate the main cohort count.
- [ ] Release record below is signed by the analysis process with timestamp and evidence paths.

## Release record

- state: LOCKED
- released_at: null
- measurement_gate: not_evaluated
- flagship_viability_gate: not_evaluated
- evidence_manifest: null
- released_by: null

If a gate fails, outcomes remain closed unless a dated amendment explicitly reclassifies the work as exploratory. Such an amendment cannot restore confirmatory status.
