"""Append-only input acquisition for the separate index-enhancement experiment."""
import json

import pandas as pd

from quant_workbench.data import ROOT, Client, write_json

BASE = ROOT / "data/enhancement_v1"


def run():
    BASE.mkdir(parents=True, exist_ok=True)
    client = Client()
    receipts = []

    def get(api, params, name):
        result = client.query(api, params)
        frame = pd.DataFrame(result["rows"], columns=result["fields_returned"])
        if len(frame) >= (2000 if api == "index_member_all" else 5000):
            raise RuntimeError(f"Potential truncation: {api} {params}")
        frame.to_parquet(BASE / f"{name}.parquet", index=False)
        receipts.append({k: result[k] for k in ["api", "params", "sha256", "fetched_at"]} | {"file": f"{name}.parquet", "rows": len(frame)})
        return frame

    dates = {"start_date": "20150101", "end_date": "20261023"}
    get("index_daily", {"ts_code": "H00300.CSI", **dates}, "benchmark")
    get("fund_daily", {"ts_code": "510300.SH", **dates}, "etf_daily")
    get("etf_limit", {"ts_code": "510300.SH", **dates}, "etf_limits")
    # fund_adj caps a response at 2600: always partition by year.
    factors = []
    for year in range(2015, 2027):
        factors.append(get("fund_adj", {"ts_code": "510300.SH", "start_date": f"{year}0101", "end_date": min(f"{year}1231", "20261023")}, f"etf_adj_{year}"))
    pd.concat(factors).to_parquet(BASE / "etf_adj.parquet", index=False)
    get("fund_div", {"ts_code": "510300.SH"}, "etf_div")
    industries = get("index_classify", {"level": "L1", "src": "SW2021"}, "industry_codes")
    all_members = []
    for n, code in enumerate(industries.index_code, 1):
        for new in ["Y", "N"]:
            all_members.append(get("index_member_all", {"l1_code": code, "is_new": new}, f"industry_{code}_{new}"))
        print(json.dumps({"stage": "industries", "completed": n, "total": len(industries)}), flush=True)
        write_json("artifacts/enhancement_v1/source_receipts.json", receipts)
    pd.concat(all_members).drop_duplicates().to_parquet(BASE / "industry_history.parquet", index=False)
    write_json("artifacts/enhancement_v1/source_receipts.json", receipts)
    print("Acquisition complete", flush=True)


if __name__ == "__main__":
    run()
