# SynthProvenance bootstrap: environment checks (-Mode Check) and Python runtime preparation (-Mode Python).
# Never downloads anything silently. The optional Python download asks for consent and verifies the
# Authenticode signature of the official Python Software Foundation package before use.
[CmdletBinding()]
param(
  [ValidateSet("Check", "Python")][string]$Mode = "Check",
  [string]$Root = (Split-Path -Parent $PSScriptRoot),
  [switch]$NonInteractive
)
$ErrorActionPreference = "Stop"
$BuildDir = Join-Path $Root "build"
New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null
$Log = Join-Path $BuildDir "build.log"
$MinMinor = 11
$MaxMinor = 14
$Preferred = @("3.12", "3.13", "3.11", "3.14")
$NuGetVersion = "3.12.10"

function Write-Log([string]$msg) {
  Add-Content -Path $Log -Value ("[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg) -Encoding UTF8
}
function Say([string]$msg) { Write-Host "      $msg"; Write-Log $msg }
function Fail([string]$reason, [string]$fix) {
  Set-Content -Path (Join-Path $BuildDir "failure.txt") -Value @(" Reason: $reason", " Remediation: $fix") -Encoding ASCII
  Write-Log "FAILED: $reason | $fix"
  exit 1
}

if ($Mode -eq "Check") {
  if (-not [Environment]::Is64BitOperatingSystem) { Fail "32-bit Windows detected." "SynthProvenance requires 64-bit Windows 10 or 11." }
  $arch = $env:PROCESSOR_ARCHITECTURE
  if ($env:PROCESSOR_ARCHITEW6432) { $arch = $env:PROCESSOR_ARCHITEW6432 }
  Say "Architecture: $arch"
  if ($arch -eq "ARM64") { Say "WARNING: ARM64 detected. An x64 Python runs under emulation (Windows 11 required)." }
  $os = [Environment]::OSVersion.Version
  Say ("Windows version: {0}" -f $os)
  if ($os.Major -lt 10) { Fail "Windows $os is not supported." "Use 64-bit Windows 10 or Windows 11." }
  try {
    $drive = (Get-Item -LiteralPath $Root).PSDrive
    if ($drive.Free) {
      Say ("Free disk space on {0}: {1:N1} GB" -f $drive.Name, ($drive.Free / 1GB))
      if ($drive.Free -lt 3GB) { Fail ("Only {0:N1} GB free." -f ($drive.Free / 1GB)) "Free at least 3 GB for the virtual environment and the build." }
    }
  } catch { Say "Free disk space: unknown" }
  if ($Root.Length -gt 120) { Say "WARNING: long project path ($($Root.Length) chars). Extract closer to the drive root if path errors occur." }
  try {
    $lp = (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name LongPathsEnabled -ErrorAction Stop).LongPathsEnabled
    Say "LongPathsEnabled: $lp"
  } catch { Say "LongPathsEnabled: unknown" }
  if ($Root -match "OneDrive") { Say "WARNING: project is inside OneDrive; sync can lock files during the build." }
  try {
    $probe = Join-Path $BuildDir ".write_probe"
    Set-Content -Path $probe -Value "ok" -Encoding ASCII
    Remove-Item $probe
  } catch { Fail "The project folder is not writable." "Extract the ZIP to a writable folder such as C:\Research\SynthProvenance." }
  exit 0
}

# Windows PowerShell 5.1 turns native-command stderr into terminating errors under "Stop".
# Python mode checks every exit code explicitly instead.
$ErrorActionPreference = "Continue"

function Test-Python([string]$exe, [string[]]$pre = @()) {
  try {
    $out = & $exe @pre -c "import sys,struct;print(sys.version_info[0], sys.version_info[1], struct.calcsize('P')*8)" 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $out) { return $null }
    $p = ("$out".Trim()) -split "\s+"
    if ([int]$p[0] -ne 3) { return $null }
    $minor = [int]$p[1]
    if ([int]$p[2] -ne 64) { Say "Skipping $exe $pre (32-bit interpreter)"; return $null }
    if ($minor -lt $MinMinor -or $minor -gt $MaxMinor) { Say "Skipping $exe $pre (Python 3.$minor; need 3.$MinMinor-3.$MaxMinor)"; return $null }
    $real = & $exe @pre -c "import sys;print(sys.executable)" 2>$null
    return @{ Exe = "$real".Trim(); Version = "3.$minor" }
  } catch { return $null }
}

$venv = Join-Path $Root ".venv"
$venvPy = Join-Path $venv "Scripts\python.exe"
$pathFile = Join-Path $BuildDir "python_path.txt"
if (Test-Path $venvPy) {
  $t = Test-Python $venvPy
  if ($t) {
    Say "Using existing virtual environment .venv (Python $($t.Version))"
    Set-Content -Path $pathFile -Value $venvPy -Encoding ASCII
    exit 0
  }
  Say "Existing .venv is unusable; recreating it."
  Remove-Item -Recurse -Force $venv
}

$found = $null
$local = Join-Path $Root "runtime\python\tools\python.exe"
if (Test-Path $local) { $found = Test-Python $local; if ($found) { Say "Found project-local runtime\python" } }
if (-not $found -and (Get-Command py -ErrorAction SilentlyContinue)) {
  foreach ($v in $Preferred) { $found = Test-Python "py" @("-$v"); if ($found) { Say "Found via py launcher (-$v)"; break } }
}
if (-not $found) {
  foreach ($c in @(Get-Command python.exe -All -ErrorAction SilentlyContinue)) {
    if ($c.Source -like "*\WindowsApps\*") { continue }
    $found = Test-Python $c.Source
    if ($found) { Say "Found on PATH"; break }
  }
}
if (-not $found) {
  foreach ($hive in @("HKCU:", "HKLM:")) {
    foreach ($v in $Preferred) {
      try {
        $ip = (Get-ItemProperty "$hive\SOFTWARE\Python\PythonCore\$v\InstallPath" -ErrorAction Stop).'(default)'
        if ($ip) {
          $exe = Join-Path $ip "python.exe"
          if (Test-Path $exe) { $found = Test-Python $exe; if ($found) { Say "Found in registry ($hive $v)"; break } }
        }
      } catch { }
    }
    if ($found) { break }
  }
}

if (-not $found) {
  Say "No supported 64-bit Python ($("3.$MinMinor")-$("3.$MaxMinor")) was found."
  $url = "https://www.nuget.org/api/v2/package/python/$NuGetVersion"
  $answer = "n"
  if (-not $NonInteractive) {
    Write-Host ""
    Write-Host "      SynthProvenance can download the OFFICIAL Python $NuGetVersion package published by the"
    Write-Host "      Python Software Foundation on nuget.org into .\runtime\python (no system-wide install)."
    Write-Host "      Source: $url"
    $answer = Read-Host "      Download it now? [y/N]"
  }
  if ($answer -notmatch "^(y|yes)$") {
    Fail "No supported Python found and the download was declined." "Install 64-bit Python 3.12 from https://www.python.org/downloads/windows/ and run build.bat again."
  }
  $rt = Join-Path $Root "runtime"
  New-Item -ItemType Directory -Force -Path $rt | Out-Null
  $pkg = Join-Path $rt "python.$NuGetVersion.zip"
  try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Say "Downloading $url"
    Invoke-WebRequest -Uri $url -OutFile $pkg -UseBasicParsing
  } catch { Fail "Download failed: $($_.Exception.Message)" "Check the internet connection or install Python 3.12 manually from python.org." }
  $dest = Join-Path $rt "python"
  if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
  try { Expand-Archive -Path $pkg -DestinationPath $dest -Force -ErrorAction Stop }
  catch { Fail "The downloaded package could not be extracted." "Install Python 3.12 manually from python.org." }
  $exe = Join-Path $dest "tools\python.exe"
  if (-not (Test-Path $exe)) { Fail "The downloaded package does not contain tools\python.exe." "Install Python 3.12 manually from python.org." }
  $sig = Get-AuthenticodeSignature -FilePath $exe
  if ($sig.Status -ne "Valid" -or $sig.SignerCertificate.Subject -notmatch "Python Software Foundation") {
    Remove-Item -Recurse -Force $dest
    Fail "Authenticode verification of the downloaded python.exe failed (status: $($sig.Status))." "Install Python 3.12 manually from python.org."
  }
  Say "Authenticode signature valid: $($sig.SignerCertificate.Subject)"
  $found = Test-Python $exe
  if (-not $found) { Fail "The downloaded Python could not be started." "Install Python 3.12 manually from python.org." }
}

Say "Python $($found.Version): $($found.Exe)"
Say "Creating virtual environment .venv"
& $found.Exe -m venv $venv 2>&1 | ForEach-Object { Write-Log "$_" }
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPy)) {
  Fail "Could not create the virtual environment." "Make sure the Python installation includes 'venv' and that the project folder is writable."
}
Set-Content -Path $pathFile -Value $venvPy -Encoding ASCII
exit 0
