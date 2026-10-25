"""Source-admitted economic evidence and reproducible conditional research inputs."""
import hashlib,json,re,sys,shutil
from datetime import datetime,timezone
from pathlib import Path
from html import unescape
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'src'))
from quant_workbench_app.swine_data import ROOT as BASE, UNIVERSE, latest_statement, read, dump
from quant_workbench_app.swine_valuation import recovery_value,funding_stress,supply_change,profit_requirement
from quant_workbench_app.swine_allocation import tier_allocation,allocation_sensitivity
ROOT=PROJECT/'runtime/research/swine_deep_20261025'

RESTRICTED={
 '002714.SZ':(2917447226.25,0,153,'AN202608201828210235'),
 '603477.SH':(256497695.92,0,163,'AN202608271828548388'),
 '605296.SH':(40934343.26,0,177,'AN202608241828361418'),
 '001201.SZ':(26647633.22,0,135,'AN202608281828625940'),
 '600975.SH':(75444798.53,227457049.21,180,'AN202608301828734271'),
 '002124.SZ':(60445090.22,0,128,'AN202608241828368721')}
COSTS={
 '002714.SZ':(11.5,'2026-09','略低于该值，严格上界而非精确成本；已含管理及财务费用','S_IR_002714','2026-10-13及10-19公司答复'),
 '603477.SH':(12.4,'2026-07','上限以内，6.2元/斤乘2；含资产处置影响','S_603477_AN202608281828634722',None),
 '605296.SH':(12.,'2026-07','月度完全成本','S_605296_AN202608251828420234',None),
 '001201.SZ':(13.8,'2026-07','商品猪完全养殖成本；代养业务另为13.26','S_001201_AN202609151829418815',2),
 '002124.SZ':(12.65,'2026H1','育肥完全成本，含空栏0.31','S_002124_AN202608241828368721',13)}

def main():
    sources=read(ROOT/'evidence/sources.json'); source_map={s['id']:s for s in sources}
    facts=[]; profiles=[]; raw_inputs={}; failures=[];financial_checks=[]
    def fact(fid,label,value,unit,period,source,locator,raw_value=None,raw_unit=None):
        facts.append({'id':fid,'kind':'fact','label':label,'value':value,'unit':unit,'period':period,'scope':'原披露范围',
                      'source_ids':[source],'locator':locator,'raw_value':value if raw_value is None else raw_value,
                      'raw_unit':raw_unit or unit,'normalization_rule':'raw_value' if raw_value is None else '斤价×2换算公斤价'})
    def financial_fact(code,field,value,period,source,unit='CNY'):
        if value is None:return None
        pages=read((ROOT/source_map[source]['local_path']).with_suffix('.json'))
        forms=[f'{abs(value):.2f}']
        if float(value).is_integer():forms.append(str(int(abs(value))))
        hits=[]
        for p in pages:
            clean=re.sub(r'[,，\s]','',p['text'])
            for needle in forms:
                at=clean.find(needle)
                if at>=0:
                    hits.append({'page':p['page'],'context':clean[max(0,at-65):at+len(needle)+65]});break
        fid=f'F_{code[:6]}_{period}_{field}'
        financial_checks.append({'id':fid,'field':field,'value':value,'source':source,'evidence':hits,'status':'located' if hits else 'missing'})
        if not hits:failures.append(fid+' amount not located in original');return None
        fact(fid,field,value,unit,period,source,'PDF文件页'+','.join(str(h['page']) for h in hits))
        return fid
    capacity=[{'period':'2025Q4','sows':3961,'sow_yoy':-.029,'output_yoy':.024,'meat_yoy':.041,'source':'S_NBS_2025','published':'2026-01-19','target':3900},
              {'period':'2026Q1','sows':3904,'sow_yoy':-.033,'output_yoy':.028,'meat_yoy':.042,'source':'S_NBS_Q1','published':'2026-04-20','target':3900},
              {'period':'2026Q2','sows':3780,'sow_yoy':-.065,'output_yoy':.017,'meat_yoy':.033,'source':'S_NBS_Q2','published':'2026-07-16','target':3750},
              {'period':'2026Q3','sows':3602,'sow_yoy':-.107,'output_yoy':.014,'meat_yoy':.032,'source':'S_NBS_Q3','published':'2026-10-20','target':3750}]
    for row in capacity:
        fact('F_SOW_'+row['period'],'能繁母猪存栏',row['sows'],'万头',row['period'],row['source'],'生猪生产段落')
        for field,label in [('sow_yoy','能繁母猪同比'),('output_yoy','累计生猪出栏同比'),('meat_yoy','累计猪肉产量同比')]:
            fact('F_'+field+'_'+row['period'],label,row[field],'ratio',row['period'],row['source'],'生猪生产段落')
    annual_capacity=[{'year':2021,'sows':4329,'pork_output':5296,'slaughter':67128,'source':'S_NBS_2021'},
                     {'year':2022,'sows':4390,'pork_output':5541,'slaughter':69995,'source':'S_NBS_2022'},
                     {'year':2023,'sows':4142,'pork_output':5794,'slaughter':72662,'source':'S_NBS_2023'},
                     {'year':2024,'sows':4078,'pork_output':5706,'slaughter':70256,'source':'S_NBS_2024'}]
    for row in annual_capacity:
        html=(ROOT/source_map[row['source']]['local_path']).read_text(encoding='utf8')
        clean=re.sub(r'[,，\s]','',unescape(re.sub('<[^>]+>',' ',html)))
        for field,label,unit in [('sows','年末能繁母猪存栏','万头'),('pork_output','全年猪肉产量','万吨'),('slaughter','全年生猪出栏','万头')]:
            if str(row[field]) not in clean:failures.append(f"{row['year']} {field} not in original")
            fact(f"F_{field}_{row['year']}",label,row[field],unit,str(row['year']),row['source'],'生猪生产段落')
    cost_observations=[]
    for code,row in COSTS.items():
        value,period,definition,sid,page=row
        locator=f'PDF文件页{page}' if isinstance(page,int) else page or '原始DOCX生产指标回答'
        fact('F_COST_'+code[:6],'已披露养殖完全成本值（含界限，见定义）',value,'元/kg',period,sid,locator,6.2 if code=='603477.SH' else None,'元/斤' if code=='603477.SH' else None)
        qualifier='strict_upper' if code=='002714.SZ' else 'upper' if code=='603477.SH' else 'reported'
        facts[-1]['value_qualifier']=qualifier;facts[-1]['definition']=definition
        if sid=='S_IR_002714':
            answers=read(ROOT/source_map[sid]['local_path'])['data']
            if not any('2026年9月' in r['answer'] and '略低于11.5' in r['answer'] and r['answerdate'].startswith('2026-10') for r in answers):
                failures.append('牧原9月成本答复未匹配')
        cost_observations.append({'code':code,'value':value,'period':period,'definition':definition,'qualifier':qualifier,'source_id':sid,'source_path':source_map[sid]['local_path'],'locator':locator})
    current={r['code']:r for r in read(BASE/'results/companies.json')}
    for code in UNIVERSE['core']:
        raw=read(BASE/'data'/f'{code}.json')
        bal=latest_statement(raw['balancesheet'],'20260630');cf=latest_statement(raw['cashflow'],'20260630');inc=latest_statement(raw['income'],'20260630')
        r=current[code];restricted,purpose,page,art=RESTRICTED[code]
        source=f'S_{code[:6]}_{art}'
        fact('F_RESTRICT_'+code[:6],'不属现金等价物的受限资金',restricted,'CNY','2026H1',source,f'PDF文件页{page}')
        if purpose:
            fact('F_PURPOSE_'+code[:6],'现金等价物内另有用途限制资金',purpose,'CNY','2026H1',source,f'PDF文件页{page}')
        if bal.get('st_borr') is None or bal.get('non_cur_liab_due_1y') is None:
            raise ValueError(code+' lacks short obligations; cannot substitute zero')
        short=bal['st_borr']+bal['non_cur_liab_due_1y']
        available=bal['money_cap']-restricted-purpose
        balance_latest=latest_statement(raw['balancesheet'],r['period'])
        bps=balance_latest['total_hldr_eqy_exc_min_int']/balance_latest['total_share']
        for api,fields in [(bal,['money_cap','st_borr','non_cur_liab_due_1y','total_liab','total_assets','total_hldr_eqy_exc_min_int','total_share']),
                           (cf,['n_cashflow_act','c_pay_acq_const_fiolta']),
                           (inc,['n_income_attr_p','total_profit','assets_impair_loss'])]:
            for field in fields:financial_fact(code,field,api.get(field),'20260630',source,'shares' if field=='total_share' else 'CNY')
        q1=latest_statement(raw['income'],'20260331')
        q1source=next(s['id'] for s in sources if s['id'].startswith('S_'+code[:6]) and ('2026年第一季度报告' in s['title'] or '2026年一季度报告' in s['title']))
        financial_fact(code,'n_income_attr_p',q1['n_income_attr_p'],'20260331',q1source)
        latest_source=source if r['period']=='20260630' else next(s['id'] for s in sources if s['id'].startswith('S_'+code[:6]) and '2026年三季度报告' in s['title'])
        if latest_source!=source:
            for field in ('total_hldr_eqy_exc_min_int','total_share'):financial_fact(code,field,balance_latest[field],r['period'],latest_source,'shares' if field=='total_share' else 'CNY')
        annual=latest_statement(raw['income'],'20251231');annual_balance=latest_statement(raw['balancesheet'],'20251231')
        annual_source=next(s['id'] for s in sources if s['id'].startswith('S_'+code[:6]) and '2025年年度报告' in s['title'])
        financial_fact(code,'n_income_attr_p',annual['n_income_attr_p'],'20251231',annual_source)
        financial_fact(code,'total_hldr_eqy_exc_min_int',annual_balance['total_hldr_eqy_exc_min_int'],'20251231',annual_source)
        profile={'code':code,'name':r['name'],'period':'20260630','ann_date':bal.get('f_ann_date') or bal['ann_date'],
                 'cash_gross':bal['money_cap'],'cash_restricted':restricted,'cash_purpose_bound':purpose,'cash_available_proxy':available,
                 'short_obligations_proxy':short,'cash_short_coverage':available/short if short else None,
                 'operating_cashflow':cf['n_cashflow_act'],'capex_cash':cf['c_pay_acq_const_fiolta'],
                 'net_profit':inc['n_income_attr_p'],'parent_equity':bal['total_hldr_eqy_exc_min_int'],
                 'debt_ratio':bal['total_liab']/bal['total_assets'],'source_id':source,'restriction_page':page,
                 'latest_period':r['period'],'latest_bps':bps,'latest_parent_equity':r['parent_equity'],'price':r['close'],
                 'latest_share_count':balance_latest['total_share'],'annual_history':r['annual_history']}
        profile['disclosed_pb']=r['close']/bps
        profile['earnings_bridge']={'q1_net_profit':q1['n_income_attr_p'],'q2_net_profit':inc['n_income_attr_p']-q1['n_income_attr_p'],
            'half_net_profit':inc['n_income_attr_p'],'half_total_profit':inc['total_profit'],'half_asset_impairment':inc.get('assets_impair_loss'),
            'profit_excluding_asset_impairment':inc['total_profit']-inc['assets_impair_loss'] if inc.get('assets_impair_loss') is not None else None,
            'definition':'Q2=半年累计−一季度累计。资产减值损益为带符号的利润表项目；剔除该项仍含折旧、处置、信用减值等，不等于现金盈利或正常化盈利。转销存货准备随已售资产结转，不直接等于当期减值转回收益。'}
        annual_history=profile['annual_history']
        profile['historical_roe_proxy']=[]
        for old,new in zip(annual_history,annual_history[1:]):
            if int(new['year'])-int(old['year'])==1 and old.get('parent_equity') and new.get('parent_equity') and new.get('net_profit') is not None and old['parent_equity']>0 and new['parent_equity']>0:
                profile['historical_roe_proxy'].append({'year':new['year'],'roe':new['net_profit']/((old['parent_equity']+new['parent_equity'])/2)})
        profile['stress']=[funding_stress(available,short,cf['n_cashflow_act'],cf['c_pay_acq_const_fiolta'],refinancing=refi,burn_factor=burn)
                           for burn in (.5,1,1.5) for refi in (0,.5,1)]
        profile['valuation']=recovery_value(bps,r['close'])
        profile['required_roe_grid']=[{'required_return':ke,'years':n,**recovery_value(bps,r['close'],ke,tuple([-.1]+[0]*(n-1)),.15)} for ke in (.08,.10,.12) for n in (1,2,3)]
        # Reconcile supplied monetary facts to original text, including exact cash restrictions.
        pages=read((ROOT/source_map[source]['local_path']).with_suffix('.json'))
        text=re.sub(r'[,，\s]','', ''.join(p['text'] for p in pages))
        for amount in [restricted,purpose,bal['money_cap'],short-(bal.get('non_cur_liab_due_1y') or 0)]:
            if amount and f'{amount:.2f}' not in text:
                failures.append(f'{code} monetary amount {amount} not located in original')
        profiles.append(profile)
        raw_inputs[code]={'half_balance':bal,'half_cashflow':cf,'half_income':inc,'q1_income':q1,'latest_balance':balance_latest,'latest_record':r}
    monthly=read(BASE/'results/monthly_operations.json')
    for row in monthly:
        sid='S_'+Path(row['source_path']).stem
        for field,unit in [('volume_10k','万头'),('revenue_100m','亿元'),('price_per_kg','元/kg')]:
            fact('F_MONTH_'+row['code']+'_'+row['month'].replace('-','')+'_'+field,
                 '公司月报'+field,row[field],unit,row['month'],sid,f"PDF文件页{row['page']} 月度表 {row['month']}")
            facts[-1]['scope']=row['scope']
    price_sensitivity=[]
    for code in ('002714','603477','605296'):
        rows=[r for r in monthly if r['code']==code]
        kg=sum(r['revenue_100m']*1e8/r['price_per_kg'] for r in rows)
        price_sensitivity.append({'code':code,'months':len(rows),'kg_proxy':kg,'annualized_kg_proxy':kg*12/len(rows),
                                  'one_yuan_spread_impact_100m':kg*12/len(rows)/1e8,
                                  'definition':'月度商品猪销售收入÷同口径价格推导重量，受四舍五入影响；按12/9年化仅规模假设；含内部交易，不等于合并归母利润'})
    profit_bridges=[]
    for row in price_sensitivity:
        p=next(p for p in profiles if p['code'].startswith(row['code']))
        profit_bridges.append({'code':p['code'],'name':p['name'],
            **profit_requirement(p['price'],p['latest_share_count'],row['annualized_kg_proxy'])})
    feeds=[]
    for sid,period in [('S_FEED_SEP','2026-09-17'),('S_FEED_OCT','2026-10-15')]:
        html=(ROOT/source_map[sid]['local_path']).read_text(encoding='utf8')
        text=re.sub(r'\s+','',unescape(re.sub('<[^>]+>',' ',html)))
        fields={'piglet':'全国仔猪平均价格','hog':'全国生猪平均价格','corn':'全国玉米平均价格','soymeal':'全国豆粕平均价格','feed':'育肥猪配合饲料平均价格'}
        row={'period':period,'source':sid}
        for key,label in fields.items():
            match=re.search(label+r'([\d.]+)元',text)
            if not match:raise ValueError(f'{sid} missing {key}')
            row[key]=float(match[1]);fact(f'F_{sid}_{key}',label,row[key],'元/kg',period,sid,label+'段落')
        row['hog_corn_ratio']=row['hog']/row['corn'];feeds.append(row)
    price_history=read(ROOT/'model/price_history.json')
    for row in price_history['rows']:
        for field in ('hog','piglet','corn','soymeal','feed'):
            fact('F_HIST_'+row['period'].replace('-','')+'_'+field,'全国集贸市场'+field,row[field],'元/kg',row['period'],row['source'],'正文全国平均价格段落')
            facts[-1]['scope']=row['sample']+'；非月均价'
    history_summary={'observations':len(price_history['rows']),
        'peak':max(price_history['rows'],key=lambda r:r['hog']),
        'low':min(price_history['rows'],key=lambda r:r['hog']),
        'latest':price_history['rows'][-1]}
    outputs={'capacity':capacity,'annual_capacity':annual_capacity,'feed_prices':feeds,'costs':cost_observations,'profiles':profiles,'price_sensitivity':price_sensitivity,'profit_bridges':profit_bridges,
             'price_history_summary':history_summary,
             'supply_scenarios':[{'efficiency_change':eff,'weight_change':weight,'supply_change':supply_change(-.107,eff,weight)} for eff in (0,.05,.10) for weight in (0,.02)],
             'failures':failures,'status':'passed' if not failures else 'failed'}
    allocation_policy=read(PROJECT/'config/swine_allocation.json')
    outputs['allocation']=tier_allocation(profiles,cost_observations,allocation_policy)
    outputs['allocation_sensitivity']=allocation_sensitivity(profiles,cost_observations,allocation_policy)
    dump(ROOT/'model/allocation_policy.json',allocation_policy)
    dump(ROOT/'model/raw_financial_inputs.json',raw_inputs)
    dump(ROOT/'model/results.json',outputs)
    dump(ROOT/'evidence/facts.json',facts)
    dump(ROOT/'model/financial_checks.json',{'checks':len(financial_checks),'records':financial_checks,'failures':failures})
    project=read(ROOT/'project.json')
    project.update(audience='用户的原生量化研究工作台',purpose='跨周期持有：判断经营承受力及现价所需恢复条件',business_perimeter='A股核心生猪养殖6家公司，允许配套产业链；观察池只作边界核查',forecast_horizon='未来1至3年过渡期＋零增长终态，条件情景而非点预测',requested_formats=['md'],
                   materiality_policy='成本口径、受限资金、期限及永久ROE足以改变结论；未知不填零',
                   methods=['条件股利折现与剩余收益恒等复核；不在产能、维持资本开支及资本成本不足时强行给FCFF目标价', '资金承受力压力模型；经营现金流不年化冒充预测','生猪产能×效率×出栏重量的供给情景','现价隐含盈利与商品猪价差的条件反推，未完成合并盈利预测桥','当前成本/现金/估值分档与资本金额独立；和历史跨周期回放分开','官方2022—2026逐月固定周价格采样，非月均价'])
    dump(ROOT/'project.json',project)
    print(json.dumps({'profiles':len(profiles),'facts':len(facts),'failures':failures},ensure_ascii=False))
    if failures:raise SystemExit(1)

if __name__=='__main__':main()
