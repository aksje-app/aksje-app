"""Same HTTP composition as production, using the existing offline UI fixture."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import streamlit as st
from starlette.middleware import Middleware
from starlette.routing import Route
from public_pdf_http import pdf_response,ReportEntryMiddleware
app=st.App(ROOT/'scripts'/'system_revision_ui_fixture.py',
    routes=[Route('/reports/{token}.pdf',pdf_response,methods=['GET','HEAD'])],
    middleware=[Middleware(ReportEntryMiddleware)])
