"""New historical acquisition for cycle context; never imports old research."""
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import httpx
from dotenv import dotenv_values

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'src'))
from quant_workbench_app.swine_data import ROOT, UNIVERSE, read, dump

def main():
    env={**dotenv_values(PROJECT.parent/'.env'),**os.environ}
    token=next((env[k] for k in ('TUSHARE_TOKEN','TS_TOKEN','TUSHARE_API_TOKEN') if env.get(k)),None)
    if not token:
        raise RuntimeError('Historical source credential unavailable')
    receipts=[]
    with httpx.Client(timeout=40) as client:
        for code in UNIVERSE['core']:
            output={'code':code}
            for api in ('daily_basic','income','balancesheet','cashflow'):
                merged=[]
                for start,end in [('20160101','20191231'),('20200101','20241231')]:
                    params={'ts_code':code,'start_date':start,'end_date':end}
                    spec={'api':api,'params':params}
                    key=hashlib.sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest()
                    path=ROOT/'sources/history'/f'{key}.json'
                    if path.exists():
                        data=read(path)
                    else:
                        data=None
                        for attempt in range(3):
                            try:
                                response=client.post('https://api.tushare.pro',json={'api_name':api,'token':token,'params':params,'fields':''})
                                response.raise_for_status()
                                body=response.json()
                                if body.get('code')!=0:
                                    raise RuntimeError('Provider unavailable')
                                block=body['data']
                                rows=[dict(zip(block['fields'],r,strict=True)) for r in block['items']]
                                data={'rows':rows,'receipt':{**spec,'fetched_at':datetime.now(timezone.utc).isoformat(),
                                      'rows':len(rows),'sha256':hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest(),
                                      'path':str(path.relative_to(PROJECT)),'source':'https://api.tushare.pro'}}
                                dump(path,data)
                                time.sleep(.4)
                                break
                            except (httpx.HTTPError,ValueError,RuntimeError):
                                if attempt==2:
                                    raise RuntimeError(f'{code} {api} historical acquisition failed; no values substituted') from None
                                time.sleep(2**attempt)
                    merged.extend(data['rows'])
                    receipts.append(data['receipt'])
                current=read(ROOT/'data'/f'{code}.json')[api]
                merged.extend(current)
                output[api]=list({json.dumps(r,sort_keys=True):r for r in merged}.values())
                print(code,api,len(output[api]),flush=True)
            dump(ROOT/'data/history'/f'{code}.json',output)
    dump(ROOT/'sources/history/receipts.json',receipts)

if __name__=='__main__':
    main()
