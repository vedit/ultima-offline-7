@echo off
setlocal
if not defined ULTIMA_OFFLINE_HOME set "ULTIMA_OFFLINE_HOME=%LOCALAPPDATA%\UltimaOffline7"
cd /d "%ULTIMA_OFFLINE_HOME%\PoCs\ClassicUO-U7-Local" || exit /b 1
set "POC=%CD%"
set "TEMP=%POC%\build-temp"
set "TMP=%TEMP%"
if not exist "%TEMP%" mkdir "%TEMP%"
if defined VSCMD_VER goto toolsready
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" (
    echo Open an x64 Visual Studio developer prompt or install Build Tools with Desktop development with C++.
    exit /b 1
)
for /f "usebackq tokens=*" %%i in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VSPATH=%%i"
if not defined VSPATH exit /b 1
call "%VSPATH%\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
:toolsready
set "PATH=%POC%\toolchain\bin;%PATH%"
if "%1"=="matoya" goto matoya
cmake -S "native\Black Gate" -B build-host -G Ninja -DCMAKE_RUNTIME_OUTPUT_DIRECTORY="%POC%\build-host\playtest-avatar-inventory" -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=clang-cl -DCMAKE_CXX_COMPILER=clang-cl
if errorlevel 1 exit /b 1
cmake --build build-host --target u7 --parallel 4
exit /b %errorlevel%
:matoya
cd /d "%POC%\native\third_party\libmatoya"
nmake /F makefile ARCH=x64 all
exit /b %errorlevel%
