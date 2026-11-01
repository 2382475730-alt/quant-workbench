"""Package only the new data needed by the 2026-11-01 application update."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

from prepare_github_snapshot import WORKSPACE, candidates, check_secrets

PROJECT = WORKSPACE / 'quant_workbench'
TAG = 'update-20261101'
OUT = PROJECT / 'runtime/github_delivery' / TAG
DOCS = PROJECT / 'docs/github'
QA = PROJECT / 'runtime/verification_artifacts/releases' / TAG


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    QA.mkdir(parents=True, exist_ok=True)
    verification = PROJECT / 'runtime/verification_artifacts'
    for name in ('all_modules_ui_20261101.json', 'overview_ui_20261101.json', 'plain_writing_20261031.json',
                 'pytest_background.json'):
        shutil.copy2(verification / name, QA / name)
    for name in ('capture_report.json', 'note_geometry.json'):
        shutil.copy2(verification / 'background' / name, QA / name)
    (QA / 'screenshots').mkdir(exist_ok=True)
    for path in sorted((verification / 'background').glob('*.png')):
        shutil.copy2(path, QA / 'screenshots' / path.name)
    roots = [PROJECT / 'runtime/research/swine_overview_20261029', PROJECT / 'runtime/editorial_20261031', QA]
    paths = sorted({p for root in roots for p in candidates(root)})
    status = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z', '--', 'quant_workbench', 'README.md'], cwd=WORKSPACE)
    code = [WORKSPACE / name for name in status.decode('utf8').split('\0') if name and not name.startswith('quant_workbench/runtime/')]
    audit = check_secrets(sorted(set(paths + code)))
    archive = OUT / 'workbench-update-20261101.zip'
    files = []
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in paths:
            relative = path.relative_to(WORKSPACE).as_posix()
            data = path.read_bytes()
            z.writestr(relative, data)
            files.append({'path': relative, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'asset': archive.name})
    manifest = {'version': 1, 'repository': '2382475730-alt/quant-workbench', 'tag': TAG,
                'requires': 'snapshot-20261025', 'created_at': datetime.now(timezone.utc).isoformat(),
                'assets': [{'name': archive.name, 'bytes': archive.stat().st_size,
                            'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}], 'files': files,
                'scope': 'Official overview data, reviewed report copies and isolated UI verification. Base data is unchanged.',
                'exclusions': ['credentials', 'environments', 'UI state', 'discussion notes', 'exports', 'browser profiles', 'unrelated projects']}
    data = json.dumps(manifest, ensure_ascii=False, indent=2)
    (OUT / 'update-manifest.json').write_text(data, encoding='utf8')
    (DOCS / 'update-20261101-manifest.json').write_text(data, encoding='utf8')
    (OUT / 'secret_scan.json').write_text(json.dumps(audit, indent=2), encoding='utf8')
    print(json.dumps({'files': len(files), 'archive_bytes': archive.stat().st_size, 'scan': audit}, ensure_ascii=False))


if __name__ == '__main__':
    main()
