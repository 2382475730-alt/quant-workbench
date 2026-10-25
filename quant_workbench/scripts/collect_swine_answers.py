"""Archive public company answers through the issuer IR platform's published API."""
import hashlib,sys
from datetime import datetime,timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import httpx
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'src'))
from quant_workbench_app.swine_data import UNIVERSE,read,dump
ROOT=PROJECT/'runtime/research/swine_deep_20261025'

def capture(code):
    url=f'https://{code[:6]}.irlianmeng.com/ydyapi/InteractiveEasy/interactiveEasyList'
    params={'stock_code':code[:6],'rows':0,'pagesize':50,'status':0}
    response=httpx.get(url,params=params,timeout=30,follow_redirects=True);response.raise_for_status()
    body=response.json()
    if body.get('status')!=1 or not body.get('data'):return None
    path=ROOT/'sources'/f'S_IR_{code[:6]}.json';dump(path,body)
    rows=[r for r in body['data'] if r.get('answerdate') and r['answerdate']<'2026-10-25']
    relevant=[r for r in rows if any(w in r['answer'] for w in ('成本','PSY','资金','料肉','产能','母猪'))]
    dump(ROOT/'sources'/f'IR_selected_{code[:6]}.json',relevant)
    print(code,[(r['answerdate'],r['answer']) for r in relevant[:8]],flush=True)
    return {'id':'S_IR_'+code[:6],'title':body['data'][0]['stock_name']+'投关平台公开问答（含互动易/上证e互动公司答复）',
            'publisher':body['data'][0]['stock_name']+'公开答复，投关易平台存档','url':str(response.url),
            'local_path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'retrieved_at':datetime.now(timezone.utc).isoformat(),'published_date':max(r['answerdate'][:10] for r in rows),
            'published_date_utc_offset':'+08:00','publication_evidence':'每条答复answerdate；原始问答与回答方保存在JSON内，问题不能代替公司答复',
            'version':'2026-10-25取得的公开公司答复；快照仅用于当前研究，不回填历史信号','admission':'accepted'}

if __name__=='__main__':
    registry={s['id']:s for s in read(ROOT/'evidence/sources.json')}
    with ThreadPoolExecutor(max_workers=4) as executor:
        for item in executor.map(capture,UNIVERSE['core']):
            if item:registry[item['id']]=item
    dump(ROOT/'evidence/sources.json',list(registry.values()))
