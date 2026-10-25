"""Prepare bounded release archives without credentials, environments or UI caches."""
from datetime import datetime,timezone
import hashlib,json,os,re,zipfile
from pathlib import Path

WORKSPACE=Path(__file__).resolve().parents[2]
OUT=WORKSPACE/'quant_workbench/runtime/github_delivery'
DOCS=WORKSPACE/'quant_workbench/docs/github'
DENY={'.git','.venv','__pycache__','.pytest_cache','.ruff_cache','node_modules','.next','logs','legacy_pytest_cache','pytest_cache'}
MAX_BYTES=512*1024**2

def candidates(root):
    if root.is_file():yield root;return
    for base,dirs,files in os.walk(root,followlinks=False):
        dirs[:]=sorted(d for d in dirs if d not in DENY and not (Path(base)/d).is_symlink())
        for name in sorted(files):
            p=Path(base)/name
            if p.is_symlink() or name=='.env' or name.startswith('.env.') or p.suffix.lower() in {'.pyc','.pyo','.log','.pem','.key'}:continue
            yield p

def check_secrets(paths):
    known=[]
    env=WORKSPACE/'.env'
    if env.is_file():
        for line in env.read_text(encoding='utf8').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                value=line.split('=',1)[1].strip().strip('"\'')
                if len(value)>=12 and not any(x in value.lower() for x in ['your_','placeholder','example','localhost']):known.append(value.encode())
    patterns=[rb'gh[opusr]_[A-Za-z0-9_]{25,}',rb'github_pat_[A-Za-z0-9_]{30,}',rb'sk-[A-Za-z0-9_-]{30,}',rb'AKIA[0-9A-Z]{16}',rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----']
    flagged=[]
    for p in paths:
        data=p.read_bytes()
        if any(value in data for value in known) or any(re.search(pattern,data) for pattern in patterns):flagged.append(str(p.relative_to(WORKSPACE)))
    if flagged:raise RuntimeError('Potential secret matches (values suppressed): '+json.dumps(flagged,ensure_ascii=False))
    return {'checked_files':len(paths),'known_credential_values_checked':len(known),'potential_matches':0,'values_never_recorded':True}

def main():
    OUT.mkdir(parents=True,exist_ok=True);DOCS.mkdir(parents=True,exist_ok=True)
    roots=[WORKSPACE/'research_library',WORKSPACE/'quant_workbench/runtime/research',
           WORKSPACE/'quant_workbench/runtime/cleanup',WORKSPACE/'quant_workbench/runtime/verification_artifacts']
    roots += [p for p in (WORKSPACE/'quant_workbench/runtime').glob('*.json') if p.name!='ui_state.json']
    paths=sorted({p for root in roots for p in candidates(root)})
    code=[p for p in candidates(WORKSPACE/'quant_workbench') if 'runtime' not in p.relative_to(WORKSPACE).parts]
    code += [WORKSPACE/n for n in ['.env.example','.gitignore','.gitattributes','AGENTS.md','README.md','LaunchWorkbench.bat']]
    audit=check_secrets(sorted(set(paths+code)))
    (OUT/'secret_scan.json').write_text(json.dumps(audit,indent=2),encoding='utf8')
    groups=[];group=[];size=0
    for p in paths:
        n=p.stat().st_size
        if group and size+n>MAX_BYTES:groups.append(group);group=[];size=0
        group.append(p);size+=n
    if group:groups.append(group)
    assets=[];files=[]
    for i,group in enumerate(groups,1):
        name=f'workbench-data-{i:02d}.zip';archive=OUT/name
        with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
            for p in group:
                relative=p.relative_to(WORKSPACE).as_posix();data=p.read_bytes()
                z.writestr(relative,data)
                files.append({'path':relative,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'asset':name})
        assets.append({'name':name,'bytes':archive.stat().st_size,'sha256':hashlib.file_digest(archive.open('rb'),'sha256').hexdigest()})
        print(name,archive.stat().st_size,flush=True)
    manifest={'version':1,'repository':'2382475730-alt/quant-workbench','tag':'snapshot-20261025',
              'created_at':datetime.now(timezone.utc).isoformat(),'assets':assets,'files':files,
              'exclusions':['credentials and .env variants','Python/Node environments','compiled and tool caches','logs','runtime exports/explorations/UI state'],
              'scope':'Current retained research library plus new swine research and verification; no previously deleted research is restored'}
    content=json.dumps(manifest,ensure_ascii=False,indent=2)
    (OUT/'snapshot-manifest.json').write_text(content,encoding='utf8')
    (DOCS/'snapshot-manifest.json').write_text(content,encoding='utf8')
    print(json.dumps({'files':len(files),'raw_bytes':sum(f['bytes'] for f in files),'archive_bytes':sum(a['bytes'] for a in assets),'secret_scan':audit},ensure_ascii=False))

if __name__=='__main__':main()
