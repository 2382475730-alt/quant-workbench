"""Acquire suspension evidence and reconcile gaps, without imputing tradable quotes."""
import hashlib
import json

import pandas as pd

from .collect import END, START, save_frame
from .data import ROOT, Client, ProviderError, write_json


def collect():
    symbols = json.loads((ROOT / "artifacts/universe_manifest.json").read_text())["symbols"]
    client = Client()
    failed = []
    for index, code in enumerate(symbols):
        try:
            rows = client.query("suspend_d", {"ts_code": code, "start_date": START, "end_date": END})["rows"]
            if len(rows) >= 5000:
                rows = []
                for year in range(2015, 2027):
                    chunk = client.query("suspend_d", {"ts_code": code, "start_date": f"{year}0101",
                                                         "end_date": min(f"{year}1231", END)})["rows"]
                    if len(chunk) >= 5000:
                        raise ProviderError("Suspension result may be truncated")
                    rows.extend(chunk)
            save_frame(f"suspend_d/{code}.parquet", rows)
        except ProviderError as exc:
            failed.append({"code": code, "error": str(exc)})
        if (index + 1) % 25 == 0 or index + 1 == len(symbols):
            state = {"stage": "complete" if index + 1 == len(symbols) else "collecting", "completed": index + 1,
                     "total": len(symbols), "failures": failed}
            write_json("artifacts/suspension_collection.json", state)
            print(json.dumps(state, ensure_ascii=False), flush=True)


def audit(close=None):
    from .prepare import load_table
    close = pd.read_parquet(ROOT / "data/panels/close.parquet") if close is None else close
    master = load_table("stock_basic").set_index("ts_code")
    source_file = ROOT / "config/listing_suspensions.json"
    intervals = json.loads(source_file.read_text(encoding="utf-8")) if source_file.exists() else []
    for interval in intervals:
        for source in interval["sources"]:
            path = (ROOT / source["path"]).resolve()
            if not path.is_relative_to(ROOT.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
                raise ValueError("Listing-status source missing or changed")
    profiles = []
    for code in close:
        valid = close[code].dropna()
        if valid.empty:
            continue
        listed = pd.Timestamp(master.at[code, "list_date"])
        delisted = pd.Timestamp(master.at[code, "delist_date"]) if pd.notna(master.at[code, "delist_date"]) else None
        window = close.index >= max(listed, close.index[0])
        if delisted is not None:
            window &= close.index < delisted
        in_listing = close.loc[window, code]
        gaps = in_listing.index[in_listing.isna()]
        suspension = load_table("suspend_d", code)
        stopped = set(pd.to_datetime(suspension.loc[suspension.suspend_type.eq("S"), "trade_date"])) if len(suspension) else set()
        explained = set(gaps) & stopped
        listing_gap = set()
        evidence = []
        for interval in intervals:
            if interval["code"] != code:
                continue
            window = (close.index >= pd.Timestamp(interval["start"])) & (close.index < pd.Timestamp(interval["end_exclusive"]))
            if close.loc[window, code].notna().any():
                raise ValueError(f"Quotes conflict with reviewed listing suspension: {code}")
            listing_gap.update(set(close.index[window]) & set(gaps))
            evidence.append(interval)
        unknown = sorted(set(gaps) - stopped - listing_gap)
        profiles.append({"code": code, "missing_during_listing": len(gaps), "suspension_rows_match": len(explained),
                         "listing_suspension_only_match": len(listing_gap - explained), "listing_status_evidence": evidence,
                         "unexplained_dates": [str(d.date()) for d in unknown],
                         "delist_date": str(delisted.date()) if delisted is not None else None,
                         "last_quote": str(valid.index[-1].date())})
    result = {"profiles": profiles,
              "totals": {key: sum(p[key] for p in profiles) for key in
                         ["missing_during_listing", "suspension_rows_match", "listing_suspension_only_match"]},
              "unexplained_count": sum(len(p["unexplained_dates"]) for p in profiles),
              "limitation": "Suspension records are evidence, not a licence to forward-fill tradable prices. Last-quote holdings remain economically exposed and may be untradeable."}
    write_json("artifacts/suspension_audit.json", result)
    return result


if __name__ == "__main__":
    collect()
    audit()
