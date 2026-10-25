"""Acquire original MOA third-week price observations, never monthly averages."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from html import unescape
import hashlib,json,re,sys
from pathlib import Path
from urllib.parse import urljoin
import httpx
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'src'))
from quant_workbench_app.swine_data import read,dump
ROOT=PROJECT/'runtime/research/swine_deep_20261025'
BASE='https://xmsyj.moa.gov.cn/jcyj/'
FIELDS={'hog':'全国生猪平均价格','piglet':'全国仔猪平均价格','corn':'全国玉米(?:平均)?价格','soymeal':'全国豆粕(?:平均)?价格','feed':'育肥猪配合饲料(?:平均)?价格'}

def plain(html):return re.sub(r'\s+','',unescape(re.sub('<[^>]+>',' ',html)))

def main():
    indexes=ROOT/'sources/price_history_indexes';indexes.mkdir(parents=True,exist_ok=True)
    def index(i):
        file=indexes/f'index_{i}.html';url=BASE+('index.htm' if i==0 else f'index_{i}.htm')
        if not file.exists():
            response=httpx.get(url,timeout=30,follow_redirects=True);response.raise_for_status();file.write_text(response.text,encoding='utf8')
        rows=[]
        for item in re.findall(r'<li\b[^>]*>(.*?)</li>',file.read_text(encoding='utf8'),re.S):
            link=re.search(r'href=["\']([^"\']+)',item);pub=re.search(r'\d{4}-\d{2}-\d{2}',item)
            title=re.search(r'<span class="sj_gztzle">(.*?)</span>',item,re.S)
            if not (link and pub and title):continue
            title=plain(title[1]);pub=pub[0]
            if '畜产品和饲料' not in title or not re.search('第[3三]周',title) or not '2019-01-01'<=pub<='2026-10-25':continue
            rows.append({'title':title,'published_date':pub,'url':urljoin(BASE,link[1])})
        return rows
    first=index(0)
    page_count=int(re.search(r'countPage\s*=\s*(\d+)',(indexes/'index_0.html').read_text(encoding='utf8'))[1])
    with ThreadPoolExecutor(max_workers=4) as pool:entries=first+[r for batch in pool.map(index,range(1,page_count)) for r in batch]
    entries=list({r['url']:r for r in entries}.values())
    sources=read(ROOT/'evidence/sources.json');known={s['url']:s for s in sources if s['admission']=='accepted'}
    latest=next(s for s in sources if s['id']=='S_FEED_OCT')
    entries.append({'title':latest['title'],'published_date':latest['published_date'],'url':latest['url'],'sample':'本月最新可得，第2周'})
    def article(e):
        old=known.get(e['url']);sid=old['id'] if old else 'S_MOA_WEEK_'+e['published_date'].replace('-','')
        path=ROOT/old['local_path'] if old else ROOT/'sources'/f'{sid}.html'
        if not path.exists():
            response=httpx.get(e['url'],timeout=30,follow_redirects=True);response.raise_for_status();path.write_text(response.text,encoding='utf8')
        text=plain(path.read_text(encoding='utf8'));month=re.search(r'(\d+)月',e['title'])
        if not month:return None,None,{'url':e['url'],'reason':'month missing'}
        year=int(e['published_date'][:4]);month=int(month[1])
        if month>int(e['published_date'][5:7]):year-=1
        period=f'{year}-{month:02d}'
        if period<'2019-01':return None,None,None
        row={'period':period,'published_date':e['published_date'],'source':sid,'sample':e.get('sample','每月第3周'),'observation_date':None}
        collection=re.search(r'采集日为(\d+)月(\d+)日',text)
        if collection:row['observation_date']=f'{year}-{int(collection[1]):02d}-{int(collection[2]):02d}'
        for key,label in FIELDS.items():
            match=re.search(label+r'([\d.]+)元',text)
            if not match:return None,None,{'url':e['url'],'reason':key+' price missing'}
            row[key]=float(match[1])
        row['hog_corn_ratio']=row['hog']/row['corn'];row['hog_feed_ratio']=row['hog']/row['feed']
        source=old or {'id':sid,'title':e['title'],'publisher':'农业农村部畜牧兽医局','url':e['url'],
            'local_path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'retrieved_at':datetime.now(timezone.utc).isoformat(),'published_date':e['published_date'],
            'published_date_utc_offset':'+08:00','publication_evidence':'政府栏目列表公布日期；正文每月第3周，若有采集日另列',
            'version':'2026-10-25重新采集原文','admission':'accepted'}
        return row,source,None
    def safe_article(e):
        try:return article(e)
        except (httpx.HTTPError,ValueError) as exc:return None,None,{'url':e['url'],'reason':str(exc)}
    with ThreadPoolExecutor(max_workers=4) as pool:received=list(pool.map(safe_article,entries))
    rows=sorted([r for r,s,e in received if r],key=lambda r:r['period']);errors=[e for r,s,e in received if e]
    if len({r['period'] for r in rows})!=len(rows):raise ValueError('Duplicate monthly sample; review original dates')
    by_id={s['id']:s for s in sources}
    by_id.update({s['id']:s for r,s,e in received if s})
    dump(ROOT/'evidence/sources.json',list(by_id.values()))
    dump(ROOT/'model/price_history.json',{'method':'政府栏目现存历史每月第3周的全国集贸市场样本；2026年10月采用最新第2周，非月均价。缺月不插值，采集日缺失保留null。金额元/kg，比值不是利润。','index_pages':page_count,'rows':rows,'unresolved':errors})
    print(json.dumps({'observations':len(rows),'first':rows[0]['period'] if rows else None,'last':rows[-1]['period'] if rows else None,'unresolved':errors},ensure_ascii=False))

if __name__=='__main__':main()
