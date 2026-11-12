param([string] $Root = 'E:\UltimaOffline')
$ErrorActionPreference = 'Stop'
$source = Join-Path $Root 'Tools\U7Revisited-1c55579828a0e1c1c18902dac2aee412b15f3cf8\ThirdParty\lua\src'
$bin = Join-Path $Root 'Tools\Lua-5.4.7'
$compiler = Join-Path $Root 'Tools\w64devkit\bin\gcc.exe'
$env:TMP = Join-Path $Root 'Cache'
$env:TEMP = $env:TMP
New-Item -ItemType Directory -Path $bin -Force | Out-Null
$files = @(Get-ChildItem -LiteralPath $source -File -Filter '*.c' |
    Where-Object Name -NotIn 'luac.c','onelua.c','ltests.c' | Sort-Object Name | ForEach-Object FullName)
if (!$files.Count) { throw "Lua sources missing from $source" }
$tempBinary = Join-Path $bin ("lua-" + [guid]::NewGuid().ToString('N') + ".exe")
try {
    & $compiler -O2 '-Wl,--no-insert-timestamp' -o $tempBinary @files
    if ($LASTEXITCODE) { throw "Lua compilation failed" }
    $lock = Get-Content (Join-Path $PSScriptRoot '..\u7uo\profiles.json') -Raw | ConvertFrom-Json
    if ((Get-FileHash -LiteralPath $tempBinary).Hash -ne $lock.tools.Lua.sha256) { throw "Lua tool lock mismatch" }
    [IO.File]::Move($tempBinary, (Join-Path $bin 'lua.exe'), $true)
}
finally {
    if (Test-Path -LiteralPath $tempBinary) { Remove-Item -LiteralPath $tempBinary }
}
