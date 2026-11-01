"""Reader editions preserve figures/evidence and fall back when stale."""
from hashlib import sha256
import importlib.util
import json
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote

from quant_workbench_app.paths import PROJECT
from quant_workbench_app import reading


def test_html_sources_and_figures_use_portable_relative_links():
    class Links(HTMLParser):
        def __init__(self):
            super().__init__(); self.urls=[]
        def handle_starttag(self, tag, attrs):
            self.urls += [value for key,value in attrs if key in ('href','src')]
    manifest=json.loads((reading.READING_ROOT/'manifest.json').read_text(encoding='utf8'))
    for row in manifest['documents']:
        path=reading.READING_ROOT/row['html']
        parser=Links();parser.feed(path.read_text(encoding='utf8'))
        for url in parser.urls:
            parts=urlsplit(url)
            assert parts.scheme != 'file'
            if not parts.scheme and parts.path:
                assert (path.parent/unquote(parts.path)).resolve().is_file()


def builder():
    spec = importlib.util.spec_from_file_location("plain_reports", PROJECT / "scripts/build_plain_reports.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_reading_edition_preserves_all_report_facts_and_sources():
    module = builder()
    manifest = json.loads((reading.READING_ROOT / "manifest.json").read_text(encoding="utf8"))
    assert len(manifest["documents"]) == 18
    for row in manifest["documents"]:
        original = (PROJECT / row["source"]).resolve()
        target = reading.READING_ROOT / row["reading"]
        assert sha256(original.read_bytes()).hexdigest() == row["source_sha256"]
        assert sha256(target.read_bytes()).hexdigest() == row["reading_sha256"]
        assert module.protected(original.read_text(encoding="utf8")) == module.protected(target.read_text(encoding="utf8"))
        assert reading.reading_path(original) == target.resolve()
        assert (reading.READING_ROOT / row["html"]).is_file()
        assert sha256((reading.READING_ROOT / row["html"]).read_bytes()).hexdigest() == row["html_sha256"]
        assert '#harmful-link' not in (reading.READING_ROOT / row["html"]).read_text(encoding='utf8')
        assert row["changes"]
        revised, _ = module.rewrite(original.read_text(encoding="utf8"))
        assert revised.encode("utf8") == target.read_bytes()


def test_reading_falls_back_for_changed_source_or_reading_copy(tmp_path, monkeypatch):
    original = tmp_path / "source.md"
    original.write_text("原报告", encoding="utf8")
    target = tmp_path / "reading.md"
    target.write_text("阅读版", encoding="utf8")
    row = {"source": str(original), "reading": target.name,
           "source_sha256": sha256(original.read_bytes()).hexdigest(),
           "reading_sha256": sha256(target.read_bytes()).hexdigest()}
    (tmp_path / "manifest.json").write_text(json.dumps({"documents": [row]}), encoding="utf8")
    monkeypatch.setattr(reading, "READING_ROOT", tmp_path)
    assert reading.read_report(original) == "阅读版"
    target.write_text("修改后的阅读版", encoding="utf8")
    assert reading.read_report(original) == "原报告"
    row["reading_sha256"] = sha256(target.read_bytes()).hexdigest()
    (tmp_path / "manifest.json").write_text(json.dumps({"documents": [row]}), encoding="utf8")
    original.write_text("更新的原报告", encoding="utf8")
    assert reading.read_report(original) == "更新的原报告"
