param([string]$Root = 'E:\UltimaOffline')
$ErrorActionPreference = 'Stop'
$source = Join-Path $Root 'Tools\U7Revisited-1c55579828a0e1c1c18902dac2aee412b15f3cf8\ThirdParty\lua\src'
$cache = Join-Path $Root 'Cache\DialogueHost'
$env:TEMP = Join-Path $Root 'Cache\Temp'
$env:TMP = $env:TEMP
$env:DOTNET_ROOT = Join-Path $Root 'Tools\dotnet'
$env:DOTNET_CLI_HOME = Join-Path $Root 'Cache\Dotnet'
$env:NUGET_PACKAGES = Join-Path $Root 'Cache\NuGet'
$staging = Join-Path $cache ([guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $staging | Out-Null
$names = [string[]]@(Get-ChildItem -LiteralPath $source -File | Where-Object Extension -In '.c','.h' | ForEach-Object Name)
[Array]::Sort($names, [StringComparer]::Ordinal)
$hashes = foreach ($name in $names) {
    $sha = (Get-FileHash -LiteralPath (Join-Path $source $name)).Hash.ToLowerInvariant()
    "$name $sha"
}
$manifest = [Text.Encoding]::UTF8.GetBytes(($hashes -join "`n") + "`n")
if ([Convert]::ToHexStringLower([Security.Cryptography.SHA256]::HashData($manifest)) -ne 'bd3f40679fc00a627669db4947665768145fbe4e8ef40b1ce64dece1ccf9d6dc') {
    throw 'Pinned Lua 5.4.7 sources changed.'
}
$units = $names | Where-Object { $_ -like '*.c' -and $_ -notin 'lua.c','luac.c','onelua.c','ltests.c' } | ForEach-Object { Join-Path $source $_ }
# GNU PE ld derives its default image base from the output path. Set that
# header field explicitly; Windows can still relocate this ASLR-enabled DLL.
& (Join-Path $Root 'Tools\w64devkit\bin\gcc.exe') -shared -O2 -s '-Wl,--image-base,0x180000000,--no-insert-timestamp' "-I$source" -o "$staging\U7DialogueNative.dll" (Join-Path $PSScriptRoot 'native.c') @units
if ($LASTEXITCODE) { throw 'Native dialogue host build failed.' }
& (Join-Path $env:DOTNET_ROOT 'dotnet.exe') build (Join-Path $PSScriptRoot 'U7DialogueHost.csproj') -c Release -o $staging --source $env:NUGET_PACKAGES "-p:ModernUODir=$Root\Builds\ModernUO" "-p:EntityDir=$Root\Cache\EntitiesHost" "-p:BaseIntermediateOutputPath=$staging\obj\" -p:DebugType=None -p:DebugSymbols=false -p:NuGetAudit=false -v:q
if ($LASTEXITCODE) { throw 'ModernUO dialogue host build failed.' }
foreach ($name in 'U7DialogueNative.dll','U7DialogueHost.dll') {
    [IO.File]::Move((Join-Path $staging $name), (Join-Path $cache $name), $true)
    Get-FileHash -LiteralPath (Join-Path $cache $name)
}
