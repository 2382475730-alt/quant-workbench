"""Shared native presentation rules; research values and table models stay intact."""
import re
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

NOTE_COLOR = '#465a6d'
UP_COLOR = '#b02a37'
DOWN_COLOR = '#187345'
WARNING_COLOR = '#885713'


def change_color(value):
    return NOTE_COLOR if value is None or value == 0 else UP_COLOR if value > 0 else DOWN_COLOR


def change_column(title):
    if re.search(r'权重|仓位|覆盖|分位|波动|跟踪|偏差|偏离|净资产|市值|目标|估值', title):
        return False
    return bool(re.search(r'收益|回撤|同比|环比|涨跌|涨幅|增速|净利|利润|盈亏|变化|变动|比免费.+差', title))


def number_value(text):
    text = str(text).strip().replace(',', '').replace('−', '-')
    match = re.fullmatch(r'([+\-]?\d+(?:\.\d+)?)\s*(?:%|亿元|万元|元|个百分点)?', text)
    return float(match[1]) if match else None


def change_spans(text):
    """Color changes in prose, excluding dates, holdings and probability levels."""
    for match in re.finditer(r'(?<![\d./\-])([+\-−]?\d+(?:\.\d+)?)(%|个百分点|亿元|万元)', text):
        prefix = re.split(r'[\n；。]', text[:match.start()])[-1][-45:]
        if re.search(r'https?://\S*$', prefix):
            continue
        signed = match[1].startswith(('+', '-', '−'))
        context = re.search(r'同比|环比|较上|较前|相对现价|收益|年化|回撤|涨幅|跌幅|增速|净利|利润|盈亏|累计收益', prefix)
        context = context or '历史ROE' in text[:match.start()].split('\n')[-1]
        if not context and not (signed and match[2] == '%' and not re.search(r'须|阈值|有效|范围|上限|预算', prefix)):
            continue
        # A nearby level label overrides a more distant reference to returns.
        last_clause = re.split(r'[，、：=＝]', prefix)[-1]
        if re.search(r'仓位|权重|现金|分位|概率|覆盖|负债率|波动|分红|要求回报|收益率目标', last_clause):
            continue
        value = float(match[1].replace('−', '-'))
        if not signed and re.search(r'回撤|下降|下跌|减少', last_clause):
            value = -abs(value)
        yield match.start(), match.end(), change_color(value)


def color_text(widget):
    for tag, color in [('change_up', UP_COLOR), ('change_down', DOWN_COLOR)]:
        widget.tag_configure(tag, foreground=color)
        widget.tag_remove(tag, '1.0', 'end')
    content = widget.get('1.0', 'end-1c')
    for start, end, color in change_spans(content):
        if 'report_code' in widget.tag_names(f'1.0+{start}c'):
            continue
        tag = 'change_up' if color == UP_COLOR else 'change_down' if color == DOWN_COLOR else None
        if tag:
            widget.tag_add(tag, f'1.0+{start}c', f'1.0+{end}c')
            widget.tag_raise(tag)


class NoteLabel(tk.Text):
    """A wrapping label that supports colored numeric spans and cget('text')."""
    def __init__(self, parent, text='', heading=False, **kwargs):
        self._text = ''
        self._wraplength = 1000
        self._style = 'Heading.TLabel' if heading else 'Sub.TLabel'
        self._sizing = False
        super().__init__(parent, width=1, height=1, wrap='word', borderwidth=0,
                         highlightthickness=0, relief='flat', padx=0, pady=0,
                         bg='#f4f6f9', fg=NOTE_COLOR, cursor='arrow', takefocus=False,
                         font=('Microsoft YaHei', 12 if heading else 10, 'bold' if heading else 'normal'), **kwargs)
        self.bind('<Configure>', self._schedule_size)
        self.configure(text=text)

    def configure(self, cnf=None, **kwargs):
        if isinstance(cnf, dict):
            kwargs = {**cnf, **kwargs}; cnf = None
        text = kwargs.pop('text', None)
        self._wraplength = kwargs.pop('wraplength', self._wraplength)
        self._style = kwargs.pop('style', self._style)
        result = super().configure(cnf, **kwargs)
        if text is not None:
            self._text = str(text)
            super().configure(state='normal')
            self.delete('1.0', 'end'); self.insert('1.0', self._text)
            color_text(self)
            super().configure(state='disabled')
            self._schedule_size()
        return result

    config = configure

    def cget(self, key):
        if key == 'text': return self._text
        if key == 'wraplength': return self._wraplength
        if key == 'style': return self._style
        return super().cget(key)

    def _schedule_size(self, event=None):
        if not self._sizing:
            self._sizing = True
            self.after_idle(self._fit)

    def _fit(self):
        self._sizing = False
        if not self.winfo_exists(): return
        width = self.winfo_width()
        if width < 50: return
        try:
            actual_lines = int(self.tk.call(self._w, 'count', '-update', '-displaylines', '1.0', 'end-1c')) + 1
        except tk.TclError:
            actual_lines = 1
        font = tkfont.Font(font=self.cget('font'))
        lines = 0
        for paragraph in self._text.split('\n'):
            used = 0
            lines += 1
            for token in re.findall(r'[A-Za-z0-9_./:%+−-]+|\s+|.', paragraph):
                parts = [token] if font.measure(token) <= width else list(token)
                for part in parts:
                    size = font.measure(part)
                    if used and used + size > width:
                        lines += 1; used = 0
                    used += size
        lines = max(lines, actual_lines)
        if int(super().cget('height')) != lines:
            super().configure(height=lines)


def upgrade_notes(panel, names):
    for name in names:
        old = getattr(panel, name, None)
        if old is None or isinstance(old, NoteLabel): continue
        options = old.pack_info()
        options.pop('in', None)
        item = NoteLabel(old.master, str(old.cget('text')))
        item.pack(**options, before=old)
        old.destroy()
        setattr(panel, name, item)


class CellColors:
    """Paint only numeric cells; a row can show both a gain and a drawdown."""
    def __init__(self, tree):
        self.tree = tree
        self.cells = {}
        self.pending = False
        for event in ('<Configure>', '<<TreeviewSelect>>', '<KeyRelease>', '<MouseWheel>'):
            tree.bind(event, self.schedule, add='+')
        for name in ('insert', 'delete', 'detach', 'move', 'item', 'heading', 'set'):
            original = getattr(tree, name)
            def changed(*args, _call=original, _name=name, **kwargs):
                result = _call(*args, **kwargs)
                if _name not in ('item', 'heading', 'set') or kwargs or (_name == 'set' and len(args) > 2):
                    self.schedule()
                return result
            setattr(tree, name, changed)
        for option in ('xscrollcommand', 'yscrollcommand'):
            original = str(tree.cget(option))
            def scroll(first, last, _original=original):
                if _original:
                    tree.tk.call(*tree.tk.splitlist(_original), first, last)
                self.schedule()
            tree.configure(**{option: scroll})
        self.schedule()

    def schedule(self, event=None):
        if not self.pending and self.tree.winfo_exists():
            self.pending = True
            self.tree.after_idle(self.paint)

    def paint(self):
        self.pending = False
        tree = self.tree
        if not tree.winfo_exists(): return
        for canvas in self.cells.values(): canvas.place_forget()
        style = ttk.Style(tree)
        selected = set(tree.selection())
        style_name = tree.cget('style') or 'Treeview'
        font = style.lookup(style_name, 'font') or ('Microsoft YaHei', 10)
        columns = list(tree['columns'])
        for iid in tree.get_children():
            values = tree.item(iid, 'values')
            for index, column in enumerate(columns):
                title = str(tree.heading(column, 'text'))
                if not change_column(title) or index >= len(values): continue
                value = number_value(values[index])
                if value is None or value == 0: continue
                if '回撤' in title: value = -abs(value)
                bounds = tree.bbox(iid, column)
                if not bounds: continue
                x, y, width, height = bounds
                left, right = max(1, x), min(tree.winfo_width()-1, x+width)
                if right <= left: continue
                bg = style.lookup(style_name, 'background', ('selected',)) if iid in selected else style.lookup(style_name, 'background')
                if iid not in selected:
                    for tag in tree.item(iid, 'tags'):
                        bg = tree.tag_configure(tag, 'background') or bg
                key = (iid, column)
                if key not in self.cells:
                    canvas = tk.Canvas(tree, highlightthickness=0, borderwidth=0, takefocus=False)
                    for sequence in ('<ButtonPress-1>', '<ButtonRelease-1>', '<MouseWheel>'):
                        def forward(event, sequence=sequence):
                            tree.event_generate(sequence, x=event.x_root-tree.winfo_rootx(),
                                                y=event.y_root-tree.winfo_rooty(),
                                                **({'delta': event.delta} if sequence == '<MouseWheel>' else {'time': event.time}))
                        canvas.bind(sequence, forward)
                    self.cells[key] = canvas
                canvas = self.cells[key]
                canvas.configure(bg=bg or 'white')
                canvas.delete('all')
                anchor = str(tree.column(column, 'anchor'))
                pos = x-left + (width/2 if anchor == 'center' else width-6 if anchor == 'e' else 5)
                canvas.create_text(pos, height/2, text=str(values[index]), anchor=anchor if anchor in ('w','e','center') else 'w',
                                   font=font, fill=change_color(value))
                canvas.place(x=left, y=y, width=right-left, height=height)
                canvas.tk.call('raise', str(canvas))
        # Remove cached cells after period/company switches.
        for key in list(self.cells):
            if not tree.exists(key[0]): self.cells.pop(key).destroy()


def style_tree(tree):
    if not hasattr(tree, '_cell_colors'):
        # Increase heading width before values are inserted; wide tables remain scrollable.
        font = tkfont.Font(font=('Microsoft YaHei', 10, 'bold'))
        for column in tree['columns']:
            width = max(int(tree.column(column, 'minwidth')), font.measure(tree.heading(column, 'text')) + 22)
            tree.column(column, minwidth=width, width=max(width, int(tree.column(column, 'width'))))
        tree._cell_colors = CellColors(tree)
    tree._cell_colors.schedule()


def style_figure(figure):
    canvas = figure.canvas
    if not getattr(canvas, '_readable_axes', False):
        original = canvas.draw
        def draw(*args, **kwargs):
            for ax in figure.axes:
                ax.tick_params(colors=NOTE_COLOR, labelsize=10)
                for text in (ax.xaxis.label, ax.yaxis.label):
                    text.set_color(NOTE_COLOR)
            return original(*args, **kwargs)
        canvas.draw = draw
        canvas._readable_axes = True
        canvas.draw_idle()


def responsive_controls(frame):
    """Wrap a horizontal parameter/button row when its controls no longer fit."""
    if getattr(frame, '_responsive_controls', False): return
    if frame.winfo_manager() == 'pack' and frame.pack_info()['fill'] not in ('x', 'both'):
        return
    children = frame.winfo_children()
    if not children or not all(w.winfo_manager() == 'pack' and w.pack_info()['side'] in ('left', 'right') for w in children):
        return
    frame._responsive_controls = True
    options = {w: {k: v for k, v in w.pack_info().items() if k != 'in'} for w in children}
    pending = [False]
    flowing = [False]
    def arrange():
        pending[0] = False
        if not frame.winfo_exists(): return
        width = frame.winfo_width()
        if width < 50: return
        required = sum(w.winfo_reqwidth() + 8 for w in children if w.winfo_exists())
        if required <= width:
            if flowing[0]:
                for w in children: w.grid_forget()
                for w in children: w.pack(**options[w])
                flowing[0] = False
            return
        if not flowing[0]:
            for w in children: w.pack_forget()
            flowing[0] = True
        row = col = used = 0
        for w in children:
            size = min(width, w.winfo_reqwidth() + 14)
            if col and used + size > width:
                row += 1; col = used = 0
            w.grid(row=row, column=col, padx=4, pady=4, sticky='w')
            if isinstance(w, ttk.Label) and w.winfo_reqwidth() > width:
                w.configure(wraplength=max(100, width-12))
            col += 1; used += size
    def schedule(event=None):
        if not pending[0]:
            pending[0] = True; frame.after_idle(arrange)
    frame.bind('<Configure>', schedule, add='+')
    schedule()


def style_panel(panel):
    from matplotlib.figure import Figure
    def visit(widget):
        if isinstance(widget, (ttk.Frame, tk.Frame)): responsive_controls(widget)
        if isinstance(widget, ttk.Treeview): style_tree(widget)
        if isinstance(widget, ttk.Label) and not getattr(widget, '_readable_wrap', False):
            widget._readable_wrap = True
            def wrap(event, item=widget):
                if event.width > 30 and int(float(item.cget('wraplength') or 0)):
                    item.configure(wraplength=max(80, event.width - 4))
            widget.bind('<Configure>', wrap, add='+')
        if isinstance(widget, tk.Text) and str(widget.cget('state')) == 'disabled': color_text(widget)
        for child in widget.winfo_children(): visit(child)
    visit(panel)
    for value in vars(panel).values():
        if isinstance(value, Figure): style_figure(value)
