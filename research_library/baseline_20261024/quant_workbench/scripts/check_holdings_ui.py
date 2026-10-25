"""Exercise our Tk widgets and snapshot the changed pages for review."""
import json
import tkinter as tk

from PIL import ImageGrab
from quant_workbench.desktop import PHASES, Desktop

from quant_workbench.data import ROOT, write_json

app = Desktop()
app.update()
page = app.positions_page
assert app.tabs.select() == str(app.enhancement if app.enhancement.data else page)
app.tabs.select(page)
assert page.view["held_count"] == 16 and page.view["target_count"] == 20
assert len(page.table.get_children()) == 22
assert abs(page.view["cash"] - 374804.5308870999) < .01
checks = []
for phase in PHASES:
    app.phase_display.set(PHASES[phase])
    app.choose_phase(None)
    for label, experiment in page.options.items():
        page.strategy.set(label)
        page.choose()
        app.update()
        assert app.table.selection() == (experiment,)
        assert page.view["asof"] == app.summary["end"]
        checks.append({"phase": phase, "experiment": experiment, "held": page.view["held_count"]})
app.phase_display.set(PHASES["final_repaired"])
app.choose_phase(None)
app.update()
page.date.set("2026-09-29")
page.draw()
assert page.view["decision_date"] == "2026-08-31"
assert (page.view["trades"].date <= "2026-09-29").all()
page.latest()
directory = ROOT / "artifacts/ui_holdings"
directory.mkdir(exist_ok=True)


def save(name):
    app.update()
    ImageGrab.grab(window=int(app.frame(), 16)).save(directory/f"{name}.png")


def capture_holdings():
    app.tabs.select(page)
    save("portfolio_holdings")
    page.table.yview_moveto(1)
    app.after(300, capture_bottom)


def capture_bottom():
    save("portfolio_cash_and_zero_targets")
    app.tabs.select(app.stock)
    app.symbol.set("600519.SH")
    app.draw_stock()
    app.after(500, finish)


def finish():
    save("single_stock_explanation")
    app.open_stock_rules()
    app.update()
    windows = [child for child in app.winfo_children() if isinstance(child, tk.Toplevel)]
    assert len(windows) == 1
    def texts(widget):
        result = []
        for child in widget.winfo_children():
            if isinstance(child, tk.Text):
                result.append(child.get("1.0", "end"))
            result.extend(texts(child))
        return result
    assert any("w_t=I_t" in value for value in texts(windows[0]))
    windows[0].destroy()
    write_json("artifacts/ui_holdings/verification.json", {"checks": checks, "initial_tab": "指数增强" if app.enhancement.data else "组合持仓",
               "historical_date_no_future_target": True, "cash_reconciled": True, "full_stock_rules_opened": True,
               "screenshots_require_visual_review": True})
    print(json.dumps({"strategy_phase_views_checked": len(checks), "default_rows": len(page.table.get_children()), "status": "passed"}))
    app.destroy()


app.after(600, capture_holdings)
app.mainloop()
