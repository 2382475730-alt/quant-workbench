"""Financial meaning, policy boundaries and immutable-source admission checks."""
import hashlib
import json

import pytest

from quant_workbench_app.swine_overview import OVERVIEW_ROOT, capacity_zone


@pytest.mark.parametrize('value,prefix', [
    (3299.99, '红色'), (3300, '黄色'), (3449.99, '黄色'),
    (3450, '绿色'), (3862.5, '绿色'), (3862.51, '黄色'),
    (3975, '黄色'), (3975.01, '红色')])
def test_policy_threshold_endpoints(value, prefix):
    assert capacity_zone(value)[0].startswith(prefix)


def test_cash_excludes_dedicated_money_even_when_reported_as_cash_equivalents():
    data = json.loads((OVERVIEW_ROOT / 'overview.json').read_text(encoding='utf-8'))
    rows = {r['code']: r for r in data['companies']}
    # Both notes classify this as cash equivalents, yet its permitted use is
    # narrower than general working cash. Omitting it overstates liquidity.
    assert rows['002124.SZ']['cash_purpose_bound'] == 41064200
    assert rows['002124.SZ']['cash_available'] == pytest.approx(53558073.96)
    assert rows['600975.SH']['cash_purpose_bound'] == 227457049.21
    assert rows['600975.SH']['cash_available'] == pytest.approx(305406579.76)
    for row in rows.values():
        assert row['cash_period'] == '2026-06-30'
        assert row['cash_available'] == pytest.approx(
            row['cash_gross'] - row['cash_restricted'] - row['cash_purpose_bound'])
        assert row['cash_published'] <= data['as_of']
        assert row['debt_published'] <= data['as_of']
        if row['debt_period'] != row['cash_period']:
            assert '未将本期货币资金当作可动用现金' in row['latest_cash_status']


def test_sources_hashes_dates_and_statistical_scope():
    data = json.loads((OVERVIEW_ROOT / 'overview.json').read_text(encoding='utf-8'))
    sources = {r['id']: r for r in json.loads((OVERVIEW_ROOT / 'sources.json').read_text(encoding='utf-8'))}
    for source in sources.values():
        path = (OVERVIEW_ROOT / source['local_path']).resolve()
        assert path.is_relative_to(OVERVIEW_ROOT.resolve()) and path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source['sha256']
        assert not source.get('published_date') or source['published_date'] <= data['as_of']
    for row in data['companies']:
        assert 'static.cninfo.com.cn' in sources[row['cash_source']]['url']
        assert 'static.cninfo.com.cn' in sources[row['debt_source']]['url']
    assert data['capacity'][-1]['sows'] == 3602
    assert sum(r['sows'] is None for r in data['capacity']) == 7
    assert data['industry']['hog_inventory']['value'] == 42533
    assert data['industry']['slaughter']['period'] == '2026年1—9月'
    assert data['industry']['pork_output']['value'] == 4508
    assert '非全国官方统计' in data['psy']['scope']
    assert data['latest_price']['observation_date'] == '2026-10-22'
    assert data['latest_price']['published_date'] == '2026-10-27'
