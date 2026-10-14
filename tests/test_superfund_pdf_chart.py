from superfund_reports import _fund_chart_flowable

def test_pdf_chart_uses_real_timestamped_price_observations():
    points=[{'price_at':'2026-10-12T14:00:00Z','nok_price':100},
            {'price_at':'2026-10-13T14:00:00Z','nok_price':98},
            {'price_at':'2026-10-14T14:00:00Z','nok_price':101}]
    chart=_fund_chart_flowable(points)
    assert chart is not None
    assert chart.width>300 and len(chart.contents)>=4

def test_pdf_chart_does_not_invent_missing_history():
    assert _fund_chart_flowable([]) is None
    assert _fund_chart_flowable([{'price_at':'2026-10-14T14:00:00Z','nok_price':100}]) is None
    assert _fund_chart_flowable([{'price_at':'bad','nok_price':100}]) is None
