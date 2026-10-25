"""Integration tests of adapters, six companies, exports, and UI state isolation."""
import json
import time
from pathlib import Path

import pandas as pd
import pytest

from quant_workbench_app import LIBRARY
from quant_workbench_app.desktop import Workbench
from quant_workbench_app.paths import SETTINGS, read_json


def pump(app, predicate=lambda: True, seconds=30):
    deadline = time.monotonic() + seconds
    while True:
        app.update()
        if predicate():
            return
        if time.monotonic() > deadline:
            raise AssertionError("UI task did not finish")
        time.sleep(.02)


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    from quant_workbench_app import pork
    from quant_workbench_app import swine_deep_panel
    patch = pytest.MonkeyPatch()
    output_root = tmp_path_factory.mktemp("outputs")
    patch.setattr(pork, "RUNTIME", output_root)
    patch.setattr(swine_deep_panel,"RUNTIME",output_root)
    ui = Workbench(state_path=tmp_path_factory.mktemp("ui") / "state.json")
    ui.test_output_root = output_root
    ui.withdraw()
    failures = []
    ui.report_callback_exception = lambda exc, value, tb: failures.append(value)
    pump(ui, lambda: "pork" in ui.panels)
    yield ui
    ui.close()
    patch.undo()
    assert not failures, failures


def test_four_independent_modules_lazy_and_no_legacy_tabs(app):
    assert list(app.buttons) == ["pork", "stocks", "enhancement", "small"]
    assert set(app.panels) == {"pork"}
    for key in app.buttons:
        app.show_module(key)
        pump(app)
        assert key in app.panels
        assert app.active == key
        assert all(p.winfo_manager() == ("grid" if k == key else "") for k, p in app.panels.items())


@pytest.mark.parametrize("code", list(SETTINGS["companies"]))
def test_six_stock_cases_match_saved_ledgers(app, code):
    app.show_module("stocks")
    panel = app.panels["stocks"]
    panel.company.set(next(label for label, c in panel.names.items() if c == code))
    panel.refresh()
    assert panel.symbol.get() == code
    assert len(panel.metrics.get_children()) == 3
    curves = panel.stock_fig.axes[0].get_lines()
    assert len(curves) == 3
    rows = [r for r in panel.rows if r["symbol"] == code and r["scenario"] == "base"
            and r["strategy"] in {"trend_200", "buy_hold", "trend_200_risk"}]
    for row in rows:
        from quant_workbench.desktop import LABELS
        line = next(line for line in curves if line.get_label() == LABELS[row["strategy"]])
        assert float(line.get_ydata()[-1]) - 1 == pytest.approx(row["total_return"])
    assert "不随历史回测区间改变" in panel.facts.get("1.0", "end")


def test_stock_period_changes_chart_and_account_together(app):
    panel = app.panels["stocks"]
    for display, phase in [("2022—2024 验证", "validation"), ("2017—2021 开发", "development")]:
        panel.period.set(display)
        panel.refresh()
        assert panel.phase.get() == phase
        assert panel.summary["end"] in panel.account.cget("text").replace("-", "") or (
            pd.Timestamp(panel.summary["end"]).strftime("%Y-%m-%d") in panel.account.cget("text"))


def test_enhancement_versions_and_period_consistency(app):
    app.show_module("enhancement")
    p = app.panels["enhancement"]
    assert len(p.comparison.get_children()) == 4
    p.show_history.set(True)
    p.filter_versions()
    assert len(p.comparison.get_children()) == len(p.phase_data["rows"])
    p.show_history.set(False)
    p.filter_versions()
    p.strategy.set("防御备选")
    pump(app)
    assert p.comparison.selection() == ("defensive_constrained",)
    assert p.view == p.phase_data["holdings"]["defensive_constrained"]
    p.period.set("2022—2024 回溯")
    p.load("validation")
    pump(app)
    assert p.phase_data["end"] in p.note.cget("text")
    assert len(p.comparison.get_children()) == 4


def test_small_capital_summary_uses_exact_saved_wealth(app):
    app.show_module("small")
    p = app.panels["small"]
    p.phase.set("2022—2024")
    p.draw()
    rows = [r for r in p.data["main_results"] if r["phase"] == "validation" and r["strategy"] != "legacy"]
    assert len(p.summary_table.get_children()) == 4
    assert len(p.figure.axes[0].get_lines()) == 4
    for line, row in zip(p.figure.axes[0].get_lines(), rows, strict=True):
        assert float(line.get_ydata()[-1]) - 1 == pytest.approx(row["total_return"])


def test_pork_background_replay_and_export_stay_outside_library(app):
    app.show_module("pork")
    replay = app.panels["pork"]
    assert replay.model.entry_dates[0] == pd.Timestamp('2026-06-01')
    replay.date.set('2026-10-23')
    replay.horizon.set('共同终点')
    replay.recalculate()
    assert replay.result['summary']['start'] == '2026-10-23'
    replay.export()
    folder = max((app.test_output_root / "exports/swine").iterdir(), key=lambda p: p.stat().st_mtime_ns)
    exported = read_json(folder / "summary.json")
    assert exported["start"] == "2026-10-23"
    assert (folder / "comparison.png").is_file()
    assert not folder.is_relative_to(LIBRARY)
    assert len(replay.replay_table.get_children()) == 5
    replay.horizon.set('60个交易日')
    replay.recalculate()
    assert replay.result is None
    assert not replay.replay_table.get_children()
    replay.capital.set('nan')
    replay.calculate_capital()
    assert replay.capital_result is None
    replay.capital.set('100000')
    replay.calculate_capital()
    assert replay.capital_result['cash'] >= 0


def test_state_isolated_and_reopened_without_starting_all_modules(app, tmp_path):
    app.show_module("stocks")
    panel = app.panels["stocks"]
    panel.pages.select(1)
    app.save()
    saved = json.loads(Path(app.state_path).read_text(encoding="utf-8"))
    assert saved["active"] == "stocks"
    restored = Workbench(state_path=app.state_path)
    restored.withdraw()
    restored.report_callback_exception = lambda exc, value, tb: pytest.fail(str(value))
    try:
        pump(restored, lambda: "stocks" in restored.panels)
        assert set(restored.panels) == {"stocks"}
        assert restored.panels["stocks"].company.get() == panel.company.get()
        assert restored.panels["stocks"].period.get() == panel.period.get()
        assert restored.panels["stocks"].pages.index(restored.panels["stocks"].pages.select()) == 1
    finally:
        restored.close()


def test_current_report_and_cost_report_use_correct_period(app, monkeypatch):
    from quant_workbench_app import pork
    opened=[]
    monkeypatch.setattr(pork.os,'startfile',lambda path:opened.append(Path(path)))
    app.show_module('pork')
    panel=app.panels['pork']
    panel.company_table.selection_set('002124.SZ')
    panel.open_company_document()
    panel.open_company_document(half_year=True)
    assert opened[0].is_file() and opened[1].is_file()
    assert opened[0]!=opened[1]
    docs=pork.source_documents('002124.SZ')
    current=next(d for d in docs if pork.PROJECT/d['path']==opened[0])
    assert '三季度报告' in current['title']


def test_swine_valuation_company_switch_and_bad_scenario(app):
    panel=app.panels['pork']
    for label,code in panel.valuation_names.items():
        panel.valuation_company.set(label)
        panel.draw_valuation()
        assert panel.by_code[code]['name'] in panel.valuation_summary.cget('text')
        assert len(panel.valuation_figure.axes)==2
    panel.scenario_pb.set('nan')
    panel.draw_valuation()
    assert '请输入' in panel.valuation_scenario.cget('text')
    assert not panel.valuation_figure.axes
    panel.scenario_pb.set('2')


def test_swine_core_filter_keeps_candidate_boundaries_separate(app):
    panel=app.panels['pork']
    panel.company_scope.set('核心生猪公司')
    panel.filter_companies()
    assert len(panel.company_table.get_children())==6
    assert '300498.SZ' not in panel.company_table.get_children()
    panel.company_scope.set('观察公司')
    panel.filter_companies()
    assert len(panel.company_table.get_children())==3
    assert '603717.SH' in panel.company_table.get_children()
    panel.company_scope.set('全部候选及边界')
    panel.filter_companies()
    assert len(panel.company_table.get_children())==22
    panel.company_scope.set('核心生猪公司')
    panel.filter_companies()


def test_library_root_is_relocated_and_computation_seal_survives():
    from quant_workbench.data import ROOT
    assert ROOT == LIBRARY
    assert (LIBRARY / 'artifacts/small_capital_v1/delivery_manifest.json').is_file()


def test_deep_six_company_switch_inputs_and_export_clear_invalid_state(app):
    p=app.panels['pork']
    for label,code in p.deep_names.items():
        p.recovery_company.set(label);p.funding_company.set(label)
        p.calculate_recovery();p.calculate_funding()
        assert p.recovery_result['code']==code
        assert p.deep_profiles[code]['name'] in p.funding_note.cget('text')
        assert abs(p.recovery_result['identity_error'])<1e-9
    p.export_recovery()
    folder=max((app.test_output_root/'exports/swine_recovery').iterdir(),key=lambda x:x.stat().st_mtime_ns)
    result=read_json(folder/'scenario.json')
    assert result['code']==code and (folder/'scenario.png').is_file()
    p.required_return.set('0');p.calculate_recovery()
    assert p.recovery_result is None and not p.recovery_figure.axes and not p.recovery_history.cget('text')
    p.required_return.set('10');p.calculate_recovery()
    before=p.recovery_result['required_terminal_roe']
    p.book_adjustment.set('-10');p.calculate_recovery()
    assert p.recovery_result['required_terminal_roe']>before
    assert p.recovery_result['book_per_share']==pytest.approx(p.recovery_result['reported_bps']*.9)
    p.book_adjustment.set('0');p.calculate_recovery()
    p.refinancing.set('101');p.calculate_funding()
    assert p.funding_result is None
    p.refinancing.set('50');p.calculate_funding()
    p.efficiency.set('nan');p.calculate_supply()
    assert p.supply_result is None
    p.efficiency.set('5');p.calculate_supply()


def test_overview_links_selected_company_and_actual_cost_source(app,monkeypatch):
    from quant_workbench_app import pork
    p=app.panels['pork'];opened=[]
    monkeypatch.setattr(pork.os,'startfile',lambda path:opened.append(Path(path)))
    assert len(p.overview_table.get_children())==6
    p.overview_table.selection_set('001201.SZ');p.overview_navigate('funding')
    assert p.pages.select()==str(p.frames['companies'])
    assert p.research_books['companies'].index(p.research_books['companies'].select())==1
    assert p.deep_names[p.funding_company.get()]=='001201.SZ'
    p.overview_navigate('companies');p.open_cost_document()
    assert opened[0].name=='S_001201_AN202609151829418815.pdf' and opened[0].is_file()
    assert '2026-07' in p.company_detail.get('1.0','end')


@pytest.mark.parametrize('version',['swine_v2','swine_v3'])
def test_swine_deep_state_survives_restart(app,tmp_path,version):
    p=app.panels['pork'];p.required_return.set('12');p.interim_roes.set('-15,-5,10,15')
    p.bridge_pe.set('20');p.bridge_volume.set('10')
    p.research_books['companies'].select(2);p.pages.select(p.frames['companies'])
    state={'active':'pork','panels':{'pork':p.state()}}
    state['panels']['pork'].update(version=version,capital_basis='跨周期规则最新目标')
    file=tmp_path/'deep_state.json';file.write_text(json.dumps(state,ensure_ascii=False),encoding='utf8')
    restored=Workbench(state_path=file);restored.withdraw()
    try:
        pump(restored,lambda:'pork' in restored.panels)
        q=restored.panels['pork']
        assert q.required_return.get()=='12' and len(q.recovery_result['path'])==4
        assert q.bridge_result['normal_pe']==20 and q.bridge_result['volume_change']==.1
        assert q.research_books['companies'].index(q.research_books['companies'].select())==2
        assert q.pages.select()==str(q.frames['companies'])
        assert q.capital_basis.get()==('当前分档条件草案' if version=='swine_v2' else '跨周期规则最新目标')
    finally:restored.destroy()
    p.required_return.set('10');p.interim_roes.set('-10,0,10');p.calculate_recovery()
    p.bridge_pe.set('15');p.bridge_volume.set('0');p.calculate_profit_bridge()


def test_profit_bridge_three_companies_state_and_export(app):
    p=app.panels['pork']
    assert len(p.bridge_names)==3
    for name,code in p.bridge_names.items():
        p.bridge_company.set(name);p.calculate_profit_bridge()
        assert p.bridge_result['code']==code
        assert len(p.bridge_figure.axes)==1
    p.export_profit_bridge()
    folder=max((app.test_output_root/'exports/swine_profit_bridge').iterdir(),key=lambda x:x.stat().st_mtime_ns)
    exported=read_json(folder/'scenario.json')
    assert exported['code']==code and exported['scope'] and (folder/'scenario.png').is_file()
    p.bridge_pe.set('nan');p.calculate_profit_bridge()
    assert p.bridge_result is None and not p.bridge_figure.axes
    p.bridge_pe.set('15');p.bridge_volume.set('-95');p.calculate_profit_bridge()
    assert p.bridge_result is not None
    p.bridge_volume.set('0');p.calculate_profit_bridge()


def test_capital_basis_preserves_policy_targets_across_amounts(app):
    p=app.panels['pork'];p.capital_basis.set('跨周期规则最新目标')
    p.capital.set('10000');p.calculate_capital();small=p.capital_result
    p.capital.set('1000000');p.calculate_capital();large=p.capital_result
    assert [r['target_weight'] for r in small['rows']]==[r['target_weight'] for r in large['rows']]
    assert small['cash_weight']!=large['cash_weight']
    assert small['target_basis']=='跨周期规则最新目标'
    p.capital_basis.set('80%等权研究对照');p.calculate_capital()
    assert sum(r['target_weight'] for r in p.capital_result['rows'])==pytest.approx(.8)
    p.capital_basis.set('跨周期规则最新目标');p.capital.set('100000');p.calculate_capital()


def test_current_tier_weights_link_capital_export_and_clear_bad_inputs(app):
    p=app.panels['pork'];p.capital_basis.set('当前分档条件草案')
    p.allocation_roe.set('25');p.calculate_allocation()
    p.capital.set('10000');p.calculate_capital();small=p.capital_result
    p.capital.set('10000000');p.calculate_capital();large=p.capital_result
    assert [r['target_weight'] for r in small['rows']]==[r['target_weight'] for r in large['rows']]
    assert large['allocation_evidence']['rows']==p.allocation_result['rows']
    p.allocation_roe.set('40');p.export_capital()
    assert p.capital_result['allocation_evidence']['terminal_roe']==.4
    p.export_allocation()
    folder=max((app.test_output_root/'exports/swine_allocation').iterdir(),key=lambda x:x.stat().st_mtime_ns)
    assert read_json(folder/'allocation.json')['terminal_roe']==.4
    p.allocation_return.set('0');p.calculate_capital()
    assert p.allocation_result is None and p.capital_result is None
    assert not p.scale_table.get_children() and not p.capital_table.get_children()
    p.allocation_return.set('10');p.allocation_roe.set('25');p.capital.set('100000');p.calculate_allocation()


def test_source_search_and_price_periods_are_readable_evidence(app):
    p=app.panels['pork'];sources=p.open_source_catalog()
    try:
        total=len(sources.source_view.get_children())
        sources.source_query.set('002714')
        assert 0<len(sources.source_view.get_children())<total
        sources.source_query.set('不存在的检索条件')
        assert not sources.source_view.get_children()
        sources.source_query.set('2022-10-25')
        assert sources.source_view.get_children()
    finally:sources.destroy()
    prices=p.open_price_observations()
    try:
        assert len(prices.price_view.get_children())==58
        assert prices.price_view.selection()==('2026-10',)
        assert prices.price_view.item('2026-10','values')[1:3]==('2026-10-15','2026-10-20')
    finally:prices.destroy()
