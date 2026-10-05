# SynthProvenance build entry point for PowerShell users (equivalent to build.bat).
# Usage:  powershell -ExecutionPolicy Bypass -File .\build.ps1 [-SkipTests]
param([switch]$SkipTests)
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$env:PYTHONUTF8 = "1"; $env:PYTHONIOENCODING = "utf-8"; $env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
$BuildDir = Join-Path $Root "build"
New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null
Remove-Item -ErrorAction SilentlyContinue (Join-Path $BuildDir "failure.txt")
Set-Content -Path (Join-Path $BuildDir "build.log") -Value "==== SynthProvenance build started $(Get-Date -Format s) ====" -Encoding UTF8
Write-Host ""
Write-Host "============================================================"
Write-Host " SynthProvenance Build System"
Write-Host " Insyide Innovations x NuRichter Workspace"
Write-Host "============================================================"
Write-Host ""
function Show-Failure([string]$stage) {
  Write-Host ""
  Write-Host "============================================================"
  Write-Host " BUILD FAILED"
  Write-Host "============================================================"
  if ($stage) { Write-Host " Stage: $stage" }
  $f = Join-Path $BuildDir "failure.txt"
  if (Test-Path $f) { Get-Content $f | ForEach-Object { Write-Host " $_" } }
  Write-Host " Log  : build\build.log"
  exit 1
}
Write-Host "[1/8] Checking environment..."
& (Join-Path $Root "scripts\bootstrap.ps1") -Mode Check -Root $Root
if ($LASTEXITCODE -ne 0) { Show-Failure "1/8 Checking environment" }
Write-Host "[2/8] Preparing runtime..."
& (Join-Path $Root "scripts\bootstrap.ps1") -Mode Python -Root $Root
if ($LASTEXITCODE -ne 0) { Show-Failure "2/8 Preparing runtime" }
$py = (Get-Content (Join-Path $BuildDir "python_path.txt") -TotalCount 1).Trim()
$args2 = @((Join-Path $Root "scripts\build.py"), "--root", $Root)
if ($SkipTests) { $args2 += "--skip-tests" }
& $py @args2
if ($LASTEXITCODE -ne 0) { Show-Failure "" }
Write-Host ""
Write-Host "============================================================"
Write-Host " BUILD SUCCESSFUL"
Write-Host "============================================================"
Write-Host " Output: dist\SynthProvenance\SynthProvenance.exe"
