from functools import lru_cache


@lru_cache(maxsize=1)
def load_sentiment_model():
    """Load sentiment model once. First load can take time."""
    from transformers import pipeline
    return pipeline("sentiment-analysis")


def get_sentiment_score(texts: list[str]) -> float:
    """Return sentiment score from 0.0 to 1.0. 0.5 means neutral/no data."""
    if not texts:
        return 0.5

    try:
        model = load_sentiment_model()
        scores = []

        for text in texts:
            if not text:
                continue
            result = model(text[:512])[0]
            label = result.get("label", "").upper()
            confidence = float(result.get("score", 0.5))

            if "POSITIVE" in label:
                scores.append(confidence)
            elif "NEGATIVE" in label:
                scores.append(-confidence)
            else:
                scores.append(0)

        if not scores:
            return 0.5

        avg = sum(scores) / len(scores)
        return round((avg + 1) / 2, 3)
    except Exception as e:
        print("Feil ved sentiment-analyse:", e)
        return 0.5
