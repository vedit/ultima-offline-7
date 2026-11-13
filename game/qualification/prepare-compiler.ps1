$ErrorActionPreference = 'Stop'
$poc = Split-Path $PSScriptRoot
Set-Location -LiteralPath $poc
$pkg = Join-Path $poc 'toolchain\LLVM-18.1.8-win64.exe'
$hash = (Get-FileHash -LiteralPath $pkg).Hash
if ($hash -ne '94AF030060D88CC17E9F00EF1663EBDC1126B35E16BEBDFA1E807984B70ABD8F') { throw "LLVM download hash mismatch: $hash" }
& 'E:\UltimaOffline\Tools\7zip\Files\7-Zip\7z.exe' x -y '-otoolchain' $pkg 'bin\clang-cl.exe' 'lib\clang\18\include\*' -r
if ($LASTEXITCODE) { exit $LASTEXITCODE }
if ((Get-Item -LiteralPath 'toolchain\bin\clang-cl.exe').Length -lt 1000000) {
    & 'E:\UltimaOffline\Tools\7zip\Files\7-Zip\7z.exe' x -y '-otoolchain' $pkg 'bin\clang.exe'
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
    Copy-Item -LiteralPath 'toolchain\bin\clang.exe' -Destination 'toolchain\bin\clang-cl.exe' -Force
}
& .\toolchain\bin\clang-cl.exe --version
if ($LASTEXITCODE) { exit $LASTEXITCODE }
Get-PSDrive E | Select-Object Free
& .\qualification\build-native.cmd *> evidence\native-build.log
$code = $LASTEXITCODE
Get-Content evidence\native-build.log -Tail 20
exit $code
