"""Validate and restore private-release data, without overwriting changed local files."""
import argparse,hashlib,json,shutil,zipfile
from pathlib import Path,PurePosixPath

WORKSPACE=Path(__file__).resolve().parents[2]

def safe_destination(root,name):
    p=PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name:
        raise ValueError('Unsafe archive path')
    if not (name.startswith('research_library/') or name.startswith('quant_workbench/runtime/')):
        raise ValueError('Archive path outside research data scope')
    target=(root/Path(*p.parts)).resolve()
    if not target.is_relative_to(root.resolve()):raise ValueError('Archive path escapes workspace')
    return target

def restore(assets,root=WORKSPACE,check_only=False,manifest_path=None):
    manifest_path=manifest_path or WORKSPACE/'quant_workbench/docs/github/snapshot-manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf8'))
    expected={r['path']:r for r in manifest['files']}
    if len(expected)!=len(manifest['files']):raise ValueError('Duplicate manifest path')
    for a in manifest['assets']:
        archive=assets/a['name']
        with archive.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
        if archive.stat().st_size!=a['bytes'] or digest!=a['sha256']:raise ValueError('Archive checksum mismatch: '+a['name'])
    # Validate every entry and existing destination before writing any file.
    seen=set()
    for a in manifest['assets']:
        with zipfile.ZipFile(assets/a['name']) as z:
            for info in z.infolist():
                target=safe_destination(root,info.filename);r=expected.get(info.filename)
                if info.filename in seen or not r or r['asset']!=a['name'] or info.file_size!=r['bytes']:raise ValueError('Unexpected archive member')
                seen.add(info.filename)
                with z.open(info) as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
                if digest!=r['sha256']:raise ValueError('File checksum mismatch: '+info.filename)
                if target.exists():
                    if not target.is_file():raise ValueError('Destination is not a file')
                    with target.open('rb') as f:existing=hashlib.file_digest(f,'sha256').hexdigest()
                    if existing!=digest:raise ValueError('Local file differs; refusing overwrite: '+info.filename)
    if seen!=set(expected):raise ValueError('Missing archive members')
    if not check_only:
        for a in manifest['assets']:
            with zipfile.ZipFile(assets/a['name']) as z:
                for info in z.infolist():
                    target=safe_destination(root,info.filename)
                    if target.exists():continue
                    target.parent.mkdir(parents=True,exist_ok=True)
                    with z.open(info) as source,target.open('xb') as destination:shutil.copyfileobj(source,destination)
    print(json.dumps({'files_verified':len(seen),'check_only':check_only,'status':'passed'}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('assets',type=Path);parser.add_argument('--check-only',action='store_true')
    args=parser.parse_args();restore(args.assets,check_only=args.check_only)
