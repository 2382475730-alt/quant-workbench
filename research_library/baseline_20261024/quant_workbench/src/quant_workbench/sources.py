"""Archive public primary documents with content hashes and PDF structure checks."""
from __future__ import annotations

import hashlib
import io
import json
from datetime import UTC, datetime

import httpx
from pypdf import PdfReader

from .data import ROOT, write_json


def archive(url: str):
    key = hashlib.sha256(url.encode()).hexdigest()[:20]
    directory = ROOT / "data/source_documents"
    directory.mkdir(parents=True, exist_ok=True)
    receipt_path = directory / f"{key}.json"
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        cached = ROOT / receipt["path"]
        if not cached.is_file() or hashlib.sha256(cached.read_bytes()).hexdigest() != receipt["sha256"]:
            raise ValueError("Archived source missing or hash mismatch")
        return receipt
    response = httpx.get(url, timeout=60, follow_redirects=True)
    response.raise_for_status()
    content = response.content
    is_pdf = content.startswith(b"%PDF")
    if url.lower().endswith(".pdf") and not is_pdf:
        raise ValueError("Expected PDF; received another content type")
    suffix = ".pdf" if is_pdf else ".html"
    path = directory / f"{key}{suffix}"
    path.write_bytes(content)
    receipt = {"url": url, "resolved_url": str(response.url), "path": str(path.relative_to(ROOT)),
               "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content),
               "downloaded_at": datetime.now(UTC).isoformat()}
    if is_pdf:
        reader = PdfReader(io.BytesIO(content))
        receipt["pages"] = len(reader.pages)
        extracted = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        path.with_suffix(".txt").write_text(extracted, encoding="utf-8")
        receipt["text_characters"] = len(extracted)
    write_json(str(receipt_path.relative_to(ROOT)), receipt)
    return receipt


def archive_overrides():
    overrides = json.loads((ROOT / "config/action_overrides.json").read_text(encoding="utf-8"))
    receipts = []
    for url in sorted({o["source"] for o in overrides}):
        receipts.append(archive(url))
        print(url, receipts[-1]["bytes"], flush=True)
    write_json("artifacts/action_source_receipts.json", receipts)


if __name__ == "__main__":
    archive_overrides()
