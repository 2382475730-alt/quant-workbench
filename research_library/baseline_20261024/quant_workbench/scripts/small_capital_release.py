"""Seal/verify delivered source and evidence views, separately from computation freeze."""
import argparse
import hashlib
import importlib.metadata
import json
import platform
from datetime import UTC, datetime

from quant_workbench.small_capital_v1.data import BASE, dump
from quant_workbench.small_capital_v1.runner import ROOT, verify


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['seal', 'verify'])
    command = parser.parse_args().command
    target = BASE/'delivery_manifest.json'
    integrity = verify()
    if command == 'verify':
        record = json.loads(target.read_text(encoding='utf-8'))
        changed = [name for name, expected in record['hashes'].items() if not (ROOT/name).is_file() or digest(ROOT/name) != expected]
        if changed:
            raise ValueError(f'Delivery changed: {changed}')
        print(json.dumps({'delivery_files_verified':len(record['hashes']), 'computation':integrity}, ensure_ascii=False, indent=2))
        return
    if target.exists():
        raise FileExistsError('Delivery already sealed; create a separately named revision')
    paths = []
    for folder in ['src/quant_workbench/small_capital_v1', 'research/small_capital_v1', 'reports/small_capital_v1', 'data/small_capital_v1']:
        paths += [p for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    paths += [ROOT/name for name in ['README.md', 'src/quant_workbench/desktop.py', 'src/quant_workbench/agent_interface.py', 'config/small_capital_v1.json', 'tests/test_small_capital_v1.py']]
    paths += list((ROOT/'scripts').glob('small_capital_*.py'))
    paths += list((BASE/'runs').glob('*/manifest.json'))
    for name in ['freeze.json','legacy_before.json','data_audit_initial_failure.json','data_audit.json','example_task.json','example_plan.json','uncertainty.json','risk_drift.json','legacy_holding_quality.json','agent_tool_verification.json','tests_full.log']:
        paths.append(BASE/name)
    now = datetime.now(UTC)
    started = datetime.fromisoformat('2026-10-24T07:24:48+00:00')
    versions = {name: importlib.metadata.version(name) for name in ['numpy','pandas','scipy','pyarrow','matplotlib','pytest','nbformat','nbclient']}
    record = {'version':'small_capital_v1', 'created_at':now.isoformat(), 'started_at':started.isoformat(),
              'elapsed_wall_minutes':(now-started).total_seconds()/60, 'deadline':'2026-10-24T10:24:48+00:00',
              'python':platform.python_version(), 'libraries':versions, 'verification':integrity,
              'tests_passed':83, 'notebook_executed_cells':6, 'forward_days':0,
              'ui_verified':'default cost/client-value page only; user stopped Computer Use with Escape',
              'hashes':{str(p.relative_to(ROOT)):digest(p) for p in sorted(set(paths))}}
    dump(target, record)
    print(json.dumps({k:v for k,v in record.items() if k != 'hashes'} | {'delivery_files':len(record['hashes'])}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
