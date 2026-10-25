"""Build narrative and an executed companion notebook from existing evidence."""
from __future__ import annotations

import json

import mistune
import nbformat
from nbclient import NotebookClient

from quant_workbench.data import ROOT

folder = ROOT / "reports/enhancement_v1"
data = json.loads((folder/"dashboard.json").read_text(encoding="utf-8"))
audits = json.loads((folder/"frozen_reference_audit.json").read_text(encoding="utf-8"))


def pct(x):
    return f"{x:.2%}" if x is not None else "—"


lines = ["# 指数增强研究：执行改进已完成，稳定超额收益尚未得到证明", "",
         "数据截止2026-10-23；研究于2026-10-24执行。100万元模拟本金。当前工程版本v1r4，全部区间均为已看过的历史回溯。旧工作台、旧183项实验及本轮v1/v1r2/v1r3失败结果保留。",
         "", "## 1. 结论先读", "",
         "最新约束动量主方案在2025—2026-10-23累计收益9.25%，沪深300全收益9.51%，ETF对照8.83%，原动量20股5.05%。主方案的最大回撤从旧方案35.54%降为16.18%，实现跟踪误差从19.10%降为3.42%。这说明风险结构明显接近指数，却还不能说明它具有可信的超额收益。",
         "", "2022—2024主方案累计亏损16.91%，比全收益指数亏损13.87%更差。2017—2021虽然较强，也不能挑出这一段宣称成功。预设防御备选近期收益10.38%，但实现TE4.71%超过4%预算，旧版早期区间曾未能启动，修订版仍保留首次失败；不能因为近期跑赢就换它做主方案。",
         "", "所有主动基础方案经24项比较校正的年化日均超额收益区间均包含零。更重要的是，历史已见、部分资料时点为代理、实际持仓有超限，因此本轮没有满足实盘采用门槛。下一步优先补执行风控和新数据前向证据，而不是扩大参数搜索。",
         "", "## 2. Portfolio到底如何选择", "",
         "以510300沪深300ETF作为至少50%的底仓，其余为历史沪深300股票池中的主动持股。底仓用于保留市场暴露，主动部分承担选股判断；现金按交易单位和成本留存。候选数40不等于最终持仓数，旧持股也可能因换手限制保留。",
         "", "每月末收盘，仅使用当时以前的数据。历史指数权重取严格早于决策日的最近快照；行业按纳入/剔除区间匹配，不能用今天的行业覆盖全部过去。没有行业或足够信号历史、过去20日成交额不足、最小交易单位超过单股预算、历史ST/退警示、窗口内未核清公司行动的股票不新增。",
         "", "主信号是252日至21日前的动量，在每个行业内部排名并映射至[-1,1]。这让模型倾向于选本行业表现更强的股票，减少直接押注过去最强行业的倾向。防御备选固定为动量排名与负60日波动排名各50%。动量持续、低波动风险特征只是可检验假设，都有反转、拥挤与风格失效风险。",
         "", "先每行业取一个候选，再按同一排名补足40名。连续优化权衡：信号得分、相对指数风险和交易幅度，目标等价于最小化 `−0.03×信号·权重 + 2×预测主动方差 + 0.002×双边权重变动`。0.03只是固定设计尺度，不是预测年收益3%，也不代表某只股票有确定的预期回报。",
         "", "风险使用过去252个交易日、至少126条观察的协方差，并用10%对角收缩减少噪声。缺失和停牌采用披露的估计口径；模型风险仍存在。求解器找到的只是给定假设与估计量下的解，不能制造投资优势。",
         "", "## 3. 约束如何落实，哪里还未做到", "",
         "| 项目 | 外部研究预算 | v1r4沿用整数订单缓冲 |", "|---|---:|---:|",
         "| 行业主动偏离 | 每行业±3个百分点 | ±2.8个百分点 |",
         "| 直接持股权重 | 单只≤3% | 单只≤2.9% |",
         "| ETF底仓 | ≥50% | ≥50% |",
         "| 预测年化跟踪误差 | ≤4% | ≤3.8% |",
         "| 预测波动 / 指数波动 | ≤1.10 | ≤1.08 |",
         "| 月度单边换手（首次建仓除外） | ≤15% | ≤14% |",
         "| 现金 | 原连续模型0.5% | 整数方案0.5%—0.7% |", "",
         "跟踪误差是每日组合收益减基准收益的标准差乘√252。单边权重换手含现金，定义为各项权重变动绝对值之和的一半；实际成交另按买卖金额较大者除决策权益核验。首次建仓豁免明确记录。ETF穿透暴露用于行业检查，但直接单股3%上限不等于含ETF穿透后每家公司总暴露≤3%。",
         "", "整数投影以最接近连续目标为准，直接求合法交易单位及现金；二次风险用凸外逼近并重新完整验证，最多12轮、每轮2秒，不声称总能找到全局最优。次日按冻结股数发出模拟订单，保留停牌、涨跌停、容量、现金不足和未成交。目标无法满足约束时保留实际持仓并记录失败，不放宽风险预算。",
         "", "这些是决策/订单约束，尚非持续盘中硬风控。月内行情、分红、订单未成交及最新行业权重变化都会令实际仓位超限。工作台逐日审计并显示红色超限，不能把求解器成功当作全期间合规。风险冲突时，未来生产版本必须有明确优先级和降险订单机制；不能同时口头保证绝对行业上限、绝对换手上限和随时可成交。",
         "", "## 4. 公平比较结果", "",
         "全收益基准为H00300.CSI，按同一交易日及共同期初权益归一，含股息再投资。ETF对照为510300，按同一账本、费用、滑点、分红到账与月度规则模拟99.5%ETF。理论指数无投资者交易摩擦，ETF对照检验可交易替代品；二者都必须保留。",
         "", "个股采用原始价格、股数、现金和应收账本处理分红与股本事件，股息税前。手续费、印花税/过户费适用日期、ETF费用差异及滑点均纳入；ETF管理等费用已经反映在市场价格中，未额外重复扣除。现金收益设零。ETF与指数差距还包括市场价格偏离、分红再投资时间和现金，不能全归因于手续费。",
         "", "相对全收益一列是 `(1+组合累计收益)/(1+指数累计收益)−1`，不是简单百分点差。所有区间独立以100万元启动，不把三段直接拼成真实连续账户。旧等权受交易单位和现金约束，不能将其当作满仓市场指数。"]
for phase, detail in data["phases"].items():
    lines += ["", f"### {detail['label']}：{detail['start']}—{detail['end']}", "",
              "| 方案 | 累计收益 | 相对全收益 | 最大回撤 | 实现TE |", "|---|---:|---:|---:|---:|"]
    for r in detail["rows"]:
        lines.append(f"| {r['name']} | {pct(r['total_return'])} | {pct(r['relative_return'])} | {pct(r['max_drawdown'])} | {pct(r['tracking_error'])} |")
    lines += ["", f"![净值及主动收益]({phase}_comparison.png)", "",
              "防御备选若累计收益和回撤为零，表示未能建仓而保持现金，不代表成功避险。存档版本仅供审计，不能按历史胜负倒选。"]
lines += ["", "## 5. 实际约束与失败记录", "",
          "| 区间/方案v1r4 | 行业超限天数 | 最大行业偏离 | 单股超限天数 | ETF不足天数 | 换手超限次数 | 调仓失败/总次数 |",
          "|---|---:|---:|---:|---:|---:|---:|"]
for detail in data["phases"].values():
    for key in ["momentum_constrained", "defensive_constrained"]:
        r = detail["details"][key]
        c = r["actual_constraints"]
        name = "主方案" if key.startswith("momentum") else "防御备选"
        lines.append(f"| {detail['label']}/{name} | {c['industry_violation_days']}/{r['days']} | {pct(c['max_actual_industry_deviation'])} | {c['direct_stock_cap_violation_days']} | {c['core_floor_violation_days']} | {c['executed_turnover_violations']} | {r['solver_failed_or_held']}/{r['decision_count']} |")
lines += ["", "行业表使用每天最新可用的历史指数权重。`turnover_reconciliation.json`按首次实际成交日独立复核建仓豁免：r4原结果的换手审计仍使用区间起始日，延后建仓会误报首次换手；当前展示纠正此统计标志，原结果/净值/成交不改写。`frozen_reference_audit.json`还按最近被接受决策使用的参考权重重新计算，区分参考变化与持仓漂移；二者都不能掩盖超限。", "",
          "v1保留连续权重，出现整手误差和初始求解失败。v1r2修正数值尺度并向ETF收缩，但2022—2024主方案的离散投影连续36次失败。v1r3改用整数规划和固定股数后，主方案三个区间失败分别为0、1、0次。修订改善执行可行性，并不保证提高收益。", "",
          "前三版防御备选2017年启动失败的链条是：首次连续解未通过风险约束，纯ETF备用方案也不满足当时预测风险预算；保持现金后又受换手上限限制。v1r4按首次实际持仓关闭豁免，失败后仍允许依法重试，之后清仓不能重获豁免。本地2016年风险窗口的ETF与全收益指数日收益差在1月7—8日约4.2个百分点，ETF实现TE约6.87%。保留该真实输入风险，不以删掉极端日期或改风险上限强行启动。熔断背景有交易所公告，但ETF个别价格未完成独立第二源核验，不能把差异的成因说成已证实。", "",
          "## 6. 成本、时延和统计不确定性", "",
          "| 区间/方案 | 基础收益 | 双倍费用滑点 | 额外延迟一日 |", "|---|---:|---:|---:|"]
for detail in data["phases"].values():
    for key, label in [("etf_reference", "ETF"), ("momentum_constrained", "主方案"), ("defensive_constrained", "防御")]:
        results = {r["scenario"]: r for r in detail["stress"] if r["strategy"] == key}
        lines.append(f"| {detail['label']}/{label} | {pct(results['base']['total_return'])} | {pct(results['double_cost']['total_return'])} | {pct(results['extra_delay']['total_return'])} |")
lines += ["", "时延压力有时收益更高，不能因此把更长时延选为策略参数；三种情景同样公开。成本压力是执行敏感性，未覆盖所有市场冲击模型。", "",
          "20日区块自助法、固定随机种子、4000次重采样，18个主动基础方案×区间×工程版本比较使用Bonferroni区间。它对应年化日均主动收益，而不是累计收益或CAGR差的置信区间。此前原项目试验、资料回填、选题选择偏差仍存在，不能将统计校正解释为未来胜率。全部108项结果见`all_108_experiments.csv`。", "",
          "## 7. 最新实际持仓是什么", ""]
h = data["phases"]["review"]["holdings"]["momentum_constrained"]
etf = next(r for r in h["rows"] if r["code"] == "510300.SH")
lines += [f"截至{h['asof']}，最近接受的目标日{h['decision_date']}。模拟权益{h['equity']:,.2f}元，现金{h['cash']:,.2f}元（{pct(h['cash_weight'])}），应收{h['receivable']:,.2f}元。ETF底仓{pct(etf['actual_weight'])}，直接股票合计{pct(h['stock_weight']-etf['actual_weight'])}。共{h['held_count']}项证券持仓，含1只ETF。", "",
          "| 代码 | 名称 | 行业 | 实际股/份 | 实际权重 | 最近目标 |", "|---|---|---|---:|---:|---:|"]
for r in h["rows"]:
    lines.append(f"| {r['code']} | {r['name']} | {r['industry']} | {r['shares']:,} | {pct(r['actual_weight'])} | {pct(r['target_weight'])} |")
lines += ["", "建设银行与伊利股份的实际直接权重已略高于3%，是价格漂移后的风险提醒，不能把上述账本直接当作现在的新资金买入清单。当前完整股数、金额、目标差异及行业穿透在原生窗口“指数增强→实际持仓/行业偏离”中展示，也可读取同名CSV。", "",
          "## 8. Shreve两卷给了什么，不能给什么", "",
          "沿用项目已核对的Shreve I印刷第9/36页与II第154/214页的框架：财富由证券、现金和应收构成；策略适应当时信息；交易必须晚于信号；真实测度P的经验收益与风险中性测度Q的定价不能混用。本轮对应账本守恒测试、因果时序测试与明确的真实历史收益比较。", "",
          "这些理论提供一致的建模和核算语言，不直接证明动量有效，也不保证受约束最优组合超过指数。来源页码和既有阅读记录见`research/methodology.md`；本轮没有把局部核对说成重新通读两书。", "",
          "## 9. 如何做一个能复刻的Agent", "",
          "已提供本地确定性工具层：`python -m quant_workbench.quant_agent status|verify|run|report`。它检查四个冻结版本、108项实验及1080个结果文件，核对账本和时间顺序；保存可验证哈希链事件日志。已完成的实验复用核验，不重写历史净值。", "",
          "LLM应负责限定问题、提出可证伪假设、解释证据和报告；数据、账本、约束及门禁由代码执行。任务合同固定基准、风险、时间与实验预算。工具只接受白名单结构化参数，外部PDF/网页内容不成为执行指令。新规则写入新版本，已见历史不再称盲测，失败不可删除。", "",
          "当前未接LLM API或券商，并非全自动量化投顾。完整架构、工具协议、停止规则和后续缺口在`research/quant_agent_design.md`。下一步最有价值的闭环是：每日冻结计划→新数据只追加→记录模拟成交及风险冲突→用一段真正新历史评价，而非继续搜索历史最优参数。", "",
          "## 10. 来源、复核与未解决事项", "",
          "- 本地原始查询与哈希：`artifacts/enhancement_v1/source_receipts.json`；数据质量：`artifacts/enhancement_v1/data_quality.json`。",
          "- 新增全收益/ETF/复权数据各2867个交易日；行业7926条历史区间记录。历史成分公告时间、行业发布时间和修订版本不完整，不能称完整point-in-time。",
          "- ETF官方限价接口仅从2019-06-26起有数据，早期缺1090日，部分精度不足；回测采用前收除息参考×±10%、0.001刻度并向内收0.006的披露模型，不冒称逐日交易所实测限价。",
          "- ETF行业穿透使用可用指数权重代理，不是基金逐日实际持仓。部分历史行业归属未知并保留UNKNOWN，不能强行归零。",
          "- 前向证据为零；实际行业/个股/ETF底仓并非全日合规；极端ETF价格尚需第二源核验。数据核验通过只说明已执行检查，不能消除这些限制。",
          "- 可复算伴随笔记：`enhancement_review.ipynb`与HTML预览。脚本`verify_delivery.py`核验旧323个文件、36个输入及183项旧实验；`quant_agent verify`核验本轮完整证据。", "",
          "官方/原始来源：",
          "- [中证指数沪深300事实表：全收益代码H00300](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/000300factsheet.pdf)",
          "- [Tushare历史行业成员接口](https://tushare.pro/document/2?doc_id=335)",
          "- [TushareETF涨跌停接口](https://tushare.pro/document/2?doc_id=491)",
          "- [Tushare基金分红每股口径](https://tushare.pro/document/2?doc_id=120)",
          "- [上交所ETF交易知识](https://www.sse.com.cn/assortment/fund/etf/question/c/c_20240118_5734754.shtml)",
          "- [上交所2016年1月8日起暂停指数熔断通知](https://www.sse.com.cn/aboutus/mediacenter/hotandd/c/c_20160107_4033450.shtml)"]
text = "\n".join(lines)+"\n"
(folder/"report.md").write_text(text, encoding="utf-8")
css = "body{max-width:1150px;margin:45px auto;padding:0 25px;font:17px/1.8 'Microsoft YaHei',sans-serif;color:#23364c}h1,h2{color:#153c66}table{width:100%;border-collapse:collapse;font-size:14px}th,td{border-bottom:1px solid #d8e0e9;padding:8px;text-align:left}th{background:#edf3fa}img{max-width:100%}code{background:#eef2f6;padding:2px 4px}a{color:#176aa2}"
(folder/"report.html").write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>指数增强研究</title><style>'+css+'</style><body>'+mistune.create_markdown(plugins=['table'])(text)+'</body></html>', encoding="utf-8")

nb = nbformat.v4.new_notebook()
nb.metadata.kernelspec = {"display_name": "Python 3", "language": "python", "name": "python3"}
nb.cells = [nbformat.v4.new_markdown_cell("# 指数增强：独立复核伴随笔记\n所有输入来自已冻结本地产物。此笔记只读取、核验和展示；不更改研究规则、不请求网络。全部历史已见，非新样本外。")]
cells = [
'''from pathlib import Path
import json, hashlib
import numpy as np
import pandas as pd
from IPython.display import display, Image
root = Path.cwd()
while not (root/'config/enhancement_v1r4.json').exists():
    if root.parent == root: raise RuntimeError('Run inside quant_workbench')
    root = root.parent
report = root/'reports/enhancement_v1'
for version in ['enhancement_v1','enhancement_v1r2','enhancement_v1r3','enhancement_v1r4']:
    seal = json.loads((root/f'artifacts/{version}/freeze.json').read_text(encoding='utf-8'))
    assert all(hashlib.sha256((root/p).read_bytes()).hexdigest()==h for p,h in seal['hashes'].items())
    print(version, len(seal['hashes']), 'frozen inputs unchanged')''',
'''quality = json.loads((root/'artifacts/enhancement_v1/data_quality.json').read_text(encoding='utf-8'))
profiles=[]
for name in ['benchmark','etf_daily','etf_adj']:
    frame=pd.read_parquet(root/f'data/enhancement_v1/{name}.parquet')
    assert not frame.duplicated(['ts_code','trade_date']).any()
    profiles.append({'table':name,'rows':len(frame),'first':frame.trade_date.min(),'last':frame.trade_date.max()})
display(pd.DataFrame(profiles))
display(quality)
print('Passing checks does not establish publication-vintage PIT or actual ETF daily limit history.')''',
'''all_runs=pd.read_csv(report/'all_108_experiments.csv')
assert len(all_runs)==108
assert all_runs.groupby(['version','phase']).size().eq(9).all()
display(all_runs.groupby(['version','phase']).agg(runs=('id','size'),failed_decisions=('solver_failed_or_held','sum')))
print('All failed/zero-return starts remain registered; never discard them as outliers.')''',
'''rows=[]
for phase in ['development','validation','review']:
    folder=root/f'artifacts/enhancement_v1r4/runs/{phase}/momentum_constrained_base'
    nav=pd.read_parquet(folder/'nav.parquet')
    bench=pd.read_parquet(folder/'benchmark.parquet')
    assert nav.index.equals(bench.index)
    a=nav.equity.pct_change(fill_method=None); a.iloc[0]=nav.equity.iloc[0]/1e6-1
    b=bench.equity.pct_change(fill_method=None); b.iloc[0]=bench.equity.iloc[0]/1e6-1
    saved=json.loads((folder/'result.json').read_text())
    te=(a-b).std()*np.sqrt(252)
    assert np.isclose(te,saved['vs_total_return_index']['tracking_error'])
    positions=pd.read_parquet(folder/'positions.parquet')
    values=positions.assign(value=positions.shares*positions.mark).groupby('date').value.sum().reindex(nav.index).fillna(0)
    assert np.allclose(values+nav.cash+nav.receivable,nav.equity)
    rows.append({'phase':phase,'strategy_return':nav.equity.iloc[-1]/1e6-1,'index_return':bench.equity.iloc[-1]/1e6-1,'tracking_error':te,'cash_min':nav.cash.min()})
display(pd.DataFrame(rows))''',
'''comparison=pd.read_csv(report/'comparison.csv')
display(comparison.loc[comparison.phase.eq('review'),['name','total_return','max_drawdown','tracking_error','familywise_lower','familywise_upper']])
audit=json.loads((report/'frozen_reference_audit.json').read_text())
display(pd.DataFrame(audit))
display(Image(filename=str(report/'review_comparison.png')))'''
]
nb.cells += [nbformat.v4.new_code_cell(code) for code in cells]
nb.cells.append(nbformat.v4.new_markdown_cell("## 判定\n主方案近期风险较旧方案下降，但没有可信的稳定超额证据。实际持仓约束仍超限，前三版防御方案存在未启动区间，v1r4修复重试状态但仍保留首次失败。技术复核不等于采用批准。未来必须补数据时点、执行门禁和真正新数据的前向观察。"))
NotebookClient(nb, timeout=180, kernel_name="python3", resources={"metadata":{"path":str(ROOT)}}).execute()
nbformat.write(nb, folder/"enhancement_review.ipynb")
from nbconvert import HTMLExporter

body, _ = HTMLExporter().from_notebook_node(nb)
(folder/"enhancement_review.html").write_text(body, encoding="utf-8")
print(json.dumps({"report":str(folder/"report.html"),"executed_cells":len(cells)}, ensure_ascii=False))
