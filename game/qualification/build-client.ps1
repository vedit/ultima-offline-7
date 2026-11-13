$ErrorActionPreference = 'Stop'
$installRoot = if ($env:ULTIMA_OFFLINE_HOME) { $env:ULTIMA_OFFLINE_HOME } else { 'E:\UltimaOffline' }
$poc = Join-Path $installRoot 'PoCs\ClassicUO-U7-Local'
$installed = Join-Path (Split-Path (Split-Path $poc)) 'Tools\dotnet'
$packageMirror = Join-Path (Split-Path (Split-Path $poc)) 'Cache\NuGet'
$env:DOTNET_CLI_HOME = Join-Path $poc 'cache\dotnet'
$env:NUGET_PACKAGES = Join-Path $poc 'cache\packages'
$env:NUGET_HTTP_CACHE_PATH = Join-Path $poc 'cache\nuget-http'
$env:TMP = $env:TEMP = Join-Path $poc 'build-temp'
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$env:DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE = 'true'
$env:MSBUILDDISABLENODEREUSE = '1'
$project = Join-Path $poc 'client\src\ClassicUO.Client\ClassicUO.Client.csproj'
& "$installed\dotnet.exe" build $project -c Release -p:PublishAot=false -p:UseSharedCompilation=false -p:NuGetAudit=false "-p:RestoreFallbackFolders=$packageMirror" --source $packageMirror --disable-build-servers
exit $LASTEXITCODE
