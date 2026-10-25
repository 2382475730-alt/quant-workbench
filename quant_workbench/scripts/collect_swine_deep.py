"""Additional originals for cycle transmission, operating efficiency and funding."""
import hashlib,json,re,shutil
from zipfile import ZipFile
from xml.etree import ElementTree
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin
import httpx
from pypdf import PdfReader

PROJECT=Path(__file__).resolve().parents[1]
BASE=PROJECT/'runtime/research/swine_v1_20261025'
ROOT=PROJECT/'runtime/research/swine_deep_20261025'

def main():
    receipts=[]
    def capture(client,sid,title,url,published,publisher):
        suffix='.pdf' if '.pdf' in url.lower() else '.html'
        path=ROOT/'sources'/f'{sid}{suffix}'
        if not path.exists():
            response=client.get(url)
            response.raise_for_status()
            path.write_bytes(response.content)
        if suffix=='.pdf':
            if path.read_bytes()[:2]==b'PK':
                with ZipFile(path) as archive:
                    document=ElementTree.fromstring(archive.read('word/document.xml'))
                    text='\n'.join(''.join(p.itertext()) for p in document.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'))
                actual=path.with_suffix('.docx')
                shutil.copyfile(path,actual)
                path=actual
                pages=[{'page':None,'locator':'DOCX paragraph sequence, not paginated','text':text}]
            else:
                cached_text=path.with_suffix('.json')
                if cached_text.exists():
                    pages=json.loads(cached_text.read_text(encoding='utf8'))
                else:
                    reader=PdfReader(path)
                    pages=[{'page':i+1,'text':page.extract_text()} for i,page in enumerate(reader.pages)]
            path.with_suffix('.json').write_text(json.dumps(pages,ensure_ascii=False),encoding='utf8')
        receipts.append({'id':sid,'title':title,'url':url,'publisher':publisher,'local_path':str(path.relative_to(ROOT)),
                         'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'retrieved_at':datetime.now(timezone.utc).isoformat(),
                         'published_date':published[:10],'published_date_utc_offset':'+08:00',
                         'publication_evidence':'Original issuer announcement index or original government page date',
                         'version':'Disclosed original archived 2026-10-25','admission':'accepted'})
        print(sid,title,flush=True)
    with httpx.Client(timeout=45,follow_redirects=True) as client:
        for d in json.loads((BASE/'sources/documents/receipts.json').read_text(encoding='utf8')):
            if d.get('path'):
                sid='S_'+Path(d['path']).stem
                target=ROOT/'sources'/f'{sid}.pdf'
                if not target.exists():
                    shutil.copyfile(PROJECT/d['path'],target)
                capture(client,sid,d['title'],d['url'],d['notice_date'],d['code']+'上市公司')
        for index in (BASE/'sources/documents').glob('*_index_*.json'):
            entries=json.loads(index.read_text(encoding='utf8')).get('data',{}).get('list',[])
            for item in entries:
                title=item['title']
                if not any(k in title for k in ['投资者关系活动记录','投资者关系管理信息','调研活动信息']):
                    continue
                code=index.name[:6]
                capture(client,f"S_{code}_{item['art_code']}",title,f"https://pdf.dfcfw.com/pdf/H2_{item['art_code']}_1.pdf",item['notice_date'],code+'上市公司')
        items=[
            ('S_NBS_2021','2021年农业生产回顾','https://www.stats.gov.cn/sj/sjjd/202302/t20230202_1896581.html','2022-01-18','国家统计局'),
            ('S_NBS_2022','2022年农业生产回顾','https://www.stats.gov.cn/zt_18555/zthd/lhfw/2023/sjjd/202302/t20230219_1913352.html','2023-01-18','国家统计局'),
            ('S_NBS_2023','2023年农业经济形势','https://www.stats.gov.cn/sj/sjjd/202401/t20240118_1946695.html','2024-01-18','国家统计局'),
            ('S_NBS_2024','2024年农业经济形势','https://www.stats.gov.cn/sj/sjjd/202501/t20250117_1958344.html','2025-01-17','国家统计局'),
            ('S_NBS_2025','2025年农业经济形势','https://www.stats.gov.cn/sj/zxfbhjd/202601/t20260119_1962332.html','2026-01-19','国家统计局'),
            ('S_NBS_Q1','一季度农业生产形势','https://www.stats.gov.cn/zs/tjwh/tjkw/tjqk/zgxxb/202604/P020260420319590487193.pdf','2026-04-20','国家统计局中国信息报'),
            ('S_NBS_Q2','上半年农业生产形势','https://www.stats.gov.cn/sj/sjjd/202607/t20260716_1964140.html','2026-07-16','国家统计局'),
            ('S_NBS_Q3','前三季度农业经济形势','https://www.stats.gov.cn/sj/zxfbhjd/202610/t20261019_1965646.html','2026-10-20','国家统计局'),
            ('S_FEED_SEP','9月第3周畜产品和饲料价格','https://xmsyj.moa.gov.cn/jcyj/202609/t20260922_6488016.htm','2026-09-22','农业农村部'),
            ('S_POLICY','2026年产能调控方案修订','https://www.nahs.org.cn/dt/nyncbxx/202605/t20260518_472227.htm','2026-05-18','全国畜牧总站转农业农村部'),
            ('S_HOG_OCT','10月第3周屠宰企业生猪收购价','https://xmsyj.moa.gov.cn/jcyj/202610/t20261022_6488854.htm','2026-10-22','农业农村部')]
        for args in items:
            try:
                capture(client,*args)
            except (httpx.HTTPError,ValueError) as exc:
                receipts.append({'id':args[0],'title':args[1],'url':args[2],'admission':'unresolved','failure':type(exc).__name__})
        index=client.get('https://xmsyj.moa.gov.cn/jcyj/index.htm').text
        for href,title in re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',index,re.S):
            clean=re.sub('<[^>]+>','',title).strip()
            if '10月第2周畜产品和饲料' in clean:
                capture(client,'S_FEED_OCT',clean,urljoin('https://xmsyj.moa.gov.cn/jcyj/index.htm',href),'2026-10-20','农业农村部')
                break
    # Shared current inputs are copied into this new, independently auditable package.
    for name in ('companies','monthly_operations','cycle','financial_reconciliation'):
        shutil.copyfile(BASE/f'results/{name}.json',ROOT/f'model/{name}.json')
    registry=ROOT/'evidence/sources.json'
    existing=json.loads(registry.read_text(encoding='utf8')) if registry.exists() else []
    receipts.extend(r for r in existing if r['id'] not in {s['id'] for s in receipts})
    registry.write_text(json.dumps(receipts,ensure_ascii=False,indent=2),encoding='utf8')
    print('sources',len(receipts),'unresolved',sum(x['admission']!='accepted' for x in receipts))

if __name__=='__main__':main()
