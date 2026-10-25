"""Native holdings page bound to one saved experiment and valuation date."""
import tkinter as tk
from tkinter import messagebox, ttk

import pandas as pd

from .data import ROOT
from .holding_view import EVENTS, REASONS, export_snapshot, load_ledger, snapshot


class HoldingsPanel(ttk.Frame):
    def __init__(self, parent, labels, on_select):
        super().__init__(parent, padding=12)
        self.labels, self.on_select = labels, on_select
        self.phase = self.experiment = None
        self.view = None
        basics = pd.read_parquet(ROOT / "data/normalized/stock_basic.parquet")
        self.names = dict(zip(basics.ts_code, basics.name))
        self.prices = pd.read_parquet(ROOT / "data/panels/close.parquet")
        controls = ttk.Frame(self)
        controls.pack(fill="x")
        ttk.Label(controls, text="组合方案").pack(side="left")
        self.strategy = tk.StringVar()
        self.selector = ttk.Combobox(controls, textvariable=self.strategy, state="readonly", width=26)
        self.selector.pack(side="left", padx=8)
        self.selector.bind("<<ComboboxSelected>>", self.choose)
        ttk.Label(controls, text="账本日期").pack(side="left", padx=(12, 4))
        self.date = tk.StringVar()
        self.date_choice = ttk.Combobox(controls, textvariable=self.date, state="readonly", width=13)
        self.date_choice.pack(side="left")
        self.date_choice.bind("<<ComboboxSelected>>", lambda _: self.draw())
        ttk.Button(controls, text="回到期末", command=self.latest).pack(side="left", padx=8)
        ttk.Button(controls, text="导出持仓与流水", command=self.export).pack(side="right")
        self.summary = ttk.Label(self, wraplength=1160, font=("Microsoft YaHei", 12, "bold"))
        self.summary.pack(fill="x", pady=(14, 6))
        self.note = ttk.Label(self, wraplength=1160, style="Sub.TLabel")
        self.note.pack(fill="x", pady=(0, 10))
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True)
        columns = ("code", "name", "shares", "mark", "value", "actual", "target", "gap", "status")
        self.table = ttk.Treeview(frame, columns=columns, show="headings", height=12)
        for key, title, width in zip(columns, ["代码", "公司", "实际股数", "估值价", "持仓市值（元）", "实际权重", "最近目标", "偏离（pp）", "状态"],
                                     [110, 120, 90, 80, 125, 90, 90, 95, 180]):
            self.table.heading(key, text=title)
            self.table.column(key, width=width, minwidth=65, anchor="w" if key in {"code", "name", "status"} else "e")
        y = ttk.Scrollbar(frame, command=self.table.yview)
        y.pack(side="right", fill="y")
        x = ttk.Scrollbar(frame, orient="horizontal", command=self.table.xview)
        x.pack(side="bottom", fill="x")
        self.table.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        self.table.pack(fill="both", expand=True)
        self.table.tag_configure("cash", background="#e4eef7")
        self.table.tag_configure("warning", foreground="#99521f")
        logs = ttk.Frame(self)
        logs.pack(side="bottom", fill="x", before=frame)
        lower = ttk.Frame(logs)
        lower.pack(fill="x", pady=(10, 0))
        ttk.Label(lower, text="成交与未成交记录", font=("Microsoft YaHei", 11, "bold")).pack(side="left")
        self.log_mode = tk.StringVar(value="最近成交")
        chooser = ttk.Combobox(lower, textvariable=self.log_mode, state="readonly", values=["最近成交", "最近执行事件"], width=16)
        chooser.pack(side="left", padx=12)
        chooser.bind("<<ComboboxSelected>>", lambda _: self.draw_log())
        log_body = ttk.Frame(logs)
        log_body.pack(fill="x", pady=(5, 0))
        self.log = tk.Text(log_body, height=5, wrap="word", font=("Microsoft YaHei", 10), relief="flat", padx=10, pady=8)
        log_scroll = ttk.Scrollbar(log_body, command=self.log.yview)
        log_scroll.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=log_scroll.set)
        self.log.pack(fill="x")

    def set_context(self, phase, results):
        self.phase = phase
        self.experiment = None
        self.options = {self.labels[r["strategy"]]: r["id"] for r in results if r["category"] == "portfolio" and r["scenario"] == "base"}
        self.selector.configure(values=list(self.options))
        if self.options:
            preferred = "portfolio_pool_momentum_252_20_base"
            self.set_experiment(preferred if preferred in self.options.values() else next(iter(self.options.values())))
        else:
            self.view = None
            self.table.delete(*self.table.get_children())
            self.summary.configure(text="所选区间没有已完成的组合账本")

    def choose(self, _=None):
        experiment = self.options[self.strategy.get()]
        self.set_experiment(experiment)
        self.on_select(experiment)

    def set_experiment(self, experiment):
        if experiment == self.experiment:
            return
        self.experiment = experiment
        self.strategy.set(next(k for k, v in self.options.items() if v == experiment))
        self.ledger = load_ledger(self.phase, experiment)
        dates = self.ledger["nav"].index.strftime("%Y-%m-%d").tolist()
        self.date_choice.configure(values=dates[::-1])
        self.date.set(dates[-1])
        self.draw()

    def latest(self):
        if self.experiment:
            self.date.set(str(self.ledger["nav"].index[-1].date()))
            self.draw()

    def draw(self):
        date = self.date.get()
        prices = self.prices.loc[pd.Timestamp(date)] if pd.Timestamp(date) in self.prices.index else None
        self.view = snapshot(self.ledger, date, self.names, prices)
        v = self.view
        self.summary.configure(text=f"{date} 收盘账本：实际持有 {v['held_count']} 只 / 最近目标 {v['target_count']} 只\n"
                                    f"总资产 {v['equity']:,.2f}元    股票 {v['market_value']:,.2f}元（{v['stock_weight']:.2%}）    现金 {v['cash']:,.2f}元（{v['cash_weight']:.2%}）    应收权益 {v['receivable']:,.2f}元")
        self.note.configure(text=f"回测模拟账本，非券商实盘。最近目标决策：{v['decision_date'] or '无'}收盘；该目标最早下一交易日才可能成交。\n"
                                "偏离=实际权重−最近目标，仅作核对，不是立即调仓指令。价格变化、整手、费用及执行限制会造成偏离；未持有与残留仓位均保留。新资金试算另见“新资金与风险”。")
        self.table.delete(*self.table.get_children())
        for r in v["rows"]:
            mark = f"{r['mark']:.2f}" if r['mark'] is not None else "—"
            self.table.insert("", "end", values=(r["code"], r["name"], f"{r['shares']:,}", mark, f"{r['market_value']:,.2f}",
                              f"{r['actual_weight']:.2%}", f"{r['target_weight']:.2%}" if r['target_weight'] is not None else "—",
                              f"{r['gap_pp']:+.2f}" if r['gap_pp'] is not None else "—", r["status"]),
                              tags=("warning",) if r["status"] != "持有" else ())
        for label, amount in [("现金", v["cash"]), ("应收权益", v["receivable"])]:
            self.table.insert("", "end", values=("—", label, "—", "—", f"{amount:,.2f}", f"{amount/v['equity']:.2%}", "—", "—", "不计入股票只数"), tags=("cash",))
        self.draw_log()

    def draw_log(self):
        if self.view is None:
            return
        lines = []
        if self.log_mode.get() == "最近成交":
            for r in self.view["trades"].tail(7).iloc[::-1].itertuples():
                lines.append(f"{r.date}　{self.names.get(r.code, r.code)} {r.code}　{'买入' if r.shares > 0 else '卖出'} {abs(r.shares):,}股 × {r.price:.2f}元　费用 {r.fee:.2f}元　信号 {r.decision_date}")
        else:
            for _, r in self.view["events"].tail(7).iloc[::-1].iterrows():
                reason = REASONS.get(r.get("reason"), "")
                lines.append(f"{r['date']}　{r['code']}　{EVENTS.get(r['type'], r['type'])}　{reason}")
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.insert("1.0", "\n".join(lines) or "截至所选日期没有此类记录。")
        self.log.configure(state="disabled")

    def export(self):
        if self.view is not None:
            folder = export_snapshot(self.view, self.phase, self.experiment)
            messagebox.showinfo("已导出", f"持仓、账户、成交与事件已保存：\n{folder}", parent=self)
