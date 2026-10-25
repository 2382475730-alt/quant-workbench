"""Launch the real Tk app and capture each tab for visual review."""
from PIL import ImageGrab
from quant_workbench.desktop import Desktop

from quant_workbench.data import ROOT, write_json

app = Desktop()
app.update()
directory = ROOT / "artifacts/ui"
directory.mkdir(exist_ok=True)
labels = ["portfolio", "portfolio_holdings", "single_stock", "holdings_risk", "data_quality", "methods", "enhancement"]


def capture(index=0):
    if index >= len(labels):
        write_json("artifacts/ui/runtime_check.json", {
            "window": [app.winfo_width(), app.winfo_height()], "tabs": len(app.tabs.tabs()),
            "phase": app.phase.get(), "experiments_loaded": len(app.rows), "dpi_scale": scale,
            "outlook_rows": len(app.holdings_table.get_children()),
            "boundary": "Actual native Tk window opened and each tab captured; images require separate visual review."})
        app.destroy()
        return
    app.tabs.select(index)
    app.update()
    app.after(400, lambda: save(index))


def save(index):
    ImageGrab.grab(window=int(app.frame(), 16)).save(directory / f"{labels[index]}.png")
    app.after(100, lambda: capture(index + 1))


scale = ImageGrab.grab().width / app.winfo_screenwidth()
app.after(1000, capture)
app.mainloop()
