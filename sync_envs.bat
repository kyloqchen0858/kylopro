@echo off
chcp 65001 > nul
setlocal

set SCRIPT_DIR=%~dp0
set NANOBOT_DIR=%SCRIPT_DIR%..
set CONSTRAINTS=%NANOBOT_DIR%\constraints-runtime.txt
set REQUIREMENTS=%SCRIPT_DIR%requirements.txt

echo.
echo ========================================
echo   Kylopro 运行时约束同步
echo ========================================
echo   约束文件: %CONSTRAINTS%
echo   依赖文件: %REQUIREMENTS%
echo ========================================
echo.

if not exist "%CONSTRAINTS%" (
    echo [ERROR] 未找到约束文件: %CONSTRAINTS%
    echo         请确认 constraints-runtime.txt 在 nanobot 根目录
    pause
    exit /b 1
)

REM ---- 同步 venv ----
if exist "%NANOBOT_DIR%\venv\Scripts\pip.exe" (
    echo [venv] 正在按约束对齐...
    "%NANOBOT_DIR%\venv\Scripts\pip.exe" install -r "%REQUIREMENTS%" -c "%CONSTRAINTS%" --quiet
    if errorlevel 1 (
        echo [venv] ⚠ 安装出错，请检查上方输出
    ) else (
        echo [venv] ✅ 对齐完成
    )
    echo [venv] 关键依赖版本：
    "%NANOBOT_DIR%\venv\Scripts\pip.exe" show litellm 2>nul | findstr "^Version"
) else (
    echo [venv] 未找到，跳过
)

echo.

REM ---- 同步 .venv ----
if exist "%NANOBOT_DIR%\.venv\Scripts\pip.exe" (
    echo [.venv] 正在按约束对齐...
    "%NANOBOT_DIR%\.venv\Scripts\pip.exe" install -r "%REQUIREMENTS%" -c "%CONSTRAINTS%" --quiet
    if errorlevel 1 (
        echo [.venv] ⚠ 安装出错，请检查上方输出
    ) else (
        echo [.venv] ✅ 对齐完成
    )
    echo [.venv] 关键依赖版本：
    "%NANOBOT_DIR%\.venv\Scripts\pip.exe" show litellm 2>nul | findstr "^Version"
) else (
    echo [.venv] 未找到，跳过
)

echo.
echo ========================================
echo   同步结束
echo   如需升级约束，请先在隔离环境验证，
echo   通过后再修改 constraints-runtime.txt
echo ========================================
echo.
pause
