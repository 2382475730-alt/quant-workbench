"""Render report HTML in a headless browser on an isolated Windows desktop."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urljoin

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT / 'runtime/editorial_20261031'
OUT = PROJECT / 'runtime/verification_artifacts/reading_reports'
OUT.mkdir(parents=True, exist_ok=True)

if '--isolated' not in sys.argv:
    user = ctypes.windll.user32
    user.CreateDesktopW.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    user.CreateDesktopW.restype = wintypes.HANDLE
    user.CloseDesktop.argtypes = [wintypes.HANDLE]
    name = 'ReadingReportQA_' + str(os.getpid())
    handle = user.CreateDesktopW(name, None, None, 0, 0x01FF, None)
    if not handle:
        raise ctypes.WinError()
    try:
        startup = subprocess.STARTUPINFO(); startup.lpDesktop = name
        result = subprocess.run([sys.executable, __file__, '--isolated'], startupinfo=startup, capture_output=True, text=True)
        print(result.stdout)
        if result.returncode:
            print(result.stderr)
        sys.exit(result.returncode)
    finally:
        user.CloseDesktop(handle)

browser = Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
reports = {
    'swine': 'app/runtime/research/swine_deep_20261025/report/research.html',
    'stocks': 'library/reports/量化研究报告.html',
    'enhancement': 'library/reports/enhancement_v1/report.html',
    'small': 'library/reports/small_capital_v1/report.html',
    'company': 'library/artifacts/company/000333.SZ/summary.html',
    'index': 'index.html',
}
records = []
common = [str(browser), '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
          '--disable-background-networking', '--disable-extensions', '--hide-scrollbars',
          '--user-data-dir=' + str(OUT / 'browser_profile'), '--window-size=1420,1050', '--virtual-time-budget=2000']
for name, relative in reports.items():
    target = OUT / (name + '.png')
    args = common + ['--screenshot=' + str(target), (ROOT / relative).as_uri()]
    result = subprocess.run(args, capture_output=True, timeout=40, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode or not target.is_file():
        raise RuntimeError(f'Report render failed: {name}: {result.returncode}')
    records.append({'name': name, 'image': str(target), 'html': relative})
# Check every report's images and layout in the browser, including content below the fold.
checks = []
manifest = json.loads((ROOT / 'manifest.json').read_text(encoding='utf8'))
for index, row in enumerate(manifest['documents']):
    source = ROOT / row['html']
    qa = OUT / f'layout_{index}.html'
    script = '''<script>addEventListener('load',()=>{
      const images=[...document.images];
      document.body.dataset.qa=JSON.stringify({images:images.length,
        broken:images.filter(x=>!x.naturalWidth).length,
        horizontalOverflow:document.documentElement.scrollWidth>innerWidth});
    });</script>'''
    original = source.read_text(encoding='utf8')
    original = original.replace('<meta charset="utf-8">', '<meta charset="utf-8"><base href="' + source.as_uri() + '">', 1)
    qa.write_text(original + script, encoding='utf8')
    result = subprocess.run(common + ['--dump-dom', qa.as_uri()], capture_output=True, timeout=40, creationflags=subprocess.CREATE_NO_WINDOW)
    from html import unescape
    match = re.search(r'data-qa="([^"]+)"', result.stdout.decode('utf8', errors='replace'))
    if not match:
        raise RuntimeError('Browser layout check did not finish: ' + row['html'])
    status = json.loads(unescape(match[1]))
    if status['broken'] or status['horizontalOverflow']:
        raise RuntimeError('Broken media or page overflow: ' + row['html'] + str(status))
    checks.append({'html': row['html'], **status})
    if status['images']:
        from html.parser import HTMLParser
        class ImageLinks(HTMLParser):
            def __init__(self):
                super().__init__(); self.urls = []
            def handle_starttag(self, tag, attrs):
                if tag == 'img':
                    self.urls.append(dict(attrs)['src'])
        links = ImageLinks(); links.feed(source.read_text(encoding='utf8'))
        # A separate figure view avoids Chromium's scrolled screenshot paint race.
        figure_page = OUT / f'figure_{index}.html'
        from html import escape
        figure_page.write_text('<!doctype html><meta charset="utf-8"><style>body{font:18px Microsoft YaHei;max-width:1300px;margin:30px auto}img{max-width:100%}</style>'
                               '<p>报告图表 · <a href="' + source.as_uri() + '">打开报告</a></p>'
                               '<img src="' + escape(urljoin(source.as_uri(), links.urls[0]), quote=True) + '">', encoding='utf8')
        image_path = OUT / f'report_figure_{index}.png'
        subprocess.run(common + ['--screenshot=' + str(image_path), figure_page.as_uri()], capture_output=True, timeout=40, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
(OUT / 'capture_report.json').write_text(json.dumps({'isolated_desktop': True, 'reports': records}, ensure_ascii=False, indent=2), encoding='utf8')
(OUT / 'layout_checks.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding='utf8')
print(json.dumps({'reports_rendered': len(records), 'isolated_desktop': True}))
