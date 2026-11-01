"""Select reviewed reading copies only while their source and output match."""
from hashlib import sha256
import html
from pathlib import Path

from .paths import LIBRARY, PROJECT, read_json

READING_ROOT = PROJECT / "runtime/editorial_20261031"


def reading_path(source):
    source = Path(source).resolve()
    manifest = read_json(READING_ROOT / "manifest.json", {})
    for row in manifest.get("documents", []):
        original = (PROJECT / row["source"]).resolve()
        if original != source:
            continue
        target = (READING_ROOT / row["reading"]).resolve()
        if not target.is_relative_to(READING_ROOT.resolve()):
            return source
        if source.is_file() and target.is_file():
            if (sha256(source.read_bytes()).hexdigest() == row["source_sha256"]
                    and sha256(target.read_bytes()).hexdigest() == row["reading_sha256"]):
                return target
        return source
    return source


def read_report(source):
    path = reading_path(source)
    return path.read_text(encoding="utf-8") if path.exists() else "资料尚未生成。"


def library_report(relative):
    return read_report(LIBRARY / relative)


def report_html(source):
    source = Path(source).resolve()
    selected = reading_path(source)
    if selected != source:
        for row in read_json(READING_ROOT / "manifest.json", {}).get("documents", []):
            if (READING_ROOT / row["reading"]).resolve() == selected:
                path = (READING_ROOT / row["html"]).resolve()
                if (path.is_relative_to(READING_ROOT.resolve()) and path.is_file()
                        and sha256(path.read_bytes()).hexdigest() == row["html_sha256"]):
                    return path
    original_html = source.with_suffix(".html")
    return original_html if original_html.is_file() else source


def report_index():
    manifest = read_json(READING_ROOT / "manifest.json", {})
    if not manifest.get("documents"):
        return None
    lines = ['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>工作台报告</title>',
             '<style>body{font:16px/1.9 "Microsoft YaHei",sans-serif;max-width:1000px;margin:40px auto;padding:0 24px;color:#25374b}li{margin:12px 0}a{color:#23688c}</style>',
             '<h1>工作台报告</h1><p>文字修订于2026-10-31；数据日期见各报告。表格、数字、代码和来源链接沿用原件。</p><ul>']
    seen = set()
    for row in manifest["documents"]:
        source = (PROJECT / row["source"]).resolve()
        content = read_report(source)
        content_hash = sha256(content.encode('utf8')).hexdigest()
        if content_hash in seen:
            continue
        seen.add(content_hash)
        title = content.splitlines()[0].lstrip('# ')
        path = report_html(source)
        suffix = '（原报告；阅读版待更新）' if reading_path(source) == source else ''
        lines.append('<li><a href="' + html.escape(path.as_uri(), quote=True) + '">' + html.escape(title) + '</a>' + suffix + '</li>')
    lines.append('</ul><p>' + html.escape(manifest['unchanged_records']) + '</p></html>')
    target = READING_ROOT / 'index.html'
    target.write_text('\n'.join(lines), encoding='utf8')
    return target
