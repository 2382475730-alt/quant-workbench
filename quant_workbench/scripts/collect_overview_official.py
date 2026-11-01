"""Archive issuer and government originals for the 2026-10-29 overview.

This independent snapshot never writes the older research versions.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
from html import unescape
import json
from pathlib import Path
import re
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import httpx
from pypdf import PdfReader

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT / 'runtime/research/swine_overview_20261029'
COMPANIES = {'002714': '牧原股份', '603477': '巨星农牧', '605296': '神农集团',
             '001201': '东瑞股份', '600975': '新五丰', '002124': '天邦食品'}
ORGS = {'002714': '9900022995', '603477': '9900035087', '605296': '9900033227',
        '001201': '9900036405', '600975': 'gssh0600975', '002124': '9900002441'}
ASOF = '2026-10-29'


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def plain(text):
    text = re.sub(r'<(script|style)\b[^>]*>.*?</\1>', '', text, flags=re.S | re.I)
    return re.sub(r'\s+', ' ', unescape(re.sub('<[^>]+>', ' ', text)))


def archive(sid, title, url, published=None, publisher=None):
    suffix = '.pdf' if '.pdf' in url.lower() else '.html'
    path = ROOT / 'sources' / (sid + suffix)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        response = httpx.get(url, timeout=40, follow_redirects=True)
        response.raise_for_status()
        path.write_bytes(response.content)
    if suffix == '.pdf':
        extracted = path.with_suffix('.pages.json')
        if not extracted.exists():
            dump(extracted, [{'page': i + 1, 'text': p.extract_text()}
                             for i, p in enumerate(PdfReader(path).pages)])
    else:
        path.with_suffix('.txt').write_text(plain(path.read_text(encoding='utf-8')), encoding='utf-8')
    return {'id': sid, 'title': title, 'url': url, 'publisher': publisher,
            'published_date': published, 'retrieved_at': datetime.now(timezone.utc).isoformat(),
            'local_path': str(path.relative_to(ROOT)),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def company(code):
    entries = []
    with httpx.Client(timeout=40, follow_redirects=True) as client:
        for page in range(1, 6):
            cache = ROOT / 'indexes' / f'{code}_stock_{page}.json'
            if not cache.exists():
                response = client.post('https://www.cninfo.com.cn/new/hisAnnouncement/query', data={
                    'pageNum': page, 'pageSize': 100, 'tabName': 'fulltext', 'column': 'szse',
                    'stock': code + ',' + ORGS[code], 'searchkey': '', 'seDate': '2026-08-01~' + ASOF,
                    'sortName': 'time', 'sortType': 'desc', 'isHLtitle': 'false'})
                response.raise_for_status()
                dump(cache, response.json())
            data = json.loads(cache.read_text(encoding='utf-8'))
            for row in data.get('announcements') or []:
                if row['secCode'] != code:
                    continue
                title = re.sub('<[^>]+>', '', row['announcementTitle'])
                if any(word in title for word in ('半年度报告', '三季度报告', '第三季度报告',
                                                  '投资者关系', '调研活动', '业绩说明会')) and not any(
                        word in title for word in ('摘要', '提示性', '召开', '审阅', '英文')):
                    entries.append((row, title))
            if page * 100 >= data.get('totalAnnouncement', 0):
                break
    records = []
    for row, title in entries:
        url = urljoin('https://static.cninfo.com.cn/', row['adjunctUrl'])
        published = re.search(r'finalpage/(\d{4}-\d{2}-\d{2})/', url)[1]
        if published > ASOF:
            continue
        sid = code + '_' + str(row['announcementId'])
        records.append(archive(sid, COMPANIES[code] + '：' + title, url, published, COMPANIES[code]))
    print(code, 'official documents', len(records), flush=True)
    return records


def main():
    records = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        for batch in executor.map(company, COMPANIES):
            records.extend(batch)
    # The official issuer index omits some H1/IR entries; retain the exact
    # separately located originals and archive SZSE's separate research tab.
    records.append(archive('605296_H1', '神农集团2026年半年度报告',
        'https://static.cninfo.com.cn/finalpage/2026-08-25/1225494728.PDF', '2026-08-25', '神农集团'))
    for code in ('002714', '001201', '002124'):
        cache = ROOT / 'indexes' / f'{code}_relation.json'
        if not cache.exists():
            response = httpx.post('https://www.cninfo.com.cn/new/hisAnnouncement/query', timeout=40, data={
                'stock': code + ',' + ORGS[code], 'tabName': 'relation', 'pageSize': 30,
                'pageNum': 1, 'column': 'szse', 'seDate': '', 'searchkey': '', 'isHLtitle': 'false'})
            response.raise_for_status()
            dump(cache, response.json())
        for row in json.loads(cache.read_text(encoding='utf-8')).get('announcements') or []:
            url = urljoin('https://static.cninfo.com.cn/', row['adjunctUrl'])
            date = re.search(r'finalpage/(\d{4}-\d{2}-\d{2})/', url)[1]
            if '2026-08-01' <= date <= ASOF:
                records.append(archive(code + '_IR_' + str(row['announcementId']),
                    COMPANIES[code] + '：' + row['announcementTitle'], url, date, COMPANIES[code]))
    # SZSE Interactive Easy is separate from the announcement/IR-document tabs.
    irm_path = ROOT / 'sources/MUYUAN_COST_OFFICIAL.json'
    irm_url = 'https://irm.cninfo.com.cn/newircs/company/question'
    irm_params = {'stockcode': '002714', 'orgId': ORGS['002714'], 'pageSize': 1000,
                  'pageNum': 1, 'keyWord': '成本', 'startDay': '2026-08-01', 'endDay': ASOF}
    if not irm_path.exists():
        response = httpx.post(irm_url, params=irm_params, timeout=40)
        response.raise_for_status()
        dump(irm_path, response.json())
    replies = json.loads(irm_path.read_text(encoding='utf-8'))['rows']
    reply = next(r for r in replies if '2026年9月' in plain(r.get('attachedContent') or '') and
                 '略低于11.5' in plain(r.get('attachedContent') or ''))
    published = datetime.fromtimestamp(reply['updateDate'] / 1000, ZoneInfo('Asia/Shanghai')).date().isoformat()
    assert published <= ASOF
    records.append({'id': 'MUYUAN_COST_OFFICIAL', 'title': '牧原股份2026年9月完全养殖成本官方答复',
        'url': 'https://irm.cninfo.com.cn/ircs/question/questionDetail?questionId=' + reply['indexId'],
        'request_url': irm_url, 'request_method': 'POST', 'request_params': irm_params,
        'selected_record': reply['indexId'], 'publisher': '牧原股份／深交所互动易',
        'published_date': published, 'retrieved_at': datetime.now(timezone.utc).isoformat(),
        'local_path': str(irm_path.relative_to(ROOT)), 'sha256': hashlib.sha256(irm_path.read_bytes()).hexdigest()})
    government = [
        ('NBS_Q3', '2026年前三季度农业经济形势', 'https://www.stats.gov.cn/sj/zxfbhjd/202610/t20261019_1965646.html', '2026-10-20', '国家统计局'),
        ('NBS_Q3_TABLE', '前三季度经济运行及主要指标', 'https://www.stats.gov.cn/sj/zxfb/202610/t20261019_1965618.html', '2026-10-19', '国家统计局'),
        ('POLICY_2026', '生猪产能综合调控实施方案（2026年修订）', 'https://www.agri.cn/zx/hxgg/202605/t20260514_8836581.htm', '2026-05-14', '农业农村部'),
        ('POLICY_2024', '生猪产能调控实施方案（2024年修订）', 'https://xmsyj.moa.gov.cn/gzdt/202402/t20240229_6449331.htm', '2024-03-01', '农业农村部'),
        ('MOA_PRICE_20261027', '10月第3周畜产品和饲料集贸市场价格情况', 'https://xmsyj.moa.gov.cn/jcyj/202610/t20261027_6488962.htm', '2026-10-27', '农业农村部'),
        ('MOA_PRICE_20261020', '10月第2周畜产品和饲料集贸市场价格情况', 'https://xmsyj.moa.gov.cn/jcyj/202610/t20261020_6488772.htm', '2026-10-20', '农业农村部'),
        ('MOFCOM_PSY_CONTEXT', '生猪生产效率行业资料（转载，非官方统计）', 'https://price.mofcom.gov.cn/article/yjzx/hyzx/nyls/202605/64609.html', '2026-05-06', '商务部商品价格网转载新华财经/卓创资讯'),
        ('MOF_CASH', '企业会计准则第31号——现金流量表', 'https://kjs.mof.gov.cn/zt/kjzzss/kuaijizhunzeshishi/200806/t20080618_46250.htm', '2008-06-18', '财政部'),
        ('NEWHOPE_PSY', '新希望2025年年度报告（引述微猪样本PSY）', 'https://disc.static.szse.cn/download/disc/disk03/finalpage/2026-04-29/57fae488-018b-4dd8-87fa-f2c16de40bee.PDF', '2026-04-29', '新希望／深圳证券交易所'),
    ]
    with ThreadPoolExecutor(max_workers=4) as executor:
        records.extend(executor.map(lambda args: archive(*args), government))
    # MOA publishes actual monthly sow observations; do not interpolate quarters.
    months = [f'{year}{month:02d}' for year in (2025, 2026)
              for month in range(1, 13) if f'{year}{month:02d}' <= '202609']
    def monthly(period):
        return archive('MOA_MONTH_' + period, period + '生猪产品数据',
            f'https://www.moa.gov.cn/ztzl/szcpxx/jdsj/{period[:4]}/{period}/',
            None, '农业农村部生猪产品数据专题')
    with ThreadPoolExecutor(max_workers=4) as executor:
        records.extend(executor.map(monthly, months))
    dump(ROOT / 'sources.json', records)
    dump(ROOT / 'protocol.json', {
        'version': 'swine_overview_20261029', 'as_of': ASOF,
        'purpose': '总览页面展示补充；不覆盖2026-10-25研究、策略与历史结果',
        'cash': '同一期合并货币资金－受限资金－不重叠的专用资金；不以旧附注扣新余额。缺附注则可动用金额不推算。',
        'periods': '每项保留余额日、期间及公告日；晚于截至日的报告不采用。',
        'cost': '只采用公司原文已实现完全成本；保留不等号、范围和月份，目标不作实际成本。',
        'psy': '官方原始全国统计优先；行业样本及官方转载单列口径，禁止冒充全国官方统计。',
        'valuation': '不更新交易策略；PB明确行情日及净资产报告期。',
    })
    print('sources', len(records), str(ROOT), flush=True)


if __name__ == '__main__':
    main()
