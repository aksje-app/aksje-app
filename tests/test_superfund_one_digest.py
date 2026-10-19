from superfund_ranking_digest import pages
from superfund_ranking_report import report_text
def test_combined_readable_report():
    digest={"at":"2026-10-19T20:00:00Z","qualified_count":2,"overall":[{"name":"Long example ETF Name","score":7.65,"currency":"EUR"}],"groups":{"Energy (EUR)":[{"name":"Long example ETF Name","score":7.65,"currency":"EUR","returns":{"yield_1w":2,"yield_1m":4,"yield_3m":8}}]},"news_status":"Nyheter ikke verifisert","score_note":"Source score"}
    text=report_text(digest)
    assert "Kvalifiserte instrumenter: 2" in text
    assert "TOPP 5 PER BRANSJE/KATEGORI" in text
    assert "Long example ETF Name" in text
    assert "Nyheter ikke verifisert" in text
