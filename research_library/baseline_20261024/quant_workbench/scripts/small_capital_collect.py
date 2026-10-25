"""Separate ETF acquisition; uses the existing content-addressed transport only."""
import json
import pandas as pd
from quant_workbench.data import ROOT,Client
base=ROOT/'data/small_capital_v1'
if (ROOT/'artifacts/small_capital_v1/freeze.json').exists() or (base/'daily.parquet').exists():
 raise SystemExit('Acquisition already recorded or frozen; create a separately named research version.')
c=Client(); receipts=[]
def get(api,params,name):
 r=c.query(api,params); f=pd.DataFrame(r['rows'],columns=r['fields_returned'])
 if len(f)>=5000: raise ValueError('Possible truncation')
 f.to_parquet(base/(name+'.parquet'),index=False)
 receipts.append({k:r[k] for k in ['api','params','sha256','fetched_at']}|{'file':name+'.parquet','rows':len(f)})
 (base/'receipts.json').write_text(json.dumps(receipts,indent=2),encoding='utf-8')
 print(name,len(f),flush=True); return f
get('fund_daily',{'ts_code':'510500.SH','start_date':'20150101','end_date':'20261023'},'daily')
frames=[]
for y in range(2015,2027):
 frames.append(get('fund_adj',{'ts_code':'510500.SH','start_date':f'{y}0101','end_date':min(f'{y}1231','20261023')},f'adj_{y}'))
pd.concat(frames).to_parquet(base/'adj.parquet',index=False)
get('fund_div',{'ts_code':'510500.SH'},'div')
get('fund_basic',{'ts_code':'510500.SH','market':'E'},'basic')
