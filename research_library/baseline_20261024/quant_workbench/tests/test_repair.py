import pytest

from quant_workbench.research import verify_repair_scope


def test_repair_preserves_registered_rules_across_windows_path_keys():
    original = {"config\\experiments.json": "a", "src\\quant_workbench\\signals.py": "b",
                "research\\protocol.md": "c", "src\\quant_workbench\\engine.py": "old"}
    current = {k.replace("\\", "/"): v for k, v in original.items()}
    current["src/quant_workbench/engine.py"] = "repaired"
    verify_repair_scope(original, current)
    current["config/experiments.json"] = "retuned"
    with pytest.raises(RuntimeError, match="strategy rules"):
        verify_repair_scope(original, current)


def test_repair_rejects_missing_original_rules():
    with pytest.raises(RuntimeError, match="strategy rules"):
        verify_repair_scope({}, {})
