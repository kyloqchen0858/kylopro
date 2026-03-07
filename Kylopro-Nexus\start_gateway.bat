@echo off
chcp 65001 > nul
:: ============================================================
:: Kylopro Gateway 启动脚本
:: 由 Windows 任务计划程序在系统启动时自动执行
:: ============================================================

:: 激活 nanobot 所在的 Python 环境并启动网关
:: 注意：nanobot gateway 使用 config.json 中的 Telegram 配置自动运行

:: 动态获取项目根目录
pushd "%~dp0.."
set NANOBOT_DIR=%CD%
popd

:: 设定 Kylopro-Nexus 目录
set KYLOPRO_DIR=%~dp0

:: 优先寻找项目根目录下的 venv，如果没有则尝试当前项目下的 .venv
if exist "%NANOBOT_DIR%\venv\Scripts\python.exe" (
    set PYTHON=%NANOBOT_DIR%\venv\Scripts\python.exe
) else (
    set PYTHON=%KYLOPRO_DIR%.venv\Scripts\python.exe
)

cd /d "%KYLOPRO_DIR%"

:: 等待网络就绪（系统启动后延迟 15 秒）
timeout /t 15 /nobreak > nul

:RESTART_LOOP
echo [%date% %time%] 启动 nanobot gateway...
"%PYTHON%" -m nanobot gateway

:: 在 Gateway 启动后，额外启动 Kylopro 核心引擎（静默运行）
echo [%date% %time%] 启动 Kylopro 核心引擎...
:: 设置 PYTHONPATH 确保能找到 core 模块
set PYTHONPATH=%KYLOPRO_DIR%
start /b "" "%PYTHON%" -m core.engine

:: 如果网关意外退出，等待 10 秒后自动重启
echo [%date% %time%] Gateway 已退出，10 秒后重启...
timeout /t 10 /nobreak > nul
goto RESTART_LOOP
