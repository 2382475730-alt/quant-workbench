"""Final cross-version evidence, independent of choosing winning returns."""
import hashlib
import json

from quant_workbench.quant_agent import verify

from quant_workbench.data import ROOT, write_json

integrity = verify()
records = []
for old in sorted((ROOT/'artifacts/enhancement_v1r3/runs').glob('*/*/result.json')):
    relative = old.relative_to(ROOT/'artifacts/enhancement_v1r3/runs')
    new = ROOT/'artifacts/enhancement_v1r4/runs'/relative
    a, b = (json.loads(p.read_text(encoding='utf-8')) for p in [old, new])
    same = all(hashlib.sha256((old.parent/name).read_bytes()).hexdigest() == hashlib.sha256((new.parent/name).read_bytes()).hexdigest()
               for name in ['nav.parquet','trades.parquet','positions.parquet'])
    should_change = a['phase']=='development' and a['strategy']=='defensive_constrained'
    if not should_change and not same:
        raise ValueError('Unexpected ledger change outside the failed startup case')
    records.append({'phase':a['phase'],'id':a['id'],'ledgers_identical':same,
                    'before_return':a['total_return'],'after_return':b['total_return'],
                    'before_failed_decisions':a['solver_failed_or_held'],'after_failed_decisions':b['solver_failed_or_held']})
write_json('reports/enhancement_v1/r3_r4_comparison.json', {'records':records,
           'identical_ledgers':sum(r['ledgers_identical'] for r in records),
           'boundary':'Only the failed defensive development startup is expected to differ; no return-based selection.'})
write_json('reports/enhancement_v1/postrun_findings.json', {
    'status':'research_only', 'forward_evidence_days':0,
    'findings':[
        {'id':'realized_limits','severity':'high','evidence':'Primary review: industry breaches 164/436 days, direct-stock breaches 163 days, core breaches 124 days.',
         'meaning':'Target constraints do not create continuous execution risk control.', 'next':'Forward risk gate and explicit conflict policy before trading use.'},
        {'id':'etf_2016_prices','severity':'high','evidence':'Local ETF versus total-return index daily return differences near 4.2pp on 2016-01-07/08; 2016 ETF TE about 6.87%.',
         'meaning':'Extreme observations affect initial feasibility. Origin not independently established.',
         'next':'Obtain independent historical exchange prices; never delete observations because returns improve.'},
        {'id':'startup_audit_reconciliation','severity':'medium','evidence':'Sealed r4 raw executed-turnover audit labels exemptions by period start, while strategy uses first actual fill.',
         'meaning':'Later first entry is mislabelled a turnover violation in raw summary. Report independently reconciles against actual trade dates.',
         'next':'Read turnover_reconciliation.json; keep raw results unchanged.'}],
    'source_metadata':[{'title':'CSI 300 factsheet identifies H00300 as total return',
                        'url':'https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/000300factsheet.pdf',
                        'scope':'Benchmark identity only; historical daily values come from stored provider responses.'}]})
print(json.dumps({'integrity':integrity,'unchanged_r3_r4_ledgers':sum(r['ledgers_identical'] for r in records)},ensure_ascii=False))
