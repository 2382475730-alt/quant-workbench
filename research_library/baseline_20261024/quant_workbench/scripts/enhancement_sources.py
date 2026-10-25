"""Project reviewed, non-sensitive evidence for the inline Sources receipt."""
import json

from quant_workbench.data import ROOT

folder = ROOT/"reports/enhancement_v1"
data = json.loads((folder/"dashboard.json").read_text(encoding="utf-8"))
phase = data["phases"]["review"]
rows = [{"strategy": r["name"], "return_pct": r["total_return"]*100,
         "drawdown_pct": r["max_drawdown"]*100, "tracking_error_pct": r["tracking_error"]*100}
        for r in phase["rows"] if r["key"] in {"benchmark", "etf_reference", "momentum_constrained", "momentum_252_20"}]
active = phase["details"]["momentum_constrained"]
payload = {"schemaVersion": 1, "items": [
    {"id": "fair-comparison", "title": "近期主方案降低了风险，但没有跑赢全收益指数", "queries": [
        {"id": "same-period-ledgers", "source": {"label": "冻结模拟账本与全收益基准",
            "files": [{"label": "comparison.csv"}, {"label": "enhancement_review.ipynb"}, {"label": "source_receipts.json"}],
            "metricDefinitions": [{"label": "累计收益", "definition": "累计收益按共同初始100万元与期末权益计算；交易策略扣费用和滑点，指数为含股息再投资的理论全收益。"},
                                  {"label": "风险", "definition": "最大回撤含期初权益；跟踪误差为日主动收益标准差乘√252。"}],
            "filters": ["版本：v1r4基础费用情景", "旧方案：原动量20股冻结账本"],
            "caveats": ["所有历史区间已见，不是新的样本外证据。", "历史行业及指数权重公告时点不完整，ETF限价部分使用披露模型。"],
            "evidenceFlow": [{"kind": "validation", "title": "复核", "detail": "伴随笔记独立重算收益与跟踪误差，并检查证券市值、现金和应收与权益相等；四个冻结版本及108项结果核验通过。"}]},
         "reportingPeriod": "2025-01-02至2026-10-23，共436个交易日",
         "columns": [{"field": "strategy", "label": "方案"}, {"field": "return_pct", "label": "累计收益 %"},
                     {"field": "drawdown_pct", "label": "最大回撤 %"}, {"field": "tracking_error_pct", "label": "跟踪误差 %"}],
         "rows": rows, "preview": {"kind": "partial", "note": "显示当前主方案及三个主要对照；完整报告保留全部108项实验。", "totalRows": 12}}
    ]},
    {"id": "realized-constraints", "title": "实际约束仍有超限，当前仅适合研究与模拟", "queries": [
        {"id": "daily-risk-audit", "source": {"label": "主方案实际持仓与约束审计",
            "files": [{"label": "actual_constraints.parquet"}, {"label": "executed_turnover.json"}, {"label": "review_momentum_constrained_holdings.csv"}],
            "metricDefinitions": [{"label": "实际超限", "definition": "行业偏离按最新可用历史权重与ETF穿透代理逐日检查；直接持股上限为3%，首次建仓不计入15%单边换手限制。"}],
            "filters": ["方案：v1r4约束动量", "情景：基础费用"],
            "caveats": ["收盘目标合规不保证成交后及价格漂移期间合规。", "还没有新数据前向证据，Agent接口未连接LLM或券商。"]},
         "reportingPeriod": "2025-01-02至2026-10-23",
         "columns": [{"field": "days", "label": "交易日数"}, {"field": "industry_breach_days", "label": "行业超限日数"},
                     {"field": "stock_breach_days", "label": "单股超限日数"}, {"field": "turnover_breaches", "label": "换手超限次数"}],
         "rows": [{"days": active["days"], "industry_breach_days": active["actual_constraints"]["industry_violation_days"],
                   "stock_breach_days": active["actual_constraints"]["direct_stock_cap_violation_days"],
                   "turnover_breaches": active["actual_constraints"]["executed_turnover_violations"]}]}
    ]}
]}
(folder/"sources_payload.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
