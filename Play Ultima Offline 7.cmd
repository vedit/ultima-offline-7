@echo off
setlocal
title Ultima Offline 7
if not defined ULTIMA_OFFLINE_HOME set "ULTIMA_OFFLINE_HOME=%LOCALAPPDATA%\UltimaOffline7"
if not defined TRINSIC_INTRO_ASSETS set "TRINSIC_INTRO_ASSETS=%ULTIMA_OFFLINE_HOME%\PoCs\ClassicUO-U7-Local\intro-assets"
if not exist "%TRINSIC_INTRO_ASSETS%\intro.json" (
    echo Prepare the local intro assets first. See docs\build-local.md.
    if "%~1"=="" pause
    exit /b 1
)
if exist "%ULTIMA_OFFLINE_HOME%\venv\Scripts\python.exe" (
    "%ULTIMA_OFFLINE_HOME%\venv\Scripts\python.exe" -B "%~dp0game\qualification\play.py" investigation --from-opening %*
) else (
    py -3 -B "%~dp0game\qualification\play.py" investigation --from-opening %*
)
if not errorlevel 1 exit /b 0
echo Ultima Offline 7 could not start or exited with an error.
if "%~1"=="" pause
exit /b 1
