"""Independent native desktop reader; opening the app never collects data."""
from __future__ import annotations

import json
import os
import tkinter as tk
from tkinter import ttk

import matplotlib

matplotlib.use("TkAgg")
import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from .data import ROOT
from .enhancement_panel import EnhancementPanel
from .holding_view import load_ledger, snapshot
from .holdings_panel import HoldingsPanel
from .small_capital_v1.panel import SmallCapitalPanel

matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False
LABELS = {"equal_weight": "历史股票池 · 等权基准", "momentum_252_20": "12个月动量 · 20股",
          "momentum_126_20": "6个月动量 · 20股", "momentum_252_10": "12个月动量 · 10股",
          "momentum_252_30": "12个月动量 · 30股", "buy_hold": "买入持有", "trend_200": "200日趋势",
          "trend_200_risk": "200日趋势 + 波动控制", "trend_100": "100日趋势", "trend_250": "250日趋势"}
PHASES = {"development": "开发样本", "validation": "验证样本", "final": "留出原始结果（待修订）", "final_repaired": "留出核算修订结果"}


def read_json(path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def pct(value):
    return f"{value:.1%}" if value is not None else "—"


class Desktop(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Quant Workbench · A股量化研究工作台")
        width = min(1360, self.winfo_screenwidth() - 60)
        height = min(900, self.winfo_screenheight() - 110)
        self.geometry(f"{width}x{height}+12+12")
        self.minsize(min(1080, width), min(740, height))
        self.configure(bg="#eef2f7")
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#eef2f7")
        style.configure("TLabel", background="#eef2f7", font=("Microsoft YaHei", 10))
        style.configure("Title.TLabel", font=("Microsoft YaHei", 22, "bold"), foreground="#142b49")
        style.configure("Sub.TLabel", foreground="#53647c", font=("Microsoft YaHei", 10))
        style.configure("Treeview", rowheight=29, font=("Microsoft YaHei", 10))
        style.configure("Treeview.Heading", font=("Microsoft YaHei", 10, "bold"))
        style.configure("TNotebook.Tab", padding=(22, 11), font=("Microsoft YaHei", 11))
        header = ttk.Frame(self, padding=(25, 18, 25, 12))
        header.pack(fill="x")
        ttk.Label(header, text="A股量化研究工作台", style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text="Portfolio 组合配置  /  单股持仓研究  /  可追溯证据", style="Sub.TLabel").pack(anchor="w", pady=(5, 0))
        controls = ttk.Frame(self, padding=(25, 0, 25, 12))
        controls.pack(fill="x")
        ttk.Label(controls, text="研究区间").pack(side="left")
        self.phase = tk.StringVar(value="final")
        self.phase_display = tk.StringVar(value=PHASES["final"])
        choice = ttk.Combobox(controls, textvariable=self.phase_display, values=list(PHASES.values()), state="readonly", width=17)
        choice.pack(side="left", padx=10)
        choice.bind("<<ComboboxSelected>>", self.choose_phase)
        ttk.Button(controls, text="刷新本地结果", command=self.reload).pack(side="left")
        self.status = ttk.Label(controls, style="Sub.TLabel")
        self.status.pack(side="right")
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=25, pady=(0, 10))
        self.portfolio = ttk.Frame(self.tabs, padding=14)
        self.positions_page = HoldingsPanel(self.tabs, LABELS, self.select_holdings_strategy)
        self.stock = ttk.Frame(self.tabs, padding=14)
        self.outlook = ttk.Frame(self.tabs, padding=14)
        self.quality = ttk.Frame(self.tabs, padding=14)
        self.methods = ttk.Frame(self.tabs, padding=14)
        self.enhancement = EnhancementPanel(self.tabs)
        self.small_capital = SmallCapitalPanel(self.tabs)
        for name, frame in [("组合研究", self.portfolio), ("组合持仓", self.positions_page), ("单股研究", self.stock), ("新资金与风险", self.outlook), ("数据与核验", self.quality), ("方法与边界", self.methods)]:
            self.tabs.add(frame, text=name)
        self.tabs.add(self.enhancement, text="指数增强")
        self.tabs.add(self.small_capital, text="小资金组合")
        ttk.Button(self.portfolio, text="查看所选方案的实际持仓 →", command=lambda: self.tabs.select(self.positions_page)).pack(anchor="e", pady=(0, 6))
        self.portfolio_note = ttk.Label(self.portfolio, wraplength=1180)
        self.portfolio_note.pack(fill="x", pady=(0, 10))
        columns = ("strategy", "return", "drawdown", "vol", "exposure", "trades")
        self.table = ttk.Treeview(self.portfolio, columns=columns, show="headings", height=5, selectmode="browse")
        for col, label, width in zip(columns, ["研究方案", "年化收益", "最大回撤", "年化波动", "平均仓位", "成交笔数"], [310, 130, 130, 130, 130, 100]):
            self.table.heading(col, text=label)
            self.table.column(col, width=width, anchor="w" if col == "strategy" else "center")
        self.table.pack(fill="x")
        self.table.bind("<<TreeviewSelect>>", lambda _: self.draw_portfolio())
        self.port_fig, self.port_canvas = self.make_chart(self.portfolio)
        self.port_details = ttk.Label(self.portfolio, wraplength=1180, style="Sub.TLabel")
        self.port_details.pack(side="bottom", fill="x", pady=(7, 0), before=self.port_canvas.get_tk_widget())
        stock_controls = ttk.Frame(self.stock)
        stock_controls.pack(fill="x")
        self.symbol = tk.StringVar(value="000001.SZ")
        settings = read_json(ROOT / "config/experiments.json", {})
        selector = ttk.Combobox(stock_controls, textvariable=self.symbol, values=settings.get("single_stock_examples", []), state="readonly", width=15)
        selector.pack(side="left")
        selector.bind("<<ComboboxSelected>>", lambda _: self.draw_stock())
        self.stock_note = ttk.Label(stock_controls, text="选择股票查看持仓规则与基准比较", style="Sub.TLabel")
        self.stock_note.pack(side="left", padx=15)
        ttk.Button(stock_controls, text="原始半年报", command=self.open_company_source).pack(side="right")
        ttk.Button(stock_controls, text="完整持仓规则", command=self.open_stock_rules).pack(side="right", padx=8)
        self.stock_fig, self.stock_canvas = self.make_chart(self.stock)
        self.stock_text = self.text_area(self.stock, height=10)
        self.outlook_note = ttk.Label(self.outlook, wraplength=1180)
        self.outlook_note.pack(fill="x", pady=(0, 10))
        holdings_frame = ttk.Frame(self.outlook)
        holdings_frame.pack(fill="x")
        columns = ("code", "name", "model", "shares", "actual", "close")
        self.holdings_table = ttk.Treeview(holdings_frame, columns=columns, show="headings", height=9)
        for col, label, width in zip(columns, ["证券代码", "公司", "原模型目标", "整手试算股数", "试算实际权重", "参考收盘价"], [150, 180, 150, 160, 170, 150]):
            self.holdings_table.heading(col, text=label)
            self.holdings_table.column(col, width=width, anchor="center")
        holdings_scroll = ttk.Scrollbar(holdings_frame, command=self.holdings_table.yview)
        self.holdings_table.configure(yscrollcommand=holdings_scroll.set)
        holdings_scroll.pack(side="right", fill="y")
        self.holdings_table.pack(fill="x")
        risk_controls = ttk.Frame(self.outlook)
        risk_controls.pack(fill="x", pady=(12, 0))
        ttk.Label(risk_controls, text="条件风险情景 · 未来交易日数").pack(side="left")
        self.horizon = tk.StringVar(value="60")
        horizon = ttk.Combobox(risk_controls, textvariable=self.horizon, values=["20", "60", "120"], state="readonly", width=8)
        horizon.pack(side="left", padx=10)
        horizon.bind("<<ComboboxSelected>>", lambda _: self.draw_outlook())
        self.risk_text = self.text_area(self.outlook, height=9)
        self.quality_text = self.text_area(self.quality)
        self.method_text = self.text_area(self.methods)
        ttk.Label(self, text="研究输出 · 日线成交假设 · 股息税前 · 历史结果不保证未来表现", style="Sub.TLabel").pack(side="bottom", anchor="w", padx=27, pady=(0, 10), before=self.tabs)
        self.rows = []
        # Select the latest completed phase on first opening, without running it.
        for name in ["final_repaired", "final", "validation", "development"]:
            if (ROOT / f"artifacts/research/{name}/summary.json").exists():
                self.phase.set(name)
                self.phase_display.set(PHASES[name])
                break
        self.reload()
        self.tabs.select(self.small_capital if self.small_capital.data else self.enhancement if self.enhancement.data else self.positions_page)

    def select_holdings_strategy(self, experiment):
        if self.table.exists(experiment):
            self.table.selection_set(experiment)

    def open_stock_rules(self):
        window = tk.Toplevel(self)
        window.title("单股持仓方案 · 完整说明")
        window.geometry("920x720")
        text = self.text_area(window)
        path = ROOT / "research/single_stock_holding_guide.md"
        self.set_text(text, path.read_text(encoding="utf-8") if path.exists() else "说明文件暂不可用。")

    def choose_phase(self, _):
        self.phase.set(next(k for k, v in PHASES.items() if v == self.phase_display.get()))
        self.reload()

    def open_company_source(self):
        report = read_json(ROOT / f"artifacts/company/{self.symbol.get()}/snapshot.json", {})
        relative = report.get("primary_report_review", {}).get("source", {}).get("path")
        if relative:
            path = (ROOT / relative).resolve()
            if path.is_relative_to(ROOT.resolve()) and path.is_file():
                os.startfile(path)

    def make_chart(self, parent):
        figure = Figure(figsize=(10, 4.2), dpi=100, facecolor="#eef2f7")
        canvas = FigureCanvasTkAgg(figure, master=parent)
        canvas.get_tk_widget().configure(height=250)
        canvas.get_tk_widget().pack(fill="both", expand=True, pady=(12, 4))
        return figure, canvas

    def text_area(self, parent, height=None):
        container = ttk.Frame(parent)
        container.pack(fill="both", expand=True)
        text = tk.Text(container, wrap="word", font=("Microsoft YaHei", 10), bg="#ffffff", fg="#25374b", relief="flat", padx=15, pady=12, height=height or 20)
        scroll = ttk.Scrollbar(container, command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        text.pack(fill="both", expand=True)
        return text

    @staticmethod
    def set_text(widget, value):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def reload(self):
        self.enhancement.load(self.phase.get())
        self.small_capital.load()
        self.summary = read_json(ROOT / f"artifacts/research/{self.phase.get()}/summary.json", {})
        self.rows = self.summary.get("results", [])
        self.positions_page.set_context(self.phase.get(), self.rows)
        collection = read_json(ROOT / "artifacts/collection_status.json", {})
        stage = "已完成" if collection.get("stage") == "complete" else "采集中 / 未完成"
        self.status.configure(text=f"数据采集：{stage}   {collection.get('completed', collection.get('symbols', 0))}/{collection.get('total', 667)}")
        for item in self.table.get_children():
            self.table.delete(item)
        for row in self.rows:
            if row["category"] == "portfolio" and row["scenario"] == "base":
                self.table.insert("", "end", iid=row["id"], values=(LABELS.get(row["strategy"], row["strategy"]), pct(row["cagr"]), pct(row["max_drawdown"]), pct(row["volatility"]), pct(row["average_exposure"]), row["trade_count"]))
        phase_label = {"development": "开发样本，不能据此推荐", "validation": "验证样本", "final": "原始留出：含两项换股漏记，仅保留审计", "final_repaired": "查看留出后的换股核算修订；规则不变，并非新的未接触检验"}[self.phase.get()]
        note = f"{self.summary.get('start', '—')} 至 {self.summary.get('end', '—')} · {phase_label} · 固定规则，统一费用与成交口径。"
        if not self.rows:
            note = "该研究区间尚无已完成结果。工作台仅展示本地真实结果；打开窗口不会采集数据或启动回测。"
        self.portfolio_note.configure(text=note)
        items = self.table.get_children()
        if items:
            preferred = "portfolio_pool_momentum_252_20_base"
            self.table.selection_set(preferred if preferred in items else items[0])
        self.draw_portfolio()
        self.draw_stock()
        self.draw_quality()
        self.draw_outlook()
        path = ROOT / "research/methodology.md"
        content = path.read_text(encoding="utf-8") if path.exists() else (ROOT / "research/protocol.md").read_text(encoding="utf-8")
        self.set_text(self.method_text, content)

    def nav(self, row):
        path = ROOT / f"artifacts/research/{self.phase.get()}" / row["id"] / "nav.parquet"
        return pd.read_parquet(path)

    def plot(self, figure, canvas, rows):
        figure.clear()
        axes = figure.subplots(2, 1, sharex=True, gridspec_kw={"height_ratios": [2, 1]})
        if not rows:
            axes[0].text(.5, .5, "尚无完成的研究结果", ha="center", va="center", transform=axes[0].transAxes, fontsize=14, color="#53647c")
        for row, color in zip(rows, ["#126caa", "#b8873d", "#209586"]):
            nav = self.nav(row)
            wealth = nav.equity / self.summary.get("initial_cash", 1_000_000)
            drawdown = wealth / wealth.cummax().clip(lower=1) - 1
            label = LABELS.get(row["strategy"], row["strategy"])
            axes[0].plot(nav.index, wealth, label=label, color=color, linewidth=1.5)
            axes[1].plot(nav.index, drawdown * 100, color=color, linewidth=1)
        axes[0].set_ylabel("净值（初始=1）")
        axes[1].set_ylabel("回撤 %")
        for ax in axes:
            ax.set_facecolor("#ffffff")
            ax.grid(alpha=.16)
            ax.spines[["top", "right"]].set_visible(False)
        if rows:
            axes[0].legend(loc="upper left", frameon=True, facecolor="white", framealpha=.92, fontsize=9)
        figure.tight_layout(pad=1.5)
        canvas.draw_idle()

    def draw_portfolio(self):
        selected = self.table.selection()
        chosen = next((r for r in self.rows if selected and r["id"] == selected[0]), None)
        baseline = next((r for r in self.rows if r["id"] == "portfolio_pool_equal_weight_base"), None)
        rows = [r for r in [chosen, baseline] if r is not None]
        if chosen == baseline:
            rows = rows[:1]
        self.plot(self.port_fig, self.port_canvas, rows)
        if chosen:
            self.positions_page.set_experiment(chosen["id"])
            comparison = chosen.get("comparison", {})
            note = f"累计费用 {chosen['fees']:,.0f} 元；滑点影响 {chosen['slippage']:,.0f} 元；年双边换手 {chosen['annual_two_way_turnover']:.1f} 倍。"
            audit = chosen.get("holding_quality", {})
            if audit.get("ledger_status") == "needs_review":
                note += f" 核算待复核：{len(audit.get('unresolved_events_held', []))}项持仓事件。"
            if audit.get("long_stale_max_weight", 0) > 0:
                note += " 曾有超过20日无报价的持仓。"
            if comparison.get("supported"):
                note += f" 相对等权的年化算术收益差95%区间：{pct(comparison['lower_95'])} 至 {pct(comparison['upper_95'])}（未作全部试验多重校正）。"
            if baseline and abs(chosen['average_exposure'] - baseline['average_exposure']) > .05:
                note += f" 股票暴露：本策略{pct(chosen['average_exposure'])}、等权{pct(baseline['average_exposure'])}；收益差包含仓位差异。"
            self.port_details.configure(text=note)
        else:
            self.port_details.configure(text="数据口径、未成交和费用明细将与每次研究结果一并保存。")

    def draw_stock(self):
        rows = [r for r in self.rows if r["symbol"] == self.symbol.get() and r["scenario"] == "base" and r["strategy"] in ["trend_200", "buy_hold", "trend_200_risk"]]
        rows.sort(key=lambda r: ["trend_200", "buy_hold", "trend_200_risk"].index(r["strategy"]))
        self.plot(self.stock_fig, self.stock_canvas, rows)
        lines = [f"{self.symbol.get()} · 收益与风险分别评价"]
        for row in rows:
            lines.append(f"{LABELS[row['strategy']]}：年化 {pct(row['cagr'])}，最大回撤 {pct(row['max_drawdown'])}，平均仓位 {pct(row['average_exposure'])}。")
        risk_row = next((r for r in rows if r['strategy'] == 'trend_200_risk'), None)
        if risk_row:
            ledger = load_ledger(self.phase.get(), risk_row['id'])
            view = snapshot(ledger, ledger['nav'].index[-1])
            held = next((r['shares'] for r in view['rows'] if r['code'] == self.symbol.get()), 0)
            lines += ["", f"所选区间风险方案的实际账本（{view['asof']}）：{held:,}股，股票权重{view['stock_weight']:.2%}，现金{view['cash']:,.2f}元。",
                      f"最近已登记目标日期：{view['decision_date']}；目标与实际可能因价格漂移、整手和执行限制不同。",
                      "规则：收盘价严格高于200日均线才持有；风险权重=min(100%, 15%÷60日年化波动)。",
                      "纯趋势每日检查；风险版本仅按周检查和调整，最早下一交易日成交。没有固定百分比止损。完整解释见上方按钮。"]
        report = read_json(ROOT / f"artifacts/company/{self.symbol.get()}/snapshot.json", {})
        outlook = read_json(ROOT / f"artifacts/outlook/{self.symbol.get()}.json", {})
        if report:
            self.stock_note.configure(text=f"{report['name']} · {report['market_date']} 收盘 {report['price']:.2f}元")
            f = report['financial']
            lines += ["", f"财报期 {report['statement_period']} · 主要数据已与公司原始半年报核对",
                      f"营业收入 {f['revenue_ytd']/1e8:,.2f}亿元（同比{pct(f['revenue_yoy'])}）　归母利润 {f['parent_profit_ytd']/1e8:,.2f}亿元（同比{pct(f['parent_profit_yoy'])}）"]
            for field, label in [("pe_ttm", "市盈率TTM"), ("pb", "市净率")]:
                v = report['valuation'][field]
                current = f"{v['current']:.2f}" if v['current'] is not None else "未知"
                lines.append(f"{label} {current} · 自身近5年正值分位 {pct(v['percentile'])}，分位不等于低估。")
            review = report.get('primary_report_review', {})
            lines += ["", *review.get('observations', []), "", "持仓研究关注：" + review.get('holding_questions', '待核查')]
            if outlook:
                lines += ["", f"截至{outlook['asof']}：200日趋势{'开启' if outlook['trend_on'] else '关闭'}；60日波动估计{pct(outlook['estimated_volatility_60d'])}。",
                          f"风险控制规则的子账户内股票权重 {pct(outlook['trend_risk_sleeve_weight'])}；这不是家庭总资产建议仓位。",
                          f"教学示例：若以账户1%损失预算承受单股20%跳跌，仓位上限5%；结合当前信号后为{pct(outlook['illustrative_total_account_weight'])}。更大跳跌仍可能突破预算。"]
        else:
            lines.append("\n公司财务与估值研究尚在准备；当前不生成未经支持的操作判断。")
        self.set_text(self.stock_text, "\n".join(lines))

    def draw_outlook(self):
        p = read_json(ROOT / "artifacts/outlook/portfolio.json", {})
        for item in self.holdings_table.get_children():
            self.holdings_table.delete(item)
        if not p:
            self.outlook_note.configure(text="持仓试算与条件风险情景尚未生成。")
            return
        account = p['illustrative_cash_account']
        zero_lots = sum(r['illustrative_shares'] == 0 for r in account['rows'])
        self.outlook_note.configure(text=f"研究试算，非已通过样本外检验的配置建议。观察日 {p['asof']} · 最近月度信号 {p['last_scheduled_decision']} · 新建{account['capital']/1e4:,.0f}万元现金账户。\n"
                                   f"预计剩余现金 {account['cash_after_estimated_costs']:,.0f}元；{zero_lots}只因最小交易单位无法配置。下次月末重新评估，以下不是即时买卖指令。")
        for row in account['rows']:
            self.holdings_table.insert("", "end", values=(row['code'], row['name'], pct(row['model_weight']), row['illustrative_shares'], pct(row['portfolio_weight']), f"{row['reference_close']:.2f}"))
        horizon = self.horizon.get()
        risks = p['risk'].get('horizons', {}).get(horizon, {})
        lines = [f"组合：{horizon}个交易日条件模拟 · 实际试算权重 + 现金 · 10,000条路径", ""]
        for key, label in [("joint_historical_block_bootstrap", "历史收益分块重采样"),
                           ("joint_zero_sample_arithmetic_mean_bootstrap", "剔除历史平均收益"),
                           ("specified_all_equities_minus20pct_jump", "股票共同跳跌20%压力")]:
            r = risks.get(key)
            if r:
                lines.append(f"{label}：期末收益5%分位 {pct(r['terminal_p05'])}，中位数 {pct(r['terminal_median'])}，最差5%路径平均收益 {pct(r['mean_worst_5pct_return'])}。")
        lines += ["", "单股：零算术漂移GBM的期末收益5%分位（假设全额持有该股票；并非总账户风险）"]
        for s in read_json(ROOT / "artifacts/outlook/index.json", {}).get('stocks', []):
            detail = read_json(ROOT / f"artifacts/outlook/{s['code']}.json", {})
            r = detail.get('risk', {}).get('horizons', {}).get(horizon, {}).get('gbm_zero_arithmetic_drift')
            if r:
                lines.append(f"{s['name']}  {pct(r['terminal_p05'])}　· 趋势{'开启' if s['trend_on'] else '关闭'}　· 子账户规则权重{pct(s['trend_risk_sleeve_weight'])}")
        lines += ["", "这些分位数依赖模型与样本，不是校准后的未来概率或止损保证。历史重采样保留同期相关性，仍可能低估新冲击。当前行业分组仅作描述，未作为历史中性化约束。"]
        self.set_text(self.risk_text, "\n".join(lines))

    def draw_quality(self):
        quality = read_json(ROOT / "artifacts/data_quality.json") or read_json(ROOT / "artifacts/partial_data_quality.json", {})
        issues = quality.get("issues", [])
        scope = "完整样本" if quality.get('scope') == 'complete' else "部分样本 / 待审计"
        lines = [f"数据审计范围：{scope} / {quality.get('symbols', 0)}只股票",
                 "原始响应保留内容哈希，标准化数据与公司行动修订分开保存。", ""]
        for level, label in [("critical", "阻断级"), ("high", "尚待解释"), ("low", "轻微记录"), ("info", "来源修订及已复核记录")]:
            lines.append(f"{label}：{sum(i['severity'] == level for i in issues)}项")
        suspension = quality.get('suspensions', {})
        counts = suspension.get('totals', {})
        lines += ["", f"上市期间缺失报价 {counts.get('missing_during_listing', '—')} 个交易日；日常停牌解释 {counts.get('suspension_rows_match', '—')}；暂停上市公告补充解释 {counts.get('listing_suspension_only_match', '—')}；未解释 {suspension.get('unexplained_count', '—')}。",
                  "停牌解释完整不代表持仓可卖出；陈旧估值和退市风险仍须单独检查。"]
        lines += ["", "主要限制：", "历史成分使用上月月末快照代理，缺少完整原始公告时刻。",
                  "当前行业分类仅作描述；股息尚未扣投资者差别化红利税。",
                  "缺失报价禁止成交。已审阅配股默认不参与，保留原价稀释损失。",
                  "差异化分红按普通股东权益核算；交易所除权参考价可能采用不同分母。",
                  "本次5项未解决高等级问题未影响已登记实验持仓及可排名信号窗口，不能推广为全部数据无误。",
                  "", "留出核算修订：原始结果保留，修订并非新的未接触检验。",
                  "信达证券待换股权利沿用旧报价估值3112元；不是可卖出的现金。",
                  "", "需优先核查的记录："]
        types = {"unresolved_shareholder_entitlement": "股东实际获配权益待核实", "action_factor_mismatch": "公司行动与复权因子差异", "unexplained_factor_change": "历史复权因子变化待解释"}
        for issue in issues:
            if issue["severity"] in ["critical", "high"]:
                lines.append(f"{issue['code']} | {types.get(issue['type'], issue['type'])} | {issue.get('date', issue.get('dates', ''))}")
        self.set_text(self.quality_text, "\n".join(lines))


def main():
    Desktop().mainloop()


if __name__ == "__main__":
    main()
