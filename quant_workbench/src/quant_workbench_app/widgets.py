import os
import tkinter as tk
from tkinter import ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from .paths import LIBRARY
from .reading import library_report, report_html
from .report_text import set_report_text
from .ui_presentation import color_text, style_tree, style_figure


def text_panel(parent, content="", report=False, source=None):
    frame = ttk.Frame(parent)
    frame.pack(fill="both", expand=True)
    text = tk.Text(frame, wrap="word", font=("Microsoft YaHei", 10), bg="white",
                   fg="#25374b", relief="flat", padx=18, pady=14, spacing1=3, spacing3=5)
    scroll = ttk.Scrollbar(frame, command=text.yview)
    text.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    if report:
        horizontal = ttk.Scrollbar(frame, orient='horizontal', command=text.xview)
        text.configure(xscrollcommand=horizontal.set)
        horizontal.pack(side='bottom', fill='x')
    text.pack(fill="both", expand=True)
    if report:
        set_report_text(text, content, source)
    else:
        set_text(text, content)
    return text


def set_text(widget, content):
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    widget.insert("1.0", content)
    color_text(widget)
    widget.configure(state="disabled")


def report_tab(book, relative, title="研究记录"):
    page = ttk.Frame(book, padding=10)
    book.add(page, text=title)
    path = report_html(LIBRARY / relative)
    if path.is_file() and path.suffix == '.html':
        controls = ttk.Frame(page)
        controls.pack(fill="x", pady=(0, 8))
        ttk.Label(controls, text="数据日期与研究范围见报告正文。", style="Sub.TLabel").pack(side="left")
        ttk.Button(controls, text="打开排版版报告", command=lambda: os.startfile(path)).pack(side="right")
    text_panel(page, library_report(relative), report=True, source=LIBRARY / relative)
    return page


def table(parent, headings, height=5):
    frame = ttk.Frame(parent)
    frame.pack(fill="x", pady=6)
    tree = ttk.Treeview(frame, columns=[str(i) for i in range(len(headings))],
                        show="headings", height=height)
    for i, (label, width) in enumerate(headings):
        tree.heading(str(i), text=label)
        tree.column(str(i), width=width, minwidth=65, anchor="w")
    horizontal = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
    vertical = ttk.Scrollbar(frame, command=tree.yview)
    tree.configure(xscrollcommand=horizontal.set, yscrollcommand=vertical.set)
    vertical.pack(side="right", fill="y")
    tree.pack(fill="x")
    horizontal.pack(fill="x")
    style_tree(tree)
    return tree


def chart(parent, height=300):
    figure = Figure(figsize=(10, 3.5), dpi=100, facecolor="#f4f6f9")
    canvas = FigureCanvasTkAgg(figure, master=parent)
    canvas.get_tk_widget().configure(height=height)
    canvas.get_tk_widget().pack(fill="both", expand=True, pady=8)
    pending = [False]
    def adapt():
        pending[0] = False
        if not parent.winfo_exists() or parent.winfo_height() < 100: return
        reserved = 16
        if isinstance(parent, ttk.Frame):
            raw = parent.cget('padding')
            values = raw if isinstance(raw, (tuple, list)) else parent.tk.splitlist(str(raw))
            values = [parent.winfo_pixels(str(v)) for v in values]
            if values:
                reserved += 2 * int(values[0] if len(values) == 1 else values[1]) if len(values) < 4 else int(values[1]) + int(values[3])
        for child in parent.pack_slaves():
            if child is canvas.get_tk_widget(): continue
            info = child.pack_info()
            if info.get('side') in ('top', 'bottom'):
                raw_padding = info.get('pady', 0)
                padding = raw_padding if isinstance(raw_padding, (tuple, list)) else str(raw_padding).split()
                padding = [parent.winfo_pixels(str(v)) for v in padding]
                reserved += child.winfo_reqheight() + (sum(padding) if len(padding) == 2 else 2 * padding[0])
        target = max(120, min(height, parent.winfo_height() - reserved))
        if int(canvas.get_tk_widget().cget('height')) != target:
            canvas.get_tk_widget().configure(height=target)
    def schedule(event=None):
        if not pending[0]:
            pending[0] = True; parent.after_idle(adapt)
    parent.bind('<Configure>', schedule, add='+')
    canvas.get_tk_widget().bind('<Configure>', schedule, add='+')
    canvas.mpl_connect('resize_event',lambda event: figure.set_layout_engine('tight',pad=.7))
    style_figure(figure)
    return figure, canvas


def polish_tree(tree):
    """Add horizontal access to inherited wide tables without changing research code."""
    if tree.cget("xscrollcommand"):
        return
    scroll = ttk.Scrollbar(tree.master, orient="horizontal", command=tree.xview)
    tree.configure(xscrollcommand=scroll.set)
    scroll.pack(fill="x", after=tree)
