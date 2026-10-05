@echo off
setlocal EnableExtensions
title SynthProvenance Build System
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
cd /d "%ROOT%"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "PIP_NO_INPUT=1"
set "BUILDDIR=%ROOT%\build"
set "FAILTXT=%BUILDDIR%\failure.txt"
set "STAGE="
if not exist "%BUILDDIR%" mkdir "%BUILDDIR%"
if exist "%FAILTXT%" del /q "%FAILTXT%"
> "%BUILDDIR%\build.log" echo ==== SynthProvenance build started %DATE% %TIME% ====

echo.
echo ============================================================
echo  SynthProvenance Build System
echo  Insyide Innovations x NuRichter Workspace
echo ============================================================
echo.

where powershell >nul 2>&1
if errorlevel 1 goto :no_powershell

echo [1/8] Checking environment...
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\bootstrap.ps1" -Mode Check -Root "%ROOT%"
if errorlevel 1 goto :fail_stage1

echo [2/8] Preparing runtime...
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\bootstrap.ps1" -Mode Python -Root "%ROOT%"
if errorlevel 1 goto :fail_stage2

set "PY="
set /p PY=<"%BUILDDIR%\python_path.txt"
if not defined PY goto :no_python_path
if not exist "%PY%" goto :no_python_path

"%PY%" "%ROOT%\scripts\build.py" --root "%ROOT%"
if errorlevel 1 goto :fail

echo.
echo ============================================================
echo  BUILD SUCCESSFUL
echo ============================================================
echo.
echo  Output : dist\SynthProvenance\SynthProvenance.exe
echo  Logs   : build\build.log  build\test.log  build\verification.log
echo.
echo  Run the application: dist\SynthProvenance\SynthProvenance.exe
echo.
pause
exit /b 0

:no_powershell
set "STAGE=1/8 Checking environment"
> "%FAILTXT%" echo Reason: Windows PowerShell 5.1 was not found on PATH.
>> "%FAILTXT%" echo Remediation: Use Windows 10 or 11 with Windows PowerShell enabled.
goto :fail

:fail_stage1
set "STAGE=1/8 Checking environment"
goto :fail

:fail_stage2
set "STAGE=2/8 Preparing runtime"
goto :fail

:no_python_path
set "STAGE=2/8 Preparing runtime"
> "%FAILTXT%" echo Reason: The Python runtime path was not recorded in build\python_path.txt.
>> "%FAILTXT%" echo Remediation: Delete the .venv folder and run build.bat again.
goto :fail

:fail
echo.
echo ============================================================
echo  BUILD FAILED
echo ============================================================
if defined STAGE echo  Stage: %STAGE%
if exist "%FAILTXT%" type "%FAILTXT%"
echo  Log  : build\build.log
echo.
pause
exit /b 1
