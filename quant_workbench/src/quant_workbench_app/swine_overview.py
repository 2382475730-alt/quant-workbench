"""Source-backed swine overview, independent of the frozen strategy snapshot."""
import csv
from datetime import datetime
import json
import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from zoneinfo import ZoneInfo

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.dates import DateFormatter, MonthLocator, date2num
from matplotlib.figure import Figure

from .paths import PROJECT, RUNTIME, SETTINGS
from .swine_data import read
from .widgets import table, text_panel, set_text

OVERVIEW_ROOT = PROJECT / SETTINGS.get('swine_overview_root', 'runtime/research/swine_overview_20261029')
from .ui_presentation import NOTE_COLOR, UP_COLOR, DOWN_COLOR, change_color


def capacity_zone(value, target=3750, limits=(.88, .92, 1.03, 1.06)):
    """Inclusive green endpoints; inclusive outer yellow endpoints."""
    low_red, low_green, high_green, high_red = [target * x for x in limits]
    if value < low_red:
        return '红色区域 · 产能过度减少', '#a54848'
    if value < low_green:
        return '黄色区域 · 产能大幅减少', '#986b25'
    if value <= high_green:
        return '绿色区域 · 产能正常波动', '#35755d'
    if value <= high_red:
        return '黄色区域 · 产能大幅增加', '#986b25'
    return '红色区域 · 产能过度增加', '#a54848'


def cost_text(cost):
    if cost is None:
        return '未核实可比值'
    qualifier = {'upper': '≤', 'strict_upper': '＜', 'approximate': '约'}.get(cost['qualifier'], '')
    return qualifier + f"{cost['value']:.2f}"


class OverviewMixin:
    def build_overview(self):
        self.overview_data = read(OVERVIEW_ROOT / 'overview.json')
        self.overview_sources = {s['id']: s for s in read(OVERVIEW_ROOT / 'sources.json')}
        self.overview_profiles = {r['code']: r for r in self.overview_data['companies']}
        self.overview_change_labels = []
        page = ttk.Frame(self.pages)
        self.frames['overview'] = page
        self.pages.insert(0, page, text='研究总览')
        self.pages.select(page)
        style = ttk.Style(self)
        style.configure('Overview.Treeview', rowheight=42, font=('Microsoft YaHei', 11),
                        background='white', fieldbackground='white', foreground='#253b50',
                        borderwidth=0)
        style.configure('Overview.Treeview.Heading', font=('Microsoft YaHei', 10, 'bold'),
                        background='#edf2f6', foreground='#516579', padding=(10, 12),
                        relief='flat', borderwidth=0)
        style.map('Overview.Treeview', background=[('selected', '#e5eef6')],
                  foreground=[('selected', '#193550')])
        style.map('Overview.Treeview.Heading', background=[('active', '#e5edf4')])
        style.configure('Overview.TButton', font=('Microsoft YaHei', 10), padding=(12, 8))
        style.configure('Overview.Primary.TButton', font=('Microsoft YaHei', 10),
                        padding=(14, 9), background='#315b7a', foreground='white', borderwidth=0)
        style.map('Overview.Primary.TButton', background=[('active', '#244a69')])

        surface = tk.Canvas(page, background='#f4f6f9', highlightthickness=0, yscrollincrement=24)
        scroll = ttk.Scrollbar(page, orient='vertical', command=surface.yview)
        surface.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        surface.pack(side='left', fill='both', expand=True)
        content = tk.Frame(surface, bg='#f4f6f9', padx=24, pady=18)
        item = surface.create_window((0, 0), window=content, anchor='nw')
        surface.bind('<Configure>', lambda event: surface.itemconfigure(item, width=event.width))
        content.bind('<Configure>', lambda event: surface.configure(scrollregion=surface.bbox('all')))
        self.overview_scroll, self.overview_content = surface, content

        header = tk.Frame(content, bg='#f4f6f9')
        header.pack(fill='x', pady=(0, 12))
        actions = tk.Frame(header, bg='#f4f6f9')
        actions.pack(side='right', anchor='center')
        for text, command in [('公司对比 ↓', self.scroll_to_overview_companies),
                              ('数据来源', self.open_overview_sources), ('导出', self.export_overview)]:
            ttk.Button(actions, text=text, command=command, style='Overview.TButton').pack(side='left', padx=(8, 0))
        self.overview_label(header, '产能与价格', size=16, bold=True, bg='#f4f6f9')
        self.overview_label(header, '数据观察日 ' + self.overview_data['as_of'], size=10, color=NOTE_COLOR,
                            bg='#f4f6f9', pady=(5, 0))
        charts = tk.Frame(content, bg='#f4f6f9')
        charts.pack(fill='x')
        charts.columnconfigure(0, weight=3, uniform='overview_charts')
        charts.columnconfigure(1, weight=2, uniform='overview_charts')
        self.overview_capacity_card = tk.Frame(charts, bg='white', padx=20, pady=18)
        self.overview_capacity_card.grid(row=0, column=0, sticky='nsew', padx=(0, 9))
        self.overview_price_card = tk.Frame(charts, bg='white', padx=20, pady=18)
        self.overview_price_card.grid(row=0, column=1, sticky='nsew', padx=(9, 0))
        latest = self.overview_data['capacity'][-1]
        status, color = capacity_zone(latest['sows'])
        self.overview_capacity_status = status
        self.metric_heading(self.overview_capacity_card, '全国能繁母猪存栏',
                            f"{latest['sows']:,.0f}", '万头',
                            f"{latest['date'][:4]}年{int(latest['date'][5:7])}月末",
                            lambda: self.open_overview_metric('capacity'),
                            [('同比', latest['yoy_pct']), ('较上季', latest['mom_pct'])])
        self.overview_status_label = self.overview_label(
            self.overview_capacity_card, status, size=9, color=color, pady=(6, 0))
        price = self.overview_data['latest_price']
        previous = self.overview_data['price_comparison'][-2]
        change = (price['hog'] / previous['hog'] - 1) * 100
        self.metric_heading(self.overview_price_card, '全国生猪价格', f"{price['hog']:.2f}",
                            '元/公斤', f"采集 {price['observation_date']}",
                            lambda: self.open_overview_metric('price'), [('较前周', change)])
        self.overview_label(self.overview_price_card, '集贸市场周样本 · 非月均价',
                            size=10, color=NOTE_COLOR, pady=(6, 0))
        self.draw_overview_charts(charts)

        self.overview_metric_cards = []
        cards = tk.Frame(content, bg='#f4f6f9')
        cards.pack(fill='x', pady=(16, 30))
        for column, (key, title) in enumerate([
            ('hog_inventory', '全国生猪存栏'), ('slaughter', '生猪出栏量'),
            ('pork_output', '猪肉产量'), ('psy', '行业 PSY（样本）')]):
            cards.columnconfigure(column, weight=1, uniform='overview_metric')
            row = self.overview_data['psy'] if key == 'psy' else self.overview_data['industry'][key]
            value = f"{row['value']:,.2f}" if key == 'psy' else f"{row['value']:,.0f}"
            note = '2025年 · 微猪行业样本' if key == 'psy' else row['period']
            card = tk.Frame(cards, bg='white', padx=16, pady=16, cursor='hand2')
            card.grid(row=0, column=column, sticky='nsew', padx=(0 if column == 0 else 8, 0 if column == 3 else 8))
            self.overview_label(card, title, size=10, color=NOTE_COLOR)
            values = tk.Frame(card, bg='white')
            values.pack(anchor='w', pady=(13, 10))
            tk.Label(values, text=value, font=('Microsoft YaHei', 21, 'bold'),
                     bg='white', fg='#193550').pack(side='left')
            tk.Label(values, text='  ' + ('头/年' if key == 'psy' else row['unit']),
                     font=('Microsoft YaHei', 10), bg='white', fg=NOTE_COLOR).pack(side='left', pady=(8, 0))
            self.change_note(card, note, [] if key == 'psy' else [('同比', row['yoy_pct'])])
            self.bind_overview_click(card, lambda metric=key: self.open_overview_metric(metric))
            self.overview_metric_cards.append(card)

        company = tk.Frame(content, bg='white', padx=22, pady=22)
        company.pack(fill='x')
        self.overview_company_section = company
        company_header = tk.Frame(company, bg='white')
        company_header.pack(fill='x', pady=(0, 18))
        ttk.Button(company_header, text='返回行业 ↑', command=lambda: surface.yview_moveto(0),
                   style='Overview.TButton').pack(side='right')
        self.overview_label(company_header, '公司比较', size=16, bold=True)
        self.overview_label(company_header, '六家公司 · 成本、现金储备、杠杆与估值',
                            size=10, color=NOTE_COLOR, pady=(6, 0))
        table_frame = tk.Frame(company, bg='white')
        table_frame.pack(fill='x')
        columns = [('公司', 100), ('完全成本/元kg', 132), ('成本期间', 95),
                   ('可动用现金/亿元', 148), ('资产负债率', 110), ('PB*', 70), ('现金/负债期间', 145)]
        tree = ttk.Treeview(table_frame, columns=[str(i) for i in range(len(columns))],
                            show='headings', height=6, style='Overview.Treeview', selectmode='browse')
        for i, (title, width) in enumerate(columns):
            tree.heading(str(i), text=title, anchor='w')
            tree.column(str(i), width=width, minwidth=width, anchor='w', stretch=True)
        tree.pack(fill='x')
        horizontal = ttk.Scrollbar(table_frame, orient='horizontal', command=tree.xview)
        def horizontal_state(first, last):
            horizontal.set(first, last)
            if float(first) <= 0 and float(last) >= .9999:
                horizontal.pack_forget()
            elif not horizontal.winfo_manager():
                horizontal.pack(fill='x', pady=(5, 0))
        tree.configure(xscrollcommand=horizontal_state)
        tree.tag_configure('alternate', background='#f7f9fb')
        self.overview_table = tree
        for i, r in enumerate(self.overview_data['companies']):
            debt_period = 'Q3' if r['debt_period'].endswith('09-30') else 'H1'
            tree.insert('', 'end', iid=r['code'], tags=('alternate',) if i % 2 else (), values=(
                r['name'], cost_text(r['cost']), r['cost']['period'] if r['cost'] else '—',
                f"{r['cash_available'] / 1e8:.2f}", f"{r['debt_ratio']:.1%}", f"{r['pb']:.2f}",
                f'2026 H1 / {debt_period}'))
        tree.selection_set(next(iter(self.overview_profiles)))
        tree.bind('<Double-1>', lambda event: self.open_overview_company())
        controls = tk.Frame(company, bg='white')
        controls.pack(fill='x', pady=(20, 16))
        ttk.Button(controls, text='查看所选公司明细', command=self.open_overview_company,
                   style='Overview.Primary.TButton').pack(side='left')
        ttk.Button(controls, text='经营与成本研究', command=lambda: self.overview_navigate('companies'),
                   style='Overview.TButton').pack(side='left', padx=10)
        ttk.Button(controls, text='估值假设', command=lambda: self.overview_navigate('valuation'),
                   style='Overview.TButton').pack(side='left')
        self.overview_note = self.overview_label(
            company, '现金余额核实至 2026-06-30；*PB沿用10/23快照。各公司期间及成本限定见表格与明细。',
            size=10, color=NOTE_COLOR)
        self.overview_export_note = tk.Label(content, bg='#f4f6f9', fg='#3b6e58',
                                             font=('Microsoft YaHei', 10), anchor='w', justify='left')
        # A local bindtag handles wheel events over labels, figures and table.
        # No bind_all: other modules and detail windows keep their own scrolling.
        tag = 'OverviewScroll_' + str(id(self))
        def wheel(event):
            amount = -max(1, abs(int(event.delta / 120))) * (1 if event.delta > 0 else -1)
            surface.yview_scroll(amount * 2, 'units')
            return 'break'
        self.bind_class(tag, '<MouseWheel>', wheel)
        def attach(widget):
            widget.bindtags((tag,) + tuple(t for t in widget.bindtags() if t != tag))
            for child in widget.winfo_children():
                attach(child)
        attach(surface)
        self.overview_scroll_tag = tag

    @staticmethod
    def overview_label(parent, text, size=10, color='#253b50', bold=False, bg='white', pady=0):
        label = tk.Label(parent, text=text, bg=bg, fg=color, anchor='w', justify='left',
                         font=('Microsoft YaHei', size, 'bold' if bold else 'normal'))
        label.pack(anchor='w', fill='x', pady=pady)
        label.bind('<Configure>', lambda event: label.configure(wraplength=max(80, event.width - 2)))
        return label

    @staticmethod
    def bind_overview_click(widget, command):
        widget.configure(cursor='hand2')
        widget.bind('<Button-1>', lambda event: command())
        for child in widget.winfo_children():
            OverviewMixin.bind_overview_click(child, command)

    def change_note(self, parent, date, changes):
        frame = tk.Frame(parent, bg='white', height=22)
        frame.pack(fill='x')
        labels = [tk.Label(frame, text=date, fg=NOTE_COLOR, bg='white', font=('Microsoft YaHei', 10))]
        for title, value in changes:
            if value is None:
                continue
            item = tk.Label(frame, text=f'{title} {value:+.1f}%', fg=change_color(value),
                            bg='white', font=('Microsoft YaHei', 10, 'bold'))
            labels.append(item)
            self.overview_change_labels.append((value, item))
        def layout(event=None):
            width = max(1, frame.winfo_width())
            x, y = 0, 0
            for item in labels:
                requested = item.winfo_reqwidth()
                if x and x + requested > width:
                    x, y = 0, y + 23
                item.place(x=x, y=y)
                x += requested + 12
            frame.configure(height=y + 23)
        frame.bind('<Configure>', layout)
        frame.after_idle(layout)
        return frame

    def metric_heading(self, parent, title, value, unit, note, command, changes=()):
        self.overview_label(parent, title, size=11, bold=True)
        values = tk.Frame(parent, bg='white')
        values.pack(anchor='w', pady=(8, 4))
        tk.Label(values, text=value, fg='#193550', bg='white',
                 font=('Microsoft YaHei', 28, 'bold')).pack(side='left')
        tk.Label(values, text='  ' + unit, fg=NOTE_COLOR, bg='white',
                 font=('Microsoft YaHei', 11)).pack(side='left', pady=(13, 0))
        self.change_note(parent, note, changes)
        for child in parent.winfo_children():
            self.bind_overview_click(child, command)

    def scroll_to_overview_companies(self):
        self.overview_content.update_idletasks()
        height = max(1, self.overview_content.winfo_height())
        self.overview_scroll.yview_moveto(max(0, self.overview_company_section.winfo_y() - 16) / height)

    def draw_overview_charts(self, parent):
        for key, card, draw in [
            ('capacity', self.overview_capacity_card, self.draw_overview_capacity_axis),
            ('price', self.overview_price_card, self.draw_overview_price_axis)]:
            figure = Figure(figsize=(6, 3), dpi=100, facecolor='white')
            axis = figure.add_subplot()
            draw(axis)
            figure.subplots_adjust(left=.12 if key == 'capacity' else .14, right=.96,
                                   bottom=.15, top=.86)
            canvas = FigureCanvasTkAgg(figure, master=card)
            canvas.get_tk_widget().configure(width=1, height=260)
            canvas.get_tk_widget().pack(fill='x', pady=(12, 0))
            def chart_size(event, current_figure=figure):
                # Reserve a fixed pixel margin for tick labels and the ylabel;
                # a percentage margin clips them on narrower Windows layouts.
                width = max(260, event.width)
                current_figure.subplots_adjust(left=65 / width, right=1 - 15 / width,
                                               bottom=.15, top=.86)
                current_figure.canvas.draw_idle()
            canvas.get_tk_widget().bind('<Configure>', chart_size, add='+')
            canvas.draw_idle()
            if key == 'capacity':
                self.overview_figure, self.overview_canvas = figure, canvas
            else:
                self.overview_price_figure, self.overview_price_canvas = figure, canvas
        footer = tk.Frame(self.overview_capacity_card, bg='white')
        footer.pack(fill='x', pady=(12, 0))
        for column, (label, value, color) in enumerate([
            ('正常保有量 / 万头', '3,750', '#365b4a'),
            ('绿色区间 / 万头', '3,450–3,862.5', '#365b4a'),
            ('红线下界 / 上界', '3,300 / 3,975', '#9b6262')]):
            footer.columnconfigure(column, weight=1, uniform='policy')
            block = tk.Frame(footer, bg='white')
            block.grid(row=0, column=column, sticky='nw', padx=(0 if column == 0 else 8, 0))
            self.overview_label(block, label, size=10, color=NOTE_COLOR)
            self.overview_label(block, value, size=11, color=color, bold=True, pady=(7, 0))
        self.overview_label(self.overview_price_card,
                            '曲线取每月第3周；最新月份取已公布周。\n点击指标查看采集日、口径与原文。',
                            size=10, color=NOTE_COLOR, pady=(16, 0))

    @staticmethod
    def polish_overview_axis(axis):
        axis.tick_params(labelsize=10, colors=NOTE_COLOR, length=3, pad=7)
        axis.spines[['top', 'right']].set_visible(False)
        axis.spines[['bottom', 'left']].set_color('#d5dde5')
        axis.grid(axis='y', color='#d5dde5', alpha=.45)
        axis.set_axisbelow(True)
        axis.set_facecolor('white')

    def draw_overview_capacity_axis(self, ax):
        rows = self.overview_data['capacity']
        dates = [datetime.fromisoformat(r['date']) for r in rows]
        start, end = date2num(dates[0]) - 18, date2num(dates[-1]) + 35
        switch = date2num(datetime(2026, 5, 14))
        for lo, hi, target, ratios in [(start, switch, 3900, (.85, .92, 1.05, 1.10)),
                                       (switch, end, 3750, (.88, .92, 1.03, 1.06))]:
            bounds = [3200] + [target * x for x in ratios] + [4370]
            for lower, upper, color in zip(bounds, bounds[1:],
                    ['#f3e0e0', '#f9edcf', '#e1efe5', '#f9edcf', '#f3e0e0']):
                ax.fill_between([lo, hi], lower, upper, color=color, linewidth=0)
            ax.plot([lo, hi], [target, target], '--', color='#567761', lw=1)
        known = [r for r in rows if r['sows'] is not None]
        ax.bar([datetime.fromisoformat(r['date']) for r in known], [r['sows'] for r in known],
               width=18, color=['#39758f'] * (len(known) - 1) + ['#193f56'], zorder=3)
        ax.axvline(switch, color='#a8b3be', ls=':', lw=1)
        ax.annotate('2026版方案', (switch, 4370), xytext=(6, -12),
                    textcoords='offset points', va='top', fontsize=9, color=NOTE_COLOR)
        ax.annotate(f"{rows[-1]['sows']:,.0f}", (dates[-1], rows[-1]['sows']),
                    xytext=(0, 8), textcoords='offset points', ha='center',
                    fontsize=10, color='#20576a', fontweight='bold')
        ax.set_ylim(3200, 4370)
        ax.set_xlim(start, end)
        ax.set_ylabel('万头', fontsize=10, color=NOTE_COLOR)
        ax.xaxis.set_major_locator(MonthLocator(interval=4))
        ax.xaxis.set_major_formatter(DateFormatter('%y-%m'))
        ax.text(0, 1.08, '缺数月份留空 · 纵轴从3,200起', transform=ax.transAxes,
                fontsize=9, color=NOTE_COLOR, va='bottom')
        self.polish_overview_axis(ax)

    def draw_overview_price_axis(self, ax):
        history = self.overview_data['price_history']
        dates = [datetime.fromisoformat(r.get('observation_date') or r.get('published_date') or r['period'] + '-15') for r in history]
        ax.plot(dates, [r['hog'] for r in history], color='#b87952', lw=1.8)
        latest = self.overview_data['latest_price']
        ax.scatter(dates[-1], latest['hog'], color='#b87952', s=22)
        ax.annotate(f"{latest['hog']:.2f}", (dates[-1], latest['hog']), xytext=(-5, 12),
                    textcoords='offset points', ha='right', fontsize=10, color='#98643e')
        ax.set_ylabel('元/公斤', fontsize=10, color=NOTE_COLOR)
        ax.xaxis.set_major_locator(MonthLocator(interval=12))
        ax.xaxis.set_major_formatter(DateFormatter('%Y'))
        self.polish_overview_axis(ax)

    def make_overview_export_figure(self):
        figure = Figure(figsize=(14, 4.5), dpi=100, facecolor='white')
        grid = figure.add_gridspec(1, 2, width_ratios=[3, 2])
        capacity, price = figure.add_subplot(grid[0]), figure.add_subplot(grid[1])
        self.draw_overview_capacity_axis(capacity)
        self.draw_overview_price_axis(price)
        capacity.set_title('能繁母猪：目标3,750；绿色3,450–3,862.5；红线3,300 / 3,975',
                           loc='left', fontsize=10, pad=42)
        price.set_title('全国生猪价格 · 官方周样本', loc='left', fontsize=11, pad=42)
        figure.subplots_adjust(left=.06, right=.985, bottom=.15, top=.78, wspace=.24)
        return figure

    def selected_overview_company(self):
        selection = self.overview_table.selection()
        return self.overview_profiles[selection[0] if selection else next(iter(self.overview_profiles))]

    def source_description(self, sid):
        source = self.overview_sources[sid]
        return (f"{source['title']}\n发布：{source.get('published_date') or '专题页未列发布日期'}\n"
                f"来源：{source['url']}\n原件：{OVERVIEW_ROOT / source['local_path']}\n"
                f"{source.get('provenance', '本轮从官方披露渠道取得并归档')}\n")

    def open_overview_company(self):
        r = self.selected_overview_company()
        window = tk.Toplevel(self)
        window.title(r['name'] + ' · 可动用现金与财报原文')
        window.geometry('990x730')
        amount = lambda x: f'{x / 1e8:,.4f} 亿元'
        cost = r['cost']
        text = (f"{r['name']}  {r['code']}\n\n"
                f"可动用现金：{amount(r['cash_available'])}；余额日 {r['cash_period']}；公告日 {r['cash_published']}\n"
                f"合并货币资金 {amount(r['cash_gross'])}\n－非现金等价物内受限资金 {amount(r['cash_restricted'])}\n"
                f"－仍列现金等价物的专用资金 {amount(r['cash_purpose_bound'])}\n"
                f"＝可动用现金 {amount(r['cash_available'])}\n"
                f"定位：货币资金 PDF文件页{r['cash_balance_page']}；现金构成及限制说明 PDF文件页{r['cash_note_page']}及下一页。\n"
                '扣减项已按原文核实并去除重叠。余额按合并集团统计，母公司调拨仍受子公司及用途限制；未来经营与偿债支出尚未扣除。\n\n'
                f"最近已核实财报：{r['debt_period']}，公告日 {r['debt_published']}\n"
                f"资产负债率 {r['debt_ratio']:.2%}＝合并负债 {amount(r['liabilities'])} ÷ 合并资产 {amount(r['assets'])}\n"
                f"同期合并货币资金 {amount(r['latest_cash_gross'])}；{r['latest_cash_status']}。\n\n"
                f"完全养殖成本：{cost_text(cost)} 元/kg；期间 {cost['period'] if cost else '未披露可比值'}\n"
                f"{cost['definition'] if cost else '未核实到官方披露的可比绝对完全成本，不用成本降幅、付现成本或目标代替。'}\n"
                f"PB {r['pb']:.2f}；{r['pb_source_note']}。净资产报告期 {r['pb_book_period']}。\n\n"
                '现金来源\n' + self.source_description(r['cash_source']) + '\n资产负债率来源\n' +
                self.source_description(r['debt_source']) + ('\n成本来源\n' + self.source_description(cost['source_id']) if cost else ''))
        bar = ttk.Frame(window, padding=8)
        bar.pack(fill='x')
        ttk.Button(bar, text='打开现金附注原件', command=lambda: self.open_overview_original(r['cash_source'])).pack(side='left')
        ttk.Button(bar, text='打开最近财报', command=lambda: self.open_overview_original(r['debt_source'])).pack(side='left', padx=6)
        if cost:
            ttk.Button(bar, text='打开成本原件', command=lambda: self.open_overview_original(cost['source_id'])).pack(side='left')
        text_panel(window, text)
        return window

    def open_overview_original(self, sid):
        source = self.overview_sources[sid]
        path = (OVERVIEW_ROOT / source['local_path']).resolve()
        if not path.is_relative_to(OVERVIEW_ROOT.resolve()) or not path.is_file():
            raise ValueError('原件路径不可用')
        if path.suffix == '.json':
            self.winfo_toplevel().document('公司原始答复归档', path.read_text(encoding='utf-8'))
        else:
            os.startfile(path)

    def open_overview_metric(self, key):
        data = self.overview_data
        if key == 'capacity':
            latest = data['capacity'][-1]
            text = (f"全国能繁母猪 {latest['sows']:,.0f} 万头；{latest['date']}\n"
                f"{self.overview_capacity_status}，占正常保有量 {latest['sows'] / 3750:.2%}。\n"
                '2026版：正常保有量3750万头；红线3300/3975，绿色区间3450—3862.5（含端点）。\n'
                '图中5/14为2026方案公开日期，此前采用2024版标准。状态按公开规则计算；具体调控措施的启动情况尚未核实。\n'
                '季末变化较上季，其他月份较上月。柱形只显示已公布值，缺数月份留空；纵轴从3,200万头起。\n\n'
                + '\n'.join(f"{r['period']}：" + (f"{r['sows']:,.0f} 万头；{r['statistical_basis']}"
                            if r['sows'] is not None else '未公布') for r in data['capacity']))
            ids = [latest['source'], 'POLICY_2026', 'POLICY_2024']
        elif key == 'price':
            row = data['latest_price']
            text = (f"全国生猪平均价格 {row['hog']:.2f} 元/公斤；采集 {row['observation_date']}，发布 {row['published_date']}。\n"
                '口径：农业农村部全国500个县集贸市场和采集点周监测，与屠宰企业收购价及公司月报售价分别统计。\n'
                '长期图取每月第3周，最新月份取已公布周；各点均为周样本。\n')
            ids = [r['source'] for r in data['price_comparison']]
        elif key == 'psy':
            row = data['psy']
            text = f"行业PSY（样本）：{row['value']:.2f} {row['unit']}；{row['period']}。\n{row['scope']}\n{row['definition']}\n定位：PDF文件页{row['page']}。\n"
            ids = [row['source']]
        else:
            row = data['industry'][key]
            text = f"{row['definition']}：{row['value']:,.0f} {row['unit']}\n期间：{row['period']}；同比 {row['yoy_pct']:+.1f}%。\n存栏为期末数，出栏和猪肉产量为年初至今累计数。\n"
            ids = [row['source'], 'NBS_Q3']
        window = tk.Toplevel(self)
        window.title('行业指标 · 原文与统计口径')
        window.geometry('960x700')
        bar = ttk.Frame(window, padding=7)
        bar.pack(fill='x')
        for sid in ids:
            ttk.Button(bar, text='打开 ' + self.overview_sources[sid]['publisher'],
                       command=lambda source_id=sid: self.open_overview_original(source_id)).pack(side='left', padx=3)
        text_panel(window, text + '\n\n' + '\n'.join(self.source_description(sid) for sid in ids))
        return window

    def open_overview_sources(self):
        window = tk.Toplevel(self)
        window.title('总览 · 来源、口径与缺口')
        window.geometry('1020x720')
        view = table(window, [('资料与来源', 560), ('公布日期', 130), ('渠道', 240)], 10)
        detail = text_panel(window)
        for sid, source in self.overview_sources.items():
            view.insert('', 'end', iid=sid, values=(source['title'], source.get('published_date') or '专题页未列',
                        '公司原件既有归档' if sid.startswith('ARCHIVE_') else source.get('publisher', '')))
        def show(_=None):
            selection = view.selection()
            if selection:
                set_text(detail, self.source_description(selection[0]) + '\n展示口径与已知缺口\n' + '\n'.join(self.overview_data['notes']))
        view.bind('<<TreeviewSelect>>', show)
        view.selection_set(view.get_children()[0])
        show()
        ttk.Button(window, text='打开所选原件', command=lambda: self.open_overview_original(view.selection()[0]) if view.selection() else None).pack(anchor='w', padx=8, pady=7)
        window.overview_source_view = view
        return window

    def export_overview(self):
        folder = RUNTIME / 'exports/swine_overview' / datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d_%H%M%S_%f')
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'overview.json').write_text(json.dumps(self.overview_data, ensure_ascii=False, indent=2), encoding='utf-8')
        (folder / 'sources.json').write_text(json.dumps(list(self.overview_sources.values()), ensure_ascii=False, indent=2), encoding='utf-8')
        with (folder / 'companies.csv').open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['公司', '完全成本/元kg', '成本期间', '可动用现金/亿元', '现金余额日',
                             '资产负债率', '负债率余额日', 'PB', '行情日', 'PB净资产期'])
            for r in self.overview_data['companies']:
                writer.writerow([r['name'], cost_text(r['cost']), r['cost']['period'] if r['cost'] else '',
                    r['cash_available'] / 1e8, r['cash_period'], r['debt_ratio'], r['debt_period'],
                    r['pb'], r['pb_market_date'], r['pb_book_period']])
        self.make_overview_export_figure().savefig(folder / 'industry.png', dpi=160)
        (folder / '口径说明.txt').write_text('\n'.join(self.overview_data['notes']) + '\n\n' +
            '\n'.join(self.source_description(sid) for sid in self.overview_sources), encoding='utf-8')
        self.overview_export_note.configure(text='已导出至 ' + str(folder), wraplength=900)
        self.overview_export_note.pack(anchor='w', fill='x')
        self.overview_last_export = folder
        return folder
