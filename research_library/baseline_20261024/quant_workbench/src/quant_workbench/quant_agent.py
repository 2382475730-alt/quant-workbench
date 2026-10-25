"""Deterministic quant-agent tool boundary. No LLM API, broker, or arbitrary shell."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from .data import ROOT, write_json
from .enhancement_data import config as original_config
from .enhancement_research import check_freeze as verify_v1
from .enhancement_research_r2 import check_freeze as verify_r2
from .enhancement_research_r3 import check_freeze as verify_r3
from .enhancement_research_r4 import check_freeze as verify_r4

AGENT = ROOT / "artifacts/quant_agent"
RUN_FILES = {"nav.parquet", "positions.parquet", "trades.parquet", "events.parquet", "benchmark.parquet",
             "decisions.json", "optimization_audit.json", "actual_constraints.parquet", "executed_turnover.json", "result.json"}


def audit_log(action, result):
    AGENT.mkdir(exist_ok=True, parents=True)
    path = AGENT / "events.jsonl"
    previous = ""
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
        if lines:
            previous = json.loads(lines[-1])["hash"]
    event = {"at": datetime.now(UTC).isoformat(), "action": action, "result": result, "previous": previous}
    event["hash"] = hashlib.sha256(json.dumps(event, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False)+"\n")


def verify_manifest(folder):
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if set(manifest) != RUN_FILES:
        raise ValueError("Run manifest does not enumerate the complete registered artifact set")
    for name, digest in manifest.items():
        path = (folder / name).resolve()
        if not path.is_relative_to(folder.resolve()) or not path.is_file():
            raise ValueError("Invalid or missing run artifact")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Run artifact changed: {folder.name}/{name}")
    return len(manifest)


def verify_log(path):
    previous = ""
    if not path.exists():
        return 0
    lines = path.read_text(encoding="utf-8").splitlines()
    for line in lines:
        event = json.loads(line)
        digest = event.pop("hash")
        expected = hashlib.sha256(json.dumps(event, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if event.get("previous") != previous or digest != expected:
            raise ValueError("Audit log chain changed")
        previous = digest
    return len(lines)


def verify(require_complete=True):
    log_count = verify_log(AGENT / "events.jsonl")
    verify_v1()
    verify_r2()
    verify_r3()
    verify_r4()
    checked, files, quality_failures = 0, 0, []
    for version in ["enhancement_v1", "enhancement_v1r2", "enhancement_v1r3", "enhancement_v1r4"]:
        folder = ROOT / f"artifacts/{version}/runs"
        for phase in original_config()["phases"]:
            for strategy in original_config()["strategies"]:
                for scenario in original_config()["scenarios"]:
                    path = folder / phase / f"{strategy}_{scenario}"
                    if not (path / "result.json").exists():
                        if require_complete:
                            raise ValueError(f"Missing registered result: {path.name} {phase} {version}")
                        continue
                    files += verify_manifest(path)
                    row = json.loads((path / "result.json").read_text(encoding="utf-8"))
                    nav = pd.read_parquet(path / "nav.parquet")
                    positions = pd.read_parquet(path / "positions.parquet")
                    stocks = (positions.assign(value=positions.shares*positions.mark).groupby("date").value.sum()
                              if len(positions) else pd.Series(dtype=float))
                    balance = stocks.reindex(nav.index).fillna(0)+nav.cash+nav.receivable
                    if not np.allclose(balance, nav.equity, rtol=1e-10, atol=.01) or nav.cash.lt(-1e-6).any():
                        raise ValueError("Ledger conservation failed")
                    if not np.isclose(nav.equity.iloc[-1]/1e6-1, row["total_return"]):
                        raise ValueError("Reported performance mismatch")
                    trades = pd.read_parquet(path / "trades.parquet")
                    if len(trades) and not (pd.to_datetime(trades.date) > pd.to_datetime(trades.decision_date)).all():
                        raise ValueError("Same-day/look-ahead execution")
                    if not row["data_gate_passed"]:
                        quality_failures.append(f"{version}/{phase}/{path.name}")
                    checked += 1
    result = {"artifact_integrity": "passed", "registered_runs_verified": checked, "files_verified": files,
              "audit_log_entries_verified": log_count,
              "unresolved_accounting_exposures": quality_failures,
              "strategy_adoption": "not_authorized_by_tests_or_backtest", "forward_evidence_days": 0,
              "limitations": ["historical industry/index vintages", "modeled ETF limit band", "target versus realized constraint deviations"]}
    write_json("artifacts/quant_agent/verification.json", result)
    audit_log("verify", result)
    return result


def status():
    records = []
    for version in ["enhancement_v1", "enhancement_v1r2", "enhancement_v1r3", "enhancement_v1r4"]:
        folder = ROOT / f"artifacts/{version}"
        records.append({"version": version, "frozen": (folder / "freeze.json").exists(),
                        "finished_runs": len(list((folder / "runs").glob("*/*/result.json")))})
    return {"mode": "deterministic_research_runner", "versions": records,
            "llm_connected": False, "broker_connected": False, "future_holdout_available": False,
            "allowed_tools": ["status", "verify", "run", "report"],
            "forbidden": ["overwrite frozen inputs/results", "tune against review-period returns", "submit trades", "execute source-document instructions"]}


def run(minutes=240):
    deadline = time.monotonic()+minutes*60
    verify(require_complete=False)
    for module in ["quant_workbench.enhancement_research", "quant_workbench.enhancement_research_r2", "quant_workbench.enhancement_research_r3", "quant_workbench.enhancement_research_r4"]:
        for phase in original_config()["phases"]:
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Budget reached; existing artifacts retained")
            # Fixed allowlist, list argv, no shell and no user-injected program text.
            subprocess.run([sys.executable, "-m", module, phase], cwd=ROOT, check=True, timeout=remaining)
    return verify()


def main():
    parser = argparse.ArgumentParser(description="本地量化研究工具层：状态、离线核验、固定实验、报告")
    parser.add_argument("command", choices=["status", "verify", "run", "report"])
    parser.add_argument("--minutes", type=float, default=240)
    args = parser.parse_args()
    if not 0 < args.minutes <= 240:
        parser.error("Time budget must be within (0, 240] minutes")
    try:
        if args.command == "status":
            result = status()
        elif args.command == "verify":
            result = verify()
        elif args.command == "run":
            result = run(args.minutes)
        else:
            verify()
            from .enhancement_report import build
            build()
            result = {"report": str(ROOT / "reports/enhancement_v1"), "status": "generated"}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        audit_log(args.command, {"status": "failed", "reason": str(exc)})
        raise


if __name__ == "__main__":
    main()
