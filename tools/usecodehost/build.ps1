param([string] $Root = 'E:\UltimaOffline')
$ErrorActionPreference = 'Stop'
$source = Join-Path $Root 'Tools\U7Revisited-1c55579828a0e1c1c18902dac2aee412b15f3cf8\ThirdParty\lua\src'
$cache = Join-Path $Root 'Cache\UsecodeHost'
$env:TEMP = Join-Path $Root 'Cache\Temp'
$env:TMP = $env:TEMP
$env:DOTNET_ROOT = Join-Path $Root 'Tools\dotnet'
$env:DOTNET_CLI_HOME = Join-Path $Root 'Cache\Dotnet'
$env:NUGET_PACKAGES = Join-Path $Root 'Cache\NuGet'
New-Item -ItemType Directory -Force -Path $cache, $env:TEMP | Out-Null
$names = [string[]]@(Get-ChildItem -LiteralPath $source -File |
    Where-Object Extension -In '.c','.h' | ForEach-Object Name)
[Array]::Sort($names, [StringComparer]::Ordinal)
$hashList = foreach ($name in $names) {
    $sha = (Get-FileHash -LiteralPath (Join-Path $source $name)).Hash.ToLowerInvariant()
    "$name $sha"
}
$manifest = [Text.Encoding]::UTF8.GetBytes(($hashList -join "`n") + "`n")
$sourceId = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($manifest)).ToLowerInvariant()
if ($sourceId -ne 'bd3f40679fc00a627669db4947665768145fbe4e8ef40b1ce64dece1ccf9d6dc') {
    throw "Lua source tree differs from the qualified 5.4.7 inputs: $sourceId"
}
$units = $names | Where-Object { $_ -like '*.c' -and $_ -notin 'lua.c','luac.c','onelua.c','ltests.c' } |
    ForEach-Object { Join-Path $source $_ }
$staging = Join-Path $cache ([guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $staging | Out-Null
& (Join-Path $Root 'Tools\w64devkit\bin\gcc.exe') -shared -O2 '-Wl,--no-insert-timestamp' "-I$source" -o (Join-Path $staging 'U7LuaHost.dll') (Join-Path $PSScriptRoot 'host.c') @units
if ($LASTEXITCODE) { throw "Lua host native compilation failed" }
& (Join-Path $env:DOTNET_ROOT 'dotnet.exe') build (Join-Path $PSScriptRoot 'U7UsecodeHost.csproj') -c Release -o $staging --source $env:NUGET_PACKAGES -p:NuGetAudit=false "-p:BaseIntermediateOutputPath=$staging\obj\" "-p:ModernUODir=$Root\Builds\ModernUO" -v:q
if ($LASTEXITCODE) { throw "ModernUO host compilation failed" }
foreach ($name in 'U7LuaHost.dll','U7UsecodeHost.dll') {
    [IO.File]::Move((Join-Path $staging $name), (Join-Path $cache $name), $true)
    Get-FileHash -LiteralPath (Join-Path $cache $name)
}
