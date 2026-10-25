"""Fresh first-quarter and annual issuer originals for quarter reconciliation."""
import json,hashlib,sys
from pathlib import Path
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor
import httpx
from pypdf import PdfReader
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'src'))
from quant_workbench_app.swine_data import UNIVERSE,read,dump
ROOT=PROJECT/'runtime/research/swine_deep_20261025'

def collect(code):
    selected=[]
    with httpx.Client(timeout=45,follow_redirects=True) as client:
        for page in range(1,5):
            path=ROOT/'sources'/f'{code[:6]}_early_index_{page}.json'
            if not path.exists():
                response=client.get('https://np-anotice-stock.eastmoney.com/api/security/ann',params={
                    'sr':-1,'page_size':100,'page_index':page,'ann_type':'A','client_source':'web',
                    'stock_list':code[:6],'begin_time':'2026-03-01','end_time':'2026-05-31'})
                response.raise_for_status();dump(path,response.json())
            data=read(path)['data'];items=data.get('list',[])
            selected.extend(i for i in items if ('2026年第一季度报告' in i['title'] or '2026年一季度报告' in i['title'] or '2025年年度报告' in i['title'])
                            and not any(w in i['title'] for w in ('摘要','提示','董事','监事','说明会','更正')))
            if page*100>=data['total_hits']:break
        result=[]
        for item in selected:
            sid=f"S_{code[:6]}_{item['art_code']}";path=ROOT/'sources'/f'{sid}.pdf'
            url=f"https://pdf.dfcfw.com/pdf/H2_{item['art_code']}_1.pdf"
            if not path.exists():
                response=client.get(url);response.raise_for_status();path.write_bytes(response.content)
            if not path.with_suffix('.json').exists():
                pages=[{'page':i+1,'text':p.extract_text()} for i,p in enumerate(PdfReader(path).pages)]
                dump(path.with_suffix('.json'),pages)
            result.append({'id':sid,'title':item['title'],'url':url,'publisher':code+'上市公司',
                'local_path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                'retrieved_at':datetime.now(timezone.utc).isoformat(),'published_date':item['notice_date'][:10],
                'published_date_utc_offset':'+08:00','publication_evidence':str((ROOT/'sources'/f'{code[:6]}_early_index_1.json').relative_to(ROOT)),
                'version':'2026-10-25新下载原始披露','admission':'accepted'})
        return result

if __name__=='__main__':
    sources=read(ROOT/'evidence/sources.json');by_id={s['id']:s for s in sources}
    with ThreadPoolExecutor(max_workers=4) as executor:
        for results in executor.map(collect,UNIVERSE['core']):
            for item in results:by_id[item['id']]=item;print(item['id'],item['title'],flush=True)
    dump(ROOT/'evidence/sources.json',list(by_id.values()))
