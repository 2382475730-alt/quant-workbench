"""Build bounded reviewed report data and the executed notebook from saved runs."""
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime

import nbformat
import pandas as pd
from nbclient import NotebookClient
from nbconvert import HTMLExporter

from quant_workbench.data import ROOT, write_json

NAMES = {"000001.SZ": "平安银行", "000063.SZ": "中兴通讯", "000333.SZ": "美的集团",
         "600519.SH": "贵州茅台", "600900.SH": "长江电力", "601318.SH": "中国平安"}
LABELS = {"equal_weight": "等权基准", "momentum_252_20": "12个月动量20股",
          "momentum_126_20": "6个月动量20股", "momentum_252_10": "12个月动量10股",
          "momentum_252_30": "12个月动量30股", "buy_hold": "买入持有", "trend_200": "200日趋势",
          "trend_200_risk": "趋势与波动控制", "trend_100": "100日趋势", "trend_250": "250日趋势"}


def read(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def table(rows, columns):
    return "| " + " | ".join(columns) + " |\n|" + "|".join(["---"] * len(columns)) + "|\n" + "\n".join("| " + " | ".join(map(str, row)) + " |" for row in rows)


def pct(value):
    return f"{value:.2%}"


out = ROOT / "reports"
out.mkdir(exist_ok=True)
summaries = {p: read(f"artifacts/research/{p}/summary.json") for p in ["development", "validation", "final_repaired"]}
final = summaries["final_repaired"]
original = read("artifacts/research/final/summary.json")
changes = []
for old, new in zip(original["results"], final["results"]):
    assert old["id"] == new["id"]
    folder = f"artifacts/research/{{phase}}/{old['id']}/nav.parquet"
    a = pd.read_parquet(ROOT / folder.format(phase="final"))
    b = pd.read_parquet(ROOT / folder.format(phase="final_repaired"))
    identical = a.equals(b)
    if not identical:
        changes.append({"id": old["id"], "before_return": old["total_return"], "after_return": new["total_return"],
                        "terminal_equity_change": float(b.equity.iloc[-1] - a.equity.iloc[-1])})
assert [c["id"] for c in changes] == ["portfolio_pool_equal_weight_base"]
write_json("artifacts/research/repair_comparison.json", {"changed_navs": changes, "unchanged_navs": 60,
           "rules_changed": False, "boundary": "Comparisons versus the repaired equal-weight baseline also change. Not a new untouched test."})

all_rows = []
for phase, summary in summaries.items():
    for row in summary["results"]:
        all_rows.append({"phase": phase, **{k: v for k, v in row.items() if isinstance(v, (str, int, float, bool))},
                         "ci_lower": row.get("comparison", {}).get("lower_95"), "ci_upper": row.get("comparison", {}).get("upper_95")})
pd.DataFrame(all_rows).to_csv(out / "all_registered_results.csv", index=False, encoding="utf-8-sig")
rows = final["results"]
portfolio = [r for r in rows if r["category"] == "portfolio" and r["scenario"] == "base"]
stocks = [r for r in rows if r["category"] == "stock" and r["scenario"] == "base" and r["strategy"] in {"buy_hold", "trend_200", "trend_200_risk"}]
quality = read("artifacts/data_quality.json")
outlook = read("artifacts/outlook/portfolio.json")
companies = {code: read(f"artifacts/company/{code}/snapshot.json") for code in NAMES}
portfolio_table = table([[LABELS[r["strategy"]], pct(r["total_return"]), pct(r["cagr"]), pct(r["max_drawdown"]), pct(r["average_exposure"])] for r in portfolio],
                        ["组合方案", "累计收益", "年化收益", "最大回撤", "平均股票仓位"])
stock_table = table([[NAMES[r["symbol"]], LABELS[r["strategy"]], pct(r["cagr"]), pct(r["max_drawdown"])] for r in stocks],
                    ["股票", "持仓规则", "年化收益", "最大回撤"])
stress = [r for r in rows if r["role"] in {"primary", "primary_risk"}]
stress_table = table([[NAMES.get(r["symbol"], "组合"), LABELS[r["strategy"]], r["scenario"], pct(r["cagr"]), pct(r["max_drawdown"])] for r in stress],
                     ["对象", "规则", "成本/延迟情景", "年化收益", "最大回撤"])
case_text = []
for code, company in companies.items():
    review = company["primary_report_review"]
    signal = read(f"artifacts/outlook/{code}.json")
    finance = company["financial"]
    case_text.append(f"### {NAMES[code]}（{code}）\n\n2026半年报：营业收入 {finance['revenue_ytd']/1e8:.2f} 亿元，归母净利润 {finance['parent_profit_ytd']/1e8:.2f} 亿元。" +
                     "\n\n" + "\n\n".join(review["observations"]) +
                     f"\n\n持有条件与需跟踪事项：{review['holding_questions']}。" +
                     f"\n\n截至10月23日，200日趋势为{'开启' if signal['trend_on'] else '关闭'}；波动控制下的**单股研究子账户**权重为 {pct(signal['trend_risk_sleeve_weight'])}。这不是总家庭资产配置比例。" +
                     f"\n\n[原始半年报]({review['source']['url']})；已核对PDF页 {', '.join(map(str, review['pages']))}。")
baseline, primary = portfolio[:2]
report = f"""# A股双主线量化研究：仓位控制有用途，统一选股与择时尚未获得稳健支持

观察截止：2026-10-23。研究本金100万元；结果扣模拟交易成本，股息税前。独立工作台位于当前主项目的 quant_workbench 文件夹。

## 结论与可采取的行动

- **Portfolio：暂不将主动量组合列为可直接实盘采用的方案。** 最终区间累计收益 {pct(primary['total_return'])}，最大回撤 {pct(primary['max_drawdown'])}；同池等权基准分别为 {pct(baseline['total_return'])} 与 {pct(baseline['max_drawdown'])}。验证区间主模型年化约−10.47%，也未显示稳定优势。
- **单股：将波动控制保留为前向研究候选。** 六个案例中，风险版本在最终区间有五个案例的最大回撤小于买入持有，但平安银行是反例；降低回撤不保证增加收益。不能据这些当下选定的六只股票推断全市场有效。
- **先模拟跟踪，再讨论实盘适配。** 本次没有产生“已证明能持续赚钱”的策略。前向观察入口已与历史样本分开，尚无未来业绩；可以保留现金，不强制给出满仓买入名单。

## 1. 本次实际研究范围

沪深300历史月度成分并集667只股票，行情2015年以来至观察日。2015—2016预热；2017—2021开发；2022—2024验证；2025—2026-10-23最终区间。每阶段61项预登记实验，共183项区间结果，覆盖参数敏感性、双倍成本、增加一个交易日执行延迟。完整结果见 all_registered_results.csv；保留失败版本。

股票池使用上一个已结束月份成分快照，缺少成分公告的原始时刻，属于保守历史代理；当前行业标签仅作描述。六只公司为本次事前选定的行业分散案例，但仍带有当下选样偏差。

## 2. Portfolio：选股、配置与执行须分开评价

主模型按252日至21日前的动量排名选择20只股票等权，月度调整；另外预登记6个月动量、10只和30只版本。100万元本金和最小交易单位导致同池等权基准平均仓位只有 {pct(baseline['average_exposure'])}，主动量为 {pct(primary['average_exposure'])}。收益差异不能直接称为alpha；主模型相对基准日收益差的年化均值区间约 [{pct(primary['comparison']['lower_95'])}, {pct(primary['comparison']['upper_95'])}]，且尚未校正多次检验。

{portfolio_table}

当前20股模型目标来自最后一次计划内月末决策2026-09-30，使用10月23日收盘价试算重新投入100万元。实际整手买入后约 {outlook['illustrative_cash_account']['cash_after_estimated_costs']/10000:.2f} 万元留作现金；四只高价股票因最小交易单位无法达到5%目标。这个试算既不是历史回测的期末实际持仓，也不是下一开盘价的可成交承诺。详见当前工作台“持仓与风险情景”。

## 3. 单股：判断持有条件，并量化仓位代价

200日趋势与“趋势+60日波动估计、15%目标年化波动”的规则均与同股买入持有对照。单股规则允许0—100%的研究子账户仓位，不能直接乘到用户全部资产。最终区间结果如下：

{stock_table}

中兴通讯的波动控制明显减轻了最终区间回撤；美的集团和长江电力的趋势退出则存在明显机会成本。平安银行的风险版本累计表现弱于买入持有，其单次比较区间也为负。规则应分别接受公司基本面、估值条件和前向观察检验，不能给六家公司套同一个“最佳持仓比例”。

## 4. 六家公司：财报证据与持有条件

三表共同报告期2026半年报，公告时点严格早于观察日；关键字段已与原始PDF核对。TTM用本期累计+上年全年−上年同期，未知保留未知。银行、保险不套用工业企业自由现金流口径。财报数据库历史修订版本未完整恢复，因此这些财务数据用于当前研究，未被当作严格历史时点的价值质量因子回测。

{chr(10).join(case_text)}

## 5. 风险情景：模型敏感性比一个上涨概率更重要

组合使用739个共同有效日的收益向量，20日联合分块重采样、10000条路径；保留同日资产关系，按固定初始股数与现金模拟。未来60交易日，历史漂移版本5%分位为 {pct(outlook['risk']['horizons']['60']['joint_historical_block_bootstrap']['terminal_p05'])}；去除各资产样本算术均值后变为 {pct(outlook['risk']['horizons']['60']['joint_zero_sample_arithmetic_mean_bootstrap']['terminal_p05'])}；指定股票同步跳跌20%的情景为 {pct(outlook['risk']['horizons']['60']['specified_all_equities_minus20pct_jump']['terminal_p05'])}。这些是给定模型下的情景分位，不是已经校准的未来概率。

单股同时展示零漂移GBM、历史漂移GBM、分块重采样和指定跳跃压力。没有把风险中性定价概率冒充真实上涨概率。示例总账户单股风险预算为“1%可承受损失÷20%假设跳跌=5%上限”，只用于讲清预算关系；更大跳跌仍可突破预算，不是个性化配置或止损保证。

## 6. 核算修订与数据边界

首次最终结果已打开后，审计发现海通证券、中国重工已完成换股但旧账本未转换。已保留原始结果、原冻结输入及事先记录的修订计划，添加源文支持的换股处理，并在策略参数、信号和协议不变的条件下重新核算。**修订结果不是第二次未接触的留出检验。** 仅等权基准净值变化，期末资产较初版减少 {abs(changes[0]['terminal_equity_change']):.2f} 元，其余60条净值序列完全相同；相对基准统计随之更新。

信达证券200股截至观察日仍处待换股阶段，沿用旧报价计价3112元，约占基准期末资产0.29%；不能成交、不能提现，也不能默认值为零。中国重工换股尾数按向下取整处理，实际尾数分配可能相差不足一股目的证券，须保留这一核算精度边界。开发区间仍有康得新陈旧估值180元等退市流动性风险，不能把最后报价当作可卖出价值。

完整数据质量检查：严重问题0、高等级未解决问题5。高等级涉及海南机场/康美重整股东权益比例和北汽历史因子差异；逐一与实际持仓及所有可排名候选窗口匹配，本次登记实验未受这些未解决项影响，不能据此宣称源数据已全部正确。37,783个上市期缺报价日由停牌记录及原始暂停上市公告解释，均未补成可成交价格。

## 7. Shreve I / II 如何落实到代码

- I印刷第9页与II第154页：用现金、股票、应收分红、锁定红股/换股构造财富账本；复权价用于信号，真实原价用于成交与持仓记账。现金守恒与公司行动有独立合成检验。
- I第36页的信息适应性：收盘信号最早下一交易日成交，容量只使用此前成交量。缺失数据不能填成可执行价格，公告日期和报告期分别保存。
- II第144页Itô公式：GBM含−σ²/2修正，并以解析均值和方差核验模拟。第214页P/Q区别：无套利定价不能直接提供现实预期收益；第463页跳跃过程用于组织压力情景，而非伪造跳跃概率。
- 本次重点回查上述章节，没有声称通读两书。两书提供概率、交易和风险核算框架；预期收益信号仍需金融经济学、统计检验与实际数据共同支持。

## 8. 后续完整研究路线

1. **数据阶段：** 扩展严格历史公告时刻、退市与并购权益、财务修订版本、行业历史分类；先建立可投资且可追溯的样本，再扩大到全A股、ETF、宏观及利率。无法获得的字段明确阻断相关策略。
2. **组合阶段：** 在新预登记实验中比较价值、质量、盈利修正、低波、动量、行业中性和风险预算；考察收缩协方差、风险平价、带换手约束的组合优化及整手约束。不得用已经看过的最终区间继续挑赢家。
3. **单股阶段：** 深化产业驱动、财务质量、估值敏感性、公告事件和持有逻辑失效条件；用公司特有风险确定研究仓位，再与组合层面相关性和账户风险预算衔接。
4. **验证阶段：** 新增滚动训练/验证、嵌套选择与多重检验控制，预先登记经济意义阈值；比较相近风险暴露及可投资基准；把真实执行摩擦、税负和容量放入同一账本。
5. **前向阶段：** 使用隔离的模拟账户记录未来决策、未成交与持仓变化。当前入口支持冻结试算持仓的报价观察；还不自动再平衡或处理新增公司行动。先完成这些扩展并积累真正未来证据，再评估实盘适配。

每阶段交付应包含数据审计、全部试验、失败原因、代码输入哈希和明确采用/继续观察/淘汰结论。策略效果不合格时允许空仓或无候选，不以更多复杂模型掩盖验证失败。

## 附录：成本与延迟压力

base为基准成本，double_cost为费用/滑点翻倍，extra_delay为增加一个交易日。交易佣金0.03%最低5元，滑点10bps并按最小价位取整；印花税和过户费分历史日期，现金收益设零，未计投资者差别化股息税。详见 research/methodology.md。

{stress_table}

## 可复算资料

- research/protocol.md：计算业绩前固定的研究规则；不可按最终成绩重写。
- artifacts/research/final_repaired：修订后全部日净值、持仓、成交、事件、统计及质量审计。
- artifacts/research/final 与 artifacts/research_initial_frozen：首次最终结果和封存输入。
- artifacts/company：六家公司财务、原始报告来源和核对结果。
- artifacts/action_source_receipts.json：公司行动来源及内容哈希。
- reports/research_review.ipynb：保存执行输出的复核笔记；reports/all_registered_results.csv：183项结果。

研究输出不连接券商账户。软件测试通过、财报字段一致或某段回测盈利，均不等于实盘策略获证。
"""
(out / "量化研究报告.md").write_text(report, encoding="utf-8")

# Bounded, actual evidence for the independent report reader.
def query(rows, files, component_ids, definitions):
    return {"rows": rows, "source": {"label": "本地预登记A股研究结果", "files": files,
            "filters": ["观察截止2026-10-23；最终区间经过查看后的公司行动核算修订"],
            "evidenceFlow": [{"title": "可复算本地证据", "detail": "scripts/build_deliverables.py读取已保存研究输出；源文件SHA256见reports/input_manifest.json；未重新选择策略参数。"}],
            "metricDefinitions": [{"label": label, "definition": definition, "componentIds": component_ids,
                                   "sourceLineage": [{"files": files}]} for label, definition in definitions]},
            "methods": [{"language": "text", "code": "读取所列JSON或Parquet；仅保留本组件需要的规则和字段，收益与回撤小数乘100转为百分数。完整选择逻辑在scripts/build_deliverables.py。"}]}

queries = {}
queries["portfolio"] = query([{"strategy": LABELS[r["strategy"]], "totalReturn": r["total_return"]*100, "cagr": r["cagr"]*100,
                                "drawdown": r["max_drawdown"]*100, "exposure": r["average_exposure"]*100} for r in portfolio],
                               ["artifacts/research/final_repaired/summary.json"], ["portfolio-results", "executive-summary", "portfolio-reading"],
                               [("年化收益与回撤（%）", "CAGR按252交易日年化；回撤相对含初始本金的历史高点。扣模拟交易费，股息税前。")])
queries["stocks"] = query([{"stock": NAMES[r["symbol"]], "strategy": LABELS[r["strategy"]], "cagr": r["cagr"]*100, "drawdown": r["max_drawdown"]*100} for r in stocks],
                            ["artifacts/research/final_repaired/summary.json"], ["stock-results", "stock-reading", "executive-summary"],
                            [("单股表现", "六个事前选定案例各有三项主对照；每个案例使用独立100万元研究子账户，不是六股组合权重。")])
navs = {}
for r in portfolio[:2]:
    navs[LABELS[r["strategy"]]] = pd.read_parquet(ROOT / f"artifacts/research/final_repaired/{r['id']}/nav.parquet").equity / final["initial_cash"]
nav = pd.DataFrame(navs)
nav.index.name = "date"
nav = nav.reset_index()
nav["date"] = nav.date.dt.strftime("%Y-%m-%d")
queries["nav"] = query(nav.to_dict("records"), [f"artifacts/research/final_repaired/{r['id']}/nav.parquet" for r in portfolio[:2]], ["portfolio-nav"],
                       [("净值", "交易日收盘总资产除以初始100万元，含现金、股票及应收权益；不对缺失交易报价插值。")])
risk_labels = {"joint_historical_block_bootstrap": "历史漂移", "joint_zero_sample_arithmetic_mean_bootstrap": "移除样本均值", "specified_all_equities_minus20pct_jump": "指定股票跳跌20%"}
queries["risk"] = query([{"model": risk_labels[k], "p05": v["terminal_p05"]*100, "median": v["terminal_median"]*100, "tailMean": v["mean_worst_5pct_return"]*100} for k, v in outlook["risk"]["horizons"]["60"].items()],
                         ["artifacts/outlook/portfolio.json"], ["risk-scenarios", "risk-reading"], [("60交易日条件情景（%）", "10000条路径、20日联合分块；5%分位与最差5%均值依赖模型，非经校准的现实概率。")])
queries["company"] = query([{"stock": NAMES[code], "revenue": c["financial"]["revenue_ytd"]/1e8, "profit": c["financial"]["parent_profit_ytd"]/1e8,
                             "condition": c["primary_report_review"]["holding_questions"]} for code, c in companies.items()],
                            [f"artifacts/company/{code}/snapshot.json" for code in NAMES], ["company-evidence"], [("2026半年报（亿元）", "营业收入与归母净利润，原始报告单位已转换。银行保险现金流不套用工业公司口径。")])
queries["audit"] = query([{"severity": k, "count": v} for k,v in Counter(i["severity"] for i in quality["issues"]).items()],
                          ["artifacts/data_quality.json"], ["audit-reading"], [("数据问题", "问题条目数，不是受影响策略数；5项高等级未解决问题未跨越本次策略持仓或候选信号窗口。")])
snapshot = {"surface": "report", "title": "A股量化：先验证持仓风险，再判断策略优势", "generatedAt": datetime.now(UTC).isoformat(),
            "status": "reviewed", "filters": [], "queries": queries}
write_json("reports/reviewed_data.json", snapshot)
paths = {p for q in queries.values() for p in q["source"]["files"]}
write_json("reports/input_manifest.json", {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sorted(paths)})

cells = []
def md(s):
    cells.append(nbformat.v4.new_markdown_cell(s))
def code(s):
    cells.append(nbformat.v4.new_code_cell(s))

md("# A股双主线量化复核\n\n## tl;dr\n\n组合动量最终累计约5.05%、最大回撤35.54%，不足以支持直接采用。单股波动控制在六个案例中五个降低最终回撤，但有机会成本和失败案例。最终数据包含查看结果后的换股核算修订；原始结果保留。")
md("## Context & Methods\n\n数据截止2026-10-23。开发2017—2021、验证2022—2024、最终2025年至截止日。此笔记复核已保存结果，不访问API、不重开最终检验。\n\n### Key Assumptions\n\n100万元、日线次日成交、费用后股息税前；历史成分为月度代理；六股为案例选样；未校正多重检验。源文件及SHA256见input_manifest.json。")
code("from pathlib import Path\nimport json, hashlib\nimport numpy as np\nimport pandas as pd\nimport matplotlib.pyplot as plt\nfrom IPython.display import display\nROOT = Path.cwd().parent if Path.cwd().name == 'reports' else Path.cwd()\nassert (ROOT / 'config/experiments.json').exists()\nplt.rcParams.update({'font.sans-serif':['Microsoft YaHei'], 'axes.unicode_minus':False, 'figure.figsize':(10,4.5), 'font.size':11})\nmanifest = json.loads((ROOT/'reports/input_manifest.json').read_text(encoding='utf-8'))\nassert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in manifest.items())\nprint(f'已核验 {len(manifest)} 个报告输入文件哈希')")
md("## Data\n\n### 1. 查看数据质量与实际覆盖\n\n缺失不是零。5项未解决高等级问题保留在审计中，并检查其是否影响已登记实验。")
code("quality=json.loads((ROOT/'artifacts/data_quality.json').read_text(encoding='utf-8'))\ndisplay(pd.Series([i['severity'] for i in quality['issues']]).value_counts().rename('问题条目数').to_frame())\nprint('股票数',quality['symbols'],'停牌检查',quality['suspensions'])\nsummary=json.loads((ROOT/'artifacts/research/final_repaired/summary.json').read_text(encoding='utf-8'))\nassert summary['complete'] and len(summary['results'])==61\nassert not any(r['holding_quality']['unresolved_events_held'] or r['signal_quality']['unresolved_candidate_windows'] for r in summary['results'])")
md("## Results\n\n### 2. 组合净值与风险暴露\n\n比较同池等权与主模型；基准平均股票暴露较低，不能将全部差异视作选股能力。")
code("data=json.loads((ROOT/'reports/reviewed_data.json').read_text(encoding='utf-8'))['queries']\nnav=pd.DataFrame(data['nav']['rows']).set_index('date')\nnav.index=pd.to_datetime(nav.index)\nax=nav.plot(color=['#967343','#186e9b'],linewidth=1.4)\nax.set(title='2025—2026-10-23：累计净值',ylabel='净值（初始=1）',xlabel='交易日')\nax.grid(axis='y',alpha=.2)\nplt.tight_layout();plt.show()\ndisplay(pd.DataFrame(data['portfolio']['rows']).round(2))")
md("### 3. 单股仓位规则的回撤与收益代价\n\n两张互补图分别比较年化收益与最大回撤；没有只保留效果最好的股票。")
code("stocks=pd.DataFrame(data['stocks']['rows'])\nfig,axes=plt.subplots(2,1,figsize=(11,9))\nfor ax,field,title in zip(axes,['cagr','drawdown'],['年化收益（%）','最大回撤（%）']):\n    stocks.pivot(index='stock',columns='strategy',values=field).plot.bar(ax=ax,color=['#967343','#186e9b','#248677'],rot=0)\n    ax.set(title=title,xlabel='',ylabel='%');ax.axhline(0,color='#667',lw=.7);ax.grid(axis='y',alpha=.15)\nplt.suptitle('六个单股案例：2025—2026-10-23');plt.tight_layout();plt.show()")
md("### 4. 情景分位对漂移假设敏感\n\n历史上涨趋势被机械延续会造成乐观结果，因此并列展示移除样本均值与指定跳跃情景。")
code("risk=pd.DataFrame(data['risk']['rows']).set_index('model')\ndisplay(risk.round(2))\nax=risk[['p05','median']].rename(columns={'p05':'5%分位','median':'中位数'}).plot.barh(color=['#b75b4c','#248677'])\nax.set(title='未来60交易日条件情景',xlabel='总资产收益（%）',ylabel='')\nax.axvline(0,color='#667',lw=.7);plt.tight_layout();plt.show()")
md("### 5. 原始与修订账本保持可核对\n\n只修订公司行动核算，策略参数、信号和协议不变。相对基准统计可随基准变化。")
code("repair=json.loads((ROOT/'artifacts/research/repair_comparison.json').read_text(encoding='utf-8'))\ndisplay(pd.DataFrame(repair['changed_navs']))\nprint('净值序列完全未变的实验：',repair['unchanged_navs'])\nresults=pd.read_csv(ROOT/'reports/all_registered_results.csv')\nassert len(results)==183\nprint('预登记区间结果数：',len(results),'；不把核算修订另算独立试验')")
md("## Takeaways\n\n- 组合动量继续研究，暂不直接采用。\n- 单股风险控制有作用，但须接受基本面条件、反例和机会成本约束。\n- 下一步需要严格历史时点数据与真正前向证据，不能反复用已看过的最终区间调参。\n- 详细六公司分析、总体路线、源文与成本压力见同目录《量化研究报告.md》。")
notebook = nbformat.v4.new_notebook(cells=cells, metadata={"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}})
NotebookClient(notebook, timeout=120, kernel_name="python3", resources={"metadata": {"path": str(out)}}).execute()
nbformat.validate(notebook)
nbformat.write(notebook, out / "research_review.ipynb")
html, _ = HTMLExporter().from_notebook_node(notebook)
(out / "research_review.html").write_text(html, encoding="utf-8")
print("Report, reviewed snapshot, 183-result CSV and executed notebook created.")
