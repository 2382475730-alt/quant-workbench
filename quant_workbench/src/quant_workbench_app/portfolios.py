import tkinter as tk
from tkinter import ttk

import pandas as pd
from quant_workbench.enhancement_panel import NAMES, EnhancementPanel
from quant_workbench.small_capital_v1.panel import LABELS, PHASES, SmallCapitalPanel

from .paths import LIBRARY
from .reading import library_report
from .presentation_copy import polish_panel
from .ui_presentation import NoteLabel, upgrade_notes, style_panel, WARNING_COLOR
from .widgets import chart, polish_tree, report_tab, table

PERIODS = {"2025—2026 回溯": "review", "2022—2024 回溯": "validation", "2017—2021 回溯": "development"}


class EnhancementView(EnhancementPanel):
    def open_text(self, relative, title):
        self.winfo_toplevel().document(title, library_report(relative), source=LIBRARY / relative)

    def draw_holdings(self):
        super().draw_holdings()
        polish_panel(self)
        if hasattr(self, 'account'):
            self.account.configure(text=self.account.cget('text').replace('（红色）', '（超限，琥珀色）'))
        style_panel(self)

    def draw_audit(self, key):
        super().draw_audit(key)
        polish_panel(self, ("audit",))

    def __init__(self, parent):
        super().__init__(parent)
        upgrade_notes(self, ('note', 'account', 'industry_note'))
        for tree in (self.holdings_table, self.industry_table):
            tree.tag_configure('breach', foreground=WARNING_COLOR)
        self.show_history = tk.BooleanVar(value=False)
        controls = ttk.Frame(self)
        controls.pack(fill="x", before=self.pages, pady=5)
        self.period = tk.StringVar(value=next(iter(PERIODS)))
        choice = ttk.Combobox(controls, textvariable=self.period, values=list(PERIODS), state="readonly", width=23)
        choice.pack(side="left")
        choice.bind("<<ComboboxSelected>>", lambda _: self.load(PERIODS[self.period.get()]))
        ttk.Checkbutton(controls, text="展开历史版本对照", variable=self.show_history,
                        command=self.filter_versions).pack(side="left", padx=12)
        self.comparison.configure(height=5)
        self.comparison.heading("name", text="研究方案")
        self.strategy.trace_add("write", lambda *_: self.sync_strategy())
        self.comparison.bind("<<TreeviewSelect>>", self.sync_selection, add="+")
        for widget in (self.comparison, self.holdings_table, self.industry_table):
            polish_tree(widget)
        self.pages.tab(1, text="历史模拟持仓")
        report_tab(self.pages, "reports/enhancement_v1/report.md")
        self.load("review")

    def load(self, phase):
        # Delete detached table rows as well before rebuilding a new period.
        for row in self.phase_data.get("rows", []):
            if self.comparison.exists(row["key"]):
                self.comparison.delete(row["key"])
        super().load(phase)
        polish_panel(self, ("audit",))
        if hasattr(self, "show_history"):
            self.filter_versions()
        style_panel(self)

    def filter_versions(self):
        primary = {"benchmark", "etf_reference", "momentum_constrained", "defensive_constrained"}
        for row in self.phase_data.get("rows", []):
            key = row["key"]
            if self.show_history.get() or key in primary:
                self.comparison.move(key, "", "end")
            else:
                self.comparison.detach(key)
        selected = self.comparison.selection()
        if selected and selected[0] not in self.comparison.get_children():
            self.comparison.selection_set("momentum_constrained")
        self.draw_curve()

    def sync_selection(self, _=None):
        selected = self.comparison.selection()
        if selected and selected[0] in NAMES and self.strategy.get() != NAMES[selected[0]]:
            self.strategy.set(NAMES[selected[0]])

    def sync_strategy(self):
        key = next(k for k, v in NAMES.items() if v == self.strategy.get())
        if self.comparison.exists(key):
            self.comparison.selection_set(key)
            self.draw_curve()
            self.draw_holdings()

    def state(self):
        return {"period": self.period.get(), "strategy": self.strategy.get(),
                "history": self.show_history.get(), "tab": self.pages.index(self.pages.select())}

    def restore(self, state):
        if state.get("period") in PERIODS:
            self.period.set(state["period"])
        self.show_history.set(bool(state.get("history", False)))
        self.load(PERIODS[self.period.get()])
        if state.get("strategy") in NAMES.values():
            self.strategy.set(state["strategy"])


class SmallCapitalView(SmallCapitalPanel):
    def open_text(self, relative, title):
        self.winfo_toplevel().document(title, library_report(relative), source=LIBRARY / relative)

    def draw_history(self):
        super().draw_history()
        polish_panel(self)
        style_panel(self)

    def __init__(self, parent):
        super().__init__(parent)
        upgrade_notes(self, ('note', 'summary', 'plan_note', 'history_note', 'exposure_note'))
        summary = ttk.Frame(self.pages, padding=10)
        self.pages.insert(0, summary, text="配置概览")
        self.pages.select(summary)
        self.summary_title = ttk.Label(summary, style="Heading.TLabel")
        self.summary_title.pack(anchor="w")
        self.figure, self.canvas = chart(summary)
        self.summary_note = NoteLabel(summary)
        self.summary_note.pack(fill="x")
        self.summary_table = table(summary, [("方案", 260), ("区间收益", 120), ("最大回撤", 120),
                                             ("成交笔数", 110), ("交易费＋滑点 / 元", 180)], 4)
        self.pages.tab(self.overview, text="费用与交易明细")
        self.pages.tab(self.history, text="历史模拟持仓")
        report_tab(self.pages, "reports/small_capital_v1/report.md")
        self.draw()

    def draw(self):
        super().draw()
        polish_panel(self, ("plan_detail", "boundary_text"))
        if not hasattr(self, "figure") or not self.data:
            return
        self.note.configure(text="10万元研究账户 · 行情截至2026-10-23 · 本页独立选择历史区间。\n"
                            "新资金试算与历史持仓见各标签页。前向模拟尚未开始。")
        phase = PHASES[self.phase.get()]
        rows = [r for r in self.data["main_results"] if r["phase"] == phase and r["strategy"] != "legacy"]
        self.figure.clear()
        ax = self.figure.add_subplot()
        self.summary_table.delete(*self.summary_table.get_children())
        for row in rows:
            nav = pd.read_parquet(LIBRARY / "artifacts/small_capital_v1/runs" / row["id"] / "nav.parquet")
            ax.plot(nav.index, nav.equity / 100000, label=LABELS[row["strategy"]], linewidth=1.5)
            self.summary_table.insert("", "end", values=(LABELS[row["strategy"]], f"{row['total_return']:.2%}",
                                      f"{row['max_drawdown']:.2%}", row["trade_count"], f"{row['fees']+row['slippage']:.2f}"))
        ax.grid(alpha=.18)
        ax.set_ylabel("净值（初始=1）")
        ax.legend(fontsize=9, ncol=2)
        self.figure.tight_layout(pad=1.2)
        self.canvas.draw_idle()
        self.summary_title.configure(text=f"{self.phase.get()} · 各方案收益与回撤")
        self.summary_note.configure(text="各方案使用相同本金、区间和基础费用。现金仓位降低回撤，也会减少上涨时的收益；服务费影响见研究记录。")
        style_panel(self)

    def state(self):
        return {"period": self.phase.get(), "strategy": self.strategy.get(), "tab": self.pages.index(self.pages.select())}

    def restore(self, state):
        if state.get("period") in PHASES:
            self.phase.set(state["period"])
        if state.get("strategy") in LABELS.values():
            self.strategy.set(state["strategy"])
        self.draw()
