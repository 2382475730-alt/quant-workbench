"""Four equal research areas, lazily constructed in one native Tk window."""
import os
import tkinter as tk
import traceback
from tkinter import messagebox, ttk

import matplotlib

from .paths import LIBRARY, PROJECT, RUNTIME, SETTINGS, read_json, save_state
from .widgets import text_panel

matplotlib.use("TkAgg")
matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False


class Workbench(tk.Tk):
    def __init__(self, state_path=None):
        super().__init__()
        self.title("量化研究工作台 · 四条研究主线")
        self.state_path = state_path or RUNTIME / "ui_state.json"
        self.saved = read_json(self.state_path, {}) or {}
        self.active = ""
        self.panels = {}
        self.errors = []
        width = min(1420, self.winfo_screenwidth() - 50)
        height = min(940, self.winfo_screenheight() - 80)
        self.geometry(f"{width}x{height}+18+18")
        self.minsize(min(1100, width), min(700, height))
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#f4f6f9")
        style.configure("TLabel", background="#f4f6f9", foreground="#23364d", font=("Microsoft YaHei", 10))
        style.configure("Title.TLabel", font=("Microsoft YaHei", 17, "bold"), foreground="#193550")
        style.configure("Heading.TLabel", font=("Microsoft YaHei", 12, "bold"))
        style.configure("Sub.TLabel", foreground="#596c80", font=("Microsoft YaHei", 9))
        style.configure("TNotebook.Tab", padding=(12, 7), font=("Microsoft YaHei", 10))
        style.configure("Treeview", rowheight=26, font=("Microsoft YaHei", 10))
        style.configure("Treeview.Heading", font=("Microsoft YaHei", 10, "bold"))
        self.configure(bg="#f4f6f9")
        sidebar = tk.Frame(self, bg="#172d43", width=170)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        tk.Label(sidebar, text="量化研究\n工作台", font=("Microsoft YaHei", 19, "bold"),
                 bg="#172d43", fg="white", justify="left").pack(anchor="w", padx=18, pady=(24, 28))
        self.buttons = {}
        for module in SETTINGS["modules"]:
            key = module["id"]
            button = tk.Button(sidebar, text=module["name"], font=("Microsoft YaHei", 12),
                               anchor="w", padx=18, pady=14, bd=0, relief="flat", cursor="hand2",
                               bg="#172d43", fg="#dae4ee", activebackground="#284b6c", activeforeground="white",
                               command=lambda k=key: self.show_module(k))
            button.pack(fill="x", padx=8, pady=4)
            self.buttons[key] = button
        bottom = tk.Frame(sidebar, bg="#172d43")
        bottom.pack(side="bottom", fill="x", pady=18)
        for label, command in [("数据与核验", self.open_data), ("使用与目录说明", self.open_guide),
                                ("打开导出目录", self.open_exports)]:
            tk.Button(bottom, text=label, command=command, bg="#172d43", fg="#c3cfdd", bd=0,
                      anchor="w", padx=18, pady=8, font=("Microsoft YaHei", 10)).pack(fill="x")
        body = ttk.Frame(self, padding=(16, 12, 16, 8))
        body.pack(side="left", fill="both", expand=True)
        header = ttk.Frame(body)
        header.pack(fill="x", pady=(0, 10))
        self.heading = ttk.Label(header, style="Title.TLabel")
        self.heading.pack(anchor="w")
        self.subtitle = ttk.Label(header, style="Sub.TLabel")
        self.subtitle.pack(anchor="w", pady=(3, 0))
        self.container = ttk.Frame(body)
        self.container.pack(fill="both", expand=True)
        self.container.rowconfigure(0, weight=1)
        self.container.columnconfigure(0, weight=1)
        ttk.Label(body, text="本地研究 · 数据日期与报告期见各页面 · 历史回放 / 资金试算均非实际成交",
                  style="Sub.TLabel").pack(side="bottom", anchor="w", pady=(6, 0), before=self.container)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Configure>", self.resize_labels, add="+")
        key = self.saved.get("active", SETTINGS["default_module"])
        self.after(80, lambda: self.show_module(key if key in self.buttons else "pork"))

    def build(self, key):
        if key == "pork":
            from .pork import PorkPanel
            return PorkPanel(self.container)
        if key == "stocks":
            from .stocks import StockPanel
            return StockPanel(self.container)
        from .portfolios import EnhancementView, SmallCapitalView
        return (EnhancementView if key == "enhancement" else SmallCapitalView)(self.container)

    def show_module(self, key):
        if key not in self.buttons:
            raise ValueError("Unknown research module")
        if key not in self.panels:
            previous_widgets = set(self.container.winfo_children())
            try:
                panel = self.build(key)
                state = self.saved.get("panels", {}).get(key, {})
                if key == 'pork' and state.get('version') not in ('swine_v2','swine_v3'):
                    state = {}
                if hasattr(panel, "restore"):
                    panel.restore(state)
                tab = state.get("tab")
                if isinstance(tab, int) and 0 <= tab < len(panel.pages.tabs()):
                    panel.pages.select(tab)
                panel.grid(row=0, column=0, sticky="nsew")
                self.panels[key] = panel
            except Exception as exc:  # noqa: BLE001 -- preserve other modules when one fails
                for child in set(self.container.winfo_children()) - previous_widgets:
                    child.destroy()
                self.report_callback_exception(type(exc), exc, exc.__traceback__)
                return
        for panel_key, panel in self.panels.items():
            if panel_key == key:
                panel.grid()
            else:
                panel.grid_remove()
        self.active = key
        module = next(m for m in SETTINGS["modules"] if m["id"] == key)
        self.heading.configure(text=module["name"])
        self.subtitle.configure(text=module["subtitle"])
        for name, button in self.buttons.items():
            button.configure(bg="#315c80" if name == key else "#172d43", fg="white" if name == key else "#dae4ee")
        self.after_idle(self.resize_labels)
        self.save()

    def resize_labels(self, event=None):
        if event is not None and event.widget is not self:
            return
        width = max(500, self.container.winfo_width() - 45)
        def visit(widget):
            if isinstance(widget, ttk.Label) and int(float(widget.cget("wraplength") or 0)) > 0:
                widget.configure(wraplength=width)
            for child in widget.winfo_children():
                visit(child)
        if self.active in self.panels:
            visit(self.panels[self.active])

    def document(self, title, content):
        window = tk.Toplevel(self)
        window.title(title)
        window.geometry("980x720")
        text_panel(window, content)

    def open_guide(self):
        self.document("工作台使用与目录说明", (PROJECT / "README.md").read_text(encoding="utf-8"))

    def open_data(self):
        report = read_json(RUNTIME / "verification.json", {})
        content = ("共享研究资料库\n\n" + str(LIBRARY) + "\n\n"
                   "行情、财报与报告仍是历史快照；打开窗口不会联网下载。\n"
                   "生猪研究使用独立新采集资料，记录写入当前应用 runtime。\n\n"
                   f"最近结构核验：{report.get('status', '尚未运行')}\n"
                   f"迁移文件核验数：{report.get('migration_files_verified', '未知')}\n"
                   f"核验时间：{report.get('checked_at', '未知')}\n\n"
                   "终端复核：在 quant_workbench 目录运行 .venv\\Scripts\\python.exe scripts\\verify.py\n"
                   "已知局限保留在各研究报告中；文件完整不等于策略有效。")
        self.document("数据与核验", content)

    def open_exports(self):
        folder = RUNTIME / "exports"
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)

    def save(self):
        panels = self.saved.get("panels", {}).copy()
        panels.update({key: panel.state() for key, panel in self.panels.items()})
        self.saved = {"active": self.active or "pork", "panels": panels}
        save_state(self.saved, self.state_path)

    def close(self):
        self.save()
        self.destroy()

    def report_callback_exception(self, exc, value, tb):
        self.errors.append(str(value))
        RUNTIME.mkdir(exist_ok=True)
        with (RUNTIME / "desktop_errors.log").open("a", encoding="utf-8") as file:
            traceback.print_exception(exc, value, tb, file=file)
        messagebox.showerror("页面加载失败", str(value) + "\n详情已保存到 runtime/desktop_errors.log。", parent=self)


def main():
    Workbench().mainloop()


if __name__ == "__main__":
    main()
