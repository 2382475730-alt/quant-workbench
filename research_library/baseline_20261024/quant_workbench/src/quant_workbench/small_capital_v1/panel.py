"""Native Tk reader with distinct historical/reference/forward account labels."""
from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk

import pandas as pd

from ..data import ROOT
from .data import BASE

LABELS = {"single": "单只300ETF持有", "fixed": "固定ETF组合", "risk": "A 风险预算ETF", "band": "C 不交易区间", "legacy": "旧v1r4缩小重跑"}
PHASES = {"2017—2021": "development", "2022—2024": "validation", "2025—2026-10-23": "review"}


def pct(v):
    return "未知" if v is None else f"{v:.2%}"


def grid(parent, columns, height=8):
    outer = ttk.Frame(parent)
    outer.pack(fill="both", expand=True, pady=5)
    tree = ttk.Treeview(outer, columns=[c[0] for c in columns], show="headings", height=height)
    for key, title, width in columns:
        tree.heading(key, text=title)
        tree.column(key, width=width, minwidth=65, anchor="w")
    vs = ttk.Scrollbar(outer, orient="vertical", command=tree.yview)
    hs = ttk.Scrollbar(outer, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
    vs.pack(side="right", fill="y")
    hs.pack(side="bottom", fill="x")
    tree.pack(fill="both", expand=True)
    return tree


def text_box(parent):
    box = ttk.Frame(parent)
    box.pack(fill="both", expand=True)
    text = tk.Text(box, wrap="word", font=("Microsoft YaHei", 10), bg="white", fg="#20354b", padx=15, pady=12)
    bar = ttk.Scrollbar(box, command=text.yview)
    text.configure(yscrollcommand=bar.set)
    bar.pack(side="right", fill="y")
    text.pack(fill="both", expand=True)
    return text


def set_text(widget, content):
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    widget.insert("1.0", content)
    widget.configure(state="disabled")


def clear(tree):
    tree.delete(*tree.get_children())


class SmallCapitalPanel(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=12)
        self.data = {}
        self.note = ttk.Label(self, wraplength=1150, foreground="#9b4529")
        self.note.pack(fill="x", pady=(0, 7))
        controls = ttk.Frame(self)
        controls.pack(fill="x")
        ttk.Label(controls, text="独立回溯区间").pack(side="left")
        self.phase = tk.StringVar(value="2025—2026-10-23")
        combo = ttk.Combobox(controls, textvariable=self.phase, values=list(PHASES), state="readonly", width=20)
        combo.pack(side="left", padx=8)
        combo.bind("<<ComboboxSelected>>", lambda _: self.draw())
        ttk.Button(controls, text="完整报告", command=lambda: self.open_text("reports/small_capital_v1/report.md", "小资金研究报告")).pack(side="right")
        ttk.Button(controls, text="Agent复核说明", command=lambda: self.open_text("research/small_capital_v1/agent_guide.md", "Agent任务与复核")).pack(side="right", padx=6)
        self.pages = ttk.Notebook(self)
        self.pages.pack(fill="both", expand=True, pady=(8, 0))
        self.overview, self.plan_page, self.history, self.exposure, self.boundaries = [ttk.Frame(self.pages, padding=8) for _ in range(5)]
        for name, page in [("成本与客户价值", self.overview), ("10万元新资金试算", self.plan_page), ("历史账户实际持仓", self.history), ("ETF穿透与集中", self.exposure), ("风险、压力与边界", self.boundaries)]:
            self.pages.add(page, text=name)
        self.summary = ttk.Label(self.overview, wraplength=1120, font=("Microsoft YaHei", 12))
        self.summary.pack(fill="x", pady=6)
        self.comparison = grid(self.overview, [("name", "方案", 190), ("return", "净收益", 100), ("dd", "最大回撤", 110), ("vol", "波动", 100), ("expo", "实际权益", 100), ("trades", "成交笔数", 90), ("cost", "交易成本+滑点", 160)], 5)
        ttk.Label(self.overview, text="C方案收费后：同本金、同现金流；相对免费简单ETF（年费仅为研究假设）").pack(anchor="w")
        self.fees = grid(self.overview, [("fee", "假设年费", 100), ("paid", "累计计提", 120), ("return", "客户净收益", 140), ("single", "比免费单只ETF差", 170), ("fixed", "比免费固定组合差", 170), ("unpaid", "应付未付", 100)], 4)
        self.plan_note = ttk.Label(self.plan_page, wraplength=1120)
        self.plan_note.pack(fill="x", pady=5)
        self.plan_table = grid(self.plan_page, [("code", "代码", 110), ("name", "名称", 180), ("price", "参考价", 85), ("held", "当前份额", 90), ("target", "目标份额", 90), ("delta", "买卖变化", 90), ("value", "参考市值", 110), ("weight", "占本金", 90), ("goal", "经济目标", 90), ("fee", "估计佣金", 90)], 3)
        self.plan_detail = text_box(self.plan_page)
        hc = ttk.Frame(self.history)
        hc.pack(fill="x")
        self.strategy = tk.StringVar(value=LABELS["band"])
        cb = ttk.Combobox(hc, textvariable=self.strategy, values=list(LABELS.values()), state="readonly", width=24)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda _: self.draw_history())
        self.history_note = ttk.Label(self.history, wraplength=1120)
        self.history_note.pack(fill="x", pady=8)
        self.history_table = grid(self.history, [("code", "代码", 130), ("shares", "实际份额/股数", 150), ("mark", "估值收盘价", 130), ("value", "市值", 150), ("weight", "实际净值权重", 150)], 10)
        self.exposure_note = ttk.Label(self.exposure, wraplength=1120)
        self.exposure_note.pack(fill="x", pady=8)
        self.sectors = grid(self.exposure, [("name", "行业（当前滞后指数代理）", 340), ("weight", "占10万元试算本金", 230)], 12)
        self.boundary_text = text_box(self.boundaries)
        self.load()

    def load(self):
        path = BASE / "presentation.json"
        self.data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        self.draw()

    def draw(self):
        if not self.data:
            self.note.configure(text="small_capital_v1尚无已核验展示数据；打开窗口不会采集、回测或下单。")
            return
        self.note.configure(text="小资金组合 · 10万元研究本金 · 截至2026-10-23 · 普通现金账户权限假设未核实 · 研究原型 / 前向0天 / 不下单\n本页区间独立于顶部旧研究区间；新资金试算与历史账户分别展示。佣金万3最低5元、单边10bp滑点为研究假设。")
        phase = PHASES[self.phase.get()]
        rows = [r for r in self.data["main_results"] if r["phase"] == phase]
        clear(self.comparison)
        for s, label in LABELS.items():
            r = next(x for x in rows if x["strategy"] == s)
            self.comparison.insert("", "end", values=(label, pct(r["total_return"]), pct(r["max_drawdown"]), pct(r["volatility"]), pct(r["average_exposure"]), r["trade_count"], f"{r['fees']+r['slippage']:.2f} 元"))
        c = next(r for r in rows if r["strategy"] == "band")
        self.summary.configure(text=f"少交易可以验证，收费优势尚未证明。C本区间收益 {pct(c['total_return'])}，最大回撤 {pct(c['max_drawdown'])}；降风险伴随低仓位与机会成本。")
        clear(self.fees)
        for r in self.data["fee_results"]:
            if r["phase"] == phase and r["strategy"] == "band":
                self.fees.insert("", "end", values=(f"{r['annual_fee']} 元", f"{r['total_service_fee']:.0f} 元", pct(r["net_return"]), pct(r["excess_vs_free_single_pp"]), pct(r["excess_vs_free_fixed_pp"]), f"{r['unpaid']:.2f}"))
        p = self.data["example"]
        self.plan_note.configure(text="独立新现金账户：100,000元，无当前持仓，首次建仓。2026-10-23收盘参考试算；没有模拟或真实成交记录。\n风险预算18%，估计误差系数1.25；两只股票ETF共同暴露中国权益风险，未知用户风险偏好。")
        clear(self.plan_table)
        for r in p["rows"]:
            self.plan_table.insert("", "end", values=(r["code"], r["name"], f"{r['reference_price']:.3f}", r["current_shares"], r["target_shares"], f"{r['delta']:+d}", f"{r['market_value']:.2f}", pct(r["weight"]), pct(r["target_weight"]), f"{r['estimated_fee']:.2f}"))
        set_text(self.plan_detail, f"执行状态：{p['status']}（参考价格下整数方案可行；不等于已成交）\n\n"
                 f"预计可用现金 {p['available_cash_reference']:,.2f} 元；最低政策现金预留 {p.get('cash_reserve',0):,.2f} 元。\n"
                 f"佣金预留 {p.get('estimated_fees',0):.2f} 元，滑点预留 {p.get('estimated_slippage',0):.2f} 元；股数取整及风险预算剩余均保留为现金。\n"
                 f"原估计波动 {pct(p.get('predicted_vol'))}；乘1.25后 {pct(p.get('predicted_vol',0)*1.25)}。\n\n"
                 "选择理由：510300提供大盘底仓，510500补充中盘规模暴露；本次首次现金建仓，无需遵守后续25%换手预算。\n"
                 "后续如两项目标偏离均不超过5个百分点且风险未超限则暂不交易；普通订单低于2000元不凑单。风险降仓优先于换手限制，但停牌/触限时可能无法消除风险。\n"
                 "新资金计划没有因一手不足而完全缺失的ETF目标；直接股票无法合理配置的完整清单在报告与direct_stock_unit_audit.csv。\n"
                 "执行前必须核对实际账户佣金、可售份额、资金和下一交易日价格。今天参考收盘试算不能冒称今天买入建议。")
        look = p["lookthrough"]
        self.exposure_note.configure(text=f"仅针对新资金试算：滞后指数权重 {look['snapshot_dates']}，不是基金真实逐日持仓。\n名称重叠 {look['overlap_count']} 只，最大穿透公司 {pct(look['company_max_weight'])}，未知行业 {pct(look['unknown_industry_weight'])}；252日相关系数 {p['correlation_252d']:.3f}。历史500穿透缺失，未宣称全历史行业约束通过。")
        clear(self.sectors)
        for r in look["industries"]:
            self.sectors.insert("", "end", values=(r["name"], pct(r["weight"])))
        risk = next(x for x in self.data["risk_drift"] if x["phase"] == phase and x["strategy"] == "band")
        set_text(self.boundary_text, f"C实际风险审计 / {self.phase.get()}\n\n安全缓冲超限 {risk['buffer_breach_days']} 日；原估计波动直接超过18% {risk['raw_18pct_breach_days']} 日；实际权益超过95% {risk['exposure_95pct_breach_days']} 日。\n"
                 "安全缓冲指原估计×1.25；预算只在月末生成目标，日内/日间价格、估计及未成交使实际持仓漂移。18%不是最大亏损保证。\n\n"
                 f"当前区间C执行事件 {c['execution_events']} 项，失败/保持决策 {c['failed_or_held_decisions']} 次，风险优先例外 {c['risk_priority_overrides']} 次。\n"
                 "151项实验包含：双倍成本、额外2日延迟、每第四次漏执行、每单50%后撤销、三阶段建仓、5/20/50万元、四档年费及每月1000元追加。全部结果见报告CSV，不按收益挑版本。\n\n"
                 "前向账户：尚未启动。参考份额不是历史账户期末持仓，也不是未来模拟成交。\n"
                 "数据：新增ETF拆分公告已核对，2015原始缺口保留但不在研究窗口；已见历史、成分时点代理、模拟涨跌停和无盘口资料仍是限制。\n"
                 "产品：研究工具、标准化组合信息与个性化收费投顾须按实质认定。当前没有核验机构/人员资质或数据商业许可；仅供参考不能改变业务性质。\n"
                 "Agent只调用确定性本地函数，不接受任意命令、不连接券商。超出已验证本金/资产/费用/风险参数时返回needs_research。")
        self.draw_history()

    def draw_history(self):
        if not self.data:
            return
        strategy = next(k for k, v in LABELS.items() if v == self.strategy.get())
        row = next(x for x in self.data["main_results"] if x["phase"] == PHASES[self.phase.get()] and x["strategy"] == strategy)
        path = BASE / "runs" / row["id"]
        nav = pd.read_parquet(path / "nav.parquet")
        pos = pd.read_parquet(path / "positions.parquet")
        last = nav.iloc[-1]
        held = pos.loc[pos.date == nav.index[-1]]
        clear(self.history_table)
        for r in held.itertuples():
            self.history_table.insert("", "end", values=(r.code, r.shares, f"{r.mark:.3f}", f"{r.shares*r.mark:.2f}", pct(r.weight)))
        self.history_note.configure(text=f"历史回测账户，独立10万元起步；{nav.index[-1].date()}期末净财富 {last.equity:,.2f} 元，现金 {last.cash:,.2f} 元，应收 {last.receivable:.2f} 元，应付 {last.get('payable',0):.2f} 元。\n证券市值+现金+应收−应付=净财富。此表不能改名为当前新资金买入计划；旧v1r4的特殊权限及股息税前口径保留。")

    def open_text(self, relative, title):
        path = (ROOT / relative).resolve()
        if not path.is_relative_to(ROOT.resolve()):
            raise ValueError("Outside workspace")
        win = tk.Toplevel(self)
        win.title(title)
        win.geometry("1000x760")
        text = text_box(win)
        set_text(text, path.read_text(encoding="utf-8") if path.exists() else "文档尚未生成。")
