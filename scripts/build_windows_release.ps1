param(
    [Parameter(Mandatory = $true)]
    [string]$Version,
    [Parameter(Mandatory = $true)]
    [string]$DemoResultsDir,
    [Parameter(Mandatory = $true)]
    [string]$SfincsSourceDir,
    [string]$PythonExecutable = "python",
    [string]$OutputDir = "artifacts/windows-release"
)

$ErrorActionPreference = "Stop"
$resolvedPython = (Get-Command $PythonExecutable -ErrorAction Stop).Source
$pythonEnvironment = Split-Path -Parent $resolvedPython
if ($env:DEBUG -and $env:DEBUG.Trim().ToLowerInvariant() -eq "release") {
    Remove-Item Env:DEBUG
}
$gdalData = Join-Path $pythonEnvironment "Library\share\gdal"
$projData = Join-Path $pythonEnvironment "Library\share\proj"
$nativeBin = Join-Path $pythonEnvironment "Library\bin"
if (Test-Path -LiteralPath $nativeBin -PathType Container) {
    $env:PATH = "$nativeBin;$env:PATH"
}
if (Test-Path -LiteralPath $gdalData -PathType Container) {
    $env:GDAL_DATA = $gdalData
}
if (Test-Path -LiteralPath $projData -PathType Container) {
    $env:PROJ_DATA = $projData
}
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$resultsRoot = (Resolve-Path -LiteralPath $DemoResultsDir).Path
$sfincsSourceRoot = (Resolve-Path -LiteralPath $SfincsSourceDir).Path
$sfincsRuntimeRoot = Join-Path $sfincsSourceRoot "source\sfincs\x64\Release"
$outputRoot = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $OutputDir))
$workRoot = Join-Path $outputRoot "pyinstaller-work"
$specRoot = Join-Path $outputRoot "pyinstaller-spec"
$distRoot = Join-Path $outputRoot "pyinstaller-dist"
$bundleRoot = Join-Path $outputRoot "UrbanPluvialFloodSimulator"
$archivePath = Join-Path $outputRoot "UrbanPluvialFloodSimulator-$Version-windows-x64.zip"
$staticData = Join-Path $repoRoot "floodsim\static"
$jmaData = Join-Path $repoRoot "data\jma"
$eventIds = @(
    "2025-yokkaichi",
    "2026-chiba",
    "2019-saga",
    "2026-nagoya",
    "2000-nagoya"
)

foreach ($eventId in $eventIds) {
    $eventArchive = Join-Path $resultsRoot "$eventId.zip"
    if (-not (Test-Path -LiteralPath $eventArchive -PathType Leaf)) {
        throw "Required demo result is missing: $eventArchive"
    }
}
$manifestPath = Join-Path $resultsRoot "manifest.json"
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Required demo manifest is missing: $manifestPath"
}

New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null
foreach ($target in @($workRoot, $specRoot, $distRoot, $bundleRoot, $archivePath)) {
    $resolvedTarget = [System.IO.Path]::GetFullPath($target)
    if (-not $resolvedTarget.StartsWith($outputRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a path outside the release output directory: $resolvedTarget"
    }
    if (Test-Path -LiteralPath $resolvedTarget) {
        Remove-Item -LiteralPath $resolvedTarget -Recurse -Force
    }
}

Push-Location $repoRoot
try {
    & $resolvedPython -m PyInstaller `
        --noconfirm `
        --clean `
        --onedir `
        --name UrbanPluvialFloodSimulator `
        --workpath $workRoot `
        --specpath $specRoot `
        --distpath $distRoot `
        --add-data "$staticData;floodsim/static" `
        --add-data "$jmaData;data/jma" `
        --add-data "$gdalData;gdal_data" `
        --add-data "$projData;proj_data" `
        --collect-all rasterio `
        --collect-all pyproj `
        --collect-all shapely `
        --collect-all geopandas `
        --collect-all hydromt_sfincs `
        --collect-all xugrid `
        --collect-all pyogrio `
        --collect-all scipy `
        --hidden-import pyogrio._geometry `
        scripts/windows_desktop.py
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

Copy-Item -LiteralPath (Join-Path $distRoot "UrbanPluvialFloodSimulator") -Destination $bundleRoot -Recurse
$bundledSfincs = Join-Path $bundleRoot "sfincs"
New-Item -ItemType Directory -Force -Path $bundledSfincs | Out-Null
$sfincsFiles = @(
    "sfincs.exe",
    "netcdf.dll",
    "hdf.dll",
    "hdf5_hl.dll",
    "hdf5.dll",
    "libcurl.dll",
    "zlib1.dll",
    "libiomp5md.dll",
    "libifcoremd.dll",
    "libmmd.dll"
)
foreach ($fileName in $sfincsFiles) {
    $sourceFile = Join-Path $sfincsRuntimeRoot $fileName
    if (-not (Test-Path -LiteralPath $sourceFile -PathType Leaf)) {
        throw "Required self-built SFINCS runtime file is missing: $sourceFile"
    }
    Copy-Item -LiteralPath $sourceFile -Destination $bundledSfincs
}
$visualCppRuntime = Join-Path $sfincsSourceRoot "source\third_party_open\netcdf\netCDF 4.9.2\bin\vcruntime140.dll"
if (-not (Test-Path -LiteralPath $visualCppRuntime -PathType Leaf)) {
    throw "Required Visual C++ runtime is missing: $visualCppRuntime"
}
Copy-Item -LiteralPath $visualCppRuntime -Destination $bundledSfincs
Copy-Item -LiteralPath (Join-Path $sfincsSourceRoot "LICENSE") -Destination (Join-Path $bundledSfincs "LICENSE-GPL-3.0.txt")
Copy-Item -LiteralPath (Join-Path $sfincsSourceRoot "README.rst") -Destination (Join-Path $bundledSfincs "README-SFINCS.rst")
$sourceArchive = Join-Path $bundledSfincs "SFINCS-v2.4.0-Galibier-source.zip"
& git -C $sfincsSourceRoot archive `
    --format=zip `
    --output=$sourceArchive `
    HEAD
if ($LASTEXITCODE -ne 0) {
    throw "Creating the corresponding SFINCS source archive failed with exit code $LASTEXITCODE"
}
$sfincsCommit = (& git -C $sfincsSourceRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Reading the SFINCS source commit failed with exit code $LASTEXITCODE"
}
$sfincsHash = (Get-FileHash -LiteralPath (Join-Path $bundledSfincs "sfincs.exe") -Algorithm SHA256).Hash
@(
    "SFINCS v2.4.0 Galibier",
    "Source: https://github.com/Deltares/SFINCS",
    "Source commit: $sfincsCommit",
    "Executable SHA-256: $sfincsHash",
    "Built locally from the GPL-3.0 source; not the separately licensed Deltares precompiled binary."
) | Set-Content -LiteralPath (Join-Path $bundledSfincs "BUILD-INFO.txt") -Encoding utf8
$bundledResults = Join-Path $bundleRoot "demo-results"
New-Item -ItemType Directory -Force -Path $bundledResults | Out-Null
Copy-Item -LiteralPath $manifestPath -Destination $bundledResults
foreach ($eventId in $eventIds) {
    Copy-Item -LiteralPath (Join-Path $resultsRoot "$eventId.zip") -Destination $bundledResults
}
Copy-Item -LiteralPath (Join-Path $repoRoot "docs\release\portable-readme-ja.txt") -Destination (Join-Path $bundleRoot "はじめにお読みください.txt")

Compress-Archive -Path (Join-Path $bundleRoot "*") -DestinationPath $archivePath -CompressionLevel Optimal
$hash = Get-FileHash -LiteralPath $archivePath -Algorithm SHA256
[pscustomobject]@{
    archive = $archivePath
    bytes = (Get-Item -LiteralPath $archivePath).Length
    sha256 = $hash.Hash
}
