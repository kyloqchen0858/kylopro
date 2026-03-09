@echo off
chcp 65001 > nul
set NANOBOT_DIR=%~dp0..
echo.
echo ========================================
echo   Kylopro-Nexus 环境初始化
echo ========================================
echo.

REM 检查 Python
python --version > nul 2>&1
if errorlevel 1 (
    echo [ERROR] 未检测到 Python，请先安装 Python 3.11+
    pause
    exit /b 1
)

REM 检查 nanobot 源码环境
echo [1/4] 检查 nanobot 源码环境...
if exist "%NANOBOT_DIR%\venv\Scripts\python.exe" (
    set PYTHON=%NANOBOT_DIR%\venv\Scripts\python.exe
    set PIP=%NANOBOT_DIR%\venv\Scripts\pip.exe
) else if exist "%NANOBOT_DIR%\.venv\Scripts\python.exe" (
    set PYTHON=%NANOBOT_DIR%\.venv\Scripts\python.exe
    set PIP=%NANOBOT_DIR%\.venv\Scripts\pip.exe
) else (
    echo [ERROR] 未找到 nanobot 源码环境，请先在 %NANOBOT_DIR% 初始化 venv 或 .venv
    pause
    exit /b 1
)
echo       使用 Python: %PYTHON%

REM 安装依赖到 nanobot 源码环境
echo [2/4] 安装依赖（按运行时约束）...
"%PIP%" install -r requirements.txt -c "%NANOBOT_DIR%\constraints-runtime.txt" --quiet

REM 复制 .env 模板
if not exist .env (
    echo [3/4] 初始化 .env 配置文件...
    copy .env.example .env > nul
    echo       请编辑 .env 填写你的 API Keys
) else (
    echo [3/4] .env 已存在，跳过
)

REM 创建数据目录
if not exist data mkdir data

echo [4/4] 完成！
echo.
echo ✅ Kylopro 环境初始化成功
echo.
echo 下一步：
echo   1. 编辑 .env 填写 API Keys（nanobot config.json 已配置的会自动读取）
echo   2. 运行: start_gateway.bat
echo   3. 需要开机自启时运行: register_gateway_service.bat
echo.
echo 当前生产链路：
echo   - 唯一 Python 环境：nanobot 源码环境
echo   - 唯一启动脚本：start_gateway.bat
echo   - 唯一启动入口：python -m nanobot gateway
echo.
pause
