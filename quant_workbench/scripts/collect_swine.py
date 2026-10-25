"""Fresh, credential-safe acquisition for the independent swine study."""
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import dotenv_values

PROJECT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((PROJECT / 'config/swine_research.json').read_text(encoding='utf-8'))
DEST = PROJECT / CONFIG['research_root']
CANDIDATES = {'002714.SZ': '牧原股份', '300498.SZ': '温氏股份', '002100.SZ': '天康生物',
              '002157.SZ': '正邦科技', '002124.SZ': '天邦食品', '002567.SZ': '唐人神',
              '002548.SZ': '金新农', '002726.SZ': '龙大美食', '000876.SZ': '新希望',
              '603477.SH': '巨星农牧', '002840.SZ': '华统股份', '002714.SZ': '牧原股份',
              '000735.SZ': '罗牛山', '002385.SZ': '大北农', '600975.SH': '新五丰',
              '300761.SZ': '立华股份', '002311.SZ': '海大集团', '001201.SZ': '东瑞股份',
              '605296.SH': '神农集团', '000048.SZ': '京基智农', '603363.SH': '傲农生物',
              '603717.SH': '天域生物', '000702.SZ': '正虹科技'}


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def acquire():
    token = None
    for env in (os.environ, dotenv_values(PROJECT.parent / '.env'), dotenv_values(PROJECT / '.env')):
        token = next((env[k] for k in ('TUSHARE_TOKEN', 'TS_TOKEN', 'TUSHARE_API_TOKEN') if env.get(k)), None)
        if token:
            break
    if not token:
        raise RuntimeError('行情源凭据不可用，未输出或创建凭据')
    receipts = []
    client = httpx.Client(timeout=40)
    def query(api, params, label):
        spec = {'api': api, 'params': params}
        key = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()
        target = DEST / 'sources' / f'{key}.json'
        if target.exists():
            cached = json.loads(target.read_text(encoding='utf-8'))
            receipts.append(cached['receipt'])
            return cached['rows']
        for attempt in range(3):
            try:
                response = client.post('https://api.tushare.pro', json={'api_name': api, 'token': token, 'params': params, 'fields': ''})
                response.raise_for_status()
                body = response.json()
                if body.get('code') != 0:
                    raise RuntimeError(f'provider_code_{body.get("code")}')
                data = body.get('data') or {'fields': [], 'items': []}
                rows = [dict(zip(data['fields'], r, strict=True)) for r in data['items']]
                receipt = {**spec, 'label': label, 'fetched_at': datetime.now(timezone.utc).isoformat(),
                           'rows': len(rows), 'sha256': hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest(),
                           'source': 'https://api.tushare.pro', 'path': str(target.relative_to(PROJECT))}
                save(target, {'receipt': receipt, 'rows': rows})
                receipts.append(receipt)
                print(f'{label} {api}: {len(rows)} rows', flush=True)
                time.sleep(.4)
                return rows
            except (httpx.HTTPError, ValueError, RuntimeError):
                if attempt == 2:
                    receipts.append({**spec, 'label': label, 'status': 'failed', 'reason': 'provider query unavailable'})
                    print(f'{label} {api}: unavailable', flush=True)
                    return []
                time.sleep(2 ** attempt)
    basic = query('stock_basic', {'list_status': 'L'}, '全市场上市公司')
    save(DEST / 'data/stock_basic.json', basic)
    calendar = query('trade_cal', {'exchange': 'SSE', 'start_date': '20250101', 'end_date': '20261023'}, '交易日历')
    save(DEST / 'data/calendar.json', calendar)
    for code, name in CANDIDATES.items():
        values = {'code': code, 'name': name}
        for api in ('daily', 'adj_factor', 'daily_basic', 'stk_limit'):
            values[api] = query(api, {'ts_code': code, 'start_date': '20250101', 'end_date': '20261023'}, name)
        for api in ('income', 'balancesheet', 'cashflow', 'fina_indicator'):
            values[api] = query(api, {'ts_code': code, 'start_date': '20250101', 'end_date': '20261023'}, name)
        values['dividend'] = query('dividend', {'ts_code': code}, name)
        values['fina_mainbz'] = query('fina_mainbz', {'ts_code': code, 'period': '20260630', 'type': 'P'}, name)
        save(DEST / f'data/{code}.json', values)
        save(DEST / 'sources/receipts.json', receipts)
    benchmark = query('index_daily', {'ts_code': '000300.SH', 'start_date': '20250101', 'end_date': '20261023'}, '沪深300价格指数')
    save(DEST / 'data/benchmark.json', benchmark)
    etf = {'code': '510300.SH', 'name': '沪深300ETF'}
    for api, field in [('fund_daily', 'daily'), ('fund_adj', 'adj_factor')]:
        etf[field] = query(api, {'ts_code': '510300.SH', 'start_date': '20250101', 'end_date': '20261023'}, '沪深300ETF')
    save(DEST / 'data/510300.SH.json', etf)
    save(DEST / 'sources/receipts.json', receipts)
    client.close()


if __name__ == '__main__':
    acquire()
