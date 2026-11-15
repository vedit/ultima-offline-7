@echo off
setlocal
title Ultima Offline 7 - Dream opening
set "TRINSIC_CLIENT_BIN=%~dp0game\intro\bin\creation-client"
set "TRINSIC_HOST_EXECUTABLE=%~dp0game\intro\bin\native-creation\Ultima7.exe"
set "TRINSIC_INTRO_ASSETS=%~dp0game\intro\bin\painted-assets"
set "TRINSIC_READY="
if not exist "%TRINSIC_CLIENT_BIN%\cuo.dll" (
    echo Build the separate dream client using game\intro\README.md first.
    pause
    exit /b 1
)
py -3 -B "%~dp0game\qualification\play.py" investigation --from-opening --run player-dream-intro %*
if not errorlevel 1 exit /b 0
echo The dream client exited with an error. See the run's client.log.
if "%~1"=="" pause
exit /b 1
