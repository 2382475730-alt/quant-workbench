"""Inspectable company snapshots; statement revisions are not historical alpha inputs."""
from __future__ import annotations

import hashlib
import json
import math

import numpy as np
import pandas as pd

from .data import ROOT, write_json
from .prepare import load_table

NAMES = {"000001.SZ": "平安银行", "000063.SZ": "中兴通讯", "000333.SZ": "美的集团",
         "600519.SH": "贵州茅台", "600900.SH": "长江电力", "601318.SH": "中国平安"}
FINANCIAL = {"000001.SZ", "601318.SH"}
FIELDS = {"income": ["total_revenue", "revenue", "n_income_attr_p", "n_income"],
          "balancesheet": ["total_assets", "total_liab", "total_hldr_eqy_exc_min_int",
                           "total_hldr_eqy_inc_min_int", "money_cap", "goodwill"],
          "cashflow": ["n_cashflow_act", "c_pay_acq_const_fiolta"]}


def number(value):
    return float(value) if value is not None and pd.notna(value) and np.isfinite(float(value)) else None


def divide(a, b):
    return a / b if a is not None and b is not None and b != 0 else None


def available_statements(frame, asof, fields):
    """Later of disclosed dates, conservatively one calendar day after announcement.

    Returns one latest known record per reporting period. This does not recreate
    unavailable historical database vintages; only current descriptive use is valid.
    """
    if frame.empty:
        return frame.copy(), {"input_rows": 0, "available_rows": 0}
    x = frame.copy()
    dates = pd.concat([pd.to_datetime(x[c], errors="coerce") for c in ["ann_date", "f_ann_date"] if c in x], axis=1)
    x["available_date"] = dates.max(axis=1)
    cutoff = pd.Timestamp(asof)
    valid = x.available_date.notna() & x.available_date.lt(cutoff) & pd.to_datetime(x.end_date).le(cutoff)
    if "report_type" in x:
        valid &= x.report_type.astype(str).eq("1")
    x = x.loc[valid].copy()
    x["update_order"] = pd.to_numeric(x.get("update_flag", pd.Series(0, index=x.index)), errors="coerce").fillna(0)
    # Equal rank with different economic values has no defensible tie-breaker.
    for key, group in x.groupby(["end_date", "available_date", "update_order"]):
        if any(group[f].dropna().nunique() > 1 for f in fields if f in group):
            raise ValueError(f"Conflicting same-rank statement records: {key}")
    x = x.sort_values(["end_date", "available_date", "update_order"], kind="stable")
    before = len(x)
    x = x.drop_duplicates("end_date", keep="last").set_index("end_date").sort_index()
    audit = {"input_rows": len(frame), "available_rows": before, "unique_periods": len(x),
             "excluded_unavailable_or_nonconsolidated": int((~valid).sum()),
             "duplicate_or_older_versions": before - len(x),
             "availability": "max(ann_date,f_ann_date) strictly before asof; report_type=1"}
    return x, audit


def cell(frame, period, field):
    if period not in frame.index or field not in frame:
        return None
    return number(frame.loc[period, field])


def trailing_year(frame, period, field):
    """YTD current + previous full year - prior-year same YTD; never annualize H1."""
    current = cell(frame, period, field)
    if period.endswith("1231"):
        return current
    year = int(period[:4]) - 1
    annual = cell(frame, f"{year}1231", field)
    previous = cell(frame, f"{year}{period[4:]}", field)
    return current + annual - previous if all(v is not None for v in [current, annual, previous]) else None


def cash_metrics(operating, capex, consolidated_profit, financial=False):
    if financial:
        return {"operating_cash_minus_capex": None, "cash_to_consolidated_profit": None,
                "reason": "银行与保险不采用工业企业自由现金流及现金利润比评价"}
    return {"operating_cash_minus_capex": operating - capex if operating is not None and capex is not None else None,
            "cash_to_consolidated_profit": divide(operating, consolidated_profit),
            "reason": "经营现金流减购建长期资产现金为代理，不等于FCFF或FCFE；不含收购及全部再投资调整"}


def reconcile_primary_report(report):
    registry = ROOT / "config/company_report_checks.json"
    if not registry.exists():
        return {"status": "not_reviewed"}
    row = next((r for r in json.loads(registry.read_text(encoding="utf-8"))
                if r["code"] == report["code"] and r["period"] == report["statement_period"]), None)
    if row is None:
        return {"status": "not_reviewed_for_current_period"}
    path = (ROOT / row["source"]["path"]).resolve()
    if not path.is_relative_to(ROOT.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != row["source"]["sha256"]:
        raise ValueError("Company primary report missing or changed")
    checks = []
    for field, expected in row["financial_checks"].items():
        actual = report["financial"].get(field)
        passed = actual is not None and math.isclose(actual, expected, rel_tol=0, abs_tol=max(1, row["source_unit_cny"] / 2))
        checks.append({"field": field, "source_value_cny": expected, "structured_value_cny": actual, "passed": passed})
    if not all(c["passed"] for c in checks):
        raise ValueError(f"Primary report reconciliation failed: {report['code']} {checks}")
    return {**row, "status": "selected_headline_values_reconciled", "checks": checks,
            "boundary": "Only the listed headline fields are independently checked; not a full financial statement audit."}


def build(code, asof="2026-10-23"):
    frames, audits = {}, {}
    for api, fields in FIELDS.items():
        frames[api], audits[api] = available_statements(load_table(api, code), asof, fields)
    common = sorted(set.intersection(*(set(f.index) for f in frames.values())))
    if not common:
        raise ValueError(f"No common available financial period for {code}")
    period = common[-1]
    inc, bs, cf = frames["income"], frames["balancesheet"], frames["cashflow"]
    # The companies' headline operating revenue excludes subsidiary interest
    # income included in total_revenue (notably Midea and Moutai).
    revenue_field = "revenue" if cell(inc, period, "revenue") is not None else "total_revenue"
    prior = f"{int(period[:4])-1}{period[4:]}"
    revenue = cell(inc, period, revenue_field)
    parent_profit = cell(inc, period, "n_income_attr_p")
    old_revenue, old_profit = cell(inc, prior, revenue_field), cell(inc, prior, "n_income_attr_p")
    ttm_profit = trailing_year(inc, period, "n_income_attr_p")
    ttm_earnings = trailing_year(inc, period, "n_income")
    ttm_revenue = trailing_year(inc, period, revenue_field)
    ttm_operating = trailing_year(cf, period, "n_cashflow_act")
    ttm_capex = trailing_year(cf, period, "c_pay_acq_const_fiolta")
    assets, liabilities = cell(bs, period, "total_assets"), cell(bs, period, "total_liab")
    equity = cell(bs, period, "total_hldr_eqy_inc_min_int")
    balance_error = assets - liabilities - equity if all(v is not None for v in [assets, liabilities, equity]) else None
    if balance_error is not None and abs(balance_error) > max(10000, abs(assets) * .00001):
        raise ValueError(f"Balance sheet identity fails for {code}: {balance_error}")
    market = load_table("daily_basic", code).sort_values("trade_date")
    market = market.loc[market.trade_date <= asof.replace("-", "")]
    if market.empty:
        raise ValueError(f"No market snapshot for {code}")
    latest = market.iloc[-1]
    start = (pd.Timestamp(asof) - pd.DateOffset(years=5)).strftime("%Y%m%d")
    multiples = {}
    for field in ["pe_ttm", "pb"]:
        value = number(latest.get(field))
        history = pd.to_numeric(market.loc[market.trade_date.ge(start), field], errors="coerce")
        history = history.loc[history.gt(0)]
        multiples[field] = {"current": value, "positive_observations": len(history),
                            "percentile": float(history.le(value).mean()) if value is not None and value > 0 and len(history) else None,
                            "quantiles": {str(q): float(history.quantile(q)) for q in [.2, .5, .8]} if len(history) else {}}
    price = number(latest.close)
    scenario_basis = "book_value" if code in FINANCIAL else "earnings"
    scenarios = [{"fundamental_change": growth, "multiple_change": reprice,
                  "conditional_price": price * (1 + growth) * (1 + reprice),
                  "price_return": (1 + growth) * (1 + reprice) - 1}
                 for growth in [-.2, 0., .2] for reprice in [-.25, 0., .25]]
    annual_rows = []
    for p in sorted(set(inc.index) & set(cf.index)):
        if p.endswith("1231") and p >= "20211231":
            annual_rows.append({"period": p, "revenue": cell(inc, p, revenue_field),
                                "parent_profit": cell(inc, p, "n_income_attr_p"),
                                "operating_cash": cell(cf, p, "n_cashflow_act"),
                                "capex": cell(cf, p, "c_pay_acq_const_fiolta")})
    report = {"code": code, "name": NAMES[code], "asof": asof, "statement_period": period,
              "statement_announcements": {k: str(f.loc[period, "available_date"].date()) for k, f in frames.items()},
              "market_date": str(latest.trade_date), "price": price,
              "financial": {"revenue_ytd": revenue, "revenue_field": revenue_field,
                            "total_revenue_ytd": cell(inc, period, "total_revenue"),
                            "parent_profit_ytd": parent_profit,
                            "operating_cash_ytd": cell(cf, period, "n_cashflow_act"),
                            "revenue_yoy": divide(revenue, old_revenue) - 1 if revenue is not None and old_revenue is not None and old_revenue > 0 else None,
                            "parent_profit_yoy": divide(parent_profit, old_profit) - 1 if parent_profit is not None and old_profit is not None and old_profit > 0 else None,
                            "ttm_revenue": ttm_revenue, "ttm_parent_profit": ttm_profit,
                            "ttm_operating_cash": ttm_operating, "ttm_capex": ttm_capex,
                            "total_assets": assets, "total_liabilities": liabilities,
                            "parent_equity": cell(bs, period, "total_hldr_eqy_exc_min_int"),
                            "liabilities_assets": divide(liabilities, assets),
                            **cash_metrics(ttm_operating, ttm_capex, ttm_earnings, code in FINANCIAL)},
              "valuation": multiples, "scenario_basis": scenario_basis, "scenarios": scenarios,
              "annual": annual_rows, "audit": {"statements": audits, "balance_identity_residual_cny": balance_error},
              "limitations": ["本快照使用当前数据库中截至截止日前公告的版本；不能证明原始历史数据库版本，因此未用作历史选股因子。",
                              "同日公告保守延迟一天；期末和公告日分别记录。",
                              "估值分位是近5年正值样本描述，不表示低估；会受盈利变化、会计口径和市场制度影响。",
                              "情景为共同预设的敏感性网格，不赋予概率，不称为目标价；股数变化、股息与费用另行分析。",
                              "Tushare报表是结构化来源，重要结论仍须与公司原始报告核对。"]}
    report["primary_report_review"] = reconcile_primary_report(report)
    write_json(f"artifacts/company/{code}/snapshot.json", report)
    path = ROOT / f"artifacts/company/{code}/summary.md"
    path.write_text(markdown(report), encoding="utf-8")
    return report


def fmt(value, mode="money"):
    if value is None:
        return "未知"
    if mode == "pct":
        return f"{value:.1%}"
    if mode == "multiple":
        return f"{value:.2f}"
    return f"{value / 1e8:,.2f}亿元"


def markdown(r):
    f = r["financial"]
    lines = [f"# {r['name']}（{r['code']}）单股财务与估值快照", "",
             f"观察日 {r['asof']}；报价日 {r['market_date']}，收盘 {r['price']:.2f} 元。三表共同报告期 {r['statement_period']}。",
             "", "| 指标 | 数值 |", "|---|---:|",
             f"| 年初至今营业收入 | {fmt(f['revenue_ytd'])} |",
             f"| 营业收入同比 | {fmt(f['revenue_yoy'], 'pct')} |",
             f"| 年初至今归母净利润 | {fmt(f['parent_profit_ytd'])} |",
             f"| 归母净利润同比 | {fmt(f['parent_profit_yoy'], 'pct')} |",
             f"| 最近12个月营业收入 | {fmt(f['ttm_revenue'])} |",
             f"| 最近12个月归母净利润 | {fmt(f['ttm_parent_profit'])} |",
             f"| 负债/资产 | {fmt(f['liabilities_assets'], 'pct')} |", ""]
    for field, label in [("pe_ttm", "市盈率TTM"), ("pb", "市净率")]:
        v = r["valuation"][field]
        lines.append(f"{label} {fmt(v['current'], 'multiple')}；近5年正值观察分位 {fmt(v['percentile'], 'pct')}（{v['positive_observations']}天）。")
    review = r.get("primary_report_review", {})
    if review.get("status") == "selected_headline_values_reconciled":
        source = review["source"]
        lines += ["", f"已与[公司原始半年报]({source['url']})核对 {len(review['checks'])} 项主要数据；PDF页码 {', '.join(map(str, review['pages']))}。", ""]
        lines.extend(f"- {note}" for note in review["observations"])
        lines += ["", f"持仓研究关注：{review['holding_questions']}。"]
    lines += ["", f"现金流口径：{f['reason']}。"]
    if r["code"] not in FINANCIAL:
        lines.append(f"最近12个月经营现金流 {fmt(f['ttm_operating_cash'])}，购建长期资产现金 {fmt(f['ttm_capex'])}，两者差额 {fmt(f['operating_cash_minus_capex'])}。")
        lines.append(f"经营现金流/合并净利润 {fmt(f['cash_to_consolidated_profit'], 'multiple')}。")
    else:
        lines.append("负债率仅作结构描述，不与工业企业直接比较；银行还需资本充足率与资产质量，保险还需偿付能力、保险服务及投资表现。")
    basis = "每股净资产" if r["scenario_basis"] == "book_value" else "每股盈利"
    lines += ["", f"条件情景：假定{basis}变化为-20%/0/+20%，估值倍数变化为-25%/0/+25%。极端组合对应价格变化-40%至+50%，这不是预测区间或合理价值区间。", "",
              "持仓研究应同时查看趋势、风险预算、组合集中度及原始财报；本财务快照本身不触发买卖。", "", "数据边界：", ""]
    lines.extend(f"- {item}" for item in r["limitations"])
    return "\n".join(lines) + "\n"


def run():
    settings = json.loads((ROOT / "config/experiments.json").read_text(encoding="utf-8"))
    results = [build(code) for code in settings["single_stock_examples"]]
    write_json("artifacts/company/index.json", [{k: r[k] for k in ["code", "name", "asof", "statement_period", "market_date"]} for r in results])
    print(f"Company snapshots: {len(results)}")


if __name__ == "__main__":
    run()
