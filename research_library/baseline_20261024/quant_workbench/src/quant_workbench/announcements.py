"""Find public issuer notices for flagged corporate actions; never auto-adjudicate."""
from __future__ import annotations

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import httpx
import pandas as pd
from pypdf.errors import PdfReadError

from .data import ROOT, write_json
from .sources import archive

NOTICE_ENDPOINT = "https://np-anotice-stock.eastmoney.com/api/security/ann"
RELEVANT = re.compile(r"权益分派.*实施|权益分派.*补充|股息分派.*实施|利润分配.*实施|分红派息.*实施|配股发行结果|配股股份变动|差异化|除权|除息|转增股本.*实施|转增股本.*登记")


def search_notices(code, begin, end):
    """Enumerate a bounded date window, retaining every page and its hash."""
    found = []
    for page in range(1, 51):
        params = {"sr": -1, "page_size": 100, "page_index": page, "ann_type": "A",
                  "client_source": "web", "stock_list": code[:6],
                  "begin_time": begin, "end_time": end}
        key = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:20]
        path = ROOT / "data/announcement_indexes" / f"{key}.json"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
        else:
            response = httpx.get(NOTICE_ENDPOINT, params=params, timeout=30)
            response.raise_for_status()
            payload = {"url": str(response.url), "response_sha256": hashlib.sha256(response.content).hexdigest(),
                       "response": response.json()}
            write_json(str(path.relative_to(ROOT)), payload)
        raw = payload["response"]
        if raw.get("success") != 1:
            raise ValueError("Public notice index unsuccessful")
        data = raw.get("data", {})
        items = data.get("list", [])
        found.extend({**item, "index_path": str(path.relative_to(ROOT))} for item in items)
        if len(found) >= int(data.get("total_hits", 0)):
            return found
        if not items:
            raise ValueError("Missing announcement index page")
    raise ValueError("Announcement search exceeds 5000 records")


def notices(code, date):
    day = pd.Timestamp(date).date()
    params = {"sr": -1, "page_size": 100, "page_index": 1, "ann_type": "A",
              "client_source": "web", "stock_list": code[:6],
              "begin_time": str(day - timedelta(days=45)),
              "end_time": str(day + timedelta(days=10))}
    key = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:20]
    path = ROOT / "data/announcement_indexes" / f"{key}.json"
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        response = httpx.get(NOTICE_ENDPOINT, params=params, timeout=30)
        response.raise_for_status()
        raw = response.json()
        if raw.get("success") != 1:
            raise ValueError("Public notice index unsuccessful")
        payload = {"url": str(response.url), "response_sha256": hashlib.sha256(response.content).hexdigest(),
                   "response": raw}
        write_json(str(path.relative_to(ROOT)), payload)
    raw = payload["response"]
    data = raw.get("data", {})
    if int(data.get("total_hits", 0)) > 100:
        raise ValueError(f"Notice search truncated: {code} {date}")
    found = []
    for item in data.get("list", []):
        if RELEVANT.search(item["title"]):
            url = f"https://pdf.dfcfw.com/pdf/H2_{item['art_code']}_1.pdf"
            try:
                receipt = archive(url)
                found.append({"title": item["title"], "notice_date": item["notice_date"], "receipt": receipt})
            except (httpx.HTTPError, ValueError, OSError, PdfReadError) as exc:
                found.append({"title": item["title"], "url": url, "error": str(exc)})
    return {"code": code, "date": date, "index": str(path.relative_to(ROOT)), "notices": found}


def main():
    events = json.loads((ROOT / "artifacts/held_issue_queue.json").read_text(encoding="utf-8"))
    def fetch(event):
        try:
            return notices(event["code"], event["date"])
        except (httpx.HTTPError, ValueError, OSError, PdfReadError) as exc:
            return {"code": event["code"], "date": event["date"], "error": str(exc)}
    result = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        for row in pool.map(fetch, events):
            result.append(row)
            print(row["code"], row["date"], row.get("error", [(n["title"], n.get("error", "archived")) for n in row.get("notices", [])]), flush=True)
    write_json("artifacts/held_event_notices.json", result)


if __name__ == "__main__":
    main()
