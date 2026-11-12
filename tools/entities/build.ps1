param([string]$Root = 'E:\UltimaOffline', [switch]$WithReplay)
$ErrorActionPreference = 'Stop'
$cache = Join-Path $Root 'Cache\EntitiesHost'
$env:DOTNET_ROOT = Join-Path $Root 'Tools\dotnet'
$env:DOTNET_CLI_HOME = Join-Path $Root 'Cache\Dotnet'
$env:NUGET_PACKAGES = Join-Path $Root 'Cache\NuGet'
$env:TEMP = Join-Path $Root 'Cache\Temp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $cache | Out-Null
& (Join-Path $env:DOTNET_ROOT 'dotnet.exe') build (Join-Path $PSScriptRoot 'U7EntitiesHost.csproj') -c Release -o $cache --source $env:NUGET_PACKAGES "-p:ModernUODir=$Root\Builds\ModernUO" "-p:BaseIntermediateOutputPath=$cache\obj\" -p:NuGetAudit=false -v:q
if ($LASTEXITCODE -ne 0) { throw 'Campaign entity host build failed' }
if ($WithReplay) {
    & (Join-Path $env:DOTNET_ROOT 'dotnet.exe') build (Join-Path $PSScriptRoot 'replay/EntityReplay.csproj') -c Release -o "$cache\replay" --source $env:NUGET_PACKAGES "-p:ModernUODir=$Root\Builds\ModernUO" "-p:EntityDir=$cache" "-p:BaseIntermediateOutputPath=$cache\replay-obj\" -p:NuGetAudit=false -v:q
    if ($LASTEXITCODE -ne 0) { throw 'Disposable entity replay build failed' }
}
