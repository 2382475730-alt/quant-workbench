"""Native swine research: cycle, operations, valuation, entry dates, execution."""
from datetime import datetime, timedelta
import os
import tkinter as tk
from tkinter import ttk

import pandas as pd

from .paths import PROJECT, RUNTIME
from .swine_data import ROOT, UNIVERSE, all_companies, dump, read, source_documents
from .swine_engine import STRATEGIES, SwineModel, capital_plan, export_run
from .widgets import chart, set_text, table, text_panel
from .swine_deep_panel import DeepResearchMixin, DEEP
from .swine_allocation import tier_allocation


def number(value, scale=1):
    return '未取得' if value is None else f'{value/scale:,.2f}'


def percent(value):
    return '未取得' if value is None else f'{value:.2%}'


class PorkPanel(DeepResearchMixin,ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.records = all_companies()
        self.by_code = {r['code']: r for r in self.records}
        self.model = SwineModel()
        self.result = None
        self.deep = read(DEEP/'model/results.json')
        self.allocation_policy=read(PROJECT/'config/swine_allocation.json')
        self.allocation_result=tier_allocation(self.deep['profiles'],self.deep['costs'],self.allocation_policy)
        self.pages = ttk.Notebook(self)
        self.pages.pack(fill='both', expand=True)
        self.frames = {}
        for key, name in [('cycle','行业周期'), ('companies','公司经营'), ('valuation','估值观察'),
                          ('replay','建仓实验'), ('capital','资金适配'), ('evidence','证据与讨论')]:
            page = ttk.Frame(self.pages, padding=10)
            self.pages.add(page, text=name)
            self.frames[key] = page
        for build in (self.build_cycle,self.build_companies,self.build_valuation,self.build_replay,self.build_capital,self.build_evidence):
            build()
        self.build_deep_research()
        self.build_overview()

    def label(self, parent, text, heading=False):
        item = ttk.Label(parent, text=text, style='Heading.TLabel' if heading else 'Sub.TLabel', wraplength=1000)
        item.pack(anchor='w', fill='x', pady=(3,5))
        item.bind('<Configure>',lambda event: item.configure(wraplength=max(200,event.width-4)))
        return item

    def build_cycle(self):
        page = self.split_research_page('cycle','周期概览','供给传导与饲料')
        data = read(ROOT / 'results/cycle.json')
        self.label(page, data['headline'], True)
        self.label(page, '观察日期 2026-10-25 · 原始公告 / 官方统计 · 月报售价覆盖4家公司，其余未补造序列')
        metrics = table(page, [('观察指标',260), ('数值',140), ('期间',230), ('同比',100)], height=5)
        for item in data['facts']:
            metrics.insert('', 'end', values=(item['indicator'], f"{item['value']:,.2f} {item['unit']}", item['period'],
                                             f"{item['yoy']:+.1f}%" if 'yoy' in item else '政策目标'))
        bottom = ttk.Frame(page)
        bottom.pack(side='bottom', fill='x')
        self.label(bottom, data['interpretation'])
        self.label(bottom, '下一步验证：猪价是否覆盖同口径成本 → 经营现金流是否改善 → 净资产是否停止消耗。\n公司月报价格有区域、品种与渠道差异，不用于直接排名成本竞争力。')
        self.cycle_figure, self.cycle_canvas = chart(page, 230)
        ax = self.cycle_figure.add_subplot()
        monthly = pd.DataFrame(read(ROOT / 'results/monthly_operations.json'))
        for code, group in monthly.groupby('code'):
            group = group.sort_values('month')
            name = next(r['name'] for r in self.records if r['code'].startswith(code))
            ax.plot(pd.to_datetime(group.month), group.price_per_kg, marker='o', markersize=3, label=name)
        ax.set_ylabel('月报商品猪售价 / 元每公斤')
        ax.grid(alpha=.2)
        ax.legend(ncol=4, fontsize=9)
        self.cycle_figure.tight_layout()
        self.cycle_canvas.draw_idle()

    def build_companies(self):
        page = self.split_research_page('companies','经营与成本','现金承受力')
        self.label(page, '先判断经营本质，再比较财务承受力', True)
        self.label(page, '核心6家、观察3家，其余候选明确排除。纳入研究不等于纳入持仓。财务单位亿元，期间按已披露报告。')
        filter_bar=ttk.Frame(page)
        filter_bar.pack(fill='x')
        ttk.Label(filter_bar,text='显示范围').pack(side='left')
        self.company_scope=tk.StringVar(value='核心生猪公司')
        scope=ttk.Combobox(filter_bar,textvariable=self.company_scope,values=['核心生猪公司','观察公司','全部候选及边界'],state='readonly',width=22)
        scope.pack(side='left',padx=8)
        scope.bind('<<ComboboxSelected>>',self.filter_companies)
        self.company_table = table(page, [('公司 / 分类',190), ('报告期',100), ('营收',100), ('归母净利',100),
                                          ('经营现金流',120), ('资产负债率',110)], height=6)
        controls = ttk.Frame(page)
        controls.pack(fill='x')
        ttk.Button(controls,text='打开所选公司当前财报',command=self.open_company_document).pack(side='left')
        ttk.Button(controls,text='已核实成本原文',command=self.open_cost_document).pack(side='left',padx=5)
        self.company_note = ttk.Label(controls,style='Sub.TLabel')
        self.company_note.pack(side='left',padx=10)
        self.company_detail = text_panel(page)
        self.company_table.bind('<<TreeviewSelect>>', self.show_company)
        self.filter_companies()

    def filter_companies(self,_=None):
        labels={'core':'核心','watch':'观察','excluded':'排除'}
        group={'核心生猪公司':'core','观察公司':'watch'}.get(self.company_scope.get())
        rows=[r for r in self.records if group is None or r['group']==group]
        self.company_table.delete(*self.company_table.get_children())
        for r in rows:
            self.company_table.insert('','end',iid=r['code'],values=(r['name']+' / '+labels[r['group']],r['period'],
                number(r['revenue'],1e8),number(r['net_profit'],1e8),number(r['operating_cashflow'],1e8),percent(r['debt_ratio'])))
        if rows:
            self.company_table.selection_set(rows[0]['code'])
            self.show_company()

    def show_company(self, _=None):
        selected = self.company_table.selection()
        if not selected:
            return
        r = self.by_code[selected[0]]
        business = '\n'.join(f"  {b['bz_item']}：{number(b.get('bz_sales'),1e8)} 亿元" for b in r['business']
                             if b['bz_item'] not in ('产品', '合计特别调整'))
        cashflow,capex = r['operating_cashflow'],r['capex_cash']
        cash_after = cashflow-capex if cashflow is not None and capex is not None else None
        notes = []
        if r['net_profit'] is not None and r['net_profit'] < 0:
            notes.append('本期亏损：不能直接用本期PE评估便宜程度，应检验可持续盈利恢复条件。')
        if r['debt_ratio'] is not None and r['debt_ratio'] >= .7:
            notes.append('资产负债率达到70%以上：进一步核对短债、授信、受限资金和再融资；此阈值只是提示。')
        if cash_after is not None and cash_after < 0:
            notes.append('经营现金流不足以覆盖本期购建长期资产支出，需关注资金来源与资本开支节奏。')
        cost = next((x for x in self.deep['costs'] if x['code']==r['code']),None)
        cost_text = f"{cost['period']}：{cost['value']} 元/kg，{cost['definition']}；原文位置 {cost['locator']}。这是本研究已核实月份，不冒充当前月成本。" if cost else '未核实到可比单位完全成本，不能用毛利率代替。'
        content = (f"{r['name']}  {r['code']}\n\n研究边界：{r['reason']}\n\n"
                f"财务报告期：{r['period']}；公告日期：{r['ann_date']}。不同期间不能直接比较累计增长。\n"
                f"货币资金：{number(r['cash'],1e8)}亿元；债务代理：{number(r['debt_proxy'],1e8)}亿元。\n"
                '债务代理=短借+长借+债券+一年内到期非流动负债，可能含非借款项且未覆盖全部租赁；货币资金未扣受限，不能直接当净债务。\n'
                f"经营现金流减购建长期资产现金：{number(cash_after,1e8)}亿元（非严格自由现金流）。\n\n经营风险提示\n"
                +'\n'.join(notes or ['当前几项筛查未触发阈值，不等于无风险。'])+'\n\n'
                f"成本证据\n{cost_text}\n\n2026H1业务收入（原报表口径）\n{business}\n\n"
                '分部可能含内部销售抵消；不加总含“合计”的行，不按90%硬筛。\n'
                '继续研究：单位成本构成、生产效率、出栏结构、减值与现金回收。')
        set_text(self.company_detail,content)
        self.company_note.configure(text=f"{r['name']} · 来源可追溯")

    def open_cost_document(self):
        selected=self.company_table.selection()
        cost=next((r for r in self.deep['costs'] if selected and r['code']==selected[0]),None)
        if cost:
            path=DEEP/cost['source_path']
            if path.suffix=='.json':
                rows=read(path)['data']
                self.winfo_toplevel().document('成本公司答复原文','\n\n'.join(r['answerdate']+'\n'+r['question']+'\n'+r['answer'] for r in rows if '成本' in r['answer']))
            else:os.startfile(path)
        else:self.company_note.configure(text='尚无已核实的同口径完全成本原文。')

    def open_company_document(self,half_year=False):
        selected=self.company_table.selection()
        if not selected:
            return
        word='半年度报告' if half_year or self.by_code[selected[0]]['period'].endswith('0630') else '三季度报告'
        docs=[d for d in source_documents(selected[0]) if word in d['title']]
        if docs:
            os.startfile(PROJECT / docs[0]['path'])
        else:
            self.company_note.configure(text='此候选未下载原报表；财务表仅有数据源记录。')

    def build_valuation(self):
        page=self.split_research_page('valuation','历史估值','跨周期恢复模型')
        self.label(page,'估值需要盈利恢复与资产质量共同支持',True)
        controls=ttk.Frame(page)
        controls.pack(fill='x')
        self.valuation_names={self.by_code[c]['name']+' '+c:c for c in UNIVERSE['core']}
        self.valuation_company=tk.StringVar(value=next(iter(self.valuation_names)))
        choice=ttk.Combobox(controls,textvariable=self.valuation_company,values=list(self.valuation_names),state='readonly',width=23)
        choice.pack(side='left')
        choice.bind('<<ComboboxSelected>>',self.draw_valuation)
        ttk.Label(controls,text='情景PB').pack(side='left',padx=(15,4))
        self.scenario_pb=tk.StringVar(value='2.0')
        ttk.Entry(controls,textvariable=self.scenario_pb,width=7).pack(side='left')
        ttk.Label(controls,text='净资产折损%').pack(side='left',padx=(12,4))
        self.haircut=tk.StringVar(value='10')
        ttk.Entry(controls,textvariable=self.haircut,width=7).pack(side='left')
        ttk.Button(controls,text='更新情景',command=self.draw_valuation).pack(side='left',padx=10)
        self.valuation_summary=self.label(page,'')
        self.valuation_scenario=self.label(page,'')
        self.label(page,'PB情景只是参数敏感性，不是目标价。历史自2016年或上市后起；巨星从重组后2021年起。负PE不作低估依据。')
        bottom=ttk.Frame(page)
        bottom.pack(side='bottom',fill='x')
        self.valuation_detail=text_panel(bottom)
        self.valuation_detail.configure(height=5)
        self.valuation_figure,self.valuation_canvas=chart(page,240)
        self.draw_valuation()

    def draw_valuation(self,_=None):
        r=self.by_code[self.valuation_names.get(self.valuation_company.get(),self.valuation_company.get())]
        try:
            multiple=float(self.scenario_pb.get())
            haircut=float(self.haircut.get())/100
            if not 0<multiple<=20 or not 0<=haircut<1:
                raise ValueError
        except ValueError:
            self.valuation_scenario.configure(text='请输入0至20之间的正PB，以及0至100%（不含100）的净资产折损。')
            self.valuation_summary.configure(text=f"{r['name']} · 输入无效，旧情景已清除")
            self.valuation_figure.clear()
            self.valuation_canvas.draw_idle()
            set_text(self.valuation_detail,'参数有效后重新显示估值观察，避免把上一家公司的图表当成当前结果。')
            return
        pe=number(r['pe_ttm']) if r['pe_ttm'] and r['pe_ttm']>0 else '亏损/不适用'
        self.valuation_summary.configure(text=f"{r['name']} · {r['quote_date']}收盘 {number(r['close'])}元 · 数据源总市值 {number(r['market_cap'],1e8)}亿元 · PB {number(r['pb'])} · PE(TTM) {pe}")
        if r['pb'] and r['pb']>0:
            implied=r['close']/r['pb']
            scenario=implied*(1-haircut)*multiple
            self.valuation_scenario.configure(text=f"参考每股净资产=股价/PB={implied:.2f}元；折损{haircut:.0%}、PB={multiple:g}时价格={scenario:.2f}元。相对现价{scenario/r['close']-1:+.1%}，不代表上涨概率。")
        history_path=ROOT/'data/history'/f"{r['code']}.json"
        raw=read(history_path if history_path.exists() else ROOT/'data'/f"{r['code']}.json")
        frame=pd.DataFrame(raw['daily_basic']).drop_duplicates('trade_date').sort_values('trade_date')
        frame=frame[frame.trade_date>=r['pb_start']]
        self.valuation_figure.clear()
        ax=self.valuation_figure.add_subplot(121)
        ax.plot(pd.to_datetime(frame.trade_date),frame.pb,color='#2f6e89')
        ax.axhline(multiple,color='#ba873c',linestyle='--',label='输入情景PB')
        ax.set_ylabel('PB（数据源口径）')
        ax.grid(alpha=.2)
        ax.legend()
        profit=self.valuation_figure.add_subplot(122)
        annual=[x for x in r['annual_history'] if x['net_profit'] is not None]
        profit.bar([x['year'] for x in annual],[x['net_profit']/1e8 for x in annual],color=['#3b8b72' if x['net_profit']>=0 else '#bf6457' for x in annual])
        profit.axhline(0,color='#7b8794',linewidth=.6)
        profit.set_title('年度归母净利（含非经常项）/ 亿元',fontsize=10)
        profit.tick_params(axis='x',rotation=45,labelsize=8)
        profit.grid(axis='y',alpha=.2)
        self.valuation_figure.tight_layout()
        self.valuation_canvas.draw_idle()
        required='；'.join(f"{multiple}倍需{r['market_cap']/multiple/1e8:.2f}亿元" for multiple in (10,15,20))
        set_text(self.valuation_detail,f"当前PB在{r['pb_start']}以来{r['pb_count']}个观察中的分位：{percent(r['pb_percentile'])}。\n"
                 f"{r['history_scope']}。年度历史来自新采集财务API；最新报告的42项核心金额已对原文定位，未声称所有历史年报逐页复核。\n"
                 f"反向盈利检验：现有市值若对应正常化PE，{required}的年归母净利润。倍数是情景，不是推荐估值。\n"
                 '跨周期持有要核对：这些利润需要怎样的猪价、单位成本、销量与资产周转；不能把高景气单年利润当永久能力。\n'
                 '历史归母利润包含非经常项目；重整收益、资产处置和减值须另行拆解，不能直接当正常化盈利。\n'
                 '低分位只说明相对本样本便宜；减值、持续亏损、股本变化会改变分母。\n'
                 '总市值来自数据源（万元转元）；A/H公司不等于分别按两地价格计算的真实总市值。\n'
                 '未建立完整盈利预测及独立DCF，不把PB敏感性包装为估值结论。结合经营页的成本、现金流、负债判断。')

    def build_replay(self):
        page=self.frames['replay']
        self.label(page,'从2026年6月起，检验每一个可选建仓日',True)
        self.label(page,'当前五家公司研究篮子：等权、技术对照与跨周期条件持仓分别比较，有选股回看偏差。失败订单等待下一次允许交易的复评。')
        bar=ttk.Frame(page)
        bar.pack(fill='x')
        self.date=tk.StringVar(value='2026-06-01')
        self.strategy=tk.StringVar(value=STRATEGIES['cycle_hold'])
        self.horizon=tk.StringVar(value='共同终点')
        dates=[d.strftime('%Y-%m-%d') for d in self.model.entry_dates]
        ttk.Combobox(bar,textvariable=self.date,values=dates,width=12,state='readonly').pack(side='left')
        ttk.Combobox(bar,textvariable=self.strategy,values=list(STRATEGIES.values()),width=24,state='readonly').pack(side='left',padx=5)
        ttk.Combobox(bar,textvariable=self.horizon,values=['共同终点','20个交易日','60个交易日'],width=15,state='readonly').pack(side='left')
        ttk.Button(bar,text='重算',command=self.recalculate).pack(side='left',padx=5)
        ttk.Button(bar,text='导出账本',command=self.export).pack(side='left')
        ttk.Button(bar,text='决策依据',command=self.show_decisions).pack(side='left',padx=5)
        self.replay_status=self.label(page,'')
        bottom=ttk.Frame(page)
        bottom.pack(side='bottom',fill='x')
        self.replay_table=table(bottom,[('方案',230),('区间收益',110),('最大回撤',110),('平均仓位',110),('首笔成交',120)],5)
        page.bind('<Configure>',lambda event:self.replay_table.configure(height=3 if event.height<650 else 5),add='+')
        self.rolling_note=self.label(bottom,'')
        self.label(bottom,'单位模型允许碎股、无最低佣金；佣金万3、过户成本万0.1、卖出税费万5、单边滑点10bp为研究假设。分红扣留20%保守估计；期末未清仓。')
        self.replay_figure,self.replay_canvas=chart(page,220)
        self.recalculate()

    def recalculate(self):
        start=pd.Timestamp(self.date.get())
        count={'共同终点':0,'20个交易日':20,'60个交易日':60}[self.horizon.get()]
        index=self.model.dates.get_loc(start)
        if count and index+count-1>=len(self.model.dates):
            self.result=None
            self.replay_status.configure(text='此起点尚无完整持有期，不能用较短区间代替；请选择更早起点。')
            self.replay_figure.clear()
            self.replay_canvas.draw_idle()
            self.replay_table.delete(*self.replay_table.get_children())
            self.rolling_note.configure(text='')
            return
        end=self.model.dates[index+count-1] if count else self.model.dates[-1]
        selected=next(k for k,v in STRATEGIES.items() if v==self.strategy.get())
        self.replay_figure.clear()
        ax=self.replay_figure.add_subplot()
        self.replay_table.delete(*self.replay_table.get_children())
        for key,label in STRATEGIES.items():
            run=self.model.run(start,key,end=end)
            summary=run['summary']
            frame=pd.DataFrame(run['nav'])
            x=[start.to_pydatetime()-timedelta(hours=1)]+[pd.Timestamp(v).to_pydatetime() for v in frame.date]
            ax.plot(x,[1]+list(frame.nav),label=label,linewidth=2.2 if key==selected else 1,alpha=1 if key==selected else .6)
            self.replay_table.insert('','end',values=(label,percent(summary['return']),percent(summary['max_drawdown']),percent(summary['mean_exposure']),summary['first_fill'] or '未成交'))
            if key==selected:
                self.result=run
        ax.set_ylabel('净值')
        ax.grid(alpha=.2)
        ax.legend(fontsize=8,ncol=2)
        self.replay_figure.tight_layout()
        self.replay_canvas.draw_idle()
        self.replay_status.configure(text=f"{start.date()} → {end.date()} · {self.result['summary']['sessions']}个交易日 · 各方案从全现金独立起算")
        summary=next(r for r in read(ROOT/'results/rolling_summary.json') if r['strategy']==selected and r['horizon']==count)
        self.rolling_note.configure(text=f"全部{summary['count']}个起点：正收益占比{summary['positive_share']:.1%}，收益中位数{summary['median_return']:.1%}，最差{summary['worst_return']:.1%}，最深回撤{summary['worst_drawdown']:.1%}。起点高度重叠，不是独立胜率样本。")
        folder=RUNTIME/'explorations/swine'
        folder.mkdir(parents=True,exist_ok=True)
        with (folder/'requests.jsonl').open('a',encoding='utf-8') as file:
            import json
            file.write(json.dumps({'at':datetime.now().isoformat(),'start':str(start.date()),'end':str(end.date()),'strategy':selected},ensure_ascii=False)+'\n')

    def export(self):
        if self.result is None:
            self.replay_status.configure(text='没有完整有效的回放结果可以导出。')
            return
        destination=RUNTIME/'exports/swine'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        try:
            export_run(self.result,destination)
            self.replay_figure.savefig(destination/'comparison.png',dpi=150)
            dump(destination/'plot_scope.json',{'plot':'五方案同起点比较','ledger':self.result['summary']['strategy']})
            self.replay_status.configure(text=f'所选方案账本、决策依据与五方案图已导出：{destination}')
        except (OSError,ValueError) as exc:
            self.replay_status.configure(text=f'导出失败：{exc}')

    def build_capital(self):
        page=self.frames['capital']
        self.label(page,'策略权重不随本金改写，执行精度随资金量变化',True)
        self.label(page,'默认沿用公司经营页的当前分档条件草案；历史规则目标和等权保留作对照。各口径独立，目标不随本金变化，未释放或买不起的额度保留现金。')
        bar=ttk.Frame(page)
        bar.pack(fill='x')
        self.capital=tk.StringVar(value='100000')
        self.capital_basis=tk.StringVar(value='当前分档条件草案')
        choice=ttk.Combobox(bar,textvariable=self.capital_basis,values=['当前分档条件草案','跨周期规则最新目标','80%等权研究对照'],state='readonly',width=22)
        choice.pack(side='left',padx=4);choice.bind('<<ComboboxSelected>>',lambda _:self.calculate_capital())
        ttk.Label(bar,text='资金 / 元').pack(side='left')
        ttk.Entry(bar,textvariable=self.capital,width=15).pack(side='left',padx=8)
        ttk.Button(bar,text='试算',command=self.calculate_capital).pack(side='left')
        ttk.Button(bar,text='导出资金计划',command=self.export_capital).pack(side='left',padx=8)
        self.capital_table=table(page,[('公司',130),('参考价格',100),('目标权重',100),('股数',100),('实际权重',110),('偏差',100),('费用',100)],5)
        self.capital_status=self.label(page,'')
        self.scale_table=table(page,[('资金/元',130),('实际现金占比',130),('最大权重偏差',135),('未买入公司数',135),('容量天数代理',125),('费用/元',100)],5)
        self.scale_table.configure(height=3)
        self.capital_notes=text_panel(page,'')
        self.capital_notes.configure(height=3,pady=5,padx=5)
        self.calculate_capital()

    def calculate_capital(self):
        try:
            amount=float(self.capital.get())
            prices={c:self.by_code[c]['close'] for c in self.model.codes}
            weights={c:.8/len(prices) for c in prices}
            basis_date='80%等权对照'
            allocation=None
            if self.capital_basis.get()=='当前分档条件草案':
                if hasattr(self,'allocation_budget'):self.calculate_allocation(refresh_capital=False)
                allocation=self.allocation_result
                if allocation is None:
                    self.clear_capital('分档参数无效，请先修正公司经营页参数。');return
                prices={r['code']:self.by_code[r['code']]['close'] for r in allocation['rows']}
                weights={r['code']:r['target_weight'] for r in allocation['rows']}
                basis_date=allocation['as_of']+'当前研究条件'
            if self.capital_basis.get()=='跨周期规则最新目标':
                if not hasattr(self,'capital_policy_run'):
                    self.capital_policy_run=self.model.run('2026-06-01','cycle_hold')
                weights={r['code']:r['target'] for r in self.capital_policy_run['decisions']}
                basis_date=self.capital_policy_run['decisions'][-1]['decision_date']+'计划'
            volumes={c:float(self.model.adv[-1,j]) for j,c in enumerate(self.model.codes)}
            for code in prices.keys()-volumes.keys():
                daily=sorted(read(ROOT/'data'/f'{code}.json')['daily'],key=lambda r:r['trade_date'])
                volumes[code]=sum(float(r['vol'])*100 for r in daily[-21:-1])/20
            plan=capital_plan(amount,prices,weights,volumes=volumes)
            plan.update(target_basis=self.capital_basis.get(),target_date=basis_date,quote_date='2026-10-23')
            if allocation is not None:plan['allocation_evidence']=allocation
        except (ValueError,OverflowError):
            self.clear_capital('请输入有效正数资金；不能输入空值、负数或无穷大。')
            return
        self.capital_result=plan
        self.capital_table.delete(*self.capital_table.get_children())
        for r in plan['rows']:
            self.capital_table.insert('','end',values=(self.by_code[r['code']]['name'],number(r['reference_price']),percent(r['target_weight']),r['shares'],percent(r['actual_weight']),percent(r['weight_gap']),number(r['fees'])))
        self.capital_status.configure(text=f"{basis_date} · 目标总仓位{sum(weights.values()):.1%} · 10月23日价格参考 · 余现金{plan['cash']:,.2f}元（{plan['cash_weight']:.2%}） · 未能买入{len(plan['omitted_names'])}家公司。{plan['warning']}")
        set_text(self.capital_notes,f"非零目标各至少1手的理论本金下限约{plan['minimum_capital_for_one_lot_each']:,.0f}元；不是建议本金。目标现金{plan['target_cash_weight']:.1%}，整手/容量及费用使额外现金余量{plan['implementation_cash_gap']:.1%}。\n100股单位、最低佣金5元、单只前20日均量1%。小资金可合并分批、减少频率、接受余量；大资金按容量分日，不自动增加目标仓位。历史保留权重不是新开账户的当前买入信号。")
        self.scale_table.delete(*self.scale_table.get_children())
        for amount in (10000,50000,100000,1000000,10000000):
            p=capital_plan(amount,prices,weights,volumes=volumes)
            self.scale_table.insert('','end',values=(f'{amount:,}',percent(p['cash_weight']),percent(p['max_weight_gap']),len(p['omitted_names']),p['capacity_days_proxy'],number(p['fees'])))

    def export_capital(self):
        self.calculate_capital()
        if not self.capital_result:
            return
        folder=RUNTIME/'exports/swine_capital'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        dump(folder/'plan.json',self.capital_result)
        pd.DataFrame(self.capital_result['rows']).to_csv(folder/'orders_reference.csv',index=False,encoding='utf-8-sig')
        self.capital_status.configure(text=f'参考计划已导出：{folder}')

    def clear_capital(self,message):
        self.capital_result=None;self.capital_status.configure(text=message)
        self.capital_table.delete(*self.capital_table.get_children())
        self.scale_table.delete(*self.scale_table.get_children());set_text(self.capital_notes,'')

    def build_evidence(self):
        page=self.frames['evidence']
        self.label(page,'事实、研究判断、假设与未完成问题分别保留',True)
        bar=ttk.Frame(page)
        bar.pack(fill='x')
        ttk.Button(bar,text='打开研究资料',command=lambda:os.startfile(ROOT)).pack(side='left')
        ttk.Button(bar,text='完整研究说明',command=self.open_research_note).pack(side='left',padx=5)
        ttk.Button(bar,text='来源与原文目录',command=self.open_source_catalog).pack(side='left',padx=5)
        ttk.Button(bar,text='保存讨论记录',command=self.save_notes).pack(side='left',padx=10)
        self.notes_status=ttk.Label(bar,style='Sub.TLabel')
        self.notes_status.pack(side='left')
        bottom=ttk.Frame(page)
        bottom.pack(side='bottom',fill='x')
        self.label(bottom,'讨论笔记（仅保存本地，不会改变策略参数）')
        self.notes=tk.Text(bottom,height=4,wrap='word',font=('Microsoft YaHei',10))
        self.notes.pack(fill='x')
        path=RUNTIME/'research/swine_discussion.txt'
        if path.exists():
            self.notes.insert('1.0',path.read_text(encoding='utf-8'))
        evidence=read(ROOT/'results/cycle.json')
        lines=['公司池：'+UNIVERSE['rule'],UNIVERSE['basket_note'],'研究协议与规则在config，数据与原始公告在runtime/research/swine_v1_20261025。',
               '全部建仓日起点、20/60日比较与账本可复算。没有前向绩效，不把重叠起点当独立统计样本。',
               '三批：第1/11/21个交易日目标40%/60%/80%；风险方案每20个交易日检查前期60日均线及波动。',
               '旧研究删除清单在runtime/cleanup；公共数据仅保留给其他三个模块。','行业证据：']
        lines += [s['title']+'  '+s['date']+'\n'+s['url'] for s in evidence['sources']]
        lines += ['用户已确认：愿意跨周期持有，重点看盈利恢复与估值。',
                  '持有依据：同口径成本下降、产能去化逐步传导、经营现金流与净资产改善，且正常化盈利足以支持估值。',
                  '重新评估条件：成本竞争力持续恶化、流动性或稀释风险上升、经营恢复假设被后续报告证伪，或价格已提前兑现乐观情景。短期跌价本身不是自动退出条件。',
                  '跨周期草案已编码：每20交易日按此前公告的产能、财报、PB分位重评；冻结新增、分批兑现及资金恶化退出。阈值是研究纪律，未优化，不能据此断言有效。',
                  '旧编译与工具缓存按用户要求暂不处理，不作为本轮阻塞。']
        text_panel(page,'\n\n'.join(lines))

    def save_notes(self):
        path=RUNTIME/'research/swine_discussion.txt'
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(self.notes.get('1.0','end-1c'),encoding='utf-8')
        self.notes_status.configure(text='讨论记录已保存')

    def open_research_note(self):
        path=DEEP/'report/research.md'
        self.winfo_toplevel().document('生猪养殖：跨周期研究说明',path.read_text(encoding='utf-8'))

    def state(self):
        return {'version':'swine_v3','tab':self.pages.index(self.pages.select()),'date':self.date.get(),
                'strategy':self.strategy.get(),'horizon':self.horizon.get(),'capital':self.capital.get(),
                'company':self.valuation_company.get(),'scenario_pb':self.scenario_pb.get(),'haircut':self.haircut.get(),
                'deep':{key:getattr(self,key).get() for key in self.deep_state_fields},
                'research_tabs':{key:book.index(book.select()) for key,book in self.research_books.items()},
                'capital_basis':self.capital_basis.get()}

    def restore(self,state):
        if state.get('version') not in ('swine_v2','swine_v3'):
            return
        if state.get('date') in [d.strftime('%Y-%m-%d') for d in self.model.entry_dates]:
            self.date.set(state['date'])
        if state.get('strategy') in STRATEGIES.values():
            self.strategy.set(state['strategy'])
        if state.get('horizon') in ('共同终点','20个交易日','60个交易日'):
            self.horizon.set(state['horizon'])
        for key in ('capital','scenario_pb','haircut'):
            if key in state:
                getattr(self,key).set(state[key])
        if state.get('company') in self.valuation_names:
            self.valuation_company.set(state['company'])
        elif state.get('company') in UNIVERSE['core']:
            self.valuation_company.set(next(k for k,v in self.valuation_names.items() if v==state['company']))
        self.draw_valuation()
        if state.get('version')=='swine_v3' and state.get('capital_basis') in ('当前分档条件草案','跨周期规则最新目标','80%等权研究对照'):self.capital_basis.set(state['capital_basis'])
        for key,value in state.get('deep',{}).items():
            if key in self.deep_state_fields:
                if key in ('funding_company','recovery_company') and value not in self.deep_names:continue
                if key=='bridge_company' and value not in self.bridge_names:continue
                getattr(self,key).set(value)
        for key,index in state.get('research_tabs',{}).items():
            if key in self.research_books and isinstance(index,int) and 0<=index<len(self.research_books[key].tabs()):self.research_books[key].select(index)
        self.calculate_supply();self.calculate_funding();self.calculate_recovery();self.calculate_profit_bridge();self.calculate_allocation()
        self.calculate_capital()
        self.recalculate()
