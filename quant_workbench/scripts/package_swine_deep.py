"""Build source-linked research, a standalone model, and explicit judgment registries."""
import hashlib,json,shutil,sys,subprocess
from pathlib import Path
from datetime import datetime,timezone
from decimal import Decimal,ROUND_HALF_UP
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'src'))
from quant_workbench_app.swine_data import ROOT as BASE,read,dump
ROOT=PROJECT/'runtime/research/swine_deep_20261025'

def hashed(path):
    return {'path':str(path.relative_to(ROOT)).replace('\\','/'),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

def main():
    results=read(ROOT/'model/results.json');facts=read(ROOT/'evidence/facts.json');sources=read(ROOT/'evidence/sources.json')
    facts=[f for f in facts if not f['id'].startswith('F_QUOTE_')]
    sources=[s for s in sources if not s['id'].startswith('S_MARKET_')]
    for p in results['profiles']:
        code=p['code'];original=None
        for path in (BASE/'sources').rglob('*.json'):
            data=read(path)
            if isinstance(data,dict) and data.get('receipt',{}).get('api')=='daily' and data['receipt']['params'].get('ts_code')==code:
                original=data;break
        if original is None:raise ValueError('Missing acquired quote receipt '+code)
        quote=next(r for r in original['rows'] if r['trade_date']=='20261023')
        assert quote['close']==p['price']
        path=ROOT/'sources'/f'S_MARKET_{code[:6]}.json';dump(path,original)
        sid='S_MARKET_'+code[:6]
        sources.append({'id':sid,'title':p['name']+'本轮新采集行情原始响应','publisher':'Tushare行情数据服务',
            'url':'https://api.tushare.pro','local_path':str(path.relative_to(ROOT)),
            'sha256':hashed(path)['sha256'],'retrieved_at':original['receipt']['fetched_at'],'published_date':'2026-10-23',
            'published_date_utc_offset':'+08:00','publication_evidence':'报价行trade_date=20261023；不声称独立逐笔对账交易所',
            'version':'2026-10-25新采集行情快照','admission':'accepted'})
        facts.append({'id':'F_QUOTE_'+code[:6],'kind':'fact','label':'2026-10-23未复权收盘价','value':p['price'],
            'unit':'CNY/share','period':'2026-10-23','scope':'A股','source_ids':[sid],
            'locator':'rows[trade_date=20261023].close','raw_value':p['price'],'raw_unit':'CNY/share','normalization_rule':'identity'})
    dump(ROOT/'evidence/facts.json',facts);dump(ROOT/'evidence/sources.json',sources)
    assumptions=[
      {'id':'A_RETURN','value':.10,'rationale':'用户要求跨周期持有，需要明确等待的机会成本；10%只是一组要求回报情景，不是测得的资本成本。','basis_ids':['F_QUOTE_002714'],'model_fields':['recovery.required_return'],'alternatives':[.08,.12],'effect':'要求回报越高，现价隐含终态ROE越高，条件价值越低。'},
      {'id':'A_PATH','value':[-.10,0,.10],'rationale':'显式呈现先亏损、再修复、后盈利的过渡路径；不是对任何公司未来三年的点预测。','basis_ids':['F_002714_20260630_n_income_attr_p','F_605296_20260630_n_income_attr_p'],'model_fields':['recovery.interim_roes'],'alternatives':[[-.1],[-.1,0],[-.2,-.1,0]],'effect':'恢复推迟及亏损消耗净资产会抬高长期盈利要求。'},
      {'id':'A_TERMINAL','value':.15,'rationale':'统一终态ROE用于比较条件，不把周期高点利润永久化；应与历史ROE及公司经营逻辑交叉检查。','basis_ids':['F_002714_20251231_n_income_attr_p','F_605296_20251231_n_income_attr_p'],'model_fields':['recovery.terminal_roe'],'alternatives':[.10,.20],'effect':'终态能力占价值较大部分，敏感性必须展示。'},
      {'id':'A_PAYOUT','value':.30,'rationale':'过渡期正利润分配30%，亏损年零分配；终态零增长、盈利全分配。隐含无新增股本且维持性投入足以支撑盈利。','basis_ids':['F_002714_20260630_total_hldr_eqy_exc_min_int'],'model_fields':['recovery.payout','recovery.terminal_growth'],'alternatives':[0,.5,1],'effect':'分红改变当期现金回报和留下的净资产，不能把同一利润重复计价。'},
      {'id':'A_REFI','value':.50,'rationale':'短期到期义务有一半续作只作为压力情景；没有把授信承诺等同现金。','basis_ids':['F_600975_20260630_st_borr','F_600975_20260630_non_cur_liab_due_1y'],'model_fields':['funding.refinancing'],'alternatives':[0,1],'effect':'续作比例下降增加新融资或经营改善需求。'},
      {'id':'A_BURN','value':1,'rationale':'把半年经营现金减资本开支的净流出流速保持12个月，衡量资金压力；净流入不外推为稳定收益。','basis_ids':['F_002714_20260630_n_cashflow_act','F_002714_20260630_c_pay_acq_const_fiolta'],'model_fields':['funding.burn_factor','funding.months','funding.horizon'],'alternatives':[.5,1.5],'effect':'流出变化和支出削减会改变缺口；额外利息、分红、租赁等尚未完整纳入。'},
      {'id':'A_SUPPLY','value':{'efficiency':.05,'weight':.02},'rationale':'不把母猪去化直接等同肉量下降，单列效率与体重的抵消。','basis_ids':['F_SOW_2026Q3','F_meat_yoy_2026Q3'],'model_fields':['supply.efficiency_change','supply.weight_change'],'alternatives':[{'efficiency':0,'weight':0},{'efficiency':.1,'weight':.02}],'effect':'乘法供给情景没有包含全部生物滞后、进口、库存和需求，不能直接推成猪价。'},
      {'id':'A_POLICY','value':read(PROJECT/'config/swine_cycle_policy.json'),'rationale':'用户愿意跨周期持有，采用估值、资金承受力和供给证据分批；规则在观察期结束后提出，未按收益选优。','basis_ids':['F_SOW_2026Q3','F_600975_20260630_total_liab'],'model_fields':['policy.thresholds','policy.review_sessions'],'alternatives':['估值门槛上下10个百分点','资金门槛收紧/放松','10/40交易日复核'],'effect':'目标不随本金改变；冻结时不恢复权重买入；满足低估与收缩条件时可向阶段目标再平衡。'}]
    assumptions.extend([
      {'id':'A_BRIDGE','value':{'normal_pe':15,'cost_per_kg':12,'volume_change':0,'other_profit':0},'rationale':'反向诊断现价需要多少利润和价差；PE、成本、销量与其他业务贡献均为输入情景，不把月报量年化视为预测。','basis_ids':['F_MONTH_002714_202609_revenue_100m','F_MONTH_002714_202609_price_per_kg','F_QUOTE_002714'],'model_fields':['profit_bridges.normal_pe','profit_bridges.cost_per_kg','profit_bridges.volume_change','profit_bridges.other_profit_assumption'],'alternatives':[{'normal_pe':10,'cost_per_kg':11.5,'volume_change':-.2},{'normal_pe':20,'cost_per_kg':12.5,'volume_change':.2}],'effect':'同一价格下PE越低、销量越低，需要的单位价差越高；成本升高抬高所需售价。价差未完成税项、少数股东及内部交易抵消，不能直接当归母净利。'},
      {'id':'A_BOOK_BRIDGE','value':0,'rationale':'披露日至观察日的权益变化尚未完整核实；默认0仅作占位，用户可在工作台调整。','basis_ids':['F_002714_20260630_total_hldr_eqy_exc_min_int'],'model_fields':['recovery.book_adjustment'],'alternatives':[-.1,.1],'effect':'报告后亏损、分红或股本变化会改变每股权益起点；不能将半年报当实时净资产。'}])
    assumptions.append({'id':'A_ALLOCATION','value':read(PROJECT/'config/swine_allocation.json'),
      'rationale':'用户选择按成本、现金承受力和估值条件分档。先给候选上限，再按估值门槛释放；未知与资金硬约束不被综合分数抵消。全部阈值是显式研究纪律，未按收益优化。',
      'basis_ids':['F_COST_002714','F_RESTRICT_600975','F_605296_20260630_c_pay_acq_const_fiolta','F_QUOTE_001201'],
      'model_fields':['allocation.tiers','allocation.target_weights'],'alternatives':['要求回报8%/10%/12% × 终态ROE20%/25%/35%/45%'],
      'effect':'本金不进入权重计算。候选上限及未释放额度留现金。当前资料形成的新条件不能回填至6月历史信号。'})
    dump(ROOT/'evidence/assumptions.json',assumptions)
    claims=[
      {'id':'C_CYCLE','judgment':'基础产能持续减少，但供给收缩仍在传导，不能确认现货与盈利已经反转。','evidence_ids':['F_SOW_2026Q3','F_output_yoy_2026Q3','F_meat_yoy_2026Q3','A_SUPPLY'],'mechanism':'时点母猪影响未来仔猪，效率、体重、现有猪群和二次育肥改变当期肉量；价格还取决于需求。','model_treatment':'母猪×效率×体重情景，不输出确定的猪价目标。','counterevidence':'肉量仍同比增长，饲料与猪价对现金利润的挤压没有自动消失。','change_condition':'连续同口径出栏/体重/猪价及现金流证据与当前方向相反时重估。'},
      {'id':'C_COST','judgment':'牧原属于核心生猪公司；配套屠宰不是剔除理由，成本优势应按定义与期间验证。','evidence_ids':['F_COST_002714','S_002714_AN202608201828210235','S_IR_002714'],'mechanism':'产业链一体化服务养殖收益，但内部销售抵消和商品猪口径会影响收入占比与成本比较。','model_treatment':'按经营本质纳入，不用90%硬阈值；保留成本上界和月份。','counterevidence':'低成本不等于当前盈利，屠宰增长也不必然提高股东回报。','change_condition':'持续经营结构转向非猪业务或可比成本优势丧失时重估。'},
      {'id':'C_FUNDING','judgment':'跨周期需要评估融资承受力，账面货币资金不能全部当可自由使用现金。','evidence_ids':['F_RESTRICT_600975','F_PURPOSE_600975','F_RESTRICT_002714','A_REFI','A_BURN'],'mechanism':'受限及用途资金不能任意补偿经营流出；续贷与资本开支节奏决定资金桥。','model_treatment':'可用现金代理逐项扣减，展示续作与流出二维情景；不是违约概率。','counterevidence':'实际猪价、资本开支、资产处置及融资条件可能好于压力假设。','change_condition':'受限资金释放、资本开支削减、实际融资落地或经营现金扭转。'},
      {'id':'C_EARNINGS','judgment':'减值是亏损解释的一部分，六家公司剔除资产减值损益后H1利润总额仍为负。','evidence_ids':['F_'+p['code'][:6]+'_20260630_total_profit' for p in results['profiles']]+['F_'+p['code'][:6]+'_20260630_assets_impair_loss' for p in results['profiles']],
       'mechanism':'售价成本缺口及其他费用仍然消耗利润，资产损益加回不创造现金。','model_treatment':'分列Q1/Q2、带符号的资产减值与剔除后的利润总额，不标作正常化净利。','counterevidence':'会计转销可能改善后续成本，经营改善幅度需等待新披露。','change_condition':'后续同口径利润、经营现金和权益同步改善。'},
      {'id':'C_VALUE','judgment':'持有理由必须包括现价需要的恢复强度和时间，低历史PB不足以单独证明便宜。','evidence_ids':['A_RETURN','A_PATH','A_TERMINAL','A_PAYOUT','F_QUOTE_002714','F_002714_20260630_total_hldr_eqy_exc_min_int'],'mechanism':'过渡亏损减少每股净资产，等待折现与终态能力共同决定条件价值。','model_treatment':'股利折现与剩余收益恒等检验，反算终态ROE，不给确定目标价。','counterevidence':'高效率成长或资本结构变化可以改变终态，当前假设并非估计的真实未来。','change_condition':'新财报净资产、增发/回购、持续ROE、维持资本开支与长期增长证据变化。'},
      {'id':'C_POLICY','judgment':'跨周期草案可用于有纪律的研究回放，现有窗口不足以证明穿越完整猪周期。','evidence_ids':['A_POLICY','A_REFI','A_PATH'],'mechanism':'资金安全、估值条件决定新增与退出，资金金额只影响执行精度。','model_treatment':'从2026年6月逐日移动起点；前一交易日前已公告资料；完整决策与交易账本；参数敏感性不挑最优。','counterevidence':'当前选股、历史PB修订、事后规则及重叠窗口仍有限制，低回撤部分来自低仓位。','change_condition':'后续真实可得数据与不同周期的独立检验不足时不升级为已验证策略。'}]
    claims.append({'id':'C_ALLOCATION','judgment':'当前研究分档应保留现金与不确定性，不能因跨周期持有意愿就强行配置满额。',
      'evidence_ids':['A_ALLOCATION','A_RETURN','A_PATH','F_RESTRICT_600975','F_QUOTE_001201'],
      'mechanism':'低成本优势需要融资承受力支撑，良好公司也可能需要超出当前假设的盈利恢复才能解释现价。',
      'model_treatment':'成本/现金分档给候选上限，条件价与现价的覆盖倍数释放额度；提供12组估值敏感性；当前分档不参与历史回放。',
      'counterevidence':'削减扩张支出、释放受限资金、更高长期ROE或不同恢复路径可能提高额度；共同25%终态ROE并非逐公司预测。',
      'change_condition':'核实新成本、资金用途、资本开支计划及报告后净资产后重分档；改假设须保留输入。'})
    dump(ROOT/'evidence/claims.json',claims)
    gaps=[
      {'id':'G_COST','issue':'新五丰缺少已核实可比完全成本；巨星/神农/东瑞最近已核实成本为7月，不能冒充9月。','impact':'阻止精确成本排名与当前月利润估计。','treatment':'显示未核实或历史月份；保留公司答复而非把目标当实绩。','affected_claims':['C_COST','C_EARNINGS']},
      {'id':'G_FORECAST','issue':'缺少完整、可独立校准的长期销量、维持性资本开支、终态增长及资本成本预测。','impact':'不能给可信的单一DCF目标价。','treatment':'保留条件估值与反向要求；10%等输入清楚标为假设，用户可改。','affected_claims':['C_VALUE']},
      {'id':'G_DEMAND','issue':'需求、进口、冻品库存及二次育肥未形成完整连续可比序列。','impact':'母猪变化无法唯一决定猪价和反转月份。','treatment':'只做供给机制情景，不给反转时间保证。','affected_claims':['C_CYCLE']},
      {'id':'G_FUNDING','issue':'历史信号未逐季拆完受限资金和用途限制；当前压力桥未包含全部租赁、融资利息与未来分红。','impact':'历史现金覆盖可能高估，压力缺口不是完整付款预算。','treatment':'历史信号注明货币资金上界代理；当前H1另做受限扣除；不把授信当现金。','affected_claims':['C_FUNDING','C_POLICY']},
      {'id':'G_VALIDATION','issue':'策略事后提出、当前公司池选择，供应商PB可能追溯修订；实际观察期未跨完整周期。','impact':'回放不能证明长期投资有效或把重叠起点当胜率。','treatment':'明确情景回放，保留全部起点及阈值敏感性，未做最佳参数选择。','affected_claims':['C_POLICY']},
      {'id':'G_FRESHNESS','issue':'除天邦已披露三季报外，其余核心公司最新财务仍为半年报；实时账户费率与税收不同。','impact':'不能把报表当10月实时资产负债表，也不能把研究账本当实际成交。','treatment':'财报及行情日期逐项列示，资金压力统一H1，费用和滑点明确为假设。','affected_claims':['C_FUNDING','C_VALUE','C_POLICY']}]
    dump(ROOT/'evidence/gaps.json',gaps)
    static={k:v for k,v in results.items() if k not in ('profiles','price_history_summary','allocation','allocation_sensitivity','profit_bridges','supply_scenarios','failures','status')}
    static['profiles']=[{k:v for k,v in p.items() if k not in ('valuation','stress','required_roe_grid')} for p in results['profiles']]
    dump(ROOT/'model/static_inputs.json',static)
    shutil.copyfile(PROJECT/'src/quant_workbench_app/swine_valuation.py',ROOT/'model/valuation_engine.py')
    allocation_source=(PROJECT/'src/quant_workbench_app/swine_allocation.py').read_text(encoding='utf8').replace('from .swine_valuation import','from valuation_engine import')
    (ROOT/'model/allocation_engine.py').write_text(allocation_source,encoding='utf8')
    runner='''import json\nfrom pathlib import Path\nfrom valuation_engine import recovery_value,funding_stress,supply_change\nR=Path(__file__).resolve().parent\nread=lambda p:json.loads(p.read_text(encoding="utf8"))\nx=read(R/"static_inputs.json");raw=read(R/"raw_financial_inputs.json")\nf={r["id"]:r for r in read(R.parent/"evidence/facts.json")}\na={r["id"]:r["value"] for r in read(R.parent/"evidence/assumptions.json")}\nfor p in x["profiles"]:\n code=p["code"];v=raw[code];bal=v["half_balance"];cf=v["half_cashflow"];latest=v["latest_balance"]\n available=bal["money_cap"]-f["F_RESTRICT_"+code[:6]]["value"]-f.get("F_PURPOSE_"+code[:6],{"value":0})["value"]\n assert abs(available-p["cash_available_proxy"])<.001\n short=bal["st_borr"]+bal["non_cur_liab_due_1y"]\n bps=latest["total_hldr_eqy_exc_min_int"]/latest["total_share"]\n assert abs(bps-p["latest_bps"])<1e-9\n p["valuation"]=recovery_value(bps,p["price"],a["A_RETURN"],a["A_PATH"],a["A_TERMINAL"],a["A_PAYOUT"])\n p["stress"]=[funding_stress(available,short,cf["n_cashflow_act"],cf["c_pay_acq_const_fiolta"],refinancing=refi,burn_factor=burn) for burn in (.5,1,1.5) for refi in (0,.5,1)]\n p["required_roe_grid"]=[{"required_return":ke,"years":n,**recovery_value(bps,p["price"],ke,tuple([-.1]+[0]*(n-1)),.15)} for ke in (.08,.1,.12) for n in (1,2,3)]\nx["supply_scenarios"]=[{"efficiency_change":e,"weight_change":w,"supply_change":supply_change(f["F_sow_yoy_2026Q3"]["value"],e,w)} for e in (0,.05,.1) for w in (0,.02)]\nx["failures"]=[];x["status"]="passed"\n(R/"reproduced.json").write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding="utf8")\nprint("Standalone six-company model reproduced")\n'''
    runner=runner.replace('recovery_value,funding_stress,supply_change','recovery_value,funding_stress,supply_change,profit_requirement')
    bridge_runner='''monthly=read(R/"monthly_operations.json")
for row in x["price_sensitivity"]:
 code=row["code"];rows=[r for r in monthly if r["code"]==code]
 kg=sum(f["F_MONTH_"+code+"_"+r["month"].replace("-","")+"_revenue_100m"]["value"]*1e8/f["F_MONTH_"+code+"_"+r["month"].replace("-","")+"_price_per_kg"]["value"] for r in rows)
 assert row["kg_proxy"]==kg and row["annualized_kg_proxy"]==kg*12/len(rows)
x["profit_bridges"]=[]
for row in x["price_sensitivity"]:
 p=next(p for p in x["profiles"] if p["code"].startswith(row["code"]))
 x["profit_bridges"].append({"code":p["code"],"name":p["name"],**profit_requirement(p["price"],p["latest_share_count"],row["annualized_kg_proxy"],**a["A_BRIDGE"])})
'''
    runner=runner.replace('x["failures"]=[];',bridge_runner+'x["failures"]=[];')
    runner=runner.replace('x["failures"]=[];','from allocation_engine import tier_allocation,allocation_sensitivity\np=read(R/"allocation_policy.json")\nx["allocation"]=tier_allocation(x["profiles"],x["costs"],p)\nx["allocation_sensitivity"]=allocation_sensitivity(x["profiles"],x["costs"],p)\nx["failures"]=[];')
    history_runner='''history=read(R/"price_history.json")["rows"]
for row in history:
 for field in ("hog","piglet","corn","soymeal","feed"):
  assert f["F_HIST_"+row["period"].replace("-","")+"_"+field]["value"]==row[field]
x["price_history_summary"]={"observations":len(history),"peak":max(history,key=lambda r:r["hog"]),"low":min(history,key=lambda r:r["hog"]),"latest":history[-1]}
'''
    runner=runner.replace('x["failures"]=[];',history_runner+'x["failures"]=[];')
    history_roe_runner='''for p in x["profiles"]:
 years=raw[p["code"]]["latest_record"]["annual_history"];computed=[]
 for old,new in zip(years,years[1:]):
  if int(new["year"])-int(old["year"])==1 and old.get("parent_equity") and new.get("parent_equity") and new.get("net_profit") is not None and old["parent_equity"]>0 and new["parent_equity"]>0:
   computed.append({"year":new["year"],"roe":new["net_profit"]/((old["parent_equity"]+new["parent_equity"])/2)})
 assert computed==p["historical_roe_proxy"]
'''
    runner=runner.replace('x["failures"]=[];',history_roe_runner+'x["failures"]=[];')
    (ROOT/'model/run.py').write_text(runner,encoding='utf8')
    subprocess.run([sys.executable,str(ROOT/'model/run.py')],check=True)
    reproduced=read(ROOT/'model/reproduced.json')
    assert reproduced==results,'Standalone results differ from workbench model'
    shutil.copyfile(BASE/'results/policy_sensitivity.json',ROOT/'model/policy_sensitivity.json')
    shutil.copyfile(BASE/'results/rolling_summary.json',ROOT/'model/rolling_summary.json')
    policy_inputs,policy_code=package_policy(results)
    subprocess.run([sys.executable,str(ROOT/'model/run_policy.py')],check=True)
    write_report(results,sources)
    manifest={'command':['python model/run.py','python model/run_policy.py'],'runtime':sys.version+'; pandas and numpy from the existing workbench environment','scope':'Standalone conditional models plus full 1,080 rolling entries and 686 rule sensitivity scenarios, with copied actual inputs and code',
              'inputs':[hashed(ROOT/p) for p in ('project.json','evidence/facts.json','evidence/assumptions.json','model/static_inputs.json','model/raw_financial_inputs.json','model/monthly_operations.json','model/allocation_policy.json','model/price_history.json')]+policy_inputs,
              'code':[hashed(ROOT/p) for p in ('model/run.py','model/valuation_engine.py','model/allocation_engine.py','model/run_policy.py')]+policy_code,
              'outputs':[hashed(ROOT/p) for p in ('model/results.json','model/reproduced.json','model/financial_checks.json','model/policy_sensitivity.json','model/rolling_summary.json')]}
    dump(ROOT/'model/manifest.json',manifest)
    dump(ROOT/'report/manifest.json',{'deliverables':[hashed(ROOT/'report/research.md')]})
    print('Packaged',len(sources),'sources',len(facts),'facts',len(claims),'judgments')

def package_policy(results):
    workspace=ROOT/'model/replay_workspace'
    package=workspace/'src/quant_workbench_app';package.mkdir(parents=True,exist_ok=True)
    (package/'__init__.py').write_text('',encoding='utf8')
    (package/'paths.py').write_text('from pathlib import Path\nPROJECT=Path(__file__).resolve().parents[2]\n',encoding='utf8')
    code=[package/'__init__.py',package/'paths.py'];inputs=[]
    for name in ('swine_data.py','swine_cycle_policy.py','swine_engine.py'):
        target=package/name;shutil.copyfile(PROJECT/'src/quant_workbench_app'/name,target);code.append(target)
    for name in ('swine_research.json','swine_universe.json','swine_cycle_policy.json'):
        target=workspace/'config'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(PROJECT/'config'/name,target);inputs.append(target)
    base=workspace/'runtime/research/swine_v1_20261025'
    universe=read(PROJECT/'config/swine_universe.json')
    paths=['data/calendar.json']+[f'data/{c}.json' for c in universe['research_basket']]+[f'data/history/{c}.json' for c in universe['research_basket']]
    for relative in paths:
        target=base/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(BASE/relative,target);inputs.append(target)
    capacity=workspace/'runtime/research/swine_deep_20261025/model/results.json';dump(capacity,{'capacity':results['capacity']});inputs.append(capacity)
    for name in ('run_swine_research.py','stress_swine_policy.py'):
        target=workspace/'scripts'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(PROJECT/'scripts'/name,target);code.append(target)
    runner='''import subprocess,sys,json\nfrom pathlib import Path\nR=Path(__file__).resolve().parent\nW=R/"replay_workspace"\nfor name in ("run_swine_research.py","stress_swine_policy.py"):\n subprocess.run([sys.executable,str(W/"scripts"/name)],check=True)\nfor name in ("rolling_summary.json","policy_sensitivity.json"):\n a=json.loads((R/name).read_text(encoding="utf8"))\n b=json.loads((W/"runtime/research/swine_v1_20261025/results"/name).read_text(encoding="utf8"))\n assert a==b, name+" failed exact reproduction"\nprint("Independent copied workspace reproduced all strategy and sensitivity results")\n'''
    (ROOT/'model/run_policy.py').write_text(runner,encoding='utf8')
    return [hashed(p) for p in inputs],[hashed(p) for p in code]

def write_report(data,sources):
    sm={s['id']:s for s in sources};bindings=[]
    def n(pointer,decimals=2,scale=1,label=None):
        value=data
        for key in pointer.strip('/').split('/'):value=value[int(key)] if isinstance(value,list) else value[key]
        result=(Decimal(str(value))*Decimal(str(scale))).quantize(Decimal(1).scaleb(-decimals),rounding=ROUND_HALF_UP)
        bindings.append({'label':label or pointer,'report_location':'research.md: '+(label or pointer),'model_path':'model/results.json','pointer':pointer,'scale':scale,'decimals':decimals,'value':str(result)})
        return f'{result:,.{decimals}f}'
    def source(sid):
        s=sm[sid];return f"[{s['title']}]({s['url']})"
    lines=['# 生猪养殖：行业、经营承受力与跨周期估值研究',
      '研究观察日：2026-10-25；行情截至2026-10-23。财务比较统一2026H1，估值净资产按各公司最新已披露报告。新研究独立从零采集，不沿用已删除研究的结论。',
      '## 先看公司对比',
      '牧原、巨星、神农、东瑞、新五丰、天邦为核心经营来自生猪的研究公司；允许配套饲料和屠宰，不机械套用90%收入门槛。纳入研究不等于纳入持仓。温氏等猪禽并重企业未进入核心池。',
      '|公司|已核实完全成本 元/kg|期间|可用现金代理/短期义务|披露权益PB|等待情景隐含终态ROE|',
      '|---|---:|---|---:|---:|---:|']
    for i,p in enumerate(data['profiles']):
        cost=next((c for c in data['costs'] if c['code']==p['code']),None)
        j=data['costs'].index(cost) if cost else None
        c=({'strict_upper':'<','upper':'≤'}.get(cost['qualifier'],'')+n(f'/costs/{j}/value')) if cost else '未核实'
        lines.append(f"|{p['name']}|{c}|{cost['period'] if cost else '—'}|{n(f'/profiles/{i}/cash_short_coverage',1,100)}%|{n(f'/profiles/{i}/disclosed_pb')}|{n(f'/profiles/{i}/valuation/required_terminal_roe',1,100)}%|")
    lines += ['同列不等于同口径：巨星成本披露为上界，牧原为“略低于”；成本月份不同。现金为H1货币资金扣除本研究已核实受限及用途资金；短期义务为短借＋一年内到期非流动负债，包含部分租赁。PB用披露归母权益÷期末股本计算，可能不同于供应商PB。',
      '隐含ROE的统一条件为未来三年−10%/0%/10%、要求回报10%、过渡盈利分红30%，终态零增长并分配全部盈利。这是现价需要的条件，不是未来盈利预测或目标价。',
      '## 行业周期：去化成立，盈利反转尚需证据',
      f"2026Q3能繁母猪为{n('/capacity/3/sows',0)}万头，同比{n('/capacity/3/sow_yoy',1,100)}%；但1—9月出栏与肉量仍分别同比{n('/capacity/3/output_yoy',1,100)}%和{n('/capacity/3/meat_yoy',1,100)}%。基础产能减少与当期肉量增加可以同时发生。"+source('S_NBS_Q3'),
      '|期间|能繁母猪 万头|母猪同比|出栏累计同比|肉量累计同比|公布日期|','|---|---:|---:|---:|---:|---|']
    for i,r in enumerate(data['capacity']):lines.append(f"|{r['period']}|{n(f'/capacity/{i}/sows',0)}|{n(f'/capacity/{i}/sow_yoy',1,100)}%|{n(f'/capacity/{i}/output_yoy',1,100)}%|{n(f'/capacity/{i}/meat_yoy',1,100)}%|{r['published']}|")
    lines += ['传导链为母猪→仔猪→育肥→商品猪肉量→售价与成本差→现金流。母猪数不代表生产效率不变，也不能确定单一反转月份。政策正常保有量从3900万头调整到3750万头，不能将旧目标与新目标混用。'+source('S_POLICY'),
       f"以母猪同比变化作为起点，效率提高5%、出栏重量提高2%时，乘法供给情景为{n('/supply_scenarios/3/supply_change',1,100)}%。这不等于对未来肉量的点预测，更不能直接当猪价涨幅。",
       '历史提供反例：2023年母猪下降而全年肉量仍增加；2024年肉量才转降。存栏是时点、肉量是流量，口径与滞后必须分开。'+source('S_NBS_2023')+'；'+source('S_NBS_2024'),
       f"2026-10-15同口径集贸价格：生猪{n('/feed_prices/1/hog')}、仔猪{n('/feed_prices/1/piglet')}、玉米{n('/feed_prices/1/corn')}、豆粕{n('/feed_prices/1/soymeal')}、育肥料{n('/feed_prices/1/feed')}元/kg。猪粮比{n('/feed_prices/1/hog_corn_ratio')}是价格比，不是每家公司的盈亏线。"+source('S_FEED_OCT'),
      '另从农业农村部原文重采2022年1月至2026年10月的'+n('/price_history_summary/observations',0)+'个月价格样本，每月取第3周，最后一个月取最新第2周。样本最高为'+data['price_history_summary']['peak']['period']+'的'+n('/price_history_summary/peak/hog')+'元/kg，样本最低为'+data['price_history_summary']['low']['period']+'的'+n('/price_history_summary/low/hog')+'元/kg；这些只是抽样点的极值，不能称为完整周期最高或最低点。'+source(data['price_history_summary']['peak']['source'])+'；'+source(data['price_history_summary']['low']['source']),
      '历史图同时展示仔猪价、猪粮比和猪料比；不是月均价序列，也不是养殖利润。每条记录保留采集日、公布日与来源，缺值不插补。当前全国生猪价较4月抽样低点回升，但这不足以单独推出成本、现金流和权益均已修复。',
      '需求、进口、冻品库存和二次育肥还未形成完整连续对照，因此当前研究给出“去化在传导”的判断，不宣称盈利拐点已确认。',
       '## 公司经营：把单位成本、利润质量和资金桥分开',
       '|公司|Q1归母净利 亿元|Q2归母净利 亿元|H1资产减值损益 亿元|H1剔除该项利润总额 亿元|','|---|---:|---:|---:|---:|']
    for i,p in enumerate(data['profiles']):
        lines.append('|'+p['name']+'|'+ '|'.join(n(f'/profiles/{i}/earnings_bridge/{k}',2,1e-8) for k in ('q1_net_profit','q2_net_profit','half_asset_impairment','profit_excluding_asset_impairment'))+'|')
    lines += ['Q2用半年累计减一季度累计；原始财报金额逐项定位，见model/financial_checks.json。资产减值损益保留负号；从利润总额剔除该项后六家公司仍亏损。该加回数仍含折旧、融资费用、处置及信用减值，不是正常化净利或现金流。存货准备“转销”随已售资产结转，不等于同额“转回”收入。',
      '### 逐公司判断与需要证伪的条件']
    narratives={
      '002714.SZ':('一体化养殖及配套屠宰是核心，纯度不应被屠宰收入占比机械否定。9月成本略低于11.5元/kg，成本定义包含管理和财务费用；月报均价包含商品肉猪和退役种猪，不能直接把价格减成本乘总量当合并归母利润。屠宰、海外及品质溢价是需要后续兑现的来源，不直接写入永久增长。','若单头效率改善不能转成经营现金流，或持续追加资本与借款，成本优势不足以独立支持长期持有。','S_IR_002714'),
      '603477.SH':('7月完全成本在6.2元/斤以内，换算为12.4元/kg以内；种群PSY达到31以上、料肉比2.44。标杆种场PSY突破35不代表整个群体。低效种猪处置影响成本，四季度低于6元/斤属于目标，不能列为已经实现。皮革等非核心业务继续披露。','需核对成本改善是否持续、融资与短期义务是否稳定，不能只取标杆场数据。','S_603477_AN202608281828634722'),
      '605296.SH':('7月完全成本12元/kg、PSY31、料肉比2.46。全年11.5元/kg是带原料价格条件的目标；公司披露的“考核成本”剔除饲料上涨，与完全成本不是同一口径。Q2明显减亏但需拆分资产减值与成本结转。','若减亏主要来自会计结转、资本开支与流出未改善，应降低对恢复速度的信心。','S_605296_AN202608251828420234'),
      '001201.SZ':('成本仍受产能爬坡、固定折旧分摊和种群改良周期影响。9月说明会的公司回答给的是7月13.8元/kg；问题中提到8月，不等于公司确认8月。代养成本13.26元/kg另列，不能替代全公司值。年底13元及次年12.5元以下是管理层目标。','低PB要与资产利用率、现金流和成本兑现一起判断；如果满产或种群改善推迟，等待消耗净资产。','S_001201_AN202609151829418815'),
      '600975.SH':('经营以生猪为核心，但尚无本研究已核实的可比完全成本。H1现金等价物中另有用途受限募集资金，需要在受限货币资金之外再扣除；不能把全部账面现金当自由资金。高负债与净资产消耗应优先于“低股价”叙事。','需看到新增融资落实、经营流出下降及资产质量改善；未核实成本保持空白。','S_600975_AN202608301828734271'),
      '002124.SZ':('列入核心业务研究，但不进入默认五公司对照篮子。H1资金承受力与低净资产基础需要单独对待；三季报已披露，因此估值权益用Q3、资金横向压力仍用H1。历史正利润可能包含重大非经常项目，不能直接作为长期养殖利润。','重整、处置和融资安排会改变每股权益，无法用不增发的终态模型给确定价格。','S_002124_AN202610141830462603')}
    for p in data['profiles']:
        a,b,sid=narratives[p['code']];lines += [f"**{p['name']}**：{a}\n\n检验条件：{b}\n\n依据："+source(sid)]
    lines += ['## 现金承受力：把“能否等到恢复”做成压力情景',
      '|公司|货币资金|扣受限|另扣用途资金|可用现金代理|短期义务代理|12个月新增资金需求*|','|---|---:|---:|---:|---:|---:|---:|']
    for i,p in enumerate(data['profiles']):
        values=[n(f'/profiles/{i}/{k}',2,1e-8) for k in ('cash_gross','cash_restricted','cash_purpose_bound','cash_available_proxy','short_obligations_proxy')]
        lines.append('|'+p['name']+'|'+'|'.join(values)+'|'+n(f'/profiles/{i}/stress/4/new_funding_required',2,1e-8)+'|')
    lines += ['单位亿元。*统一假设短期义务50%续作、净流出维持半年流速12个月；本期净流入仅按零消耗。资金需求可由经营改善、支出削减、资产处置、续贷或增发填补，绝不是预测公司将违约。额外利息、全部租赁和未来分红尚未完整纳入。',
      '新五丰的资金扣减区分“不属于现金等价物的受限资金”与“现金等价物中另有用途限制”，避免漏扣或重复扣减。该项见半年报文件第180页。'+source('S_600975_AN202608301828734271'),
      '## 估值：反算现价需要什么恢复条件',
      '每年净利=期初每股权益×ROE；分红=正净利×分红比例；期末权益=期初权益＋净利−分红。过渡期后采用零增长、全部盈利分配，终态价值=期末权益×终态ROE÷要求回报。所有现金流折回观察时点。另用剩余收益恒等关系独立核对，避免把留存利润与分红重复计价。',
      '|公司|最新权益报告期|当前每股权益|现价|三年后每股权益*|条件价值*|现价所需终态ROE*|','|---|---|---:|---:|---:|---:|---:|']
    for i,p in enumerate(data['profiles']):lines.append(f"|{p['name']}|{p['latest_period']}|{n(f'/profiles/{i}/latest_bps')}|{n(f'/profiles/{i}/price')}|{n(f'/profiles/{i}/valuation/closing_book')}|{n(f'/profiles/{i}/valuation/conditional_value')}|{n(f'/profiles/{i}/valuation/required_terminal_roe',1,100)}%|")
    lines += ['*采用首页相同过渡路径及10%要求回报；条件价值另输入15%终态ROE。结果大幅低于现价，只能说明这组保守或低增长条件不能解释现价，不能直接推出应买卖或目标价。应进一步验证更高长期ROE、成长、资本效率或更低要求回报是否有足够证据。',
      '历史ROE代理采用归母净利÷期初末平均归母权益，含非经常项；增发会改变平均权益口径。周期高点不是永久能力。净资产为报告日披露值：本表将披露日至10月观察日的权益变化设为0，只是明确的占位假设，不能当实时净资产。工作台另设“披露后权益变化%”做桥接敏感性；未披露损益、分红及股本变化均可能改变起点。牧原A/H公司不把供应商总市值当分别按两地价格计量的精确总值。',
      '历史年度来自本轮新采集的供应商财务响应，已核对来源映射；2025年净利与归母权益另核对原始年报，未逐页核实所有更早年度。ROE仅对相邻年度正权益计算，不能替代公司披露的加权平均ROE。',
      '工作台允许调整等待路径、要求回报、终态ROE及分红，并导出输入和计算结果。数据不足以独立校准完整FCFF、维持资本开支和资本成本，因此本版交付可复算的条件模型，而非伪精确DCF。',
      '### 把现价所需利润连接到经营条件',
      '统一输入15倍正常化PE、12元/kg完全成本、销量变化0、其他业务贡献0；这些是诊断假设。按2026年1—9月各月商品猪收入÷该月公斤售价推算重量，再按12/9年化。仅牧原、巨星、神农有配对口径；东瑞总生猪收入不能与商品猪售价强配，其余缺口不填造。',
      '|公司|年化重量代理/亿kg|现价所需年归母利润/亿元|需养殖单位价差/元kg|输入成本下所需售价/元kg|','|---|---:|---:|---:|---:|']
    for i,p in enumerate(data['profit_bridges']):
        lines.append('|'+p['name']+'|'+n(f'/profit_bridges/{i}/annual_kg_proxy',2,1e-8)+'|'+n(f'/profit_bridges/{i}/required_company_profit',2,1e-8)+'|'+n(f'/profit_bridges/{i}/required_spread')+'|'+n(f'/profit_bridges/{i}/required_selling_price')+'|')
    lines += ['上述价差尚未完成内部交易抵消、非商品猪业务、税项、少数股东、减值和期间费用的完整桥接，不能直接称作归母盈利预测。完全成本是否已含管理和财务费用须逐公司核对；不能再重复扣同一费用。以A股每股价格反推全公司利润，不按A股价格加总A/H实际市值。重量年化不是销量预测，用户可调整销量、成本、PE并导出。',
      '## 按成本、现金与估值分档形成当前条件权重',
      '用户选择先分档再决定权重。本页使用观察日的全部已核实资料，和6月起的历史回放分开。成本≤12元/kg为低档、≤13元为中档，月份超过120天不再授予可用成本档；上界披露按保守上界判断。月份和定义不同，分档不代表精确成本排行榜。',
      '现金同时看可用现金/短期义务、资产负债率与经营现金减购建支出的消耗。现金覆盖≥50%、负债率≤65%且流出压力可覆盖12个月才列相对较强；现金覆盖≥20%且可覆盖6个月列依赖续作；其余缓冲偏薄。现金覆盖<10%，或负债率≥85%且经营净流出，先按资金约束处理。扩张支出可削减，因此资金月数不是必然结果。',
      'A=低成本且现金相对较强；B=低/中成本且有缓冲；C=成本改善待兑现或缓冲偏薄；D=资金约束、成本缺失或待更新。候选单位3/2/1/0，在组合80%额度中按比例分配，再限制单名30%/20%/10%/0；上限以外不再摊给别家公司。',
      '条件估值统一改用25%终态ROE、10%要求回报、三年−10%/0%/10%和30%过渡分红。条件价/现价达到1.25、1、0.75分别释放候选额度100%、50%、25%，否则0。25%只是可接受能力情景，未证明各公司可以永久实现；这些比例不是成功概率。',
      '|公司|成本证据|现金承受力|档位|候选额度|条件价/现价|当前条件权重|','|---|---|---|---|---:|---:|---:|']
    for i,r in enumerate(data['allocation']['rows']):
        lines.append(f"|{r['name']}|{r['cost_band']}|{r['cash_band']}|{r['tier']}|{n(f'/allocation/rows/{i}/candidate_weight',1,100)}%|{n(f'/allocation/rows/{i}/value_coverage')}|{n(f'/allocation/rows/{i}/target_weight',1,100)}%|")
    lines += ['这组假设下现金为'+n('/allocation/target_cash',1,100)+'%。它是条件筛选的结果，不是建议真实账户持有该比例或只买某一家公司，也不否定跨周期研究价值。应先检验经营与估值假设，再决定是否采用。工作台可改组合额度、要求回报和终态ROE；12组估值敏感性完整保留，未挑最优。',
      '资金适配默认承接这套当前条件权重，并保存分档依据；本金仅改变整手、费用和容量，不改变公司权重。历史规则目标及80%等权对照仍可单独切换。',
      '## 跨周期持仓与资金适配',
      '策略层与资金金额分离：按公司目标比例和现金预算决策，执行层再处理整手、最低佣金、滑点及成交参与率。小资金买不起的部分留现金，不自动加杠杆或改为押注单股。大资金考虑分日执行，未假定无限成交容量。',
      '草案每20交易日检查前一交易日前公开的信息：产能收缩且PB处于规定分位时建立观察仓或向40%/60%/80%阶段目标再平衡；资金依赖偏高时冻结新增并保留实际股数；报告期盈利且PB高分位时分批兑现；高杠杆、低现金覆盖与经营净流出同时出现时降低目标至零。短期股价下跌不是独立退出信号。',
      '阈值属于研究纪律，未从收益中选优；历史现金使用未扣受限的上界代理，当前H1受限现金不向早期回填。策略在2026-10-25事后提出，属于当前公司池历史情景回放，不是当时真实可执行的前向业绩证明。',
      '|方案|起点数（共同终点）|收益中位数|最差起点收益|最深回撤|','|---|---:|---:|---:|---:|']
    rolling=read(ROOT/'model/rolling_summary.json')
    labels={'cycle_hold':'跨周期证据分批草案','staged80':'80%三批','hold80':'80%一次','hold100':'100%参照','risk80':'趋势/波动对照'}
    for i,r in enumerate(rolling):
        if r['horizon']!=0:continue
        lines.append(f"|{labels[r['strategy']]}|{r['count']}|{r['median_return']:.2%}|{r['worst_return']:.2%}|{r['worst_drawdown']:.2%}|")
        for field in ('count','median_return','worst_return','worst_drawdown'):
            scale=1 if field=='count' else 100;dec=0 if field=='count' else 2
            bindings.append({'label':r['strategy']+' '+field,'report_location':'research.md: 全起点比较','model_path':'model/rolling_summary.json','pointer':f'/{i}/{field}','scale':scale,'decimals':dec,'value':str((Decimal(str(r[field]))*scale).quantize(Decimal(1).scaleb(-dec),rounding=ROUND_HALF_UP))})
    lines += ['从2026-06-01起，五方案共同终点及20/60交易日共1,080个情景。较晚起点持有期较短，必须结合等持有期比较；正收益起点重叠，不能称独立胜率。五个月左右的观察窗口更不能证明穿越完整周期。低回撤也可能来自更低平均仓位。',
      '另做7组预设门槛与复核频率、每组98个共同终点起点的敏感性；并在7种本金、两组滑点下检查同一目标序列。完整结果在model/policy_sensitivity.json，不用其中最佳结果替换基准参数。',
      '## 后续更新清单与使用边界',
      '优先更新各公司三季报、受限及用途资金、同口径月度完全成本和出栏结构；继续核对经营现金流、资本开支及每股权益。对新五丰的成本缺口保持显式空白；天邦融资与重整变化先更新每股权益再谈长期价值。',
      '首页按用户选择先展示关键图表及六家公司对比，详细行业传导、利润质量、资金压力及估值假设在分层页面中查看。所有数据源、事实、假设、判断和缺口分别保存在evidence目录。',
      '原始研究主体已依授权删除。残留旧编译与工具缓存按用户最新指示暂不处理，其他三模块共用资料仍保留。所有新研究、导出及验证结果均位于quant_workbench/runtime。',
      '模型复现：在本研究目录运行 `python model/run.py`。基础行情/策略从工作台目录运行 `scripts/run_swine_research.py`，压力比较运行 `scripts/stress_swine_policy.py`。核验说明只证明指定来源、计算和程序检查，不证明投资有效性。']
    text=lines[0]
    for previous,current in zip(lines,lines[1:]):text+=('\n' if previous.startswith('|') and current.startswith('|') else '\n\n')+current
    (ROOT/'report/research.md').write_text(text+'\n',encoding='utf8')
    dump(ROOT/'report/number_bindings.json',bindings)

if __name__=='__main__':main()
