@echo off
chcp 65001 > nul
setlocal
title WhatsApp Bridge

set BRIDGE_DIR=%USERPROFILE%\.nanobot\bridge

if not exist "%BRIDGE_DIR%\dist\index.js" (
    echo [ERROR] WhatsApp bridge is not built yet.
    echo Run: python -m nanobot channels login
    goto :FAIL
)

where npm.cmd >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] npm.cmd not found. Please install Node.js.
    goto :FAIL
)

for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "$listener = Get-NetTCPConnection -LocalPort 3001 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if ($listener) { $proc = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $listener.OwningProcess); if ($proc) { Write-Output ('RUNNING:' + $proc.ProcessId + ':' + $proc.Name + ':' + $proc.CommandLine) } }"`) do (
    set BRIDGE_RUNNING=%%I
)

if defined BRIDGE_RUNNING (
    echo [INFO] WhatsApp bridge is already running.
    echo [INFO] %BRIDGE_RUNNING%
    echo [INFO] Close the existing bridge first if you need to restart it in this window.
    goto :FAIL
)

cd /d "%BRIDGE_DIR%"
echo [INFO] Starting WhatsApp bridge from %BRIDGE_DIR%
echo [INFO] If WhatsApp is not linked yet, scan the QR code shown below.
echo.

npm.cmd start

:FAIL
echo.
echo Press any key to close...
pause > nul