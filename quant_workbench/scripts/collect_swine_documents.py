"""Retrieve current issuer originals, with page-level extracted text and receipts."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
from pypdf import PdfReader

PROJECT = Path(__file__).resolve().parents[1]
DEST = PROJECT / 'runtime/research/swine_v1_20261025/sources/documents'
CODES = ['002714', '603477', '600975', '001201', '605296', '002124', '603717', '000048']


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    receipts = []
    with httpx.Client(timeout=40, follow_redirects=True) as client:
        for code in CODES:
            entries = []
            for page in range(1, 6):
                params = {'sr': -1, 'page_size': 100, 'page_index': page, 'ann_type': 'A',
                          'client_source': 'web', 'stock_list': code,
                          'begin_time': '2026-08-01', 'end_time': '2026-10-25'}
                try:
                    response = client.get('https://np-anotice-stock.eastmoney.com/api/security/ann', params=params)
                    response.raise_for_status()
                    payload = response.json()
                    (DEST / f'{code}_index_{page}.json').write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
                    items = payload.get('data', {}).get('list', [])
                    entries.extend(items)
                    if len(entries) >= payload.get('data', {}).get('total_hits', 0):
                        break
                except (httpx.HTTPError, ValueError):
                    print(code, 'index unavailable', flush=True)
                    break
            selected = [x for x in entries if ('2026年半年度报告' in x['title'] or '2026年第三季度报告' in x['title'] or '2026年三季度报告' in x['title'] or ('2026年9月' in x['title'] and ('销售' in x['title'] or '经营' in x['title'])))
                        and not any(w in x['title'] for w in ['摘要', '提示', '董事', '监事', '说明会'])]
            for item in selected:
                url = f"https://pdf.dfcfw.com/pdf/H2_{item['art_code']}_1.pdf"
                target = DEST / f"{code}_{item['art_code']}.pdf"
                try:
                    if not target.exists():
                        response = client.get(url)
                        response.raise_for_status()
                        target.write_bytes(response.content)
                    reader = PdfReader(target)
                    pages = [{'page': i+1, 'text': p.extract_text()} for i, p in enumerate(reader.pages)]
                    target.with_suffix('.json').write_text(json.dumps(pages, ensure_ascii=False), encoding='utf-8')
                    receipts.append({'code': code, 'title': item['title'], 'notice_date': item['notice_date'], 'url': url,
                                     'path': str(target.relative_to(PROJECT)), 'pages': len(pages),
                                     'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                                     'fetched_at': datetime.now(timezone.utc).isoformat()})
                    print(code, item['title'], len(pages), 'pages', flush=True)
                except Exception as exc:
                    receipts.append({'code': code, 'title': item['title'], 'url': url, 'status': 'failed', 'type': type(exc).__name__})
            (DEST / 'receipts.json').write_text(json.dumps(receipts, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
