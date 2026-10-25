"""Trace displayed core financial amounts to fresh issuer reports, with page context."""
import hashlib
import json
import re
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT/'src'))
from quant_workbench_app.swine_data import ROOT, read, dump

FIELDS = {'revenue':'营业收入', 'net_profit':'归母净利润', 'operating_cashflow':'经营活动现金流净额',
          'capex_cash':'购建长期资产现金支出', 'cash':'货币资金', 'parent_equity':'归母净资产', 'total_assets':'总资产'}

def main():
    docs=read(ROOT/'sources/documents/receipts.json')
    results=[]
    failures=[]
    for row in read(ROOT/'results/companies.json'):
        if row['group']!='core':
            continue
        period_word='半年度报告' if row['period'].endswith('0630') else '三季度报告'
        doc=next(d for d in docs if d['code']==row['code'][:6] and period_word in d['title'])
        path=PROJECT/doc['path']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=doc['sha256']:
            failures.append(row['code']+' PDF hash mismatch')
        pages=read(path.with_suffix('.json'))
        for key,label in FIELDS.items():
            needle=f'{row[key]:.2f}'
            evidence=[]
            for page in pages:
                compact=re.sub(r'[,，\s]','',page['text'])
                position=compact.find(needle)
                if position>=0:
                    evidence.append({'page':page.get('page',pages.index(page)+1),
                                     'context':compact[max(0,position-65):position+len(needle)+50]})
            item={'code':row['code'],'name':row['name'],'field':key,'label':label,'value':row[key],
                  'period':row['period'],'source':doc['url'],'document':doc['path'],
                  'status':'amount_found_in_original' if evidence else 'unmatched','evidence':evidence}
            results.append(item)
            if not evidence:
                failures.append(row['code']+' '+key+' unmatched')
    report={'status':'passed' if not failures else 'failed','checks':len(results),'failures':failures,
            'scope':'Exact amounts located in original consolidated financial reports; page contexts retained. This is source reconciliation, not an audit opinion.',
            'records':results}
    dump(ROOT/'results/financial_reconciliation.json',report)
    print(json.dumps({k:v for k,v in report.items() if k!='records'},ensure_ascii=False))
    if failures:
        raise SystemExit(1)

if __name__=='__main__':
    main()
