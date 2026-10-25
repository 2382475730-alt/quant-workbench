"""Check relocation and research seals without rewriting any historical evidence."""
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))
from quant_workbench_app.paths import LIBRARY, RUNTIME, WORKSPACE


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify():
    baseline = LIBRARY.parent
    record = json.loads((PROJECT / "docs/migration_20261024/before.json").read_text(encoding="utf-8"))
    failures, migrated, cache = [], 0, {}
    deletion_path = RUNTIME / 'cleanup/deletion_manifest.json'
    deletion = json.loads(deletion_path.read_text(encoding='utf-8-sig')) if deletion_path.exists() else {}
    removed = {str(Path(r['path']).resolve()).lower(): r for r in deletion.get('files', [])}
    authorized = 0
    for row in record["files"]:
        relative = Path(row["path"])
        path = (WORKSPACE if relative.parts[0] in {".env", ".env.example"} else baseline) / relative
        deleted = removed.get(str(path.resolve()).lower())
        if deleted:
            if path.exists() or deleted['sha256'] != row['sha256'] or deleted['bytes'] != row['bytes']:
                failures.append({'path': row['path'], 'reason': 'authorized deletion mismatch'})
            else:
                authorized += 1
            continue
        if not path.is_file() or path.stat().st_size != row["bytes"]:
            failures.append({"path": row["path"], "reason": "missing or size changed"})
            continue
        actual = digest(path)
        cache[str(path)] = actual
        if actual != row["sha256"]:
            failures.append({"path": row["path"], "reason": "hash changed"})
        else:
            migrated += 1
    seals = {}
    for name in ("small_capital_v1",):
        path = LIBRARY / "artifacts" / name / "delivery_manifest.json"
        entries = json.loads(path.read_text(encoding="utf-8"))["hashes"]
        for relative, expected in entries.items():
            target = LIBRARY / relative
            actual = cache.get(str(target))
            if actual is None and target.is_file():
                actual = digest(target)
            if actual != expected:
                failures.append({"path": str(target), "reason": name + " seal mismatch"})
        seals[name] = len(entries)
    for target in deletion.get('targets', []):
        if Path(target).exists():
            failures.append({'path': target, 'reason': 'deleted target reappeared'})
    result = {"status": "passed" if not failures else "failed",
              "checked_at": datetime.now(UTC).isoformat(),
              "migration_files_verified": migrated, "migration_files_expected": len(record["files"]),
              "delivery_seals": seals, "authorized_deletions_verified": authorized,
              "failures": failures, "scope": "file integrity and computation freeze; not strategy effectiveness"}
    RUNTIME.mkdir(exist_ok=True)
    (RUNTIME / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    verify()
