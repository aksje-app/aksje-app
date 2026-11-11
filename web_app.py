"""Public Streamlit ASGI extension: same app and health routes, durable PDFs."""
from pathlib import Path
import streamlit as st
from starlette.middleware import Middleware
from starlette.routing import Route
from public_pdf_http import pdf_response,ReportEntryMiddleware

app=st.App(Path(__file__).with_name('app.py'),
    routes=[Route('/reports/{token}.pdf',pdf_response,methods=['GET','HEAD'])],
    middleware=[Middleware(ReportEntryMiddleware)])
