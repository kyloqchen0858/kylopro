@echo off
chcp 65001 > nul
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

REM 创建虚拟环境
if not exist .venv (
    echo [1/4] 创建 Python 虚拟环境...
    python -m venv .venv
) else (
    echo [1/4] 虚拟环境已存在，跳过创建
)

REM 激活并安装依赖
echo [2/4] 安装依赖...
call .venv\Scripts\activate.bat
pip install -r requirements.txt --quiet

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
echo   2. 运行: .venv\Scripts\activate.bat
echo   3. 运行: python -m core.engine
echo.
pause
