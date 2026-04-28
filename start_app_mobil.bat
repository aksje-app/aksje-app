@echo off
cd /d C:\aksje_app
echo Starter appen slik at mobilen kan koble til...
python -m streamlit run app.py --server.address 0.0.0.0
pause
