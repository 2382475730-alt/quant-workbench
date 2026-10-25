"""Resumable acquisition; performance is not computed by this module."""
from __future__ import annotations

import calendar
import json
from datetime import UTC, datetime

import pandas as pd

from .data import ROOT, Client, ProviderError, protect_legacy, write_json

START = "20150101"
END = "20261023"


def save_frame(relative, rows):
    path = (ROOT / "data" / "normalized" / relative).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("Write outside quant root")
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    temp = path.with_suffix(".tmp.parquet")
    frame.to_parquet(temp, index=False)
    temp.replace(path)
    return frame


def status(value):
    value["updated_at"] = datetime.now(UTC).isoformat()
    write_json("artifacts/collection_status.json", value)
    print(json.dumps(value, ensure_ascii=False), flush=True)


def run():
    protect_legacy()
    client = Client()
    master = []
    for listing in ["L", "D", "P"]:
        rows = client.query("stock_basic", {"exchange": "", "list_status": listing},
                            "ts_code,symbol,name,area,industry,market,exchange,list_status,list_date,delist_date")['rows']
        master.extend(rows)
    save_frame("stock_basic.parquet", master)
    cal = client.query("trade_cal", {"exchange": "SSE", "start_date": START, "end_date": END})
    save_frame("calendar.parquet", cal["rows"])
    memberships = []
    for year in range(2015, 2027):
        for month in range(1, 13):
            first = f"{year}{month:02d}01"
            if first > END:
                break
            last = min(f"{year}{month:02d}{calendar.monthrange(year, month)[1]}", END)
            rows = client.query("index_weight", {"index_code": "000300.SH", "start_date": first, "end_date": last})["rows"]
            if len(rows) >= 4500:
                # Provider cap: partition by day rather than accept silent truncation.
                rows = []
                for day in range(1, calendar.monthrange(year, month)[1] + 1):
                    date = f"{year}{month:02d}{day:02d}"
                    if date <= END:
                        rows.extend(client.query("index_weight", {"index_code": "000300.SH", "trade_date": date})["rows"])
            memberships.extend(rows)
            save_frame("membership.parquet", memberships)
            status({"stage": "membership", "month": first[:6], "rows": len(memberships)})
    member_frame = pd.DataFrame(memberships)
    if member_frame.empty:
        raise RuntimeError("No historical memberships; cannot define investment universe")
    duplicates = int(member_frame.duplicated(["index_code", "con_code", "trade_date"]).sum())
    if duplicates:
        raise RuntimeError(f"Duplicate membership keys: {duplicates}")
    codes = sorted(member_frame.con_code.unique())
    write_json("artifacts/universe_manifest.json", {
        "index": "000300.SH", "start": START, "end": END, "symbols": codes,
        "snapshot_dates": sorted(member_frame.trade_date.unique()),
        "limitation": "Monthly snapshots lack explicit announcement timestamps. Apply previous-month snapshot only; disclose point-in-time proxy limitation. Current industry labels must not be used as historical classifications."})
    for index in ["000300.SH", "000905.SH", "000001.SH"]:
        rows = client.query("index_daily", {"ts_code": index, "start_date": START, "end_date": END})["rows"]
        save_frame(f"index/{index}.parquet", rows)
    endpoints = {
        "daily": "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount",
        "adj_factor": "ts_code,trade_date,adj_factor",
        "stk_limit": "ts_code,trade_date,pre_close,up_limit,down_limit",
        "daily_basic": "ts_code,trade_date,close,turnover_rate,pe_ttm,pb,ps_ttm,dv_ttm,total_share,float_share,total_mv,circ_mv",
        "dividend": "",
        "namechange": "",
        "fina_indicator": "ts_code,ann_date,end_date,eps,bps,roe,roa,grossprofit_margin,netprofit_margin,debt_to_assets,ocf_to_or,netprofit_yoy,or_yoy,update_flag",
    }
    failures = []
    for n, code in enumerate(codes):
        counts = {}
        for api, fields in endpoints.items():
            params = {"ts_code": code}
            if api not in {"dividend", "namechange"}:
                params.update(start_date=START, end_date=END)
            try:
                rows = client.query(api, params, fields)["rows"]
                cap = 100 if api == "fina_indicator" else 5000
                if len(rows) >= cap:
                    # Split any potentially truncated date-bounded response by year.
                    if api in {"dividend", "namechange"}:
                        raise ProviderError(f"{api}: potential truncation")
                    rows = []
                    for year in range(2015, 2027):
                        chunk = client.query(api, {"ts_code": code, "start_date": f"{year}0101", "end_date": min(f"{year}1231", END)}, fields)["rows"]
                        if len(chunk) >= cap:
                            raise ProviderError(f"{api}: yearly truncation")
                        rows.extend(chunk)
                save_frame(f"{api}/{code}.parquet", rows)
                counts[api] = len(rows)
            except ProviderError as exc:
                failures.append({"symbol": code, "api": api, "error": str(exc)})
                write_json("artifacts/collection_failures.json", failures)
        status({"stage": "stocks", "completed": n + 1, "total": len(codes), "symbol": code,
                "rows": counts, "failures": len(failures)})
    status({"stage": "complete", "symbols": len(codes), "failures": len(failures)})


if __name__ == "__main__":
    run()
