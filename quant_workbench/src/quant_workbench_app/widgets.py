import tkinter as tk
from tkinter import ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from .paths import LIBRARY


def text_panel(parent, content=""):
    frame = ttk.Frame(parent)
    frame.pack(fill="both", expand=True)
    text = tk.Text(frame, wrap="word", font=("Microsoft YaHei", 10), bg="white",
                   fg="#25374b", relief="flat", padx=18, pady=14)
    scroll = ttk.Scrollbar(frame, command=text.yview)
    text.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    text.pack(fill="both", expand=True)
    set_text(text, content)
    return text


def set_text(widget, content):
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    widget.insert("1.0", content)
    widget.configure(state="disabled")


def report_tab(book, relative, title="研究记录"):
    page = ttk.Frame(book, padding=10)
    book.add(page, text=title)
    path = LIBRARY / relative
    text_panel(page, path.read_text(encoding="utf-8") if path.exists() else "资料尚未生成。")
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
    return tree


def chart(parent, height=300):
    figure = Figure(figsize=(10, 3.5), dpi=100, facecolor="#f4f6f9")
    canvas = FigureCanvasTkAgg(figure, master=parent)
    canvas.get_tk_widget().configure(height=height)
    canvas.get_tk_widget().pack(fill="both", expand=True, pady=8)
    canvas.mpl_connect('resize_event',lambda event: figure.set_layout_engine('tight',pad=.7))
    return figure, canvas


def polish_tree(tree):
    """Add horizontal access to inherited wide tables without changing research code."""
    if tree.cget("xscrollcommand"):
        return
    scroll = ttk.Scrollbar(tree.master, orient="horizontal", command=tree.xview)
    tree.configure(xscrollcommand=scroll.set)
    scroll.pack(fill="x", after=tree)
