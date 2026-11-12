@echo off
setlocal
set "PYTHONPATH=%~dp0"
py -3 -P -B -m u7uo %*
exit /b %errorlevel%
