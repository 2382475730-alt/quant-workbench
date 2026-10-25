"""Independent source-hash and cash/share ledger reconciliation."""
import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'src'))
from quant_workbench_app.swine_data import ROOT, read, dump
from quant_workbench_app.swine_engine import SwineModel, STRATEGIES

def main():
    failures=[]
    verified=0
    source_rows=defaultdict(set)
    for path in (ROOT/'sources').rglob('*.json'):
        data=read(path)
        if not isinstance(data,dict) or 'receipt' not in data or 'rows' not in data:
            continue
        actual=hashlib.sha256(json.dumps(data['rows'],sort_keys=True).encode()).hexdigest()
        if actual!=data['receipt']['sha256']:
            failures.append(str(path)+' source hash')
        receipt=data['receipt']
        key=(receipt['api'],receipt['params'].get('ts_code'))
        source_rows[key].update(json.dumps(r,sort_keys=True) for r in data['rows'])
        verified+=1
    mapped_rows=0
    for path in list((ROOT/'data').glob('*.SZ.json'))+list((ROOT/'data').glob('*.SH.json'))+list((ROOT/'data/history').glob('*.json')):
        record=read(path)
        for api,rows in record.items():
            if not isinstance(rows,list):
                continue
            source_api=({'daily':'fund_daily','adj_factor':'fund_adj'}.get(api,api)
                        if record['code']=='510300.SH' else api)
            allowed=source_rows[(source_api,record['code'])]
            for row in rows:
                if json.dumps(row,sort_keys=True) not in allowed:
                    failures.append(f'{path.name} {api} row lacks acquired source')
                mapped_rows+=1
    for sub in ('documents','industry'):
        for record in read(ROOT/f'sources/{sub}/receipts.json'):
            if not record.get('path'):
                failures.append(sub+' unavailable local source')
                continue
            path=PROJECT/record['path']
            if hashlib.sha256(path.read_bytes()).hexdigest()!=record['sha256']:
                failures.append(str(path)+' archive hash')
            verified+=1
    model=SwineModel()
    checks=[]
    for capital in (None,10000,100000,10000000):
        for strategy in STRATEGIES:
            run=model.run('2026-06-01',strategy,capital=capital)
            for decision in run['decisions']:
                if decision['information_date']>=decision['decision_date'] or (decision.get('capacity_publication') and decision['capacity_publication']>decision['information_date']):
                    failures.append('future cycle decision '+str(decision))
                for field in ('financial_publication','pb_observation_date'):
                    if decision.get(field) and decision[field]>decision['information_date'].replace('-',''):
                        failures.append('future financial/valuation '+str(decision))
            cash=float(capital or 1)
            shares=defaultdict(float)
            receivable=0.
            trades=defaultdict(list)
            events=defaultdict(list)
            for row in run['trades']:
                trades[row['date']].append(row)
            for row in run['events']:
                events[row['date']].append(row)
            for row in run['nav']:
                day=row['date']
                for event in events[day]:
                    if event['type']=='dividend_accrued':
                        receivable+=event['net_amount']
                    elif event['type']=='dividend_paid':
                        cash+=event['net_amount']
                        receivable-=event['net_amount']
                for trade in trades[day]:
                    cash-=trade['shares']*trade['price']+trade['fees']
                    shares[trade['code']]+=trade['shares']
                market_value=sum(q*float(model.market['raw_close'].loc[day,code]) for code,q in shares.items())
                expected={'cash':cash,'market_value':market_value,'receivable':receivable,'equity':cash+market_value+receivable}
                for field,value in expected.items():
                    if not math.isclose(value,row[field],rel_tol=1e-10,abs_tol=1e-7):
                        failures.append(f'{capital} {strategy} {day} {field}')
                if capital and any(abs(q/100-round(q/100))>1e-8 for q in shares.values()):
                    failures.append(f'{capital} {strategy} invalid lot')
            checks.append({'capital':capital,'strategy':strategy,'days':len(run['nav']),'trades':len(run['trades']),
                           'dividend_events':len(run['events']),'ending_cash':cash,'ending_equity':run['summary']['ending_equity']})
    result={'status':'passed' if not failures else 'failed','source_files_verified':verified,'data_rows_mapped_to_sources':mapped_rows,
            'account_scenarios':len(checks),'account_days':sum(r['days'] for r in checks),'checks':checks,'failures':failures}
    dump(ROOT/'results/source_ledger_audit.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='checks'},ensure_ascii=False))
    if failures:
        raise SystemExit(1)

if __name__=='__main__':
    main()
