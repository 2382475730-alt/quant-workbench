"""Explicit bridge to immutable historical research; new writes stay in runtime."""
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
WORKSPACE = PROJECT.parent
SETTINGS = json.loads((PROJECT / "config/workbench.json").read_text(encoding="utf-8"))
LIBRARY = (PROJECT / SETTINGS["research_library"]).resolve()
RUNTIME = PROJECT / "runtime"
if not (LIBRARY / "src/quant_workbench/data.py").is_file():
    raise RuntimeError(f"研究资料库不可用：{LIBRARY}")
sys.path.insert(0, str(LIBRARY / "src"))


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save_state(value, path=None):
    target = Path(path) if path else RUNTIME / "ui_state.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(target)
