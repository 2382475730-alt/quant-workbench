"""Native, read-only presentation of sealed index-enhancement experiments."""
from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk

import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from .data import ROOT

NAMES = {"momentum_constrained": "约束动量主方案", "defensive_constrained": "防御备选", "etf_reference": "ETF对照"}


def pct(value):
    return f"{value:.2%}" if value is not None else "—"


def table(parent, specs, height=8):
    box = ttk.Frame(parent)
    box.pack(fill="both", expand=True)
    view = ttk.Treeview(box, columns=[s[0] for s in specs], show="headings", height=height, selectmode="browse")
    for key, label, width in specs:
        view.heading(key, text=label)
        view.column(key, width=width, minwidth=65, anchor="w" if key in {"name", "code", "industry", "status"} else "e")
    scroll = ttk.Scrollbar(box, command=view.yview)
    view.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    view.pack(fill="both", expand=True)
    return view


class EnhancementPanel(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=12)
        self.data, self.phase_data, self.phase = {}, {}, "review"
        self.note = ttk.Label(self, wraplength=1180, foreground="#943e21")
        self.note.pack(fill="x", pady=(0, 7))
        controls = ttk.Frame(self)
        controls.pack(fill="x", pady=(0, 7))
        ttk.Label(controls, text="持仓与约束方案").pack(side="left")
        self.strategy = tk.StringVar(value=NAMES["momentum_constrained"])
        choice = ttk.Combobox(controls, textvariable=self.strategy, values=list(NAMES.values()), width=21, state="readonly")
        choice.pack(side="left", padx=8)
        choice.bind("<<ComboboxSelected>>", lambda _: self.draw_holdings())
        ttk.Button(controls, text="完整研究报告", command=lambda: self.open_text("reports/enhancement_v1/report.md", "指数增强研究报告")).pack(side="right")
        ttk.Button(controls, text="Agent如何复刻", command=lambda: self.open_text("research/quant_agent_design.md", "量化Agent设计与运行")).pack(side="right", padx=8)
        self.pages = ttk.Notebook(self)
        self.pages.pack(fill="both", expand=True)
        overview, holdings, industries, audit = [ttk.Frame(self.pages, padding=8) for _ in range(4)]
        for name, frame in [("公平比较", overview), ("实际持仓", holdings), ("行业偏离", industries), ("约束与压力检验", audit)]:
            self.pages.add(frame, text=name)
        self.comparison = table(overview, [("name", "方案（存档保留）", 250), ("return", "累计收益", 100),
                                         ("excess", "相对全收益", 110), ("dd", "最大回撤", 105),
                                         ("te", "实现跟踪误差", 125), ("cost", "费用+滑点 元", 120)], height=10)
        self.comparison.bind("<<TreeviewSelect>>", lambda _: self.draw_curve())
        self.figure = Figure(figsize=(10, 2.4), dpi=100, facecolor="#eef2f7")
        self.canvas = FigureCanvasTkAgg(self.figure, master=overview)
        self.canvas.get_tk_widget().configure(height=185)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, pady=(8, 0))
        self.account = ttk.Label(holdings, wraplength=1160)
        self.account.pack(fill="x", pady=(0, 8))
        self.holdings_table = table(holdings, [("code", "代码", 115), ("name", "证券", 140), ("industry", "行业", 130),
                                             ("shares", "实际股/份数", 100), ("value", "市值 元", 120),
                                             ("actual", "实际权重", 100), ("target", "最近目标", 100), ("gap", "偏差 pp", 100)], height=13)
        self.holdings_table.tag_configure("breach", foreground="#a32b20")
        ttk.Label(holdings, text="实际持仓来自模拟成交账本；最近目标不是立即交易指令。现金与应收单列；非券商账户。", style="Sub.TLabel").pack(anchor="w", pady=6)
        self.industry_note = ttk.Label(industries, wraplength=1150)
        self.industry_note.pack(fill="x", pady=(0, 7))
        self.industry_table = table(industries, [("industry", "申万一级行业", 230), ("benchmark", "基准行业权重", 190),
                                               ("actual", "实际穿透权重", 190), ("gap", "主动偏离 pp", 170), ("status", "3pp预算检查", 160)], height=15)
        self.industry_table.tag_configure("breach", foreground="#a32b20")
        self.audit = tk.Text(audit, wrap="word", font=("Microsoft YaHei", 10), bg="white", relief="flat", padx=15, pady=12)
        scroll = ttk.Scrollbar(audit, command=self.audit.yview)
        self.audit.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.audit.pack(fill="both", expand=True)

    def load(self, phase):
        self.phase = phase if phase in {"development", "validation"} else "review"
        path = ROOT / "reports/enhancement_v1/dashboard.json"
        if not path.exists():
            self.note.configure(text="指数增强报告尚未生成；不展示未完成或虚构结果。")
            return
        self.data = json.loads(path.read_text(encoding="utf-8"))
        self.phase_data = self.data["phases"][self.phase]
        self.note.configure(text=f"{self.phase_data['start']}—{self.phase_data['end']} · {self.data['version']} · 全部为已见历史回溯，尚无前向证据；实际约束仍可能超限。")
        self.comparison.delete(*self.comparison.get_children())
        for row in self.phase_data["rows"]:
            self.comparison.insert("", "end", iid=row["key"], values=(row["name"], pct(row["total_return"]), pct(row["relative_return"]),
                                                                       pct(row["max_drawdown"]), pct(row["tracking_error"]), f"{row['fees']+row['slippage']:,.0f}"))
        self.comparison.selection_set("momentum_constrained")
        self.draw_curve()
        self.draw_holdings()

    def draw_curve(self):
        if not self.phase_data:
            return
        selected = self.comparison.selection()
        key = selected[0] if selected else "momentum_constrained"
        curves = pd.read_csv(ROOT/self.phase_data["curves_file"], index_col=0, parse_dates=True)
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        names = {r["key"]: r["name"] for r in self.phase_data["rows"]}
        colors = {"benchmark": "#ad7700", "etf_reference": "#8a94a1"}
        for series in dict.fromkeys(["benchmark", "etf_reference", key]):
            color = colors.get(series, "#176aa2")
            ax.plot(curves.index, curves[series], color=color, label=names[series], linewidth=1.3)
        ax.grid(alpha=.2)
        ax.legend(loc="upper left", fontsize=8, ncol=3)
        ax.set_ylabel("初始净值=1")
        self.figure.tight_layout(pad=.8)
        self.canvas.draw_idle()

    def draw_holdings(self):
        if not self.phase_data:
            return
        key = next(k for k, v in NAMES.items() if v == self.strategy.get())
        self.view = self.phase_data["holdings"][key]
        view = self.view
        breached = sum(r["code"] != "510300.SH" and r["actual_weight"] > .030002 for r in view["rows"])
        self.account.configure(text=f"账本日期 {view['asof']}  |  最近已接受目标 {view['decision_date']}\n"
                               f"总权益 {view['equity']:,.2f}元  =  证券 {view['market_value']:,.2f}  +  现金 {view['cash']:,.2f}  +  应收 {view['receivable']:,.2f}；现金权重 {pct(view['cash_weight'])}；{breached}只直接持股超过3%（红色）")
        self.holdings_table.delete(*self.holdings_table.get_children())
        for row in view["rows"]:
            self.holdings_table.insert("", "end", values=(row["code"], row["name"], row["industry"], f"{row['shares']:,}",
                                                          f"{row['market_value']:,.2f}", pct(row["actual_weight"]), pct(row["target_weight"]),
                                                          f"{row['gap_pp']:+.2f}" if row["gap_pp"] is not None else "—"),
                                       tags=("breach",) if row["code"] != "510300.SH" and row["actual_weight"] > .030002 else ())
        self.industry_note.configure(text=f"参考权重日期 {view['industry_weight_date']}。{view['industry_boundary']}。现金也会造成相对指数的行业低配。")
        self.industry_table.delete(*self.industry_table.get_children())
        for row in view["sectors"]:
            breach = abs(row["gap"]) > .030002
            self.industry_table.insert("", "end", values=(row["industry"], pct(row["benchmark_weight"]), pct(row["actual_weight"]), f"{row['gap']*100:+.2f}",
                                                          "超限" if breach else "预算内"), tags=("breach",) if breach else ())
        self.draw_audit(key)

    def draw_audit(self, key):
        row = self.phase_data["details"][key]
        constraints = row["actual_constraints"]
        active = next(r for r in self.phase_data["rows"] if r["key"] == key)
        lines = [f"{NAMES[key]} · {self.phase_data['label']} · v1r4",
                 "外部预算：行业±3pp；直接单股≤3%；ETF≥50%；预测TE≤4%；预测波动≤指数1.10倍；月度单边换手≤15%。",
                 "整数目标采用更小缓冲；目标检查不等于每日实际合规。ETF穿透并不受直接单股3%上限约束。",
                 f"最新参考下行业超限 {constraints['industry_violation_days']}/{row['days']}天，最大偏离 {pct(constraints['max_actual_industry_deviation'])}。",
                 f"直接单股超限 {constraints['direct_stock_cap_violation_days']}天；ETF底仓不足 {constraints['core_floor_violation_days']}天。",
                 f"实际调仓换手超限 {constraints['executed_turnover_violations']}次；不含首次最大单边换手 {pct(constraints['max_monthly_one_way_excluding_initial'])}。",
                 f"调仓未接受/失败 {row['solver_failed_or_held']}/{row['decision_count']}次；失败保持实际持仓，不暗中放宽约束。",
                 f"全区间实现TE {pct(active['tracking_error'])}；63日滚动TE最高 {pct(row['vs_total_return_index']['rolling_63d_te_max'])}。",
                 f"24项比较校正的年化日均主动收益区间：[{pct(active['familywise_lower'])}, {pct(active['familywise_upper'])}]。",
                 "此区间不是未来盈利概率，不是CAGR差置信区间；不能消除事后研究偏差。", "", "固定压力情景（不据此选参数）"]
        labels = {"base": "基础费用/次日", "double_cost": "双倍费用滑点", "extra_delay": "额外延迟一日"}
        for stress in self.phase_data["stress"]:
            if stress["strategy"] == key:
                lines.append(f"{labels[stress['scenario']]}：累计 {pct(stress['total_return'])}；相对全收益 {pct(stress['vs_total_return_index']['geometric_relative_return'])}；失败调仓 {stress['solver_failed_or_held']}次。")
        lines += ["", "证据边界：历史行业及指数权重为供应商回溯快照，非完整公告时间档案；ETF涨跌停采用披露模型；股息税前。",
                  "旧方案与失败版本全部保留。当前应作为研究/模拟工具，不能据此宣布可靠跑赢或直接实盘。",
                  "Agent工具层可执行状态、完整性核验、固定实验、报告；尚未连接大模型或券商。"]
        self.audit.configure(state="normal")
        self.audit.delete("1.0", "end")
        self.audit.insert("1.0", "\n\n".join(lines))
        self.audit.configure(state="disabled")

    def open_text(self, relative, title):
        window = tk.Toplevel(self)
        window.title(title)
        window.geometry("1000x760")
        widget = tk.Text(window, wrap="word", font=("Microsoft YaHei", 11), padx=20, pady=15)
        scroll = ttk.Scrollbar(window, command=widget.yview)
        widget.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        widget.pack(fill="both", expand=True)
        path = ROOT/relative
        widget.insert("1.0", path.read_text(encoding="utf-8") if path.exists() else "报告尚未生成。")
        widget.configure(state="disabled")
