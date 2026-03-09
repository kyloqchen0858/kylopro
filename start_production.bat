@echo off
chcp 65001 >nul
echo [WARN] start_production.bat is now a compatibility wrapper.
echo [WARN] The only production startup script is start_gateway.bat.
echo.
call "%~dp0start_gateway.bat" %*