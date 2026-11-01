"""Deeper economic views embedded in the first three swine research pages."""
from datetime import datetime
import os
import tkinter as tk
from tkinter import ttk
import pandas as pd
from matplotlib.dates import MonthLocator,YearLocator,DateFormatter
from .paths import PROJECT,RUNTIME
from .swine_data import read,dump
from .swine_valuation import recovery_value,funding_stress,supply_change,profit_requirement
from .swine_allocation import tier_allocation,allocation_sensitivity
from .widgets import table,text_panel,set_text,chart

DEEP=PROJECT/'runtime/research/swine_deep_20261025'

class DeepResearchMixin:
    deep_state_fields=('efficiency','weight_change','funding_company','refinancing','burn_factor',
                       'recovery_company','required_return','terminal_roe','recovery_payout','interim_roes','book_adjustment',
                       'bridge_company','bridge_pe','bridge_cost','bridge_volume',
                       'allocation_budget','allocation_return','allocation_roe')

    def overview_navigate(self,section):
        selected=self.overview_table.selection()
        code=selected[0] if selected else next(iter(self.deep_profiles))
        if section=='allocation':
            self.pages.select(self.frames['companies']);self.research_books['companies'].select(3)
            self.allocation_table.selection_set(code);self.show_allocation_reason()
        elif section in ('companies','funding'):
            self.pages.select(self.frames['companies'])
            self.research_books['companies'].select(1 if section=='funding' else 0)
            self.company_scope.set('核心生猪公司');self.filter_companies()
            self.company_table.selection_set(code);self.show_company()
            self.funding_company.set(next(k for k,v in self.deep_names.items() if v==code));self.calculate_funding()
        elif section=='valuation':
            self.pages.select(self.frames['valuation']);self.research_books['valuation'].select(1)
            self.recovery_company.set(next(k for k,v in self.deep_names.items() if v==code));self.calculate_recovery()
        else:
            self.open_deep_report()

    def open_deep_report(self):
        from .reading import read_report
        path=DEEP/'report/research.md'
        self.winfo_toplevel().document('生猪行业、公司与跨周期恢复研究',read_report(path),source=path)

    def open_source_catalog(self):
        window=tk.Toplevel(self);window.title('本轮新采集的来源与原文');window.geometry('1000x680')
        bar=ttk.Frame(window,padding=7);bar.pack(fill='x')
        ttk.Label(bar,text='按公司代码、名称、标题或日期查找').pack(side='left')
        query=tk.StringVar();ttk.Entry(bar,textvariable=query,width=40).pack(side='left',padx=7)
        status=ttk.Label(bar,text='');status.pack(side='left')
        view=table(window,[('来源',490),('公布日期',110),('类型',130)],15)
        records={s['id']:s for s in read(DEEP/'evidence/sources.json') if s['admission']=='accepted'}
        detail=text_panel(window);detail.configure(height=4)
        def show(_=None):
            selected=view.selection()
            if selected:
                s=records[selected[0]];set_text(detail,f"来源：{s['url']}\n取得时间：{s['retrieved_at']}\n定位：{s['publication_evidence']}\n本地原件：{s['local_path']}")
        def open_original():
            selected=view.selection()
            if not selected:return
            path=(DEEP/records[selected[0]]['local_path']).resolve()
            if path.is_relative_to(DEEP.resolve()) and path.is_file():
                if path.suffix=='.json':self.winfo_toplevel().document('原始数据响应',path.read_text(encoding='utf8'))
                else:os.startfile(path)
        def filter_sources(*_):
            view.delete(*view.get_children());text=query.get().strip().lower()
            for sid,s in records.items():
                if text and text not in (sid+s['title']+s.get('published_date','')+s['publisher']).lower():continue
                view.insert('','end',iid=sid,values=(s['title'],s.get('published_date',''),s['publisher']))
            status.configure(text=f'{len(view.get_children())} / {len(records)}项')
            if view.get_children():view.selection_set(view.get_children()[0]);show()
            else:set_text(detail,'未找到匹配来源。')
        view.bind('<<TreeviewSelect>>',show)
        ttk.Button(window,text='打开所选原件',command=open_original).pack(anchor='w',padx=10,pady=5)
        query.trace_add('write',filter_sources);filter_sources()
        window.source_query=query;window.source_view=view
        return window

    def show_decisions(self):
        if self.result is None:return
        decisions=self.result.get('decisions',[])
        lines=['每20交易日检查前一交易日以前已披露的信息；阈值为显式研究纪律，未用收益调参。',
               '目标增加需产能收缩及PB分位条件；融资依赖冻结新增；盈利及高PB分位分次兑现；高杠杆、低现金覆盖与经营净流出共同触发退出。',
               '目标变化不等于成交；涨跌停、现金及容量可能阻止执行。历史财报现金是未扣受限的上界代理，当前公司池及供应商历史PB仍有回看/修订限制。']
        for r in decisions:
            lines.append(f"{r['decision_date']} {self.by_code[r['code']]['name']} 目标{r['previous_target']:.1%}→{r['target']:.1%}：{r['reason']}\n信息截至{r['information_date']}；财报{r.get('period','缺失')}于{r.get('financial_publication','未知')}披露；产能公布{r['capacity_publication']}；PB样本{r.get('pb_observations',0)}个。")
        if not decisions:lines.append('此方案为固定或技术对照，没有基本面决策记录。')
        self.winfo_toplevel().document('所选方案决策依据','\n\n'.join(lines))
    def split_research_page(self,key,overview,detail):
        if not hasattr(self,'research_books'):
            self.research_books={};self.deep_frames={}
        book=ttk.Notebook(self.frames[key]);book.pack(fill='both',expand=True)
        old=ttk.Frame(book,padding=3);new=ttk.Frame(book,padding=7)
        book.add(old,text=overview);book.add(new,text=detail)
        self.research_books[key]=book;self.deep_frames[key]=new
        return old

    def build_deep_research(self):
        self.deep=read(DEEP/'model/results.json')
        self.deep_profiles={r['code']:r for r in self.deep['profiles']}
        self.deep_names={r['name']+' '+r['code']:r['code'] for r in self.deep['profiles']}
        self.build_supply_research();self.build_funding_research();self.build_recovery_research()
        self.build_history_cycle();self.build_price_cycle();self.build_earnings_quality();self.build_profit_bridge();self.build_allocation()

    def price_history_frame(self):
        rows=read(DEEP/'model/price_history.json')['rows']
        frame=pd.DataFrame(rows);frame.index=pd.to_datetime(frame['period']+'-01')
        return frame.reindex(pd.date_range(frame.index.min(),frame.index.max(),freq='MS'))

    def build_price_cycle(self):
        page=ttk.Frame(self.research_books['cycle'],padding=7);self.research_books['cycle'].add(page,text='猪价与饲料周期')
        self.label(page,'猪价与饲料价格',True)
        s=self.deep['price_history_summary']
        self.label(page,f"农业农村部原文重采：{s['observations']}个月样本；每月第3周，2026年10月为最新第2周。非月平均、非完整周序列，不用于确定周期最低点。")
        bottom=ttk.Frame(page);bottom.pack(side='bottom',fill='x')
        self.label(bottom,f"样本最高：{s['peak']['period']} {s['peak']['hog']:.2f}元/kg；样本最低：{s['low']['period']} {s['low']['hog']:.2f}元/kg；最新：{s['latest']['hog']:.2f}元/kg。猪粮/料比只是价格比，不能直接作为上市公司盈亏平衡点。")
        self.label(bottom,'价格回升可能先于报表改善，也可能只是季节波动；需与出栏、体重、效率和公司现金流一起核对。图按月份定位样本，实际采集日与公布日在原始数据中分别保存。缺月断线，不插值。')
        row=ttk.Frame(bottom);row.pack(fill='x')
        ttk.Button(row,text='查看逐月原始数据',command=self.open_price_observations).pack(side='left')
        ttk.Button(row,text='原始来源目录',command=self.open_source_catalog).pack(side='left',padx=5)
        self.price_cycle_figure,self.price_cycle_canvas=chart(page,250)
        frame=self.price_history_frame();a=self.price_cycle_figure.add_subplot(121);b=self.price_cycle_figure.add_subplot(122)
        a.plot(frame.index,frame.hog,label='生猪',color='#b87952');a.plot(frame.index,frame.piglet,label='仔猪',color='#2a7588')
        a.set_ylabel('元/kg');a.legend(fontsize=8);a.set_title('生猪与仔猪，口径各自可比',fontsize=9)
        b.plot(frame.index,frame.hog_corn_ratio,label='猪粮比',color='#2a7588');b.plot(frame.index,frame.hog_feed_ratio,label='猪料比',color='#71978b')
        b.set_ylabel('价格比值');b.legend(fontsize=8);b.set_title('同一观察周价格相除，不是利润',fontsize=9)
        for ax in (a,b):ax.xaxis.set_major_locator(YearLocator());ax.xaxis.set_major_formatter(DateFormatter('%Y'));ax.grid(alpha=.2)
        self.price_cycle_figure.tight_layout();self.price_cycle_canvas.draw_idle()

    def open_price_observations(self):
        window=tk.Toplevel(self);window.title('全国生猪与饲料价格：逐期证据');window.geometry('1060x660')
        self.label(window,'全国集贸市场采样；每月第3周，2026年10月为第2周。价格元/kg，非月均价。')
        view=table(window,[('期间',85),('采集日',110),('公布日',110),('生猪',80),('仔猪',80),('玉米',80),('豆粕',80),('育肥料',80),('猪料比',90)],17)
        records={r['period']:r for r in read(DEEP/'model/price_history.json')['rows']}
        sources={s['id']:s for s in read(DEEP/'evidence/sources.json')}
        for key,r in records.items():view.insert('','end',iid=key,values=(key,r['observation_date'] or '未明确',r['published_date'],*[f"{r[k]:.2f}" for k in ('hog','piglet','corn','soymeal','feed','hog_feed_ratio')]))
        detail=text_panel(window);detail.configure(height=3,pady=5)
        def show(_=None):
            if not view.selection():return
            r=records[view.selection()[0]];s=sources[r['source']]
            set_text(detail,f"{r['sample']} · {s['title']}\n{s['url']}\n猪料比=生猪价格÷育肥猪配合饲料价格；不包含料肉比、人工、折旧等，不能代替完全成本或净利润。")
        def original():
            if not view.selection():return
            s=sources[records[view.selection()[0]]['source']];path=(DEEP/s['local_path']).resolve()
            if path.is_relative_to(DEEP.resolve()) and path.is_file():os.startfile(path)
        ttk.Button(window,text='打开所选期间原文',command=original).pack(anchor='w',padx=8,pady=5)
        view.bind('<<TreeviewSelect>>',show);view.selection_set(next(reversed(records)));view.see(next(reversed(records)));show()
        window.price_view=view
        return window

    def build_allocation(self):
        page=ttk.Frame(self.research_books['companies'],padding=7);self.research_books['companies'].add(page,text='分档与条件权重')
        self.label(page,'候选额度与估值条件',True)
        self.label(page,'成本、现金、估值三项分别显示。全部使用当前研究资料，未回填至6月；默认25%终态ROE是一组可修改情景。')
        row=ttk.Frame(page);row.pack(fill='x')
        self.allocation_budget=tk.StringVar(value='80');self.allocation_return=tk.StringVar(value='10');self.allocation_roe=tk.StringVar(value='25')
        for label,var in [('组合额度上限%',self.allocation_budget),('要求回报%',self.allocation_return),('可接受终态ROE%',self.allocation_roe)]:
            ttk.Label(row,text=label).pack(side='left',padx=4);ttk.Entry(row,textvariable=var,width=6).pack(side='left')
        ttk.Button(row,text='重算分档',command=self.calculate_allocation).pack(side='left',padx=5)
        ttk.Button(row,text='导出权重依据',command=self.export_allocation).pack(side='left')
        ttk.Button(row,text='查看资金适配',command=lambda:self.pages.select(self.frames['capital'])).pack(side='left',padx=5)
        ttk.Button(row,text='假设敏感性',command=self.show_allocation_sensitivity).pack(side='left')
        footer=ttk.Frame(page);footer.pack(side='bottom',fill='x')
        self.allocation_table=table(page,[('公司',95),('成本证据',150),('现金承受力',115),('档位',55),('条件价/现价',110),('候选额度',90),('估值释放',90),('当前条件权重',120)],6)
        page.bind('<Configure>',lambda event:self.allocation_table.configure(height=4 if event.height<600 else 6))
        self.allocation_table.bind('<<TreeviewSelect>>',self.show_allocation_reason)
        self.allocation_summary=self.label(page,'')
        self.allocation_reason=text_panel(page,'');self.allocation_reason.configure(height=6,padx=10,pady=5)
        self.label(footer,'A/B/C/D候选单位3/2/1/0，单名上限30%/20%/10%/0；条件价/现价≥1.25/1/0.75时释放100%/50%/25%。完整分档定义见研究说明。')
        self.label(footer,'三年ROE−10%/0%/10%，过渡分红30%，披露后权益变化0；阈值为研究假设，未按收益优化。')
        self.calculate_allocation()

    def calculate_allocation(self,refresh_capital=True):
        try:
            result=tier_allocation(self.deep['profiles'],self.deep['costs'],self.allocation_policy,
                float(self.allocation_budget.get())/100,float(self.allocation_roe.get())/100,float(self.allocation_return.get())/100)
        except ValueError as exc:
            self.allocation_result=None;self.allocation_table.delete(*self.allocation_table.get_children())
            self.allocation_summary.configure(text=str(exc));set_text(self.allocation_reason,'')
            if self.capital_basis.get()=='当前分档条件草案':self.clear_capital('分档参数无效，请先修正公司经营页参数。')
            return
        self.allocation_result=result;self.allocation_table.delete(*self.allocation_table.get_children())
        for r in result['rows']:
            self.allocation_table.insert('','end',iid=r['code'],values=(r['name'],r['cost_band'],r['cash_band'],r['tier'],f"{r['value_coverage']:.2f}",f"{r['candidate_weight']:.1%}",f"{r['release']:.0%}",f"{r['target_weight']:.1%}"))
        self.allocation_summary.configure(text=f"条件仓位{result['target_exposure']:.1%}，现金{result['target_cash']:.1%}。额度按当前成本、资金与估值门槛释放；未满足条件的部分保留现金。")
        self.allocation_table.selection_set(result['rows'][0]['code']);self.show_allocation_reason()
        if refresh_capital and self.capital_basis.get()=='当前分档条件草案':self.calculate_capital()

    def show_allocation_reason(self,_=None):
        if self.allocation_result is None:return
        selected=self.allocation_table.selection()
        if selected:
            r=next(r for r in self.allocation_result['rows'] if r['code']==selected[0])
            set_text(self.allocation_reason,r['name']+'\n'+'\n'.join(r['reasons'])+'\n现金比较未推算成实时资产负债表；候选额度触及单名上限或估值未释放的部分均留现金。')

    def export_allocation(self):
        self.calculate_allocation()
        if self.allocation_result is None:return
        folder=RUNTIME/'exports/swine_allocation'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        dump(folder/'allocation.json',self.allocation_result);dump(folder/'policy.json',self.allocation_policy)
        dump(folder/'sensitivity.json',allocation_sensitivity(self.deep['profiles'],self.deep['costs'],self.allocation_policy,self.allocation_result['budget']))
        pd.DataFrame(self.allocation_result['rows']).to_csv(folder/'weights.csv',index=False,encoding='utf-8-sig')
        self.allocation_summary.configure(text=self.allocation_summary.cget('text')+'\n已导出至 '+str(folder))

    def show_allocation_sensitivity(self):
        self.calculate_allocation()
        if self.allocation_result is None:return
        results=allocation_sensitivity(self.deep['profiles'],self.deep['costs'],self.allocation_policy,self.allocation_result['budget'])
        lines=['不同估值假设改变可释放额度；均为当前研究条件，不按收益挑最优。成本及资金分档保持不变。',
               '要求回报 / 终态ROE → 现金；公司权重']
        for r in results:
            weights='，'.join(self.deep_profiles[c]['name']+f'{w:.1%}' for c,w in r['weights'].items() if w)
            lines.append(f"{r['required_return']:.0%} / {r['terminal_roe']:.0%} → 现金{r['target_cash']:.1%}；{weights or '全部未释放'}")
        self.winfo_toplevel().document('分档条件权重的估值敏感性','\n\n'.join(lines))

    def build_profit_bridge(self):
        page=ttk.Frame(self.research_books['valuation'],padding=7);self.research_books['valuation'].add(page,text='盈利需要怎样的价差')
        self.label(page,'估值对应的售价、成本与销量',True)
        self.label(page,'仅三家公司月报有可配对的商品猪收入与公斤价。按1—9月收入÷价格推算重量再年化，含内部销售；其余公司不补造。')
        self.bridge_names={name:code for name,code in self.deep_names.items() if any(s['code']==code[:6] for s in self.deep['price_sensitivity'])}
        row=ttk.Frame(page);row.pack(fill='x')
        self.bridge_company=tk.StringVar(value=next(iter(self.bridge_names)))
        combo=ttk.Combobox(row,textvariable=self.bridge_company,values=list(self.bridge_names),state='readonly',width=23);combo.pack(side='left');combo.bind('<<ComboboxSelected>>',self.calculate_profit_bridge)
        self.bridge_pe=tk.StringVar(value='15');self.bridge_cost=tk.StringVar(value='12');self.bridge_volume=tk.StringVar(value='0')
        for label,var in [('正常化PE假设',self.bridge_pe),('完全成本情景',self.bridge_cost),('重量变化%',self.bridge_volume)]:
            ttk.Label(row,text=label).pack(side='left',padx=4);ttk.Entry(row,textvariable=var,width=5).pack(side='left')
        ttk.Button(row,text='反算经营条件',command=self.calculate_profit_bridge).pack(side='left',padx=5)
        ttk.Button(row,text='导出情景',command=self.export_profit_bridge).pack(side='left')
        self.bridge_note=self.label(page,'')
        bottom=ttk.Frame(page);bottom.pack(side='bottom',fill='x')
        self.label(bottom,'将全公司所需利润暂由养猪承担，其他业务贡献按0假设。需要继续核对分部抵消、仔猪/种猪、少数股东、税项、减值及成本是否已含管理财务费用，不能把价差直接叫作归母净利润。')
        self.label(bottom,'12元成本和15倍PE是统一输入情景，不是实际成本或合理估值结论。以A股每股价格反推全公司利润，不按A股价格加总A/H实际市值。股本采用最新披露期末值，未披露变化另行核对。')
        self.bridge_figure,self.bridge_canvas=chart(page,260)
        self.calculate_profit_bridge()

    def calculate_profit_bridge(self,_=None):
        p=self.deep_profiles[self.bridge_names[self.bridge_company.get()]]
        volume=next(r for r in self.deep['price_sensitivity'] if r['code']==p['code'][:6])
        try:
            pe=float(self.bridge_pe.get());cost=float(self.bridge_cost.get());change=float(self.bridge_volume.get())/100
            r=profit_requirement(p['price'],p['latest_share_count'],volume['annualized_kg_proxy'],pe,cost,change)
        except ValueError as exc:
            self.bridge_result=None;self.bridge_note.configure(text=str(exc));self.bridge_figure.clear();self.bridge_canvas.draw_idle();return
        self.bridge_result={'code':p['code'],'quote_date':'2026-10-23','share_period':p['latest_period'],
                            'monthly_period':'2026-01至2026-09',**r}
        self.bridge_note.configure(text=f"{p['name']}：要求年归母利润{r['required_company_profit']/1e8:.2f}亿元；假设重量{r['scenario_kg']/1e8:.2f}亿kg，需单位价差{r['required_spread']:.2f}元/kg、售价{r['required_selling_price']:.2f}元/kg。每1元价差对应养殖口径盈余变化{r['one_yuan_spread_impact']/1e8:.2f}亿元。")
        self.bridge_figure.clear();ax=self.bridge_figure.add_subplot()
        changes=[change-.2,change,change+.2] if change>-.8 else [change,(change+1)/2-1,0]
        values=[profit_requirement(p['price'],p['latest_share_count'],volume['annualized_kg_proxy'],pe,cost,v)['required_selling_price'] for v in changes]
        ax.bar([f'基准量{v:+.0%}' for v in changes],values,color=['#bf8a6c','#2a7588','#77a18f'])
        ax.axhline(cost,color='#a24c4c',linestyle='--',label='输入完全成本情景')
        for i,value in enumerate(values):ax.text(i,value,f'{value:.2f}',ha='center',va='bottom')
        ax.margins(y=.18)
        ax.set_ylabel('所需商品猪售价 / 元kg');ax.legend(loc='lower left',fontsize=9);ax.grid(axis='y',alpha=.2)
        self.bridge_figure.tight_layout();self.bridge_canvas.draw_idle()

    def export_profit_bridge(self):
        self.calculate_profit_bridge()
        if self.bridge_result is None:return
        folder=RUNTIME/'exports/swine_profit_bridge'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        dump(folder/'scenario.json',self.bridge_result)
        self.bridge_figure.savefig(folder/'scenario.png',dpi=160)
        self.bridge_note.configure(text=self.bridge_note.cget('text')+'\n已导出至 '+str(folder))

    def build_history_cycle(self):
        page=ttk.Frame(self.research_books['cycle'],padding=7)
        self.research_books['cycle'].add(page,text='历史周期与当前差异')
        self.label(page,'能繁母猪与猪肉产量的年度变化',True)
        bottom=ttk.Frame(page);bottom.pack(side='bottom',fill='x')
        text_panel(bottom,'2023年末母猪降至4,142万头，全年猪肉产量仍增至5,794万吨；2024年末母猪继续下降，全年肉量才转为下降。存栏是时点、出栏是期间流量，仔猪存量、生产效率和出栏重量都会改变传导。\n当前2026Q3母猪同比−10.7%，但1—9月猪肉产量仍同比＋3.2%。这支持继续跟踪供给收缩，尚不足以确认盈利拐点。\n跟踪顺序：母猪及仔猪供给 → 商品猪出栏和体重 → 同口径售价与饲料成本 → 公司经营现金流与净资产。需求、库存、进口和二次育肥尚未形成完整连续序列，未对猪价做单点预测。').configure(height=6)
        figure,canvas=chart(page,240);rows=self.deep['annual_capacity']
        first=figure.add_subplot(121);second=figure.add_subplot(122)
        first.plot([r['year'] for r in rows],[r['sows'] for r in rows],marker='o',color='#2a7588');first.set_ylabel('年末能繁母猪 / 万头')
        second.bar([r['year'] for r in rows],[r['pork_output'] for r in rows],color='#71978b');second.set_ylabel('全年猪肉产量 / 万吨')
        for ax in (first,second):ax.set_xticks([r['year'] for r in rows]);ax.grid(alpha=.2)
        figure.tight_layout();canvas.draw_idle()

    def build_earnings_quality(self):
        page=ttk.Frame(self.research_books['companies'],padding=7)
        self.research_books['companies'].add(page,text='利润、减值与经营恢复')
        self.label(page,'利润变化与资产减值',True)
        self.label(page,'2026Q2=半年累计−一季度累计，六家公司均使用原始报告核对。金额亿元。')
        view=table(page,[('公司',105),('Q1归母净利',120),('Q2归母净利',120),('H1资产减值损益',150),('H1剔除该项利润总额',180)],6)
        for r in self.deep['profiles']:
            e=r['earnings_bridge']
            view.insert('','end',values=(r['name'],*[f"{e[k]/1e8:.2f}" if e[k] is not None else '未取得' for k in ('q1_net_profit','q2_net_profit','half_asset_impairment','profit_excluding_asset_impairment')]))
        text_panel(page,'神农二季度较一季度明显减亏，但仍需结合减值计提与生物资产结转解释；六家公司上半年剔除资产减值损益后的利润总额仍为负，不能把全部亏损解释成一次性账面影响。\n“转销”与“转回”不同：已出售存货对应的跌价准备随成本结转，不是同额新增利润。资产减值加回口径仍包含折旧、融资费用、处置和信用减值等，既不是正常化净利润，也不是现金流。\n判断恢复需要三个方向同时观察：售价与可比成本差缩小；经营现金流改善；归母净资产止跌。只有利润表单季变好而现金与权益持续恶化，需继续查明原因。\n历史盈利对照在估值页。天邦2024年正利润不能直接当作养殖长期盈利能力，仍需拆分非经常收益及重整/资产处置影响。')

    def build_supply_research(self):
        page=self.deep_frames['cycle']
        self.label(page,'能繁母猪、效率与出栏重量的供给情景',True)
        self.label(page,'母猪同比下降已扩大，但效率与出栏重量会抵消部分影响。下表出栏、肉量同比为年初累计口径。')
        view=table(page,[('期间',110),('能繁/万头',130),('母猪同比',110),('出栏同比',110),('肉量同比',110),('公布日期',130)],4)
        for r in self.deep['capacity']:
            view.insert('','end',values=(r['period'],f"{r['sows']:,}",f"{r['sow_yoy']:+.1%}",f"{r['output_yoy']:+.1%}",f"{r['meat_yoy']:+.1%}",r['published']))
        controls=ttk.Frame(page);controls.pack(fill='x')
        self.efficiency=tk.StringVar(value='5');self.weight_change=tk.StringVar(value='2')
        for label,var in [('每母猪产出提升%',self.efficiency),('出栏重量变化%',self.weight_change)]:
            ttk.Label(controls,text=label).pack(side='left',padx=4)
            ttk.Entry(controls,textvariable=var,width=6).pack(side='left')
        ttk.Button(controls,text='拆分供给变化',command=self.calculate_supply).pack(side='left',padx=8)
        self.supply_note=self.label(page,'')
        bottom=ttk.Frame(page);bottom.pack(side='bottom',fill='x')
        last=self.deep['feed_prices'][-1]
        self.label(bottom,f"{last['period']}集贸监测：生猪{last['hog']:.2f}、仔猪{last['piglet']:.2f}、玉米{last['corn']:.2f}、豆粕{last['soymeal']:.2f}、育肥料{last['feed']:.2f}元/kg。猪粮比{last['hog_corn_ratio']:.2f}仅作价格关系，不是公司盈亏线。")
        self.supply_figure,self.supply_canvas=chart(page,150)
        ax=self.supply_figure.add_subplot()
        rows=self.deep['capacity'];x=list(range(len(rows)))
        ax.plot(x,[r['sows'] for r in rows],marker='o',label='实际能繁母猪存栏')
        ax.step(x,[r['target'] for r in rows],where='mid',linestyle='--',label='当期政策正常保有量')
        ax.set_xticks(x,[r['period'] for r in rows]);ax.set_ylabel('万头');ax.legend(fontsize=8);ax.grid(alpha=.2)
        self.supply_figure.tight_layout();self.supply_canvas.draw_idle()
        self.calculate_supply()

    def calculate_supply(self):
        try:
            efficiency=float(self.efficiency.get())/100;weight=float(self.weight_change.get())/100
            result=supply_change(self.deep['capacity'][-1]['sow_yoy'],efficiency,weight)
            self.supply_result=result
            self.supply_note.configure(text=f"母猪−10.7% × 效率{efficiency:+.1%} × 重量{weight:+.1%} → 简化肉量变化{result:+.1%}。这是传导情景，不是对未来出栏或猪价的预测；月份滞后及二次育肥另行观察。")
        except ValueError:
            self.supply_result=None;self.supply_note.configure(text='请输入有限数值，变化率须大于−100%。')

    def build_funding_research(self):
        page=self.deep_frames['companies']
        self.label(page,'现金储备与12个月资金压力',True)
        self.label(page,'本模型保留10月25日研究输入，统一为2026H1；扣除已核实受限资金，新五丰另扣募集资金用途限制。总览采用后续核实的可动用现金，天邦专用偿债资金的扣减见总览明细。金额亿元。')
        self.funding_table=table(page,[('公司',110),('可用现金代理',130),('短期到期义务代理',160),('现金覆盖',105),('经营现金−资本开支',175)],6)
        for r in self.deep['profiles']:
            self.funding_table.insert('','end',values=(r['name'],f"{r['cash_available_proxy']/1e8:.2f}",f"{r['short_obligations_proxy']/1e8:.2f}",f"{r['cash_short_coverage']:.1%}",f"{(r['operating_cashflow']-r['capex_cash'])/1e8:.2f}"))
        bar=ttk.Frame(page);bar.pack(fill='x')
        self.funding_company=tk.StringVar(value=next(iter(self.deep_names)))
        combo=ttk.Combobox(bar,textvariable=self.funding_company,values=list(self.deep_names),state='readonly',width=23);combo.pack(side='left');combo.bind('<<ComboboxSelected>>',self.calculate_funding)
        self.refinancing=tk.StringVar(value='50');self.burn_factor=tk.StringVar(value='1')
        for label,var in [('续作比例%',self.refinancing),('流出倍数',self.burn_factor)]:
            ttk.Label(bar,text=label).pack(side='left',padx=6);ttk.Entry(bar,textvariable=var,width=6).pack(side='left')
        ttk.Button(bar,text='12个月压力测试',command=self.calculate_funding).pack(side='left',padx=6)
        self.funding_note=self.label(page,'')
        self.funding_detail=text_panel(page);self.funding_detail.configure(height=6)
        self.calculate_funding()

    def calculate_funding(self,_=None):
        r=self.deep_profiles[self.deep_names[self.funding_company.get()]]
        try:
            result=funding_stress(r['cash_available_proxy'],r['short_obligations_proxy'],r['operating_cashflow'],r['capex_cash'],
                                  burn_factor=float(self.burn_factor.get()),refinancing=float(self.refinancing.get())/100)
        except ValueError:
            self.funding_result=None;self.funding_note.configure(text='续作比例须为0%至100%，流出倍数须为非负有限值。');set_text(self.funding_detail,'无有效结果，旧压力情景已清除。');return
        self.funding_result=result
        self.funding_note.configure(text=f"{r['name']}：按半年流速计每月净流出{result['monthly_burn']/1e8:.2f}亿元；12个月后未补充融资现金{result['ending_cash_before_new_funds']/1e8:.2f}亿元；需改善经营/削减支出/新增融资合计{result['new_funding_required']/1e8:.2f}亿元。")
        text=(f"资金桥：货币资金{r['cash_gross']/1e8:.2f} − 不可自由使用{r['cash_restricted']/1e8:.2f} − 另有用途限制{r['cash_purpose_bound']/1e8:.2f} = 可用现金代理{r['cash_available_proxy']/1e8:.2f}亿元。\n"
              f"原半年报文件页{r['restriction_page']}。短期义务=短期借款＋一年内到期非流动负债，包含部分租赁，不等于全部未来付款。\n"
              '压力模型把当期经营现金流减购建长期资产的净流出延续12个月，用来量化融资依赖；不是经营预测或违约概率。若本期为净流入，仅保守按零消耗，不承诺未来持续流入。\n'
              '缺口可以由猪价/效率改善、资本开支减少、资产处置、续贷或权益融资改变；其中权益融资会稀释每股价值。尚未计额外分红、融资利息和全部租赁付款，因此不是完整偿债预算。')
        set_text(self.funding_detail,text)

    def build_recovery_research(self):
        page=self.deep_frames['valuation']
        self.label(page,'现价隐含的长期ROE与净资产变化',True)
        top=ttk.Frame(page);top.pack(fill='x')
        self.recovery_company=tk.StringVar(value=next(iter(self.deep_names)))
        combo=ttk.Combobox(top,textvariable=self.recovery_company,values=list(self.deep_names),state='readonly',width=23);combo.pack(side='left');combo.bind('<<ComboboxSelected>>',self.calculate_recovery)
        self.required_return=tk.StringVar(value='10');self.terminal_roe=tk.StringVar(value='15');self.recovery_payout=tk.StringVar(value='30');self.interim_roes=tk.StringVar(value='-10,0,10')
        for label,var in [('要求回报%',self.required_return),('终态ROE%',self.terminal_roe),('过渡分红%',self.recovery_payout)]:
            ttk.Label(top,text=label).pack(side='left',padx=4);ttk.Entry(top,textvariable=var,width=5).pack(side='left')
        row=ttk.Frame(page);row.pack(fill='x',pady=4)
        ttk.Label(row,text='未来各年ROE%（逗号分隔）').pack(side='left')
        ttk.Entry(row,textvariable=self.interim_roes,width=17).pack(side='left',padx=6)
        self.book_adjustment=tk.StringVar(value='0')
        ttk.Label(row,text='披露后权益变化%').pack(side='left')
        ttk.Entry(row,textvariable=self.book_adjustment,width=5).pack(side='left',padx=4)
        ttk.Button(row,text='反算并检查',command=self.calculate_recovery).pack(side='left')
        ttk.Button(row,text='导出情景模型',command=self.export_recovery).pack(side='left',padx=6)
        self.recovery_note=self.label(page,'')
        bottom=ttk.Frame(page);bottom.pack(side='bottom',fill='x')
        self.label(bottom,'起点为最新披露归母权益÷期末股本，披露后变化默认0%只是占位假设，并非10月实时净资产。10%为要求回报情景；终态零增长、全分配，无增发且再投资足以维持盈利。')
        self.recovery_history=self.label(bottom,'')
        self.recovery_figure,self.recovery_canvas=chart(page,220)
        self.calculate_recovery()

    def calculate_recovery(self,_=None):
        r=self.deep_profiles[self.deep_names[self.recovery_company.get()]]
        try:
            roes=tuple(float(v.strip())/100 for v in self.interim_roes.get().replace('，',',').split(','))
            ke=float(self.required_return.get())/100;terminal=float(self.terminal_roe.get())/100;payout=float(self.recovery_payout.get())/100
            adjustment=float(self.book_adjustment.get())/100
            if not -1<adjustment<=2:raise ValueError('披露后权益变化须大于−100%且不超过200%')
            starting_book=r['latest_bps']*(1+adjustment)
            if not roes:raise ValueError('至少一个过渡年度')
            result=recovery_value(starting_book,r['price'],ke,roes,terminal,payout)
        except ValueError as exc:
            self.recovery_result=None;self.recovery_note.configure(text=f'参数无效：{exc}');self.recovery_history.configure(text='');self.recovery_figure.clear();self.recovery_canvas.draw_idle();return
        self.recovery_result={'company':r['name'],'code':r['code'],'financial_period':r['latest_period'],'reported_bps':r['latest_bps'],'post_report_book_adjustment':adjustment,**result}
        self.recovery_note.configure(text=f"{r['name']} · 现价{r['price']:.2f}元：上述等待路径下需终态ROE {result['required_terminal_roe']:.1%}；输入终态ROE {terminal:.1%}对应条件价值{result['conditional_value']:.2f}元。期末每股净资产{result['closing_book']:.2f}元。")
        recent=[x for x in r['historical_roe_proxy'] if int(x['year'])>=2022]
        self.recovery_history.configure(text='历史ROE代理（归母净利÷期初末平均权益，含非经常项）：'+'；'.join(f"{x['year']}年{x['roe']:.1%}" for x in recent)+'。不直接取高点作为永久能力；需增发时重建每股模型。')
        self.recovery_figure.clear()
        ax=self.recovery_figure.add_subplot(121)
        years=[0]+[x['year'] for x in result['path']]
        ax.plot(years,[starting_book]+[x['closing_book'] for x in result['path']],marker='o',color='#2a7588')
        ax.set_xlabel('未来年度（0为调整后起点）');ax.set_ylabel('每股归母净资产 / 元');ax.set_xticks(years);ax.grid(alpha=.2)
        heat=self.recovery_figure.add_subplot(122)
        values=[[recovery_value(starting_book,r['price'],k,roes,t,payout)['conditional_value'] for t in (.10,.15,.20)] for k in (.08,.10,.12)]
        heat.imshow(values,cmap='Blues',aspect='auto');heat.set_xticks(range(3),['10%','15%','20%']);heat.set_yticks(range(3),['8%','10%','12%'])
        heat.set_xlabel('终态ROE');heat.set_ylabel('要求回报');heat.set_title('条件价值/元，其他沿用输入',fontsize=9)
        for i in range(3):
            for j in range(3):heat.text(j,i,f'{values[i][j]:.2f}',ha='center',va='center',color='black' if values[i][j]<max(map(max,values))*.75 else 'white')
        self.recovery_figure.tight_layout();self.recovery_canvas.draw_idle()

    def export_recovery(self):
        self.calculate_recovery()
        if self.recovery_result is None:return
        folder=RUNTIME/'exports/swine_recovery'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        dump(folder/'scenario.json',self.recovery_result)
        self.recovery_figure.savefig(folder/'scenario.png',dpi=150)
        self.recovery_note.configure(text=f'情景与图已导出：{folder}')
