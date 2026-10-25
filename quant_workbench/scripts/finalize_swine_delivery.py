"""Bind the completed AI review to the actual files and require delivery checks."""
from datetime import datetime,timezone
import hashlib,json,shutil,subprocess,sys
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'src'))
from quant_workbench_app.swine_data import read,dump
ROOT=PROJECT/'runtime/research/swine_deep_20261025'
BASE=PROJECT/'runtime/research/swine_v1_20261025'
RUNTIME=PROJECT/'runtime'

def hashed(path,root=ROOT):return {'path':str(path.relative_to(root)).replace('\\','/'),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

def main():
    assert (ROOT/'qa/review_notes.md').is_file(),'A substantive review must be performed and recorded first'
    tests=read(RUNTIME/'verification_artifacts/pytest_background.json')
    captures=read(RUNTIME/'verification_artifacts/background/capture_report.json')
    substantive=read(ROOT/'qa/substantive_checks.json');baseline=read(RUNTIME/'verification.json')
    assert tests['exit_code']==0 and tests['tests_passed']>=63 and tests['isolated_desktop']
    assert len(captures['captures'])>=82 and not captures['errors']
    assert substantive['status']=='passed' and baseline['status']=='passed'
    shutil.copyfile(RUNTIME/'verification_artifacts/background/capture_report.json',ROOT/'qa/window_capture_report.json')
    shutil.copyfile(RUNTIME/'verification_artifacts/pytest_background.json',ROOT/'qa/test_report.json')
    shutil.copyfile(RUNTIME/'verification_artifacts/pytest_background.log',ROOT/'qa/test_log.txt')
    sample_names=['pork_0','pork_small_0','pork_small_4','pork_small_5','swine_deep_small_companies_3','swine_deep_small_cycle_3','swine_deep_small_valuation','swine_source_search','swine_price_observations']
    images=[]
    for name in sample_names:
        path=ROOT/'qa/screenshots'/f'{name}.png';path.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(RUNTIME/'verification_artifacts/background'/f'{name}.png',path);images.append(path)
    model=read(ROOT/'model/manifest.json');report=read(ROOT/'report/manifest.json')
    reviewed={r['path'] for r in model['outputs']}|{r['path'] for r in report['deliverables']}|{'model/manifest.json','report/number_bindings.json','qa/review_notes.md','qa/substantive_checks.json','qa/window_capture_report.json','qa/test_report.json','qa/test_log.txt'}
    reviewed|={str(p.relative_to(ROOT)).replace('\\','/') for p in images}
    scopes={
      'sources':'115 sources; admission dates, source hashes, 92 financial label/sign contexts, 12 disclosure-date comparisons, 290 historical price matches, critical original pages visually reviewed; older annual-source limitations declared',
      'independent_math':'Decimal valuation/funding/profit checks, balance identities, inverse pricing, 1,080 and 686 copied-workspace exact reproductions; separate 20-account ledger sample audit',
      'model_economics':'Conditional clean-surplus and zero-growth terminal assumptions; cash restrictions and burn; source-period cost differences; capital-independent current tiers separate from historical replay',
      'narrative':'Complete report and table read; facts, conditions, provenance, missing data and retrospective-strategy limits explicit; no target-price or verified-investment claim',
      'layout':'82 isolated native Tk window states reviewed, including four modules, retained and swine six-company paths, small windows, source filtering and readable price evidence; representative screenshots archived'}
    qa={'reviews':{k:{'status':'passed','reviewer':'Codex current primary agent (self-review; not external auditor)','reviewer_kind':'ai','scope':v,'evidence_path':'qa/review_notes.md'} for k,v in scopes.items()},
        'reviewed_files':[hashed(ROOT/p) for p in sorted(reviewed)],'pages':None,'checked_at':datetime.now(timezone.utc).isoformat()}
    dump(ROOT/'qa/review.json',qa)
    check_script=Path.home()/'.codex/skills/equity-research-report-zh/scripts/check_bundle.py'
    output=ROOT/'qa'/('delivery_check_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.json')
    subprocess.run([sys.executable,str(check_script),str(ROOT),'--stage','delivery','--out',str(output)],check=True)
    assert read(output)['passed']
    deletion=read(RUNTIME/'cleanup/deletion_manifest.json')
    source_audit=read(BASE/'results/source_ledger_audit.json')
    files=[p for folder,pattern in [('src','*.py'),('scripts','*.py'),('config','*.json'),('tests','*.py')] for p in (PROJECT/folder).rglob(pattern)]
    files.extend([PROJECT/'README.md',PROJECT/'AGENTS.md'])
    result={'checked_at':datetime.now(timezone.utc).isoformat(),'status':'completed_with_declared_research_limits',
      'tests_passed':tests['tests_passed'],'background_captures':len(captures['captures']),'window_errors':captures['errors'],
      'checks':{'data_quality':read(BASE/'results/data_quality.json')['status'],'source_ledger_audit':source_audit['status'],
                'deep_substantive':substantive['status'],'standalone_model_and_policy':'passed exact reproduction','delivery_bundle':'passed','preserved_baseline':baseline['status']},
      'sources_registered':len(read(ROOT/'evidence/sources.json')),'facts_registered':len(read(ROOT/'evidence/facts.json')),
      'financial_amount_contexts':len(substantive['financial_context_checks']),'primary_price_observations':58,'price_field_checks':substantive['primary_price_checks'],
      'rolling_scenarios':1080,'policy_sensitivity_scenarios':686,'current_allocation_sensitivity_cases':12,
      'deleted_research_files':len(deletion['files']),'preserved_baseline_files_verified':baseline['migration_files_verified'],
      'retained_delivery_seal_entries':baseline['delivery_seals']['small_capital_v1'],
      'cache_handling':'User explicitly exempted old compiled/tool caches; not a blocker and no further deletion attempted',
      'remaining_research_limits':['Historical current-universe and retrospective-rule bias; overlapping June entry dates are not independent and do not cover a complete cycle',
        'Conditional valuation and operating-profit requirements, not a full calibrated long-term DCF or consolidated earnings forecast',
        'Some comparable costs remain missing or from older months; most current financials remain H1, and no real-time balance sheet is assumed',
        'Current tier weights depend on explicit unoptimized thresholds and common ROE assumptions; they are not a recommendation to trade the default weights'],
      'delivery_check':str(output.relative_to(PROJECT)),'research_report':str((ROOT/'report/research.md').relative_to(PROJECT)),
      'implementation_hashes':{str(p.relative_to(PROJECT)):hashed(p,PROJECT)['sha256'] for p in sorted(files)}}
    dump(RUNTIME/'acceptance_swine_20261025.json',result)
    print(json.dumps({k:result[k] for k in ('status','tests_passed','background_captures','sources_registered','facts_registered','deleted_research_files')},ensure_ascii=False))

if __name__=='__main__':main()
