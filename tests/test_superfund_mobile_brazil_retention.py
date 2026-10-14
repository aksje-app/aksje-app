from pathlib import Path

def test_superfund_chart_hides_oversized_modebar():
    code=Path('superfund_presentation.py').read_text()
    assert "'displayModeBar':False" in code

def test_brazil_retention_view_explains_actual_exit_gates():
    code=Path('pages/superfund.py').read_text()
    assert "Lavere rangeringspoeng utløser ikke salg alene" in code
    assert "weak_trend_dates" in code and "floor_nok" in code
    assert "ventende salgsordre" in code
