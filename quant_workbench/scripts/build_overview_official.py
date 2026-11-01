"""Build the overview from archived originals, with per-field provenance."""
import calendar
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import shutil

from collect_overview_official import ROOT, PROJECT, plain, dump

DEEP = PROJECT / 'runtime/research/swine_deep_20261025'
H1 = {'002714.SZ': '002714_1225485220', '603477.SH': '603477_1225520167',
      '605296.SH': '605296_H1', '001201.SZ': '001201_1225525045',
      '600975.SH': '600975_1225534594', '002124.SZ': '002124_1225495961'}
# Values are transcribed from the same-period notes, then checked against text.
RESTRICTIONS = {
    '002714.SZ': (2917447226.25, 0, 153),
    '603477.SH': (256497695.92, 0, 163),
    '605296.SH': (40934343.26, 0, 177),
    '001201.SZ': (26647633.22, 0, 135),
    '600975.SH': (75444798.53, 227457049.21, 180),
    '002124.SZ': (60445090.22, 41064200.00, 148),
}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def pdf_pages(source):
    return read((ROOT / source['local_path']).with_suffix('.pages.json'))


def financials(source):
    pages = pdf_pages(source)
    start = next(i for i, p in enumerate(pages) if '合并资产负债表' in p['text'])
    text = '\n'.join(p['text'] for p in pages[start:start + 12])
    # Stop before parent-only statements; the consolidated table is first.
    if '母公司资产负债表' in text:
        text = text.split('母公司资产负债表')[0]
    def field(label):
        pattern = r'(?:^|\n)\s*' + r'\s*'.join(label) + r'\s+[^\n]*?([\d,]+\.\d{2})'
        match = re.search(pattern, text)
        if not match:
            raise ValueError(source['id'] + ' missing consolidated ' + label)
        value = float(match[1].replace(',', ''))
        page = next(p['page'] for p in pages if match[1] in p['text'] and label in re.sub(r'\s+', '', p['text']))
        return value, page
    return {key: field(label) for key, label in
            [('cash', '货币资金'), ('assets', '资产总计'), ('liabilities', '负债合计')]}


def assert_value(source, value, page=None):
    texts = pdf_pages(source)
    if page:
        texts = [p for p in texts if p['page'] in (page, page + 1)]
    tokens = (f'{value:,.2f}', f'{value:g}', str(value))
    assert any(token in p['text'] for token in tokens for p in texts), (source['id'], tokens, page)


def main():
    sources = read(ROOT / 'sources.json')
    by_id = {s['id']: s for s in sources}
    old = read(DEEP / 'model/results.json')
    profiles = []
    for existing in old['profiles']:
        code = existing['code']
        source = by_id[H1[code]]
        fields = financials(source)
        restricted, purpose, page = RESTRICTIONS[code]
        assert_value(source, restricted, page)
        if purpose:
            assert_value(source, purpose, page)
        cash = fields['cash'][0]
        available = cash - restricted - purpose
        assert available >= 0
        latest_source = source
        quarters = [s for s in sources if s['id'].startswith(code[:6] + '_') and
                    any(w in s['title'] for w in ('第三季度报告', '三季度报告'))]
        if quarters:
            latest_source = max(quarters, key=lambda s: s['published_date'])
        latest_fields = financials(latest_source)
        latest_period = '2026-09-30' if latest_source is not source else '2026-06-30'
        # Existing PB is explicitly the unchanged 10/23 research snapshot.
        profiles.append({
            'code': code, 'name': existing['name'], 'cash_period': '2026-06-30',
            'cash_published': source['published_date'], 'cash_source': source['id'],
            'cash_gross': cash, 'cash_restricted': restricted, 'cash_purpose_bound': purpose,
            'cash_available': available, 'cash_note_page': page,
            'cash_balance_page': fields['cash'][1],
            'debt_ratio': latest_fields['liabilities'][0] / latest_fields['assets'][0],
            'assets': latest_fields['assets'][0], 'liabilities': latest_fields['liabilities'][0],
            'debt_period': latest_period, 'debt_published': latest_source['published_date'],
            'debt_source': latest_source['id'],
            'debt_pages': [latest_fields['assets'][1], latest_fields['liabilities'][1]],
            'latest_cash_gross': latest_fields['cash'][0],
            'latest_cash_status': '受限及专用资金附注不足，未将本期货币资金当作可动用现金' if quarters else '同现金核实期',
            'pb': existing['disclosed_pb'], 'pb_market_date': '2026-10-23',
            'pb_book_period': existing['latest_period'],
            'pb_source_note': '沿用2026-10-25研究已核实的10/23行情与当时已披露净资产快照；不回填新财报',
        })

    # Preserve issuer-original cost disclosures as evidence, never reinterpret
    # upper bounds as exact values. Their mirror provenance stays explicit.
    old_sources = {s['id']: s for s in read(DEEP / 'evidence/sources.json')}
    costs = []
    for cost in old['costs']:
        c = dict(cost)
        original = old_sources[c['source_id']]
        source = dict(original)
        source['id'] = 'ARCHIVE_' + original['id']
        source['provenance'] = '既有公司原始披露归档；下载入口为镜像/互动问答转存，非本轮官方直连'
        local = DEEP / original['local_path']
        target = ROOT / 'sources' / local.name
        if not target.exists():
            shutil.copyfile(local, target)
        source['local_path'] = str(target.relative_to(ROOT))
        source['sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
        if local.with_suffix('.json').exists() and local.suffix != '.json':
            target_pages = target.with_suffix('.pages.json')
            if not target_pages.exists():
                shutil.copyfile(local.with_suffix('.json'), target_pages)
        c['source_id'] = source['id']
        c['source_path'] = source['local_path']
        costs.append(c)
        sources.append(source)
    # Direct official corroboration of the existing July Eastroc disclosure.
    eastroc = next(c for c in costs if c['code'] == '001201.SZ')
    eastroc.update(source_id='001201_IR_1225565651', locator='PDF文件页2',
                   source_path=by_id['001201_IR_1225565651']['local_path'])
    assert_value(by_id['001201_IR_1225565651'], 13.8)
    tianbang = next(c for c in costs if c['code'] == '002124.SZ')
    tianbang.update(source_id='002124_1225495961', locator='PDF文件页13',
                   source_path=by_id['002124_1225495961']['local_path'])
    assert_value(by_id['002124_1225495961'], 12.65, 13)
    muyuan = next(c for c in costs if c['code'] == '002714.SZ')
    official_replies = read(ROOT / by_id['MUYUAN_COST_OFFICIAL']['local_path'])['rows']
    assert any('2026年9月' in plain(r.get('attachedContent') or '') and
               '略低于11.5' in plain(r.get('attachedContent') or '') for r in official_replies)
    muyuan.update(source_id='MUYUAN_COST_OFFICIAL', source_path=by_id['MUYUAN_COST_OFFICIAL']['local_path'],
                  locator='深交所互动易答复；记录ID ' + by_id['MUYUAN_COST_OFFICIAL']['selected_record'])
    for r in profiles:
        r['cost'] = next((c for c in costs if c['code'] == r['code']), None)

    monthly = []
    industry = {}
    for source in sources:
        if not source['id'].startswith('MOA_MONTH_'):
            continue
        period = source['id'][-6:]
        html = (ROOT / source['local_path']).read_text(encoding='utf-8')
        rows = []
        for raw in re.findall(r'<tr\b[^>]*>(.*?)</tr>', html, re.S):
            cells = [plain(cell).strip() for cell in re.findall(r'<td\b[^>]*>(.*?)</td>', raw, re.S)]
            if len(cells) == 5:
                rows.append(cells)
        sow = next((x for x in rows if '能繁母猪存栏' in x[1]), None)
        year, month = int(period[:4]), int(period[4:])
        if not sow:
            monthly.append({'period': f'{year}-{month:02d}',
                'date': date(year, month, calendar.monthrange(year, month)[1]).isoformat(),
                'sows': None, 'mom_pct': None, 'yoy_pct': None, 'source': source['id'],
                'definition': '该月官方专题页未公布能繁母猪数，不插值补造', 'statistical_basis': '未公布'})
            continue
        def numeric(s):
            m = re.search(r'[+-]?\d+(?:\.\d+)?', s.replace(',', ''))
            return float(m[0]) if m else None
        row = {'period': f'{year}-{month:02d}', 'date': date(year, month, calendar.monthrange(year, month)[1]).isoformat(),
               'sows': numeric(sow[2]), 'mom_pct': numeric(sow[3]), 'yoy_pct': numeric(sow[4]),
               'source': source['id'], 'definition': sow[1],
               'statistical_basis': '国家统计局季度末调查' if month % 3 == 0 else '农业农村部按月度环比推算'}
        monthly.append(row)
        if period == '202609':
            for key, token in [('hog_inventory', '生猪存栏'), ('slaughter', '生猪出栏'), ('pork_output', '猪肉产量')]:
                cells = next(x for x in rows if token in x[1] and '能繁' not in x[1])
                industry[key] = {'value': numeric(cells[2]), 'yoy_pct': numeric(cells[4]),
                                 'mom_pct': numeric(cells[3]), 'definition': cells[1], 'source': source['id'],
                                 'period': '2026Q3末' if key == 'hog_inventory' else '2026年1—9月',
                                 'unit': '万吨' if key == 'pork_output' else '万头'}
    monthly.sort(key=lambda r: r['period'])
    assert len(monthly) == 21 and len({r['period'] for r in monthly}) == 21
    assert monthly[-1]['sows'] == 3602
    # Cross-check the monthly topic against the independent NBS release.
    nbs = (ROOT / by_id['NBS_Q3']['local_path']).with_suffix('.txt').read_text(encoding='utf-8')
    for value in (3602, 42533, 53739, 4508):
        assert str(value) in nbs

    prices = []
    for sid in ('MOA_PRICE_20261020', 'MOA_PRICE_20261027'):
        text = re.sub(r'\s+', '', (ROOT / by_id[sid]['local_path']).with_suffix('.txt').read_text(encoding='utf-8'))
        price = float(re.search(r'全国生猪平均价格([\d.]+)元', text)[1])
        observation = re.search(r'采集日为(\d+)月(\d+)日', text)
        mom = re.search(r'全国生猪平均价格[\d.]+元[^。]*?比前一周(上涨|下跌|下降)([\d.]+)%', text)
        prices.append({'source': sid, 'hog': price, 'published_date': by_id[sid]['published_date'],
                       'observation_date': f'2026-{int(observation[1]):02d}-{int(observation[2]):02d}' if observation else None,
                       'wow_pct': float(mom[2]) * (1 if mom[1] == '上涨' else -1) if mom else None})
    # Officially disclosed industry sample, explicitly distinct from national statistics.
    psy = {'value': 24.34, 'unit': '头/母猪/年', 'period': '2025年',
           'source': 'NEWHOPE_PSY', 'page': 22, 'scope': '微猪平台行业样本；新希望年报引述，非全国官方统计',
           'definition': '每头母猪每年提供的断奶仔猪数；样本与官方存栏调查范围不同，不能直接相乘预测产量'}
    psy_text = re.sub(r'\s+', '', pdf_pages(by_id['NEWHOPE_PSY'])[21]['text'])
    assert '24.34' in psy_text and '微猪' in psy_text
    # Retain original official price samples with their original source receipts.
    history = read(DEEP / 'model/price_history.json')
    historic_prices = [r for r in history['rows'] if r['period'] < '2026-10']
    for row in historic_prices:
        sid = row['source']
        original = old_sources[sid]
        if not any(s['id'] == sid for s in sources):
            target = ROOT / 'sources' / Path(original['local_path']).name
            if not target.exists():
                shutil.copyfile(DEEP / original['local_path'], target)
            sources.append({**original, 'local_path': str(target.relative_to(ROOT)),
                            'provenance': '复用既有农业农村部原文归档，未重新下载'})
    historic_prices.append({'period': '2026-10', **prices[-1]})
    result = {'version': 'swine_overview_20261029', 'as_of': '2026-10-29',
              'companies': profiles, 'capacity': monthly, 'industry': industry, 'psy': psy,
              'latest_price': prices[-1], 'price_comparison': prices, 'price_history': historic_prices,
              'policies': [
                  {'from': '2024-03-01', 'target': 3900, 'ratios': [.85, .92, 1.05, 1.10], 'source': 'POLICY_2024'},
                  {'from': '2026-05-14', 'target': 3750, 'ratios': [.88, .92, 1.03, 1.06], 'source': 'POLICY_2026'}],
              'notes': [
                  '部分月份官方专题页未公布能繁母猪数，缺月保留空值；季度末环比是较上季度，不与月环比混用。',
                  '现金统一核实至2026-06-30；较新季度货币资金在明细单列，未用半年报限制额扣减季度余额。',
                  '天邦另扣偿还指定债务的专用现金4106.42万元；新五丰另扣募集资金专户22745.70万元。',
                  'PSY为行业样本，不是农业农村部或国家统计局公布的全国均值。',
                  '新五丰未核实到可比绝对完全养殖成本，保留缺口；巨星、神农成本沿用公司原件归档，来源中标明镜像入口，非本轮官方直连。',
                  'PB保留10/23历史行情及当时净资产快照；本轮补充不回填历史研究与策略。',
                  '专题月份页未标明发布日期，保留为null，不用抓取日期冒充发布日期。'],
              }
    dump(ROOT / 'sources.json', list({s['id']: s for s in sources}.values()))
    dump(ROOT / 'overview.json', result)
    dump(ROOT / 'checks.json', {'status': 'passed', 'cash_originals': 6,
                              'monthly_slots': len(monthly), 'monthly_sows': sum(r['sows'] is not None for r in monthly),
                              'missing_months': [r['period'] for r in monthly if r['sows'] is None], 'nbs_crosschecks': 4,
                              'scope': '原文取数与计算核对，不构成审计或投资验证'})
    print(json.dumps({'status': 'passed', 'companies': len(profiles), 'monthly_sows': sum(r['sows'] is not None for r in monthly),
                      'cash_100m': {r['name']: round(r['cash_available'] / 1e8, 4) for r in profiles}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
