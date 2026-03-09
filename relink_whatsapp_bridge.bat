@echo off
chcp 65001 > nul
setlocal
title WhatsApp Relink

set AUTH_DIR=%USERPROFILE%\.nanobot\whatsapp-auth
set BACKUP_ROOT=%USERPROFILE%\.nanobot\whatsapp-auth-backups

echo [WARN] This will force WhatsApp to generate a new QR code.
echo [WARN] Use this when Linked Devices shows the wrong device name or the old session is stale.
echo.
set /p CONFIRM=Type YES to continue: 
if /i not "%CONFIRM%"=="YES" goto :END

for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set TS=%%I

if exist "%AUTH_DIR%" (
    if not exist "%BACKUP_ROOT%" mkdir "%BACKUP_ROOT%"
    move "%AUTH_DIR%" "%BACKUP_ROOT%\whatsapp-auth-%TS%" > nul
    echo [INFO] Existing auth moved to backup: %BACKUP_ROOT%\whatsapp-auth-%TS%
) else (
    echo [INFO] No existing auth directory found.
)

echo [INFO] Starting bridge for fresh QR login...
start "WhatsApp Bridge" cmd /k "%~dp0start_whatsapp_bridge.bat"

:END
echo.
echo Press any key to close...
pause > nul