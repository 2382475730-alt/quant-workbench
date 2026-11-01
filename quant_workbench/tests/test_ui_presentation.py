from quant_workbench_app.ui_presentation import (
    change_spans, change_column, number_value, UP_COLOR, DOWN_COLOR,
)


def test_changes_are_distinct_from_dates_positions_and_risk_levels():
    text = '观察日2026-10-23；同比-2.6%，累计收益+1.4%，股票仓位96.2%，波动18.0%，资产负债率91.8%。'
    spans = [(text[a:b], color) for a, b, color in change_spans(text)]
    assert spans == [('-2.6%', DOWN_COLOR), ('+1.4%', UP_COLOR)]
    assert all(change_column(title) for title in ('累计收益', '最大回撤', '同比', '归母净利', '比免费单只ETF差'))
    assert not any(change_column(title) for title in ('平均仓位', '资产负债率', 'PB', '实际权重', '主动偏离 pp', '实现跟踪误差'))
    assert number_value('2026-10-23') is None
    assert number_value('−3.2%') == -3.2
    text='年化5.4%，最大回撤-24.1%，平均仓位65.8%。'
    assert [(text[a:b], color) for a,b,color in change_spans(text)] == [('5.4%',UP_COLOR),('-24.1%',DOWN_COLOR)]
