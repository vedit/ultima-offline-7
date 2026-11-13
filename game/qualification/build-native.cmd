@echo off
setlocal
if not defined ULTIMA_OFFLINE_HOME set "ULTIMA_OFFLINE_HOME=E:\UltimaOffline"
cd /d "%ULTIMA_OFFLINE_HOME%\PoCs\ClassicUO-U7-Local" || exit /b 1
set "POC=%CD%"
set "TEMP=%POC%\build-temp"
set "TMP=%TEMP%"
if not exist "%TEMP%" mkdir "%TEMP%"
call "%ProgramFiles(x86)%\Microsoft Visual Studio\2019\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
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
