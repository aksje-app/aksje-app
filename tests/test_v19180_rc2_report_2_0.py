from io import BytesIO
from pypdf import PdfReader
import market_intelligence as mi
from app_version import APP_VERSION


def _text(pdf: bytes) -> str:
    return "\n".join((p.extract_text() or "") for p in PdfReader(BytesIO(pdf)).pages)


# Historisk kontrakt arkivert i tests/HISTORICAL_TEST_MANIFEST.json
