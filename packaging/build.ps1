<#
.SYNOPSIS
    Builds the Windows release of aniREF: icon -> PyInstaller -> selftest -> portable zip -> installer.

.DESCRIPTION
    Produces, in dist\:
        aniREF\                          the app folder (what the installer packs)
        aniREF-<version>-portable.zip    same folder plus portable.txt
        aniREF-<version>-setup.exe       per-user installer, only if Inno Setup (ISCC.exe) is found

    Nothing ships that has not started: the built exe must pass `aniREF.exe --selftest`
    (opens a generated video through the real player path and steps frames) twice --
    once as an installed build, once as a portable one. The portable run also checks
    that settings and logs go into data\ next to the exe and nowhere else.

.EXAMPLE
    .\packaging\build.ps1
    .\packaging\build.ps1 -Python C:\Python310\python.exe -SkipInstaller
#>
[CmdletBinding()]
param(
    # Python to build with. Default: the repo's .venv, else python from PATH.
    [string]$Python = "",
    # Skip the Inno Setup step even if ISCC.exe is available.
    [switch]$SkipInstaller,
    # A frozen windowed app shows a dialog instead of a traceback when it cannot start,
    # so an unattended build must not wait for it forever.
    [int]$SelftestTimeoutSec = 240
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Packaging = $PSScriptRoot
$Root = Split-Path -Parent $Packaging
$Dist = Join-Path $Root "dist"
$Build = Join-Path $Root "build"
$AppDir = Join-Path $Dist "aniREF"
$Exe = Join-Path $AppDir "aniREF.exe"

function Write-Step([string]$Text) {
    Write-Host ""
    Write-Host "==> $Text" -ForegroundColor Cyan
}

function Invoke-Native([string]$What, [scriptblock]$Command) {
    # Native tools write progress to stderr; that must not look like a PowerShell error.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $Command } finally { $ErrorActionPreference = $previous }
    if ($LASTEXITCODE -ne 0) { throw "$What failed (exit code $LASTEXITCODE)" }
}

function Get-FileSnapshot([string]$Directory) {
    $entries = @{}
    foreach ($f in Get-ChildItem -LiteralPath $Directory -Recurse -Force -File) {
        $entries[$f.FullName.Substring($Directory.Length + 1)] = $f.Length
    }
    return $entries
}

function Invoke-Selftest {
    <# Runs <app>\aniREF.exe --selftest and returns the exit code, killing it on timeout. #>
    param([string]$ExePath, [hashtable]$Environment = @{})

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $ExePath
    $psi.Arguments = "--selftest"
    $psi.UseShellExecute = $false
    # Explorer and the Start menu shortcut both start the app in its own folder;
    # do the same, so a stray relative-path write would show up next to the exe.
    $psi.WorkingDirectory = Split-Path -Parent $ExePath
    $psi.EnvironmentVariables.Remove("ANIREF_DATA_DIR") | Out-Null  # never test against a developer override
    foreach ($name in $Environment.Keys) { $psi.EnvironmentVariables[$name] = $Environment[$name] }

    $process = [System.Diagnostics.Process]::Start($psi)
    if (-not $process.WaitForExit($SelftestTimeoutSec * 1000)) {
        $process.Kill()
        $process.WaitForExit()
        throw "selftest did not finish within $SelftestTimeoutSec s (an error dialog may be waiting behind it)"
    }
    return $process.ExitCode
}

function Show-SelftestLog([string]$DataDir) {
    $log = Join-Path $DataDir "logs\aniref.log"
    if (Test-Path -LiteralPath $log) {
        Write-Host "---- $log (tail) ----" -ForegroundColor Yellow
        Get-Content -LiteralPath $log -Tail 40 | ForEach-Object { Write-Host $_ }
        Write-Host "---------------------" -ForegroundColor Yellow
    } else {
        Write-Host "no log at $log - the app died before logging started" -ForegroundColor Yellow
    }
}

# ---------------------------------------------------------------------------- setup

if (-not $Python) {
    $venv = Join-Path $Root ".venv\Scripts\python.exe"
    $Python = if (Test-Path -LiteralPath $venv) { $venv } else { "python" }
}
$initPy = Join-Path $Root "src\aniref\__init__.py"
if (-not ((Get-Content -LiteralPath $initPy -Raw) -match '__version__\s*=\s*["'']([^"'']+)["'']')) {
    throw "no __version__ in $initPy"
}
$Version = $Matches[1]
$numbers = [regex]::Matches($Version, '\d+') | ForEach-Object { $_.Value }
while ($numbers.Count -lt 4) { $numbers += "0" }
$VersionNumeric = ($numbers[0..3]) -join "."

Write-Host "aniREF $Version" -ForegroundColor Green
Write-Host "python : $Python"
Write-Host "root   : $Root"

# ---------------------------------------------------------------------------- clean

Write-Step "Cleaning previous build output"
foreach ($path in @($Dist, (Join-Path $Build "pyinstaller"), (Join-Path $Build "selftest"), (Join-Path $Build "portable"))) {
    if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Recurse -Force }
}
New-Item -ItemType Directory -Force -Path $Dist | Out-Null

# ---------------------------------------------------------------------------- icon + freeze

Write-Step "Drawing the app icon"
Invoke-Native "make_icon.py" { & $Python (Join-Path $Packaging "make_icon.py") }

Write-Step "Running PyInstaller"
Invoke-Native "PyInstaller" {
    & $Python -m PyInstaller --noconfirm --clean `
        --distpath $Dist --workpath (Join-Path $Build "pyinstaller") `
        (Join-Path $Packaging "aniref.spec")
}
if (-not (Test-Path -LiteralPath $Exe)) { throw "PyInstaller produced no $Exe" }

# ---------------------------------------------------------------------------- selftest (installed layout)

Write-Step "Selftest: installed build"
$installedData = Join-Path $Build "selftest\installed"
New-Item -ItemType Directory -Force -Path $installedData | Out-Null
$before = Get-FileSnapshot $AppDir
# APPDATA is redirected so the build machine's own aniREF settings stay untouched,
# and so we can prove the app wrote there and not next to the exe.
$code = Invoke-Selftest -ExePath $Exe -Environment @{ APPDATA = $installedData }
if ($code -ne 0) {
    Show-SelftestLog (Join-Path $installedData "aniREF")
    throw "selftest failed on the built exe (exit code $code)"
}
$after = Get-FileSnapshot $AppDir
$written = $after.Keys | Where-Object { -not $before.ContainsKey($_) -or $before[$_] -ne $after[$_] }
if ($written) {
    throw "the app wrote into its own folder without portable.txt: $($written -join ', ')"
}
if (-not (Test-Path -LiteralPath (Join-Path $installedData "aniREF\settings.ini"))) {
    throw "an installed build must keep its settings in %APPDATA%\aniREF"
}
Write-Host "  ok - settings and logs went to %APPDATA%\aniREF, nothing next to the exe"

# ---------------------------------------------------------------------------- portable zip

Write-Step "Building the portable folder"
$portableRoot = Join-Path $Build "portable"
$portableApp = Join-Path $portableRoot "aniREF"
New-Item -ItemType Directory -Force -Path $portableRoot | Out-Null
Copy-Item -LiteralPath $AppDir -Destination $portableApp -Recurse
Copy-Item -LiteralPath (Join-Path $Packaging "portable.txt") -Destination $portableApp

Write-Step "Selftest: portable build"
$portableAppData = Join-Path $Build "selftest\portable-appdata"
New-Item -ItemType Directory -Force -Path $portableAppData | Out-Null
$code = Invoke-Selftest -ExePath (Join-Path $portableApp "aniREF.exe") -Environment @{ APPDATA = $portableAppData }
if ($code -ne 0) {
    Show-SelftestLog (Join-Path $portableApp "data")
    throw "selftest failed on the portable build (exit code $code)"
}
foreach ($expected in @("data\settings.ini", "data\logs\aniref.log")) {
    if (-not (Test-Path -LiteralPath (Join-Path $portableApp $expected))) {
        throw "a portable build must write $expected next to the exe"
    }
}
if (Get-ChildItem -LiteralPath $portableAppData -Recurse -Force -File) {
    throw "a portable build must not write into %APPDATA%"
}
Write-Host "  ok - settings and logs went to data\ next to the exe"
Remove-Item -LiteralPath (Join-Path $portableApp "data") -Recurse -Force  # test data, not release content

Write-Step "Zipping the portable build"
$zip = Join-Path $Dist "aniREF-$Version-portable.zip"
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory(
    $portableApp, $zip, [System.IO.Compression.CompressionLevel]::Optimal, $true)

# ---------------------------------------------------------------------------- installer

$setup = Join-Path $Dist "aniREF-$Version-setup.exe"
$iscc = $null
if (-not $SkipInstaller) {
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    )
    $iscc = $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
    if (-not $iscc) {
        $command = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
        if ($command) { $iscc = $command.Source }
    }
}
if ($iscc) {
    Write-Step "Building the installer with $iscc"
    $defines = @(
        "/DAppVersion=$Version", "/DAppVersionNumeric=$VersionNumeric",
        "/DAppSource=$AppDir", "/DOutDir=$Dist", "/DOutName=aniREF-$Version-setup"
    )
    # The license page only exists once the repo has a LICENSE (see packaging\README.md).
    if (Test-Path -LiteralPath (Join-Path $AppDir "LICENSE.txt")) { $defines += "/DWithLicense=1" }
    Invoke-Native "ISCC" { & $iscc /Qp $defines (Join-Path $Packaging "installer.iss") }
} elseif ($SkipInstaller) {
    Write-Step "Skipping the installer (-SkipInstaller)"
} else {
    Write-Step "No Inno Setup found - skipping the installer"
    Write-Host "  install it with 'choco install innosetup' or from https://jrsoftware.org/isdl.php" -ForegroundColor Yellow
}

# ---------------------------------------------------------------------------- summary

function Format-Size([long]$Bytes) { "{0:N1} MB" -f ($Bytes / 1MB) }

$folderBytes = (Get-ChildItem -LiteralPath $AppDir -Recurse -Force -File | Measure-Object -Property Length -Sum).Sum
Write-Step "Done - aniREF $Version"
Write-Host ("  {0,-44} {1}" -f "dist\aniREF (folder)", (Format-Size $folderBytes))
Write-Host ("  {0,-44} {1}" -f (Split-Path -Leaf $zip), (Format-Size (Get-Item -LiteralPath $zip).Length))
if (Test-Path -LiteralPath $setup) {
    Write-Host ("  {0,-44} {1}" -f (Split-Path -Leaf $setup), (Format-Size (Get-Item -LiteralPath $setup).Length))
}
