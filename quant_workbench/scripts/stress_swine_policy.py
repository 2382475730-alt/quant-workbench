"""Predeclared rule sensitivity; no best-parameter selection."""
import sys
from pathlib import Path
import pandas as pd
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'src'))
from quant_workbench_app.swine_data import ROOT,read,dump
from quant_workbench_app.swine_engine import SwineModel,Costs

VARIANTS={
 'base':{},
 'valuation_cautious':{'entry_pb_percentile':.6,'add_pb_percentile':.4,'harvest_pb_percentile':.7},
 'valuation_relaxed':{'entry_pb_percentile':.8,'add_pb_percentile':.6,'harvest_pb_percentile':.9},
 'funding_tight':{'funding_watch_debt_ratio':.7,'funding_watch_cash_coverage':.3,'funding_exit_debt_ratio':.8,'funding_exit_cash_coverage':.3},
 'funding_loose':{'funding_watch_debt_ratio':.8,'funding_watch_cash_coverage':.15,'funding_exit_debt_ratio':.9,'funding_exit_cash_coverage':.15},
 'review_10':{'review_sessions':10},'review_40':{'review_sessions':40}}

if __name__=='__main__':
    model=SwineModel();rows=[];summary=[]
    from quant_workbench_app.swine_cycle_policy import CyclePolicy
    for label,overrides in VARIANTS.items():
        model.cycle_policy=CyclePolicy(model.codes,overrides)
        group=[]
        for start in model.entry_dates:
            r=model.run(start,'cycle_hold',details=False)['summary']
            group.append({'variant':label,**r})
        frame=pd.DataFrame(group);rows.extend(group)
        summary.append({'variant':label,'overrides':overrides,'count':len(group),'median_return':float(frame['return'].median()),
                        'worst_return':float(frame['return'].min()),'positive_share':float((frame['return']>0).mean()),
                        'worst_drawdown':float(frame.max_drawdown.min()),'mean_exposure':float(frame.mean_exposure.mean())})
        print(label,len(group),flush=True)
    model.cycle_policy=CyclePolicy(model.codes)
    executions=[]
    for capital in (1000,10000,50000,100000,1000000,10000000,100000000):
        for slip in (.001,.003):
            r=model.run('2026-06-01','cycle_hold',capital=capital,costs=Costs(slippage=slip))
            executions.append({**r['summary'],'slippage_assumption':slip,'target_sequence':[(d['decision_date'],d['code'],d['target']) for d in r['decisions']]})
    assert all(r['target_sequence']==executions[0]['target_sequence'] for r in executions)
    dump(ROOT/'results/policy_sensitivity.json',{'protocol':VARIANTS,'summary':summary,'scenarios':rows,
        'execution_sensitivity':executions,'scope':'当前公司池、历史PB可能修订、重叠起点；未调参选优；有限期历史回放不是跨完整周期的前向验证'})
