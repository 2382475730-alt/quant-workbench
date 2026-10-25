"""Exercise the real native enhancement UI and capture rendered screens."""
import json
import tkinter as tk

from PIL import ImageGrab
from quant_workbench.desktop import PHASES, Desktop
from quant_workbench.enhancement_panel import NAMES

from quant_workbench.data import ROOT, write_json

app = Desktop()
app.update()
page = app.enhancement
assert app.tabs.select() == str(page)
assert len(app.tabs.tabs()) == 7
checks = []
for phase in ["development", "validation", "final_repaired"]:
    app.phase_display.set(PHASES[phase])
    app.choose_phase(None)
    app.update()
    assert len(page.comparison.get_children()) == 12
    for strategy in NAMES.values():
        page.strategy.set(strategy)
        page.draw_holdings()
        app.update()
        view = page.view
        assert abs(view["market_value"]+view["cash"]+view["receivable"]-view["equity"]) < .01
        assert len(page.holdings_table.get_children()) == len(view["rows"])
        assert "尚未连接" in page.audit.get("1.0", "end")
        checks.append({"phase": phase, "strategy": strategy, "securities": view["held_count"]})
page.strategy.set(NAMES["momentum_constrained"])
page.draw_holdings()
app.update()
assert page.view["held_count"] == 36
assert len([r for r in page.holdings_table.get_children() if "breach" in page.holdings_table.item(r, "tags")]) == 2
directory = ROOT/"artifacts/ui_enhancement"
directory.mkdir(exist_ok=True)
labels = ["comparison", "actual_holdings", "industry", "audit"]


def save(index):
    app.update()
    ImageGrab.grab(window=int(app.frame(), 16)).save(directory/f"{labels[index]}.png")
    if index+1 < len(labels):
        page.pages.select(index+1)
        app.after(350, lambda: save(index+1))
    else:
        for path, expected in [("reports/enhancement_v1/report.md", "稳定超额收益"), ("research/quant_agent_design.md", "确定性研究工具层")]:
            page.open_text(path, expected)
            app.update()
            window = next(c for c in page.winfo_children() if isinstance(c, tk.Toplevel))
            widget = next(c for c in window.winfo_children() if isinstance(c, tk.Text))
            assert expected in widget.get("1.0", "end")
            window.destroy()
        write_json("artifacts/ui_enhancement/verification.json", {"checks": checks, "status": "passed",
                   "tabs": 7, "comparison_rows": 12, "current_holdings": 36, "current_direct_stock_breaches": 2,
                   "report_and_agent_windows_opened": True, "screenshots_require_separate_visual_review": True})
        print(json.dumps({"checked_views": len(checks), "screenshots": len(labels), "status": "passed"}))
        app.destroy()


page.pages.select(0)
app.after(600, lambda: save(0))
app.mainloop()
