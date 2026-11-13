$ErrorActionPreference = 'Stop'
$installRoot = if ($env:ULTIMA_OFFLINE_HOME) { $env:ULTIMA_OFFLINE_HOME } else { 'E:\UltimaOffline' }
$poc = Join-Path $installRoot 'PoCs\ClassicUO-U7-Local'
Set-Location -LiteralPath $poc
$pkg = Join-Path $poc 'toolchain\LLVM-18.1.8-win64.exe'
$hash = (Get-FileHash -LiteralPath $pkg).Hash
if ($hash -ne '94AF030060D88CC17E9F00EF1663EBDC1126B35E16BEBDFA1E807984B70ABD8F') { throw "LLVM download hash mismatch: $hash" }
$sevenZip = Join-Path $installRoot 'Tools\7zip\Files\7-Zip\7z.exe'
& $sevenZip x -y '-otoolchain' $pkg 'bin\clang-cl.exe' 'lib\clang\18\include\*' -r
if ($LASTEXITCODE) { exit $LASTEXITCODE }
if ((Get-Item -LiteralPath 'toolchain\bin\clang-cl.exe').Length -lt 1000000) {
    & $sevenZip x -y '-otoolchain' $pkg 'bin\clang.exe'
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
    Copy-Item -LiteralPath 'toolchain\bin\clang.exe' -Destination 'toolchain\bin\clang-cl.exe' -Force
}
& .\toolchain\bin\clang-cl.exe --version
if ($LASTEXITCODE) { exit $LASTEXITCODE }
& (Join-Path $PSScriptRoot 'build-native.cmd') *> evidence\native-build.log
$code = $LASTEXITCODE
Get-Content evidence\native-build.log -Tail 20
exit $code
