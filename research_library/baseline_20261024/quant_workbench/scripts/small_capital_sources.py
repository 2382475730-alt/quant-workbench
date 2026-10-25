import concurrent.futures,hashlib,json,zipfile,io
from pathlib import Path
from datetime import datetime,timezone
import httpx
from pypdf import PdfReader
from xml.etree import ElementTree
base=Path('research/small_capital_v1/sources')
if (base/'receipts.json').exists():
 raise SystemExit('Source receipts already exist; preserve this version and use a new dated directory.')
urls={
'sse_2026_rules.docx':'https://www.sse.com.cn/lawandrules/sselawsrules2025/trade/universal/c/10816492/files/58bd5ce4dfc94b57a5391f60eb2719ab.docx',
'sse_2026_deferred.docx':'https://www.sse.com.cn/lawandrules/sselawsrules2025/trade/universal/c/10816492/files/7476908baade49b8b14881439d2f89b6.docx',
'csrc_2020_compilation.pdf':'https://www.sse.com.cn/lawandrules/regulations/csrcannoun/c/10117255/files/3bf4b304076849538eff00d61940125f.pdf',
'csrc_2020_amendment.pdf':'https://www.csrc.gov.cn/csrc/c101950/c1047975/1047975/files/%E9%99%84%E4%BB%B61_%E4%B8%AD%E5%9B%BD%E8%AF%81%E7%9B%91%E4%BC%9A%E5%86%B3%E5%AE%9A%E4%BF%AE%E6%94%B9%E7%9A%84%E8%A7%84%E8%8C%83%E6%80%A7%E6%96%87%E4%BB%B6.pdf',
'license.html':'https://tushare.pro/document/1?doc_id=405',
'csrc_permit.html':'https://www.csrc.gov.cn/csrc/c101968/c4188211/content.shtml',
'csrc_2026_enforcement.html':'https://www.csrc.gov.cn/shanghai/c103864/c7625964/content.shtml'}
def fetch(item):
 name,url=item; p=base/name
 try:
  r=httpx.get(url,timeout=30,follow_redirects=True); r.raise_for_status(); p.write_bytes(r.content)
  text=''
  if name.endswith('.docx'):
   root=ElementTree.fromstring(zipfile.ZipFile(io.BytesIO(r.content)).read('word/document.xml'))
   text='\n'.join(''.join(n.itertext()) for n in root.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'))
  if name.endswith('.pdf'):
   reader=PdfReader(p)
   selected=[]
   for i,pg in enumerate(reader.pages):
    t=pg.extract_text()
    if '证券投资顾问' in t or '荐股软件' in t or '第二十四条' in t and i in range(140,155): selected.append(f'PDF page {i+1}\n'+t)
   text='\n\n'.join(selected)
  if text: p.with_suffix('.txt').write_text(text,encoding='utf-8')
  return {'file':name,'url':url,'bytes':len(r.content),'sha256':hashlib.sha256(r.content).hexdigest(),'at':datetime.now(timezone.utc).isoformat()}
 except Exception as e: return {'file':name,'url':url,'failure':type(e).__name__}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex: records=list(ex.map(fetch,urls.items()))
(base/'receipts.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(records,ensure_ascii=False,indent=2))
