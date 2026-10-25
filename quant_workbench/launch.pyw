"""Stable desktop entry; does not rely on a stale editable-package installation."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from quant_workbench_app.desktop import main

main()
