@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto usepython
py -3 windows_operator.py activate
set "nok_exit=%errorlevel%"
pause
exit /b %nok_exit%
:usepython
python windows_operator.py activate
set "nok_exit=%errorlevel%"
pause
exit /b %nok_exit%
