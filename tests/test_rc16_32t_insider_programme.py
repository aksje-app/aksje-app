from datetime import datetime, timezone
from io import BytesIO

from reportlab.pdfgen import canvas

from insider_intelligence import score_transactions
from official_insider_sources import fetch_official_insider_sources
from super_portfolio import _bounded_insider_checks, SuperPortfolioConfig
from pypdf import PdfReader


class Response:
    def __init__(self, text="", content=b"", url="https://www.veidekke.com/"):
        self.text, self.content, self.url = text, content, url

    def raise_for_status(self):
        pass


def _pdf(lines):
    buffer = BytesIO()
    page = canvas.Canvas(buffer)
    for line in lines:
        page.drawString(35, 750, line)
        page.translate(0, -25)
    page.save()
    return buffer.getvalue()


def test_official_veidekke_pdf_programme_is_verified_but_neutral(monkeypatch):
    import official_insider_sources as source
    date = datetime.now(timezone.utc).strftime("%-m/%-d/%Y")
    detail = "https://www.veidekke.com/investor-relations/company-disclosures/mandatory-notification/"
    attachment = "https://mb.cision.com/Public/17348/example.pdf"
    index = f'<a href="{detail}">Mandatory notification of trade – Employee Share Purchase Programme 2026 {date}</a>'
    announcement = (f'<h1>Primary insiders in Employee Share Purchase Programme</h1>Published: {date} 8:00 AM '
                    f'The subscription price was set at NOK 167.27 per share. '
                    f'<a href="{attachment}">Share purchases by primary insiders September 2026</a>')
    pdf = _pdf(["Name Previous holding of shares Number of shares purchased New holdings of shares",
                "Jimmy Bengtsson 94 510 5 000 99 510", "Wrong Person 1 1 9"])

    class Session:
        def get(self, url, **kwargs):
            if url == source.EURONEXT_OSLO_NEWS:
                raise ConnectionError("listing blocked")
            if url == source.VEIDEKKE_DISCLOSURES:
                return Response(index, url=url)
            if url == detail:
                return Response(announcement, url=url)
            if url == attachment:
                return Response(content=pdf, url=url)
            raise AssertionError(url)

    result = fetch_official_insider_sources("VEI.OL", "Veidekke", "Norge", session=Session())
    assert result["status"] == "SUCCESS_WITH_RESULTS"
    assert len(result["transactions"]) == 1
    assert result["transactions"][0]["shares"] == 5000
    scored = score_transactions("VEI.OL", result["transactions"])
    assert scored["score"] == 50
    assert scored["buy_count"] == 0
    assert scored["programme_count"] == 1
    assert scored["evidence"][0]["primary_source_verified"] is True
    assert scored["evidence"][0]["score_effect"] == "INFORMATION_ONLY"


def test_unverified_issuer_pdf_never_turns_into_purchase(monkeypatch):
    import official_insider_sources as source
    index = '<a href="/investor-relations/company-disclosures/notification/">Employee Share Purchase Programme</a>'
    detail = ('Published: 9/7/2026 Primary insiders Employee Share Purchase Programme '
              'The subscription price was set at NOK 167.27 per share '
              '<a href="https://evil.example/anything.pdf">Share purchases by primary insiders</a>')

    class Session:
        def get(self, url, **kwargs):
            if url == source.VEIDEKKE_DISCLOSURES:
                return Response(index, url=url)
            return Response(detail, url=url)

    result = source.fetch_veidekke_disclosures(session=Session())
    assert result["transactions"] == []
    assert result["status"] == "DISCOVERY_ONLY"


def test_super_portfolio_checks_holdings_and_top_finalists_only(monkeypatch):
    import super_portfolio as sp
    import insider_intelligence as intelligence
    monkeypatch.setattr(sp, "load_state", lambda: {"positions": {"HELD.OL": {"market": "Norge"}}})
    called = []

    def fetch(ticker, **kwargs):
        called.append(ticker)
        return {"score": 50, "coverage": "CHECKED_NO_EVENTS", "evidence": []}

    monkeypatch.setattr(intelligence, "fetch_insider_intelligence", fetch)
    rows = [{"ticker": f"T{i}.OL", "market": "Norge", "investment_score": 90-i, "raw": {}} for i in range(12)]
    checks = _bounded_insider_checks(rows, SuperPortfolioConfig(market_scopes=("Norge",)))
    assert set(called) == {"HELD.OL", *(f"T{i}.OL" for i in range(5))}
    assert "HELD.OL" in checks
    assert "insider_intelligence" in rows[0]["raw"]
    assert "insider_intelligence" not in rows[10]["raw"]


def test_portfolio_pdf_discloses_programme_without_buy_recommendation():
    from super_portfolio import build_pdf
    document = build_pdf({"positions": {}, "insider_checks": {
        "VEI.OL": {"coverage": "AVAILABLE", "signal": "ANSATTPROGRAM – INGEN KJØPSSIGNAL",
                    "evidence": [{"insider": "Jimmy Bengtsson", "shares": 5000,
                                  "date": "2026-09-07", "transaction_context": "EMPLOYEE_SHARE_PROGRAMME"}]}}})
    extracted = "\n".join(page.extract_text() for page in PdfReader(BytesIO(document)).pages)
    assert "VEI.OL" in extracted
    assert "Jimmy Bengtsson" in extracted
    assert "ansattprogram" in extracted.lower()
