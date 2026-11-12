param(
    [string] $Root = 'E:\UltimaOffline',
    [switch] $Provision
)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path -LiteralPath $Root).Path
$scratch = Join-Path $Root 'Cache\Readback'
$source = Join-Path $scratch 'ClassicUO'
$pin = 'ee79d7ebc1cc0e53ff84fe6cae17d389e2737f93'
$env:DOTNET_ROOT = Join-Path $Root 'Tools\dotnet'
$env:DOTNET_CLI_HOME = Join-Path $Root 'Cache\Dotnet'
$env:NUGET_PACKAGES = Join-Path $Root 'Cache\NuGet'
$env:NUGET_HTTP_CACHE_PATH = Join-Path $Root 'Cache\NuGetHttp'
$env:TEMP = Join-Path $Root 'Cache\Temp'
$env:TMP = $env:TEMP
$dotnet = Join-Path $env:DOTNET_ROOT 'dotnet.exe'
$project = Join-Path $source 'src\ClassicUO.Assets\ClassicUO.Assets.csproj'
$libraries = Join-Path $source 'src\ClassicUO.Assets\bin\Release\net10.0'
$modern = Join-Path $Root 'Builds\ModernUO'
$bin = Join-Path $scratch 'bin'
New-Item -ItemType Directory -Force -Path $scratch | Out-Null

function Check-Command([string]$operation) {
    if ($LASTEXITCODE -ne 0) { throw "$operation failed ($LASTEXITCODE)" }
}

if ($Provision) {
    if (-not (Test-Path -LiteralPath $source)) {
        git clone --no-hardlinks --no-checkout (Join-Path $Root 'Tools\ClassicUO-Source') $source
        Check-Command 'Copy pinned ClassicUO checkout'
        git -C $source checkout --detach $pin
        Check-Command 'Select pinned ClassicUO revision'
    }
}
if (-not (Test-Path -LiteralPath $project)) {
    throw 'ClassicUO readback source missing. Use -Provision once to populate its private cache.'
}
$head = git -C $source rev-parse HEAD
Check-Command 'Read ClassicUO revision'
if ($head -ne $pin) { throw "Expected ClassicUO commit $pin, got $head" }
if ($Provision) {
    git -C $source submodule update --init --depth 1 --jobs 3
    Check-Command 'Fetch pinned ClassicUO libraries'
    git -C (Join-Path $source 'external\FNA') submodule update --init --depth 1 --jobs 4
    Check-Command 'Fetch pinned FNA bindings'
}
$dirty = git -C $source status --porcelain --untracked-files=no
Check-Command 'Check ClassicUO source integrity'
if ($dirty) { throw "Modified ClassicUO source: $dirty" }
$submodules = @(git -C $source submodule status)
Check-Command 'Read ClassicUO submodule revisions'
$submodules += @(git -C (Join-Path $source 'external\FNA') submodule status)
Check-Command 'Read FNA submodule revisions'
if ($submodules.Count -eq 0 -or ($submodules | Where-Object { $_[0] -ne ' ' })) {
    throw 'Missing or different library revision. Run with -Provision to fetch the pinned dependencies.'
}
$restoreOptions = @('-p:NuGetAudit=false')
if (!$Provision) {
    # The hierarchical global package cache contains the nupkgs downloaded by -Provision.
    $restoreOptions += @('--source', $env:NUGET_PACKAGES)
}
& $dotnet build $project -c Release @restoreOptions -v:q
Check-Command 'Build unchanged ClassicUO.Assets'
& $dotnet build (Join-Path $PSScriptRoot 'Readback.csproj') -c Release -o $bin --source $env:NUGET_PACKAGES `
    -p:NuGetAudit=false "-p:BaseIntermediateOutputPath=$scratch\obj\" `
    "-p:ClassicUOAssetsDir=$libraries" "-p:ModernUODir=$modern" -v:q
Check-Command 'Build terrain readback'
Write-Output (Join-Path $bin 'Readback.dll')
