"""Build reviewable research tables from independently acquired inputs."""
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'src'))
from quant_workbench_app.swine_data import ROOT, UNIVERSE, all_companies, dump, load_market, read

INDUSTRY_SOURCES = [
    {'id': 'capacity', 'title': '2026年修订生猪产能调控方案', 'date': '2026-05-18',
     'url': 'https://www.nahs.org.cn/dt/nyncbxx/202605/t20260518_472227.htm'},
    {'id': 'q3', 'title': '国家统计局：前三季度农业经济形势', 'date': '2026-10-20',
     'url': 'https://www.stats.gov.cn/sj/zxfbhjd/202610/t20261019_1965646.html'},
    {'id': 'q3release', 'title': '国家统计局：前三季度经济运行', 'date': '2026-10-19',
     'url': 'https://www.stats.gov.cn/sj/zxfbhjd/202610/t20261019_1965618.html'},
    {'id': 'price', 'title': '10月第3周屠宰企业收购价', 'date': '2026-10-22',
     'url': 'https://xmsyj.moa.gov.cn/jcyj/202610/t20261022_6488854.htm'}
]


def monthly_data():
    records = []
    receipts = read(ROOT / 'sources/documents/receipts.json')
    for doc in receipts:
        if '9月' not in doc['title'] or not doc.get('path'):
            continue
        pages = read((PROJECT / doc['path']).with_suffix('.json'))
        text = '\n'.join(p['text'] for p in pages)
        # Tables for the four companies share explicit year/month and five numeric columns.
        if doc['code'] not in ['002714', '603477', '001201', '605296']:
            continue
        pattern = r'2026\s*年\s*(\d{1,2})\s*月\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)'
        for match in re.finditer(pattern, text):
            month, volume, cumulative_volume, revenue, cumulative_revenue, price = match.groups()
            number = lambda s: float(s.replace(',', ''))
            records.append({'code': doc['code'], 'month': f'2026-{int(month):02}',
                            'volume_10k': number(volume), 'revenue_100m': number(revenue),
                            'price_per_kg': number(price), 'publication': doc['notice_date'][:10],
                            'source': doc['url'], 'source_path': doc['path'], 'page': 1,
                            'scope': '生猪总销量；价格为商品猪' if doc['code'] == '001201' else '商品猪（巨星为商品肥猪）；含内部销售口径依公告'})
    return records


def main():
    records = all_companies()
    dump(ROOT / 'results/companies.json', records)
    pd.DataFrame([{k: v for k, v in r.items() if k != 'business'} for r in records]).to_csv(
        ROOT / 'results/companies.csv', index=False, encoding='utf-8-sig')
    monthly = monthly_data()
    dump(ROOT / 'results/monthly_operations.json', monthly)
    source_receipts = []
    for source in INDUSTRY_SOURCES:
        target = ROOT / 'sources/industry' / f"{source['id']}.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            if not target.exists():
                response = httpx.get(source['url'], timeout=25, follow_redirects=True)
                response.raise_for_status()
                target.write_bytes(response.content)
            source_receipts.append({**source, 'path': str(target.relative_to(PROJECT)),
                                    'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'status': 'archived'})
        except httpx.HTTPError:
            source_receipts.append({**source, 'status': 'web_search_verified_local_archive_unavailable'})
    dump(ROOT / 'sources/industry/receipts.json', source_receipts)
    cycle = {
        'as_of': '2026-10-25',
        'headline': '产能去化已有证据，短期猪价与供给压力仍未解除',
        'interpretation': '研究判断：处于产能收缩与当期供给仍高并存阶段。数量去化不等于猪价立即反转，生产效率、出栏均重和需求都会改变传导。',
        'facts': [
            {'indicator': '能繁母猪正常保有量目标', 'value': 3750, 'unit': '万头', 'period': '2026年5月政策', 'source': 'capacity'},
            {'indicator': '能繁母猪存栏', 'value': 3602, 'unit': '万头', 'period': '2026年三季度末', 'yoy': -10.7, 'source': 'q3'},
            {'indicator': '生猪出栏', 'value': 53739, 'unit': '万头', 'period': '2026年前三季度', 'yoy': 1.4, 'source': 'q3release'},
            {'indicator': '猪肉产量', 'value': 4508, 'unit': '万吨', 'period': '2026年前三季度', 'yoy': 3.2, 'source': 'q3release'},
            {'indicator': '屠宰企业生猪平均收购价', 'value': 11.61, 'unit': '元/公斤', 'period': '2026-10-12至18日', 'yoy': -10.6, 'source': 'price'}
        ],
        'questions': [
            '供给：能繁母猪下降是否被PSY提升和出栏增重抵消？不能把母猪降幅直接当成未来猪肉供应降幅。',
            '经营：销售价格能否持续覆盖同口径完全成本？月报售价、现金成本、完全成本不是同一指标。',
            '财务：经营现金流是否足够覆盖资本开支与到期债务？亏损周期中的融资能力比静态PE更重要。',
            '估值：低PB是否伴随净资产继续消耗？以可持续盈利和资产质量验证，不能仅凭历史分位买入。',
            '证伪：若供给继续增加、猪价回落或现金流恶化，应下调景气判断；不因股价上涨而倒推周期判断正确。'
        ],
        'cost_observations': [
            {'code': '002714.SZ', 'value': 11.7, 'unit': '元/kg', 'period': '2026年6月', 'definition': '养殖完全成本，约数', 'document_page': 11},
            {'code': '605296.SH', 'value': 11.9, 'unit': '元/kg', 'period': '2026年6月', 'definition': '完全成本，单月', 'document_page': 13},
            {'code': '002124.SZ', 'value': 12.65, 'unit': '元/kg', 'period': '2026年上半年', 'definition': '完全成本，含空栏费用0.31元/kg', 'document_page': 13}
        ],
        'cost_warning': '成本观察的期间不同，不能与9月售价直接相减冒充当期利润；缺少同口径成本的公司明确显示未核实。',
        'sources': source_receipts
    }
    dump(ROOT / 'results/cycle.json', cycle)
    market, issues = load_market()
    failures = []
    for issue in issues:
        failures.append({'severity': 'high', 'issue': '核心公司行情缺口', **issue})
    for record in records:
        if record['group'] != 'core':
            continue
        if record['quote_date'] != '20261023':
            failures.append({'severity': 'high', 'code': record['code'], 'issue': '报价日期不一致'})
        if not record['ann_date'] or record['ann_date'] > '20261023':
            failures.append({'severity': 'high', 'code': record['code'], 'issue': '财报公告时点无效'})
    checks = {'status': 'passed' if not failures else 'failed', 'checked_at': datetime.now(timezone.utc).isoformat(),
              'company_count': len(records), 'core_count': sum(r['group']=='core' for r in records),
              'market_sessions': len(market['close']), 'monthly_rows': len(monthly), 'failures': failures,
              'limitations': ['公司池是当前判断，有历史回看偏差', '核心PB自2016年或上市后起，巨星从2021年起；业务及股本变化影响可比性',
                             '最新核心财务金额另有42项原文对账；历史年度未逐页核实；月报未经审计',
                             '内部销售抵消影响分部收入占比，不采用机械90%阈值']}
    dump(ROOT / 'results/data_quality.json', checks)
    print(json.dumps(checks, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
