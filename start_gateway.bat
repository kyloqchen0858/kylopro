@echo off
chcp 65001 > nul
setlocal
set SCRIPT_DIR=%~dp0

set SKIP_DELAY=0
set RESTART_ON_EXIT=1

:parse_args
if "%~1"=="" goto args_done
if /i "%~1"=="/NODELAY" set SKIP_DELAY=1
if /i "%~1"=="/ONESHOT" set RESTART_ON_EXIT=0
shift
goto parse_args

:args_done
set NANOBOT_DIR=%SCRIPT_DIR%..
set KYLOPRO_DIR=%SCRIPT_DIR%

if exist "%NANOBOT_DIR%\venv\Scripts\python.exe" (
    set PYTHON=%NANOBOT_DIR%\venv\Scripts\python.exe
) else if exist "%NANOBOT_DIR%\.venv\Scripts\python.exe" (
    set PYTHON=%NANOBOT_DIR%\.venv\Scripts\python.exe
) else (
    echo [ERROR] nanobot source environment not found under %NANOBOT_DIR%
    pause
    exit /b 1
)

cd /d "%KYLOPRO_DIR%"

echo [INFO] Python: %PYTHON%
echo [INFO] Entry: nanobot gateway

rem ── Pre-check: kill orphan gateways that are NOT our venv launcher NOR its Python312 child ──
for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "$py = [Regex]::Escape($env:PYTHON); $procs = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*-m nanobot gateway*' }; $venvPids = @(); foreach ($p in $procs) { if ($p.CommandLine -match $py) { $venvPids += $p.ProcessId; Write-Output ('KEEP:' + $p.ProcessId) } }; foreach ($p in $procs) { if (-not ($p.CommandLine -match $py)) { if ($p.ParentProcessId -in $venvPids) { Write-Output ('KEEP-CHILD:' + $p.ProcessId) } else { try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop; Write-Output ('KILLED:' + $p.ProcessId) } catch { Write-Output ('FAILED:' + $p.ProcessId) } } } }"`) do (
    echo [GATEWAY] %%I
)

powershell -NoProfile -Command "$py = [Regex]::Escape($env:PYTHON); $gws = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*-m nanobot gateway*' }; $hasVenv = $gws | Where-Object { $_.CommandLine -match $py }; if ($hasVenv) { exit 10 } else { exit 0 }"
if %errorlevel% equ 10 (
    echo [INFO] gateway already running in the correct environment
    echo [INFO] no action needed — window will close in 5 seconds
    timeout /t 5 /nobreak > nul
    exit /b 0
)

if %SKIP_DELAY% equ 0 (
    echo [INFO] waiting 15 seconds before startup
    timeout /t 15 /nobreak > nul
) else (
    echo [INFO] /NODELAY enabled
)

if %RESTART_ON_EXIT% equ 0 (
    echo [INFO] /ONESHOT enabled
)

rem ── NOTE: Python 3.12 venv python.exe is a launcher that spawns Python312\python.exe
rem ── as a child process. This is NORMAL — do NOT kill the Python312 child.
rem ── The "duplicate" process IS the real gateway worker.

:RESTART_LOOP
echo [%date% %time%] starting nanobot gateway...
"%PYTHON%" -m nanobot gateway

if %RESTART_ON_EXIT% equ 0 exit /b %errorlevel%
echo [%date% %time%] gateway exited, retrying in 10 seconds...
timeout /t 10 /nobreak > nul
goto RESTART_LOOP
