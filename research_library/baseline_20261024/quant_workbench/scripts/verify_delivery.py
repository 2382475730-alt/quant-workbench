"""Read-only data integrity checks and a compact local verification receipt."""
import hashlib
import json
from datetime import UTC, datetime

import nbformat
import numpy as np
import pandas as pd

from quant_workbench.data import ROOT, write_json
from quant_workbench.research import fingerprints, verify_repair_scope


def read(p):
    return json.loads(p.read_text(encoding="utf-8"))


baseline = read(ROOT / "artifacts/legacy_baseline.json")
changed = []
for relative, digest in baseline["files"].items():
    path = ROOT.parent / relative
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        changed.append(relative)
assert not changed, f"Legacy baseline differences: {changed}"
frozen = read(ROOT / "artifacts/research/repair_freeze.json")
assert frozen["hashes"] == fingerprints(), "Calculation changed after repaired final freeze"
original = read(ROOT / "artifacts/research/freeze.json")
verify_repair_scope(original["hashes"], frozen["hashes"])
for relative, digest in original["hashes"].items():
    archived = ROOT / "artifacts/research_initial_frozen/inputs" / relative
    assert hashlib.sha256(archived.read_bytes()).hexdigest() == digest
original_folder = ROOT / "artifacts/research_initial_frozen/final"
assert all(hashlib.sha256(p.read_bytes()).hexdigest() == hashlib.sha256((ROOT / "artifacts/research/final" / p.relative_to(original_folder)).read_bytes()).hexdigest()
           for p in original_folder.rglob("*") if p.is_file())
receipts = [read(p) for p in (ROOT / "data/source_documents").glob("*.json")]
verified_sources = 0
for receipt in receipts:
    if "path" in receipt and "sha256" in receipt:
        assert hashlib.sha256((ROOT / receipt["path"]).read_bytes()).hexdigest() == receipt["sha256"]
        verified_sources += 1
checked_runs = 0
for phase in ["development", "validation", "final_repaired"]:
    summary = read(ROOT / f"artifacts/research/{phase}/summary.json")
    assert summary["complete"] and len(summary["results"]) == 61
    for row in summary["results"]:
        nav = pd.read_parquet(ROOT / f"artifacts/research/{phase}/{row['id']}/nav.parquet")
        assert np.isfinite(nav.equity).all() and nav.equity.gt(0).all()
        assert np.isclose(nav.equity.iloc[-1] / summary["initial_cash"] - 1, row["total_return"])
        assert not row["holding_quality"]["unresolved_events_held"]
        assert not row["signal_quality"]["unresolved_candidate_windows"]
        checked_runs += 1
notebook = nbformat.read(ROOT / "reports/research_review.ipynb", as_version=4)
nbformat.validate(notebook)
code_cells = [c for c in notebook.cells if c.cell_type == "code"]
assert all(c.execution_count is not None and not any(o.output_type == "error" for o in c.outputs) for c in code_cells)
assert sum("image/png" in o.get("data", {}) for c in code_cells for o in c.outputs) >= 3
for relative, digest in read(ROOT / "reports/input_manifest.json").items():
    assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest
receipt = {"verified_at": datetime.now(UTC).isoformat(), "legacy_files_unchanged": len(baseline["files"]),
           "frozen_inputs_verified": len(frozen["hashes"]), "initial_final_preserved": True,
           "source_documents_hash_verified": verified_sources, "registered_phase_runs_verified": checked_runs,
           "executed_notebook_code_cells": len(code_cells), "status": "passed",
           "boundary": "File/hash and accounting consistency checks. Visual checks are separately recorded. Not investment-strategy approval."}
write_json("artifacts/delivery_verification.json", receipt)
print(json.dumps(receipt, ensure_ascii=False))
