@echo off
setlocal
title Ultima Offline 7
py -3 -B "%~dp0game\qualification\play.py" investigation %*
if not errorlevel 1 exit /b 0
echo Ultima Offline 7 could not start or exited with an error.
if "%~1"=="" pause
exit /b 1
