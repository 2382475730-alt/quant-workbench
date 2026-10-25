"""Company-statement source collection for pre-registered case studies."""
import json

from .collect import save_frame
from .data import ROOT, Client, ProviderError, write_json


def run():
    settings = json.loads((ROOT / "config/experiments.json").read_text(encoding="utf-8"))
    client = Client()
    records = []
    for code in settings["single_stock_examples"]:
        for api in ["income", "balancesheet", "cashflow"]:
            rows = []
            try:
                for year in range(2015, 2027):
                    chunk = client.query(api, {"ts_code": code, "start_date": f"{year}0101",
                                               "end_date": min(f"{year}1231", "20261023"), "report_type": "1"})["rows"]
                    if len(chunk) >= 100:
                        raise ProviderError(f"{api}: possible yearly truncation")
                    rows.extend(chunk)
                save_frame(f"{api}/{code}.parquet", rows)
                records.append({"symbol": code, "api": api, "rows": len(rows), "status": "ok"})
            except ProviderError as e:
                records.append({"symbol": code, "api": api, "status": str(e)})
            write_json("artifacts/statement_collection.json", records)
            print(records[-1], flush=True)


if __name__ == "__main__":
    run()
