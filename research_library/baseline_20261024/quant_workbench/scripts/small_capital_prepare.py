import hashlib,json
from pathlib import Path
from pypdf import PdfReader
r=Path.cwd()
out=r/'artifacts/small_capital_v1'
if (out/'legacy_before.json').exists():
 raise SystemExit('Initial preservation record already exists; refusing to replace baseline.')
paths=[]
for folder in ['artifacts/research','artifacts/research_initial_frozen','artifacts/enhancement_v1','artifacts/enhancement_v1r2','artifacts/enhancement_v1r3','artifacts/enhancement_v1r4','data/panels','data/enhancement_v1','config']:
 paths += [p for p in (r/folder).rglob('*') if p.is_file()]
record={'start_utc':'2026-10-24T07:24:48+00:00','deadline_utc':'2026-10-24T10:24:48+00:00','verification_start_latest_utc':'2026-10-24T10:04:48+00:00','hashes':{str(p.relative_to(r)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
(out/'legacy_before.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
for vol,pages in [('I',[24,25,51,52]),('II',[164,174,175,234,235])]:
 p=Path('D:/Study/金融')/f'Shreve_Stochastic_Calculus_for_Finance_{vol}.pdf'
 reader=PdfReader(p)
 text='\n\n'.join(f'PDF page {n}\n'+reader.pages[n-1].extract_text() for n in pages)
 (r/f'research/small_capital_v1/shreve_{vol}_reading.txt').write_text(text,encoding='utf-8')
 print(text)
print('Protected',len(paths),'files')
