"""Content-hashed raw API responses, resumable queries and restricted writes."""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]


def write_json(relative: str, value):
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("Write outside quant root")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
    return path


def credentials():
    # Read-only credential bridge; never print or persist credential values.
    for mapping in (os.environ, dotenv_values(ROOT / ".env"), dotenv_values(ROOT.parent / ".env")):
        for key in ("TUSHARE_TOKEN", "TS_TOKEN", "TUSHARE_API_TOKEN"):
            if mapping.get(key):
                return mapping[key]
    raise RuntimeError("Tushare credential unavailable")


class ProviderError(RuntimeError):
    pass


class Client:
    def __init__(self, delay=0.35):
        self.token = credentials()
        self.http = httpx.Client(timeout=60)
        self.delay = delay

    def query(self, api, params, fields="", refresh=False):
        spec = {"api": api, "params": params, "fields": fields}
        key = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()
        path = ROOT / "data" / "queries" / f"{key}.json"
        if path.exists() and not refresh:
            return json.loads(path.read_text(encoding="utf-8"))
        for attempt in range(4):
            time.sleep(self.delay)
            try:
                response = self.http.post("https://api.tushare.pro", json={
                    "api_name": api, "token": self.token, "params": params, "fields": fields})
                response.raise_for_status()
                body = response.json()
            except (httpx.HTTPError, ValueError):
                if attempt == 3:
                    raise ProviderError(f"{api}: transport failure") from None
                time.sleep(2 ** attempt)
                continue
            if body.get("code") != 0:
                msg = str(body.get("msg", ""))
                category = "permission_denied" if any(x in msg for x in ["权限", "积分", "无权"]) else "provider_error"
                if any(x in msg for x in ["每分钟", "频率", "每小时"]):
                    if attempt < 3:
                        time.sleep(20)
                        continue
                    category = "rate_limit"
                raise ProviderError(f"{api}: {category}; code={body.get('code')}")
            raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
            digest = hashlib.sha256(raw).hexdigest()
            raw_path = ROOT / "data" / "raw" / f"{digest}.json"
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            if not raw_path.exists():
                raw_path.write_bytes(raw)
            data = body.get("data") or {"fields": [], "items": []}
            result = {**spec, "fetched_at": datetime.now(UTC).isoformat(),
                      "sha256": digest, "fields_returned": data["fields"],
                      "rows": [dict(zip(data["fields"], r, strict=True)) for r in data["items"]]}
            write_json(f"data/queries/{key}.json", result)
            return result
        raise ProviderError(f"{api}: retries exhausted")


def protect_legacy():
    baseline = ROOT / "artifacts" / "legacy_baseline.json"
    if baseline.exists():
        return
    skip = {"quant_workbench", ".venv", ".git", ".pytest_cache", ".ruff_cache", "__pycache__", "tmp"}
    files = {}
    for current, dirs, names in os.walk(ROOT.parent):
        dirs[:] = [d for d in dirs if d not in skip]
        for name in names:
            path = Path(current) / name
            files[str(path.relative_to(ROOT.parent))] = hashlib.sha256(path.read_bytes()).hexdigest()
    write_json("artifacts/legacy_baseline.json", {"created_at": datetime.now(UTC).isoformat(), "files": files})


def probe():
    protect_legacy()
    client = Client()
    queries = [
        ("trade_cal", {"exchange": "SSE", "start_date": "20261001", "end_date": "20261024"}),
        ("stock_basic", {"exchange": "", "list_status": "L"}),
        ("stock_basic", {"exchange": "", "list_status": "D"}),
        ("daily", {"ts_code": "600000.SH", "start_date": "20261001", "end_date": "20261023"}),
        ("adj_factor", {"ts_code": "600000.SH", "start_date": "20261001", "end_date": "20261023"}),
        ("daily_basic", {"ts_code": "600000.SH", "trade_date": "20261022"}),
        ("index_weight", {"index_code": "000300.SH", "start_date": "20150101", "end_date": "20150131"}),
        ("index_daily", {"ts_code": "000300.SH", "start_date": "20261001", "end_date": "20261023"}),
        ("stk_limit", {"ts_code": "600000.SH", "start_date": "20261001", "end_date": "20261023"}),
        ("suspend_d", {"trade_date": "20261022"}),
        ("dividend", {"ts_code": "600000.SH"}),
        ("fina_indicator", {"ts_code": "600000.SH", "start_date": "20250101", "end_date": "20261023"}),
        ("namechange", {"ts_code": "600000.SH"}),
    ]
    statuses = []
    for api, params in queries:
        try:
            data = client.query(api, params)
            status = {"api": api, "params": params, "status": "ok", "rows": len(data["rows"]), "fields": data["fields_returned"]}
        except ProviderError as error:
            status = {"api": api, "params": params, "status": str(error)}
        statuses.append(status)
        write_json("artifacts/provider_probe.json", statuses)
        print(json.dumps({k: v for k, v in status.items() if k != "fields"}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    probe()
