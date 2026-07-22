from datetime import datetime, timezone

from news_intelligence import normalize_articles, score_articles
from investment_pipeline import PipelineConfig, score_candidate


def article(title, publisher="Reuters", url="https://reuters.com/x"):
    return {
        "title": title,
        "summary": title,
        "publisher": publisher,
        "url": url,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }


def test_positive_news_scores_above_neutral():
    result = score_articles("TEST", [article("Company beats earnings and raises guidance")])
    assert result["score"] > 60
    assert result["sentiment"] in {"POSITIV", "STERKT POSITIV"}


def test_negative_news_scores_below_neutral():
    result = score_articles("TEST", [article("Company cuts guidance after fraud investigation")])
    assert result["score"] < 40
    assert result["negative_count"] == 1


def test_duplicate_titles_are_collapsed():
    rows = [article("Company wins major contract"), article("Company wins major contract", url="https://example.com/y")]
    assert len(normalize_articles(rows)) == 1


def test_missing_news_is_neutral():
    result = score_articles("TEST", [])
    assert result["score"] == 50.0
    assert result["coverage"] == "MISSING"


def test_news_component_enters_score_formula():
    row = {
        "ticker": "TEST", "name": "Test", "market": "USA", "sector": "Tech",
        "strength": 70, "fundamental_score": 65, "research_score": 60,
        "validation_score": 60, "portfolio_fit_score": 60, "risk_score": 30,
        "data_quality": 80, "liquidity_score": 80, "confidence": 70,
        "insider_score": 50, "news_score": 85,
    }
    assessment = score_candidate(row, PipelineConfig())
    assert assessment.raw["score_formula"]["parts"]["news"] == 85.0
    assert assessment.raw["score_formula"]["weights"]["news"] > 0
