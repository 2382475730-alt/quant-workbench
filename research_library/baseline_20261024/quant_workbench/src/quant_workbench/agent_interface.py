"""Closed, JSON-compatible tools for a future LLM coordinator.

No model provider, credentials, arbitrary commands, network or broker routing.
The caller must enforce process isolation and its overall session budget.
"""
from __future__ import annotations

import math

from . import quant_agent

TOOLS = [
    {"name": "small_capital_status", "description": "Read isolated small-capital research status.",
     "parameters": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "small_capital_verify", "description": "Verify small-capital seals and ledger balances; no trading.",
     "parameters": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "small_capital_plan", "description": "Compute reference integer ETF plan under validated task constraints; never submit orders.",
     "parameters": {"type": "object", "properties": {"task": {"type": "object"}}, "required": ["task"], "additionalProperties": False}},
    {"name": "get_status", "description": "Read available frozen versions and research boundaries.",
     "parameters": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "verify_artifacts", "description": "Verify frozen inputs, full result manifests, ledger invariants and audit chain.",
     "parameters": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "run_registered", "description": "Resume the fixed experiment allowlist; completed results are reused after verification.",
     "parameters": {"type": "object", "properties": {"minutes": {"type": "number", "exclusiveMinimum": 0, "maximum": 240}},
                    "required": ["minutes"], "additionalProperties": False}},
    {"name": "build_report", "description": "Verify all results, then rebuild derived tables and charts. Does not tune strategies.",
     "parameters": {"type": "object", "properties": {}, "additionalProperties": False}},
]


def dispatch(name, arguments):
    if not isinstance(arguments, dict):
        raise TypeError("Arguments must be a JSON object")
    if name in {"small_capital_status", "small_capital_verify", "small_capital_plan"}:
        from .small_capital_v1.agent import dispatch as small_dispatch
        return small_dispatch(name, arguments)
    if name not in {t["name"] for t in TOOLS}:
        raise ValueError("Unknown tool; no arbitrary command execution")
    expected = {"minutes"} if name == "run_registered" else set()
    if set(arguments) != expected:
        raise ValueError("Unexpected or missing tool arguments")
    if name == "get_status":
        return quant_agent.status()
    if name == "verify_artifacts":
        return quant_agent.verify()
    if name == "run_registered":
        minutes = arguments["minutes"]
        if type(minutes) not in {int, float} or not math.isfinite(minutes) or not 0 < minutes <= 240:
            raise ValueError("Invalid finite time budget")
        return quant_agent.run(minutes)
    quant_agent.verify()
    from .enhancement_report import build
    build()
    return {"status": "generated", "report": "reports/enhancement_v1", "changes_frozen_research": False}
