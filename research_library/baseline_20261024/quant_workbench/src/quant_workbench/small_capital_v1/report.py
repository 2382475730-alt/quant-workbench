"""Derived evidence tables and readable report; never changes frozen runs."""
from __future__ import annotations

import html
import json

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from ..data import ROOT
from ..enhancement_data import benchmark_weights
from ..metrics import returns_from_nav
from .agent import example_task, plan
from .data import BASE, dump, load
from .runner import PHASES, STRATEGIES, registry, verify

OUT = ROOT / "reports/small_capital_v1"
LABELS = {"single": "单只300ETF持有", "fixed": "固定ETF组合", "risk": "A 风险预算ETF", "band": "C 不交易区间", "legacy": "旧v1r4缩小重跑"}
PHASE_LABELS = {"development": "2017—2021", "validation": "2022—2024", "review": "2025—2026-10-23"}


def pct(x):
    return "未知" if x is None else f"{x:.2%}"


def md_table(headers, rows):
    return "| " + " | ".join(headers) + " |\n|" + "|".join(["---"]*len(headers)) + "|\n" + "\n".join("| "+" | ".join(str(x) for x in row)+" |" for row in rows)


def read_run(row, name):
    return pd.read_parquet(BASE / "runs" / row["id"] / f"{name}.parquet")


def unit_audit():
    date = pd.Timestamp("2026-10-23")
    members, stamp = benchmark_weights(pd.read_parquet(ROOT / "data/normalized/membership.parquet"), date)
    prices = pd.read_parquet(ROOT / "data/panels/close.parquet").loc[date]
    names = pd.read_parquet(ROOT / "data/normalized/stock_basic.parquet").drop_duplicates("ts_code").set_index("ts_code").name
    rows = []
    for c in members.index:
        p = prices.get(c)
        unit = 200 if c.startswith("688") else 100
        special = c.startswith(("688", "300", "301", "8", "4", "92"))
        if pd.isna(p):
            continue
        rows.append({"code": c, "name": names.get(c, c), "price": float(p), "minimum_unit": unit,
                     "minimum_notional": float(p*unit), "ordinary_permission_assumed": not special,
                     "exceeds_3pct_100k": bool(p*unit > 3000), "exceeds_5pct_100k": bool(p*unit > 5000),
                     "cannot_buy_one_lot_100k": bool(p*unit+5 > 100000)})
    frame = pd.DataFrame(rows)
    frame.to_csv(OUT / "direct_stock_unit_audit.csv", index=False, encoding="utf-8-sig")
    ordinary = frame.loc[frame.ordinary_permission_assumed]
    summary = {"date": str(date.date()), "membership_snapshot": stamp, "quoted_members": len(frame), "ordinary_members": len(ordinary),
               "special_permission_members": int((~frame.ordinary_permission_assumed).sum()),
               "ordinary_over_3pct": int(ordinary.exceeds_3pct_100k.sum()), "ordinary_over_5pct": int(ordinary.exceeds_5pct_100k.sum()),
               "unaffordable_account": frame.loc[frame.cannot_buy_one_lot_100k].to_dict("records"),
               "most_expensive": ordinary.nlargest(10, "minimum_notional").to_dict("records"),
               "missing_quotes": len(members)-len(frame), "not_an_eligibility_screen": "No ST/fundamental/event clearance; only lot and permission arithmetic"}
    dump(BASE / "unit_audit.json", summary)
    return summary


def uncertainty(rows):
    outputs = []
    for phase in PHASES:
        baseline = next(r for r in rows if r["phase"] == phase and r["strategy"] == "fixed")
        bn = read_run(baseline, "nav")
        for strategy in ["risk", "band"]:
            row = next(r for r in rows if r["phase"] == phase and r["strategy"] == strategy)
            nav = read_run(row, "nav")
            difference = (returns_from_nav(nav, 100000)-returns_from_nav(bn, 100000)).to_numpy()
            rng = np.random.default_rng(20261024)
            starts = rng.integers(0, len(difference)-20+1, (4000, (len(difference)+19)//20))
            indices = (starts[:, :, None]+np.arange(20)).reshape(4000, -1)[:, :len(difference)]
            means = difference[indices].mean(axis=1)*252
            lo, hi = np.quantile(means, [.05/12, 1-.05/12])
            outputs.append({"phase": phase, "strategy": strategy, "annual_arithmetic_excess": float(difference.mean()*252),
                            "familywise_lower": float(lo), "familywise_upper": float(hi), "block": 20, "samples": 4000,
                            "scope": "6 predeclared A/C versus fixed comparisons; not correction for prior research selection"})
    dump(BASE / "uncertainty.json", outputs)
    return outputs


def build():
    verification = verify()
    OUT.mkdir(exist_ok=True, parents=True)
    rows = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((BASE / "runs").glob("*/result.json"))]
    main = [r for r in rows if r["scenario"] == "base" and r["initial"] == 100000 and r["annual_fee"] == 0 and r["monthly_contribution"] == 0]
    def pick(strategy, phase="review", fee=0):
        return next(r for r in rows if r["strategy"] == strategy and r["phase"] == phase and r["scenario"] == "base" and r["initial"] == 100000 and r["annual_fee"] == fee and r["monthly_contribution"] == 0)
    flat = [{k: v for k, v in r.items() if not isinstance(v, (dict, list))} for r in rows]
    for row, raw in zip(flat, rows):
        nav, trades = read_run(raw, "nav"), read_run(raw, "trades")
        row["annual_two_way_turnover_actual_wealth"] = float(trades.notional.sum()/nav.equity.mean()/(len(nav)/252))
    pd.DataFrame(flat).to_csv(OUT / "all_experiments.csv", index=False, encoding="utf-8-sig")
    registered = []
    for spec in registry()["runs"]:
        folder = BASE / "runs" / spec["id"]
        registered.append(spec | {"status": "complete" if (folder / "manifest.json").exists() else "failed" if (folder / "failure.json").exists() else "not_run"})
    pd.DataFrame(registered).to_csv(OUT / "experiment_registry.csv", index=False, encoding="utf-8-sig")
    annual = [dict(id=r["id"], strategy=r["strategy"], phase=r["phase"], **year) for r in main for year in r["annual"]]
    pd.DataFrame(annual).to_csv(OUT / "annual_results.csv", index=False, encoding="utf-8-sig")
    interval = uncertainty(main)
    units = unit_audit()
    market = load()
    example = plan(example_task(), market)
    dump(BASE / "example_plan.json", example)
    pd.DataFrame(example["rows"]).to_csv(OUT / "example_holdings_100k.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(example["lookthrough"]["industries"]).to_csv(OUT / "current_industry_proxy.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(example["lookthrough"]["companies"]).to_csv(OUT / "current_company_proxy.csv", index=False, encoding="utf-8-sig")
    # Explain actual historical drift independently of target success.
    daily_audits = []
    for r in main:
        if r["strategy"] not in {"risk", "band"}:
            continue
        nav = read_run(r, "nav")
        daily_audits.append({"phase": r["phase"], "strategy": r["strategy"], "days": len(nav),
                             "buffer_breach_days": int(nav.risk_breach.sum()), "raw_18pct_breach_days": int(nav.predicted_vol.gt(.18).sum()),
                             "max_estimated_raw_vol": float(nav.predicted_vol.max()), "exposure_95pct_breach_days": int(nav.exposure_breach.sum())})
    dump(BASE / "risk_drift.json", daily_audits)
    fee_rows = []
    for phase in PHASES:
        free_single, free_fixed = pick("single", phase), pick("fixed", phase)
        for s in STRATEGIES:
            for fee in [0, 300, 600, 1200]:
                r = pick(s, phase, fee)
                fee_rows.append({"phase": phase, "strategy": s, "annual_fee": fee, "net_return": r["total_return"],
                                 "net_cagr": r["cagr"], "total_service_fee": r["service_fees"], "unpaid": r["service_unpaid"],
                                 "excess_vs_free_single_pp": r["total_return"]-free_single["total_return"],
                                 "excess_vs_free_fixed_pp": r["total_return"]-free_fixed["total_return"],
                                 "ending_wealth": r["ending_equity"]})
    pd.DataFrame(fee_rows).to_csv(OUT / "client_value_fees.csv", index=False, encoding="utf-8-sig")
    # Descriptive matching to separate exposure reduction from active selection.
    attribution = []
    for phase in PHASES:
        f = pick("fixed", phase)
        fn = read_run(f, "nav")
        fr = returns_from_nav(fn, 100000)
        for s in ["risk", "band"]:
            r = pick(s, phase)
            nav = read_run(r, "nav")
            exposure_ratio = r["average_exposure"]/f["average_exposure"]
            scaled = (1+fr*exposure_ratio).cumprod()*100000
            attribution.append({"phase": phase, "strategy": s, "expost_exposure_ratio": exposure_ratio,
                                "scaled_fixed_return": float(scaled.iloc[-1]/100000-1), "actual_return": r["total_return"],
                                "not_tradable_benchmark": "uses ex-post mean exposure; explanation only, never alpha evidence"})
    dump(BASE / "exposure_attribution.json", attribution)
    plt.rcParams.update({"font.sans-serif": ["Microsoft YaHei"], "axes.unicode_minus": False, "font.size": 10})
    colors = {"single": "#506477", "fixed": "#b1782a", "risk": "#338ca1", "band": "#193e68", "legacy": "#b94f5c"}
    fig, axes = plt.subplots(3, 1, figsize=(11, 10), constrained_layout=True)
    for ax, phase in zip(axes, PHASES):
        for s, label in LABELS.items():
            r = pick(s, phase)
            nav = read_run(r, "nav")
            ax.plot(nav.index, nav.equity/100000, label=label, color=colors[s], linewidth=1.7 if s == "band" else 1)
        ax.set_title(PHASE_LABELS[phase]+" · 独立10万元启动 / 扣交易成本未扣服务费", loc="left")
        ax.grid(alpha=.2)
        ax.set_ylabel("净值")
    axes[0].legend(ncol=3, frameon=False)
    fig.savefig(OUT / "historical_comparison.png", dpi=150)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(10, 4), constrained_layout=True)
    for s in ["single", "fixed", "band"]:
        values = [pick(s, "review", fee)["total_return"]*100 for fee in [0, 300, 600, 1200]]
        ax.plot([0, 300, 600, 1200], values, marker="o", color=colors[s], label=LABELS[s])
    ax.axhline(pick("single")["total_return"]*100, color=colors["single"], linestyle="--", label="免费单只ETF对照")
    ax.set(xlabel="假设年费（元；非定价建议）", ylabel="区间客户净收益（%）", title="2025—2026-10-23：服务费来自账户现金")
    ax.grid(alpha=.2)
    ax.legend(frameon=False)
    fig.savefig(OUT / "service_fee_value.png", dpi=150)
    plt.close(fig)
    current = pick("band")
    single = pick("single")
    fixed = pick("fixed")
    risk = pick("risk")
    report = ["# 10万元小资金组合：执行更简单，尚未证明值得收费\n",
              "研究日2026-10-24；行情截至2026-10-23。small_capital_v1，原生桌面研究入口。历史全部已见，151项预登记实验全部保留；当前为研究原型，前向数据0天，未连接券商或客户。\n",
              "## 先回答产品问题\n",
              f"10万元更适合先以1—2只宽基ETF获得权益暴露，并保留由风险预算、交易单位和费用决定的现金，而不是照搬几十只直接持股。本轮主执行方案C在近期区间净收益{pct(current['total_return'])}，单只300ETF为{pct(single['total_return'])}，固定ETF组合为{pct(fixed['total_return'])}。C最大回撤{pct(current['max_drawdown'])}，单只ETF为{pct(single['max_drawdown'])}；C平均权益仓位{pct(current['average_exposure'])}，风险降低主要伴随降低市场暴露，不是已证实的选股优势。\n",
              f"C相对同风险模型A把近期成交笔数从{risk['trade_count']}降至{current['trade_count']}，佣金从{risk['fees']:.2f}元降至{current['fees']:.2f}元；累计收益差仅{(current['total_return']-risk['total_return'])*100:.3f}个百分点。该执行改善可核验，但节省金额不能自动支持300—1200元年费，更不能推断客户付费意愿。\n",
              "## 固定方法与小账户经济含义\n",
              "A：沪深300/中证500内部70/30，最高95%权益，252日协方差、10%对角收缩；以18%年化预测波动预算及1.25估计误差系数决定权益仓位。C沿用A，在5个百分点偏离容忍区间内不交易；普通最小订单2000元、月度单边换手25%，实际风险降仓优先于换手和最小金额。预算是研究假设，须另行做适当性判断。\n",
              "整数优化直接枚举合法100份组合，逐一核对费用预留、现金、风险和换手。目标权重不是实际成交；收盘目标最早下一交易日开盘执行。停牌/触限/容量/现金可阻止成交。首次实际持仓出现后永久关闭建仓换手豁免，清仓不能重获。比较基准为单只ETF买入持有、固定66.5%/28.5%ETF组合、沪深300全收益指数和旧v1r4的10万元重跑。\n",
              f"当前滞后300成分名单中有报价{units['quoted_members']}只，按普通权限假设纳入交易单位审计{units['ordinary_members']}只；其中{units['ordinary_over_3pct']}只一手超过旧3%预算，{units['ordinary_over_5pct']}只超过B假设5%预算。特殊权限{units['special_permission_members']}只单列。这里只是单位审计，不代表已完成ST、事件或基本面筛选。\n",
              md_table(["证券", "参考价格", "最小买入数量", "一手金额", "占10万元"], [[x['code']+' '+x['name'], f"{x['price']:.2f}", x['minimum_unit'], f"{x['minimum_notional']:.0f}", pct(x['minimum_notional']/100000)] for x in units['most_expensive'][:6]]),
              "\n最低5元佣金使1000/2000/3000/10000元订单单边佣金分别为0.50%/0.25%/0.167%/0.05%，尚未加10bp滑点；万3与5元最低佣金的交点约16667元。小账户并非买得越细越分散：过多证券会同时增加闲置现金、最低佣金和操作次数。B设想最多3只、每只5%、直接持股总计15%，余下ETF与现金；本轮未实现B策略和收益检验，不能宣称已排除其所有价值。高价个股可用宽基ETF获得部分市场暴露，但不能复制其特定公司收益。\n",
              "## 全部主比较\n",
              md_table(["区间", "方案", "净收益", "年化", "最大回撤", "波动", "平均权益", "成交", "佣金及税费", "滑点"], [[PHASE_LABELS[r['phase']], LABELS[r['strategy']], pct(r['total_return']), pct(r['cagr']), pct(r['max_drawdown']), pct(r['volatility']), pct(r['average_exposure']), r['trade_count'], f"{r['fees']:.2f}", f"{r['slippage']:.2f}"] for r in main]),
              "\n![历史净值](historical_comparison.png)\n",
              "所有区间同日期、同初始资金、同现金流。每段独立启动，不能把三段拼成连续实盘。ETF价格已经含基金内部费用，不重复扣管理费。旧模型含直接股票，仍为股息税前且保留原特殊权限假设。旧模型不能当普通账户可直接执行的建议。\n",
              md_table(["区间", "沪深300全收益", "C实现TE", "C平均现金", "C双边年换手", "C事件数"], [[PHASE_LABELS[p], pct(pick('band',p)['benchmark_return']), pct(pick('band',p)['tracking_error_hs300']), pct(pick('band',p)['cash_average']), f"{pick('band',p)['annual_two_way_turnover']:.2f}", pick('band',p)['execution_events']] for p in PHASES]),
              "\nfixed作为事前固定配置基准；H00300.CSI是无投资者摩擦的全收益指数，不能直接等同于可交易基金。cash_opportunity_proxy是滞后现金权重乘指数日收益的算术机会成本代理，符号可能为负，不是严格收益归因。另存exposure_attribution.json用事后平均仓位缩放fixed，仅用于解释暴露差，不是事前可交易基准。逐年结果见annual_results.csv；全151项及压力/规模见all_experiments.csv。\n",
              "## 执行压力、规模与追加资金\n",
              md_table(["C执行情景", "2017—2021净收益", "2022—2024净收益", "近期净收益"], [[scenario]+[pct(next(r for r in rows if r['phase']==phase and r['strategy']=='band' and r['scenario']==scenario and r['initial']==100000 and r['annual_fee']==0 and r['monthly_contribution']==0)['total_return']) for phase in PHASES] for scenario in ['base','double_cost','delay_2','miss_fourth','partial','staged']]),
              "\n成本加倍、额外延迟2日、每第四次漏执行、每单只执行50%后撤销余单、三个月分阶段建仓均为事前情景，不是已校准的发生概率。成本提高有时改变整数份额及调仓路径，某些区间因此收益反而提高；不能把它解释为费用有利，也不据此选版本。没有模拟真实盘口队列或极端流动性枯竭。\n",
              md_table(["C本金", "2017—2021净收益", "2022—2024净收益", "近期净收益"], [[f'{capital:,}元']+[pct(next(r for r in rows if r['phase']==phase and r['strategy']=='band' and r['scenario']=='base' and r['initial']==capital and r['annual_fee']==0 and r['monthly_contribution']==0)['total_return']) for phase in PHASES] for capital in [50000,100000,200000,500000]]),
              "\n这四个本金节点只验证整数单位与成本敏感性，不表示风险偏好相同，也未验证节点之外的规模。\n",
              md_table(["近期每月追加1000元", "累计追加", "期末财富", "净投资损益", "时间加权收益"], [[LABELS[r['strategy']],f"{r['external_contributions']:.0f}",f"{r['ending_equity']:.2f}",f"{r['net_investment_profit']:.2f}",pct(r['total_return'])] for r in rows if r['monthly_contribution']>0]),
              "\n追加在每月首个交易日开盘交易前入账，首月也追加。时间加权日收益=期末净财富÷（前日净财富+当日外部入金）−1；外部入金不计为盈利。single仍坚持原买入持有，追加现金不自动买入，因此操作政策造成的现金差异必须保留。未测试提取资金。复核发现冻结结果的换手分母使用收益评价净值，4个追加账户因此不是实际财富口径；原值完整保留，CSV新增annual_two_way_turnover_actual_wealth按实际平均财富重算。此派生纠正不改变交易、净值或收益，不重选策略。\n",
              "## 风险约束的实际失败边界\n",
              md_table(["区间", "方案", "安全缓冲超限日", "原估计超18%日", "最大原估计波动", "权益超95%日"], [[PHASE_LABELS[x['phase']], LABELS[x['strategy']], x['buffer_breach_days'], x['raw_18pct_breach_days'], pct(x['max_estimated_raw_vol']), x['exposure_95pct_breach_days']] for x in daily_audits]),
              "\n安全缓冲超限定义为原估计波动×1.25超过18%，与原估计直接超过18%分开。月末合法目标不能保证月中不超限；本原型没有每日强制风险再平衡，日内跳空、估计滞后或未成交也无法被数学目标消除。不得将18%称为保证波动或最大损失；2022—2024仍有约三成最大回撤，不适合低风险或短期必要用款账户。\n",
              md_table(["旧v1r4区间", "行业偏离超限日", "直接单股超限日", "ETF底仓不足日", "非初始换手超限月"], [[PHASE_LABELS[r['phase']]]+[json.loads((BASE/'runs'/r['id']/'constraint_summary.json').read_text())[k] for k in ['industry_violation_days','direct_stock_cap_violation_days','core_floor_violation_days','executed_turnover_violations']] for r in main if r['strategy']=='legacy']),
              "\n旧模型实际约束也未全部满足，以上包括初始执行滞后；不能因旧模型某期胜出就视作可直接采用。完整逐日检查保存在其独立运行目录。补充持仓质量审计发现旧模型2017—2021区间曾有最长停牌超过20交易日的持仓，最大占净财富4.21%，期末该类持仓为零；没有未解释公司行动持仓，但旧价格标记的流动性风险仍需复核。见legacy_holding_quality.json，不把账本守恒等同于随时可兑现。\n",
              "## 不确定性和多重比较\n",
              md_table(["区间", "方案vs固定ETF", "年化算术差", "校正区间下界", "校正区间上界"], [[PHASE_LABELS[x['phase']], LABELS[x['strategy']], pct(x['annual_arithmetic_excess']), pct(x['familywise_lower']), pct(x['familywise_upper'])] for x in interval]),
              "\n20日块、4000次固定种子，6个主比较Bonferroni；151项尝试全部披露，压力/费用/规模不是独立发现集。此前项目183项旧实验与108项增强实验也已查看，不能用此区间消除研究选择偏差。P下历史估计不是Q下定价概率，区间不代表未来盈利概率。\n",
              "## 收费后客户价值\n",
              "0/300/600/1200元是事前研究假设，不是定价建议。每个服务年开始日（首交易日与周年后的首交易日）从账户现金收全年费，最后不足一年仍全额。不足现金形成应付服务费并计减净财富，不允许外部资金偷偷补足；未付金额明确列出。这是比期末机械减费更真实的资金约束，但合同、税收和运营收费机制尚未确认。\n",
              md_table(["区间", "C假设年费", "已计服务费", "客户净收益", "比免费单只ETF差", "比免费固定ETF差", "欠费"], [[PHASE_LABELS[x['phase']], x['annual_fee'], f"{x['total_service_fee']:.0f}", pct(x['net_return']), pct(x['excess_vs_free_single_pp']), pct(x['excess_vs_free_fixed_pp']), f"{x['unpaid']:.2f}"] for x in fee_rows if x['strategy']=='band']),
              "\n![收费敏感性](service_fee_value.png)\n",
              "对10万元，300/600/1200元对应起始本金的0.3%/0.6%/1.2%年负担；对5万元为0.6%/1.2%/2.4%。不能因更大本金摊薄固定收费就自动提高风险。免费简单ETF始终作为客户机会成本；同费率各方案也全部保留。当前只能验证较少订单和部分风险下降，未发现足以支持收费收益增强的稳定证据。纪律、说明和便利可能有价值，但需真实用户研究与前向执行证据验证，不能把这些价值折算成已证实的付费意愿。\n",
              "## 10万元新资金参考试算（不是成交或今日买入建议）\n",
              md_table(["代码及名称", "参考收盘价", "目标份额", "参考市值", "占起始本金", "经济目标权重", "预估佣金"], [[x['code']+' '+x['name'], f"{x['reference_price']:.3f}", x['target_shares'], f"{x['market_value']:.2f}", pct(x['weight']), pct(x['target_weight']), f"{x['estimated_fee']:.2f}"] for x in example['rows']]),
              f"\n参考现金余额（扣预估佣金/滑点）{example['available_cash_reference']:.2f}元；最低政策现金预留{example.get('cash_reserve',0):.2f}元，余量主要由风险预算决定。预估佣金{example.get('estimated_fees',0):.2f}元，预估滑点{example.get('estimated_slippage',0):.2f}元。订单数量和份额只在参考价格下核算，次日须重新确认价格、可交易性和资金；不等于历史期末持仓。\n",
              f"两ETF滞后指数代理重叠成分{example['lookthrough']['overlap_count']}只，最大行业{pct(example['lookthrough']['industry_max_weight'])}，最大穿透公司{pct(example['lookthrough']['company_max_weight'])}，未知行业{pct(example['lookthrough']['unknown_industry_weight'])}。过去252日收益相关系数{example['correlation_252d']:.3f}：即使名称零重叠，也并非因子零重叠。代理快照{example['lookthrough']['snapshot_dates']}，不是基金逐日真实底层持仓；中证500历史穿透未恢复，只做当前描述，不伪称历史行业约束通过。\n",
              "## 产品定位、限制和下一步\n",
              "定位：已有独立权益风险承受能力、主要需要减少碎片化操作的普通现金账户研究工具。每月末提供一张当前—目标份额差异表、费用估计、现金与风险说明；落在不交易区间就明确写不交易。发生执行失败或新公司行动须停下核验。相对单只ETF增加风险预算、两类规模暴露和执行说明，也增加模型估计和维护成本。\n",
              "不适合：低风险/本金短期必需、无法承受三成级回撤、不能按月核查、佣金明显高于登记情景、无法核验权限或依赖高收益承诺的人。5万元以下未验证，规模上涨并不消除共同市场风险；单边急涨容易因低仓位落后，波动快速抬升/相关性上升/连续跌停使风险预算失效；漏执行、半执行与建仓延迟会改变暴露，不能保证总是更好。\n",
              "阶段：已完成历史研究原型与整数参考试算；没有未来模拟成交或前向收益记录。下一步先补每日风险动作契约、真实盘口/限价/账户费用、基金完整历史穿透、公司行动持续核验，再冻结前向模拟；设至少12个月并跨压力阶段的观察计划，期间不按收益改规则。未预登记新基准或模型不得混入旧实验。\n",
              "销售距离：还缺机构及人员资质/适当性/合同及留痕系统、宣传与投诉合规、数据商业许可、可靠前向执行与客户净价值证据。标准化组合信息若涉及具体品种及收费，不能仅凭标准化或仅供参考绕过业务性质认定。详见合规核验文档，当前仅标研究原型。\n",
              "## 可复核交付\n",
              f"完整性：{verification['completed']}/{verification['registered']}登记实验完成，旧冻结文件{verification['legacy_files_unchanged']}项未变。软件核验只证明实现与保存的证据，不证明策略有效。\n",
              "- 研究协议与修订：research/small_capital_v1/protocol.md、revisions.md。\n- 账本/订单/费用/失败：artifacts/small_capital_v1/runs，每项独立manifest；初始数据审计失败另存。\n- 全实验、年表、客户收费表、完整当前持仓：本报告同目录CSV。\n- 执行复核：review.ipynb与review.py；运行和Agent契约见research/small_capital_v1/agent_guide.md。\n- 教材对应、交易与合规来源见theory.md、compliance.md；所有官方来源回执位于sources/receipts.json。\n"]
    (OUT / "report.md").write_text("\n".join(report), encoding="utf-8")
    # Plain readable HTML companion is a report, never the native workbench replacement.
    try:
        import markdown
        body = markdown.markdown("\n".join(report), extensions=["tables"])
    except ImportError:
        body = "<pre>"+html.escape("\n".join(report))+"</pre>"
    (OUT / "report.html").write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>小资金组合研究</title><style>body{max-width:1120px;margin:45px auto;font:16px/1.75 "Microsoft YaHei",sans-serif;color:#20354b;padding:20px}table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:8px;border-bottom:1px solid #dbe3ec;text-align:left}th{background:#edf2f7}img{max-width:100%}h1,h2{color:#173e69}pre{white-space:pre-wrap}</style>'+body+'</html>', encoding="utf-8")
    dump(BASE / "presentation.json", {"main_results": main, "fee_results": fee_rows, "risk_drift": daily_audits,
                                      "example": example, "uncertainty": interval, "unit_audit": units,
                                      "status": verification, "labels": LABELS})
    dump(BASE / "forward_state.json", {"status": "not_started", "future_observations": 0,
                                       "reference_initialization": "example_plan.json is hypothetical only; no fills booked",
                                       "rule_frozen_at": json.loads((BASE / "freeze.json").read_text())["created_at"],
                                       "next_required": ["new independent quotes", "corporate-action audit", "approved simulated execution contract"],
                                       "no_broker_connection": True})
    print(json.dumps({"report": str(OUT / "report.md"), "experiments": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    build()
