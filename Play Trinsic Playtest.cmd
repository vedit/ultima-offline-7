@echo off
setlocal
set "installation=E:\UltimaOffline"
if defined ULTIMA_OFFLINE_HOME set "installation=%ULTIMA_OFFLINE_HOME%"
set "playtest=%installation%\Builds\UltimaOffline7\Trinsic-playtest-02"
if not exist "%playtest%\Play Trinsic.cmd" (
    echo Trinsic playtest 02 is not installed at "%playtest%".
    echo See game\receipts\trinsic-playtest-02.json for the prepared local package.
    if "%~1"=="" pause
    exit /b 1
)
call "%playtest%\Play Trinsic.cmd" %*
exit /b %errorlevel%
