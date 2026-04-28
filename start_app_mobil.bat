@echo off
cd /d C:\aksje_app
python -m streamlit run app.py --server.address 0.0.0.0
pause
