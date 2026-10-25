"""Document existing holding rules and snapshots; never rerun or retune them."""
import json

import pandas as pd
from quant_workbench.holding_view import export_snapshot, load_ledger, snapshot

from quant_workbench.data import ROOT


def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def table(headers, rows):
    return "| " + " | ".join(headers) + " |\n|" + "|".join(["---"]*len(headers)) + "|\n" + "\n".join("| " + " | ".join(map(str, r)) + " |" for r in rows)


phase = "final_repaired"
summary = read(f"artifacts/research/{phase}/summary.json")
basics = pd.read_parquet(ROOT / "data/normalized/stock_basic.parquet")
names = dict(zip(basics.ts_code, basics.name))
codes = read("config/experiments.json")["single_stock_examples"]
current, results, cases = [], [], []
for code in codes:
    signal = read(f"artifacts/outlook/{code}.json")
    ledger = load_ledger(phase, f"stock_{code}_trend_200_risk_base")
    v = snapshot(ledger, ledger["nav"].index[-1], names)
    current.append([names[code], "开启" if signal["trend_on"] else "关闭", f"{signal['estimated_volatility_60d']:.2%}",
                    f"{signal['trend_risk_sleeve_weight']:.2%}", f"{v['stock_weight']:.2%}", v['decision_date']])
    selected = {r["strategy"]: r for r in summary["results"] if r['symbol'] == code and r['scenario'] == 'base'}
    results.append([names[code]] + [f"{selected[s]['cagr']:.2%} / {selected[s]['max_drawdown']:.2%}" for s in ['buy_hold','trend_200','trend_200_risk']])
    company = read(f"artifacts/company/{code}/snapshot.json")
    cases.append(f"- **{names[code]}**：{company['primary_report_review']['holding_questions']}。")

guide = """# 单股持仓方案：完整说明

本说明解释当前已经运行的模型，不新增或调整策略。数据截止2026-10-23；六只股票分别运行独立研究子账户，不是六股组合。用户真实持仓、资金规模和风险承受能力尚未接入。

## 1. 方案到底回答什么

针对已经选定的一只股票，研究什么时候持有、股票与现金如何分配、多久调整，以及这种规则在历史上付出了多少收益和回撤代价。公司财务与估值研究帮助判断持有逻辑；当前代码的实际交易信号只用价格和波动率。财务和估值条件尚未自动进入买卖规则。

## 2. 三个对照方案

| 方案 | 股票目标权重 | 决策频率 | 现金与分红 |
|---|---|---|---|
| 买入持有 | 初始目标100% | 初始买入一次 | 分红进入现金，不自动再投资或定期补满仓 |
| 200日趋势 | 价格高于200日均线时100%，否则0% | 每个有报价的交易日收盘检查；只有状态改变才产生新目标 | 趋势持续开启时不每天补满仓，现金分红可使实际权重低于100% |
| 趋势＋波动控制 | 趋势开启时min(100%, 15%÷60日年化波动)，否则0% | 周度检查，目标变化才产生新指令 | 调整时重新分配股票与现金，禁止杠杆、禁止卖空 |

100/250日均线是预登记敏感性版本，不能在看到最终收益后挑出最好的参数当作原方案。

## 3. 趋势与仓位的计算

以复权收盘价P_t计算200日简单移动平均：MA200_t=(最近200个交易日价格之和)/200。

趋势开关I_t=1当且仅当P_t>MA200_t；等于或低于均线时为0。没有足够200日预热数据时不开仓。

以最近60个日简单收益r_t=P_t/P_(t−1)−1的样本标准差（ddof=1）估计年化波动：σ_t=std(r,60)×√252。

风险版本目标：w_t=I_t×min(1,0.15/σ_t)。估计缺失或近乎为零时置0，避免无限仓位。其余1−w_t留现金，研究中现金收益设为0。

例如趋势开启、估计波动30%，子账户股票目标50%；波动20%时目标75%；波动10%时最多100%。15%是仓位缩放参数，不是保证未来实际波动15%，更不是最大亏损或最大回撤上限。

停牌日价格在信号计算中使用沿用值，可能压低波动估计；执行引擎仍要求真实可交易报价，不能因为填充了信号价格就认为可以买卖。新的长停牌案例必须单独审计。

## 4. 什么时候执行、什么时候退出

所有信号在收盘后产生，最早下一交易日开盘尝试成交。纯趋势在每日检查后才可能退出；风险版本按周检查，周中跌破均线也不触发该模型的即时卖出。因此风险版本同时改变了仓位和检查频率，成绩差异不能全部归因于仓位缩放。

周度日期是数据中可识别的该周最后一个交易日：一般为周五，节假日可能提前。当前数据截止10月23日，回测没有将缺少下一交易日的末尾周额外补成可执行订单；outlook中的10月23日权重是独立收盘试算。最近已登记目标日期可能更早：目标一直为0时不会每周重复保存相同指令。

本模型没有单独的5%/10%固定止损、移动止盈、盘中止损或分批抄底规则。趋势退出是收盘条件，不保证特定价格成交；跳空、跌停、停牌仍可能造成更大损失。风险版本也不因价格上涨到某个估值自动卖出。

## 5. 目标如何变成股数

执行时按当时账户总资产×目标权重确定目标市值，再按未复权开盘价估算目标股数。普通A股买入按100股取整，科创板按最低200股、之后逐股增加处理；交易费用、滑点、现金余额、此前成交量容量会继续限制实际成交。卖出在模拟买入之前处理，不允许借钱补足仓位；当日新增买入不会作为当日可卖持仓。

开盘触及对应方向涨跌停、报价或限制价格缺失时保守拒单；订单有效期5个交易日，后续新指令可替换旧指令。未成交不等于已调仓；订单过期后也不会凭空补齐持仓。

费用假设：佣金0.03%、最低5元；单边10bps滑点按最小价格单位取整；印花税与过户费按历史日期分段。股息按税前计入；分红应收、实际到账和股票上市可卖日期分开处理。回测实际权重会受整手、费用、价格漂移和公司行动影响。

## 6. 子账户仓位不是总资产仓位

若总资金100万元，只给某只股票的研究子账户10万元，模型目标50%，则股票目标约5万元，占全部资金5%，之后还须扣费与取整。不能把界面91%的子账户权重理解为全部家庭资产91%买入这只股票。

工作台另有教学示例：若只愿让一个指定的20%单股跳跌造成总账户1%损失，名义股票上限是1%÷20%=5%，再乘该股模型权重。20%跳跌只是指定情景，真实跌幅、流动性冲击或多股同步下跌可能更大；这个5%不是已验证或个性化的配置比例。多只股票的独立子账户结果不能相加当作已经测试的投资组合。

## 7. 当前读数与实际账本

下表均截至2026-10-23。最新目标来自该日收盘试算；账本实际仓位来自最终修订区间的真实模拟账本，二者不是同一个字段。最新目标不是下一开盘已成交仓位。

__CURRENT__

美的、茅台、长江电力的最新试算与实际仓位差别明显，应同时查看目标时点和整手约束。0%仅表示该规则的价格趋势关闭，不等于公司没有投资价值。

## 8. 已经得到的历史结果

最终区间2025-01-01至2026-10-23，表内为“年化收益 / 最大回撤”。买入持有和规则均扣模拟交易成本、股息税前。采用252交易日年化，并非日历年年化。

__RESULTS__

风险版本在六股中五股降低了相对买入持有的最大回撤，但平安银行更差；美的、茅台和长江电力存在收益机会成本。中兴的结果还同时受周度检查与仓位缩放影响。不能据此认定“所有股票加波动控制都更好”。六股是当下选定案例，未做全部策略尝试的多重检验校正；最终区间有查看后核算修订，不能作为新的未接触检验。本次两项换股修订未改变这些单股净值。

## 9. 财务与估值如何参与判断

这些是需要继续验证的持有逻辑，当前没有在代码中变成自动开平仓阈值：

__CASES__

财务模型使用可用公告时点和原始报告核对；历史修订版本尚未完整恢复，因此不能宣称已经完成无前视的财务选时回测。市盈率/市净率低于自身历史分位也不自动等于低估。

## 10. 在工作台里怎么用

1. 在“单股研究”选择股票和研究区间，先看买入持有、纯趋势、风险版本的收益与回撤对照。
2. 在下方先看所选区间的实际股数、股票权重和现金，再看注明2026-10-23日期的最新收盘试算，避免混淆历史账本与最新信号。
3. 用“完整持仓规则”打开本说明；用“原始半年报”核查财务依据。
4. “新资金与风险”展示条件情景。GBM和历史重采样的分位数依赖假设，不是已经校准的真实未来概率，也不是自动止损价。

目前单股方案属于研究与前向观察候选，没有接入真实券商持仓。通用paper入口当前只支持组合冻结试算持仓的报价观察，不是已经为六只股票各自运行的自动模拟交易系统。进一步使用前，应预先固定账户资金、单股上限、检查周期和事件处理规则，并积累新的前向证据。

实现依据：src/quant_workbench/signals.py、research.py、engine.py；实际结果与信号来源：artifacts/research/final_repaired、artifacts/outlook。此次界面改进只读取这些封存结果，没有重跑或修改策略。
"""
guide = guide.replace("__CURRENT__", table(["股票", "趋势", "60日波动", "最新试算目标", "账本实际权重", "最近登记目标"], current))
guide = guide.replace("__RESULTS__", table(["股票", "买入持有", "200日趋势", "趋势＋波动控制"], results)).replace("__CASES__", "\n".join(cases))
(ROOT / "research/single_stock_holding_guide.md").write_text(guide, encoding="utf-8")

ledger = load_ledger(phase, "portfolio_pool_momentum_252_20_base")
v = snapshot(ledger, ledger["nav"].index[-1], names)
folder = export_snapshot(v, phase, "portfolio_pool_momentum_252_20_base")
portfolio = f"""# Portfolio实际持仓方案读法

新增“组合持仓”页默认直接展示回测实际期末账本，可切换五个组合方案与历史日期；“组合研究”的策略选择与本页联动。表中包括未实际买到的目标股，以及已不在目标中但尚未卖出的持仓。金额满足：股票市值＋现金＋应收权益＝总资产。

主模型截至{v['asof']}：总资产{v['equity']:,.2f}元；股票市值{v['market_value']:,.2f}元，占{v['stock_weight']:.2%}；现金{v['cash']:,.2f}元，占{v['cash_weight']:.2%}；应收权益{v['receivable']:,.2f}元。实际持有{v['held_count']}只，最近目标{v['target_count']}只，目标决策日{v['decision_date']}。

这是真实运行的模拟账本，并非券商账户；也不同于“新资金与风险”中拿100万元按最新价格重新建仓的试算。最近目标为月末决策，并非每天都重新排名；权重偏离不是立即调仓清单。

""" + table(["股票", "代码", "实际股数", "市值（元）", "实际权重", "最近目标"],
                 [[r['name'],r['code'],r['shares'],f"{r['market_value']:,.2f}",f"{r['actual_weight']:.2%}",f"{r['target_weight']:.2%}"] for r in v['rows']])
portfolio += f"\n\n本页同时展示最近成交与执行事件，并可导出完整持仓、账户、成交及事件CSV/JSON。默认主模型持仓导出目录：{folder.relative_to(ROOT)}。未持有不等于缺失数据，也不应把其5%目标误读为已经持有。\n\n策略仍未通过稳定采用检验，展示持仓是为了核对真实执行与风险，不将研究结果自动升级为买入建议。\n"
(ROOT / "research/portfolio_holdings_guide.md").write_text(portfolio, encoding="utf-8")
print("Holding guides and default ledger export written; frozen research unchanged.")
