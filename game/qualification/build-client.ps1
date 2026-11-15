$ErrorActionPreference = 'Stop'
$installRoot = if ($env:ULTIMA_OFFLINE_HOME) { $env:ULTIMA_OFFLINE_HOME } else { Join-Path $env:LOCALAPPDATA 'UltimaOffline7' }
$runtime = Join-Path $installRoot 'PoCs\ClassicUO-U7-Local'
$bundled = Join-Path $installRoot 'Tools\dotnet\dotnet.exe'
$dotnet = if ($env:DOTNET) { $env:DOTNET } elseif (Test-Path -LiteralPath $bundled) { $bundled } else { (Get-Command dotnet -ErrorAction Stop).Source }
$env:DOTNET_CLI_HOME = Join-Path $runtime 'cache\dotnet'
$env:NUGET_PACKAGES = Join-Path $runtime 'cache\packages'
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$project = Join-Path $runtime 'client\src\ClassicUO.Client\ClassicUO.Client.csproj'
if (!(Test-Path -LiteralPath $project)) { throw 'Stage the pinned ClassicUO checkout and source overlay first; see docs/build-local.md.' }
$argsForBuild = @('build', $project, '-c', 'Release', '-p:PublishAot=false', '-p:UseSharedCompilation=false', '--disable-build-servers')
$mirror = Join-Path $installRoot 'Cache\NuGet'
if (Test-Path -LiteralPath $mirror) { $argsForBuild += @('--source', $mirror, "-p:RestoreFallbackFolders=$mirror") }
& $dotnet @argsForBuild
exit $LASTEXITCODE
