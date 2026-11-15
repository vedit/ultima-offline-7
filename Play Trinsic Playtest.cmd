@echo off
cd /d "%~dp0"
py -3 -B "%~dp0game\qualification\play.py" investigation --from-opening --run trinsic-playtest-20261116 %*
if errorlevel 1 pause
