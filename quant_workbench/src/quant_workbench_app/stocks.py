import tkinter as tk
from tkinter import ttk

from quant_workbench.desktop import LABELS, Desktop
from quant_workbench.holding_view import load_ledger, snapshot

from .paths import LIBRARY, SETTINGS, read_json
from .widgets import chart, report_tab, set_text, table, text_panel

PERIODS = {"2025—2026 核算修订": "final_repaired", "2022—2024 验证": "validation", "2017—2021 开发": "development"}


class StockPanel(ttk.Frame):
    nav = Desktop.nav
    plot = Desktop.plot
    draw_stock = Desktop.draw_stock
    set_text = staticmethod(set_text)
    open_company_source = Desktop.open_company_source

    def __init__(self, parent):
        super().__init__(parent, padding=10)
        controls = ttk.Frame(self)
        controls.pack(fill="x", pady=(0, 10))
        self.names = {f"{name}  {code}": code for code, name in SETTINGS["companies"].items()}
        self.company = tk.StringVar(value=next(iter(self.names)))
        self.symbol = tk.StringVar(value=self.names[self.company.get()])
        choice = ttk.Combobox(controls, values=list(self.names), textvariable=self.company, state="readonly", width=25)
        choice.pack(side="left")
        choice.bind("<<ComboboxSelected>>", lambda _: self.refresh())
        self.period = tk.StringVar(value=next(iter(PERIODS)))
        self.phase = tk.StringVar(value="final_repaired")
        period = ttk.Combobox(controls, values=list(PERIODS), textvariable=self.period, state="readonly", width=24)
        period.pack(side="left", padx=10)
        period.bind("<<ComboboxSelected>>", lambda _: self.refresh())
        ttk.Button(controls, text="原始半年报", command=self.open_company_source).pack(side="right")
        self.pages = ttk.Notebook(self)
        self.pages.pack(fill="both", expand=True)
        overview, facts, holdings, notes = [ttk.Frame(self.pages, padding=10) for _ in range(4)]
        for label, page in [("持仓规则对照", overview), ("公司与估值", facts), ("历史模拟持仓", holdings), ("分析说明", notes)]:
            self.pages.add(page, text=label)
        self.stock_note = ttk.Label(overview, style="Heading.TLabel")
        self.stock_note.pack(anchor="w")
        self.stock_fig, self.stock_canvas = chart(overview)
        self.conclusion = ttk.Label(overview, wraplength=1000, style="Sub.TLabel")
        self.conclusion.pack(fill="x")
        self.metrics = table(overview, [("规则", 280), ("区间收益", 140), ("最大回撤", 140), ("平均股票仓位", 180)], 3)
        self.facts = text_panel(facts)
        self.stock_text = text_panel(notes)
        self.account = ttk.Label(holdings, wraplength=1000)
        self.account.pack(fill="x", pady=8)
        self.ledger = table(holdings, [("证券", 150), ("实际股数", 140), ("估值价格", 140), ("市值", 160), ("权重", 130)], 5)
        ttk.Label(holdings, text="展示所选历史区间的趋势＋波动控制账户；不是新资金买入计划，也不是券商持仓。",
                  wraplength=1000, style="Sub.TLabel").pack(anchor="w", pady=12)
        report_tab(self.pages, "research/single_stock_holding_guide.md", "研究记录")
        self.refresh()

    def refresh(self):
        self.symbol.set(self.names[self.company.get()])
        self.phase.set(PERIODS[self.period.get()])
        self.summary = read_json(LIBRARY / f"artifacts/research/{self.phase.get()}/summary.json", {})
        self.rows = self.summary.get("results", [])
        self.draw_stock()
        selected = [r for r in self.rows if r["symbol"] == self.symbol.get() and r["scenario"] == "base"
                    and r["strategy"] in {"buy_hold", "trend_200", "trend_200_risk"}]
        self.metrics.delete(*self.metrics.get_children())
        for row in selected:
            self.metrics.insert("", "end", values=(LABELS[row["strategy"]], f"{row['total_return']:.2%}",
                                 f"{row['max_drawdown']:.2%}", f"{row['average_exposure']:.2%}"))
        risk = next((r for r in selected if r["strategy"] == "trend_200_risk"), None)
        hold = next((r for r in selected if r["strategy"] == "buy_hold"), None)
        self.ledger.delete(*self.ledger.get_children())
        if risk and hold:
            dd = abs(hold["max_drawdown"]) - abs(risk["max_drawdown"])
            difference = risk["total_return"] - hold["total_return"]
            self.conclusion.configure(text=f"本区间波动控制相对持有：回撤幅度{'减少' if dd >= 0 else '增加'} {abs(dd)*100:.2f} 个百分点，"
                                      f"累计收益差 {difference*100:+.2f} 个百分点。仅为所选案例的历史对照。")
            ledger = load_ledger(self.phase.get(), risk["id"])
            view = snapshot(ledger, ledger["nav"].index[-1])
            self.account.configure(text=f"{view['asof']} 历史模拟账户 · 现金 {view['cash']:,.2f}元 · 股票仓位 {view['stock_weight']:.2%}")
            for row in view["rows"]:
                self.ledger.insert("", "end", values=(row["code"], row["shares"], row.get("mark", "—"),
                                   f"{row['market_value']:,.2f}", f"{row['actual_weight']:.2%}"))
        p = read_json(LIBRARY / f"artifacts/company/{self.symbol.get()}/snapshot.json", {})
        summary_path = LIBRARY / f"artifacts/company/{self.symbol.get()}/summary.md"
        content = summary_path.read_text(encoding="utf-8") if summary_path.exists() else "公司资料暂缺。"
        set_text(self.facts, f"财务与估值观察日：{p.get('market_date', '未知')}；此页不随历史回测区间改变。\n"
                 "当前买卖规则使用价格与波动率，财务和估值条件尚未自动进入信号。\n\n" + content)

    def state(self):
        return {"company": self.company.get(), "period": self.period.get(), "tab": self.pages.index(self.pages.select())}

    def restore(self, state):
        if state.get("company") in self.names:
            self.company.set(state["company"])
        if state.get("period") in PERIODS:
            self.period.set(state["period"])
        self.refresh()
