from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
AUDIT_OUT = ROOT / "audit" / "analysis_determinism_v2_1.json"

COMMANDS = [
    "analyze_primary_measurements.py",
    "run_measurement_sensitivities.py",
    "analyze_measurement_subgroups.py",
    "summarize_policy_burden_shifts.py",
    "analyze_locked_outcomes.py",
    "analyze_eicu_multiple_imputation.py",
]

ARTIFACTS = [
    "results/measurement_primary_v2.json",
    "tables/measurement_cohort_summary_v2.csv",
    "tables/measurement_estimands_v2.csv",
    "results/measurement_sensitivity_v2.json",
    "tables/measurement_sensitivity_v2.csv",
    "results/measurement_subgroups_v2.json",
    "tables/measurement_subgroups_v2.csv",
    "results/policy_burden_shifts_v2.json",
    "tables/policy_burden_shifts_v2.csv",
    "results/locked_outcome_models_v2.json",
    "tables/locked_outcome_estimands_v2.csv",
    "results/eicu_multiple_imputation_outcome_sensitivity_v2_1.json",
    "tables/eicu_multiple_imputation_outcome_sensitivity_v2_1.csv",
]

VOLATILE_JSON_KEYS = {
    "generated_at",
    "generated_at_utc",
    "generated_utc",
}


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def normalize_json(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: normalize_json(item)
            for key, item in sorted(value.items())
            if key not in VOLATILE_JSON_KEYS
        }
    if isinstance(value, list):
        return [normalize_json(item) for item in value]
    return value


def normalized_digest(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    if path.suffix.lower() == ".json":
        parsed = json.loads(payload.decode("utf-8"))
        normalized = json.dumps(
            normalize_json(parsed),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return {
            "kind": "json_without_generation_timestamps",
            "bytes": len(payload),
            "raw_sha256": sha256_bytes(payload),
            "normalized_sha256": sha256_bytes(normalized),
        }

    # Parse once to fail closed on malformed CSV, then hash exact normalized newlines.
    text = payload.decode("utf-8").replace("\r\n", "\n")
    list(csv.reader(text.splitlines()))
    normalized = text.encode("utf-8")
    return {
        "kind": "csv_with_normalized_newlines",
        "bytes": len(payload),
        "raw_sha256": sha256_bytes(payload),
        "normalized_sha256": sha256_bytes(normalized),
    }


def snapshot() -> dict[str, dict[str, object]]:
    missing = [relative for relative in ARTIFACTS if not (ROOT / relative).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing determinism artifacts: {missing}")
    return {relative: normalized_digest(ROOT / relative) for relative in ARTIFACTS}


def main() -> None:
    baseline = snapshot()
    run_records = []
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONHASHSEED"] = "0"

    for index, script_name in enumerate(COMMANDS, start=1):
        print(f"[{index}/{len(COMMANDS)}] Re-running {script_name}", flush=True)
        started = time.perf_counter()
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / script_name)],
            cwd=ROOT,
            env=environment,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        elapsed = time.perf_counter() - started
        run_records.append(
            {
                "script": f"scripts/{script_name}",
                "exit_code": completed.returncode,
                "elapsed_seconds": round(elapsed, 3),
                "stdout_tail": completed.stdout[-1000:],
                "stderr_tail": completed.stderr[-1000:],
            }
        )
        print(
            f"[{index}/{len(COMMANDS)}] exit={completed.returncode}, "
            f"elapsed={elapsed:.1f}s",
            flush=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"{script_name} failed with exit code {completed.returncode}: "
                f"{completed.stderr[-1000:]}"
            )

    repeat = snapshot()
    comparisons = []
    all_match = True
    for relative in ARTIFACTS:
        before = baseline[relative]["normalized_sha256"]
        after = repeat[relative]["normalized_sha256"]
        match = before == after
        all_match = all_match and match
        comparisons.append(
            {
                "relative_path": relative,
                "normalization": repeat[relative]["kind"],
                "baseline_normalized_sha256": before,
                "repeat_normalized_sha256": after,
                "match": match,
            }
        )

    report = {
        "schema_version": "2.1",
        "audit_type": "baseline-then-clean-repeat determinism check",
        "volatile_fields_excluded": sorted(VOLATILE_JSON_KEYS),
        "python": sys.version,
        "commands": run_records,
        "artifacts": comparisons,
        "all_normalized_artifacts_match": all_match,
        "status": "PASS" if all_match else "FAIL",
    }
    AUDIT_OUT.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Determinism audit: {report['status']} -> {AUDIT_OUT}", flush=True)
    if not all_match:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
