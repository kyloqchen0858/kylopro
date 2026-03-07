@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo ========================================
echo Kylopro全能助手 - 生产环境启动
echo ========================================
echo 时间: %date% %time%
echo 版本: 集成三层响应系统 + 分阶段提示
echo ========================================
echo.

REM 检查Python环境
echo [1/5] 检查Python环境...
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python未找到，请安装Python 3.12+
    pause
    exit /b 1
)

REM 检查虚拟环境
echo [2/5] 检查虚拟环境...
if not exist ".venv\Scripts\python.exe" (
    echo ❌ 虚拟环境不存在，请运行 setup.bat
    pause
    exit /b 1
)

REM 检查依赖
echo [3/5] 检查核心依赖...
.venv\Scripts\python -c "import nanobot_ai, ollama, openai, loguru; print('✅ 核心依赖正常')" >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 依赖检查失败，请运行 .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

REM 检查环境变量
echo [4/5] 检查环境配置...
if not exist ".env" (
    echo ⚠️  .env文件不存在，使用默认配置
    copy .env.example .env >nul
)

REM 启动Kylopro
echo [5/5] 启动Kylopro全能助手...
echo.
echo 🚀 启动核心引擎...
echo 💡 功能特性:
echo   - 三层响应系统（情感回应/状态查询/真中断）
echo   - 分阶段提示（5阶段+进度里程碑）
echo   - 双核大脑（DeepSeek + Ollama）
echo   - 任务收件箱（自动化工作流）
echo   - 8个技能框架（可扩展）
echo.
echo 📡 监听消息中...
echo 💬 你可以通过Telegram与我互动
echo ⏰ 系统时间: %date% %time%
echo ========================================
echo.

REM 启动核心引擎
.venv\Scripts\python -m core.engine

if %errorlevel% neq 0 (
    echo.
    echo ❌ Kylopro启动失败，错误代码: %errorlevel%
    echo 请检查:
    echo   1. 环境变量配置 (.env)
    echo   2. API密钥有效性
    echo   3. 网络连接状态
    pause
    exit /b %errorlevel%
)

echo.
echo ✅ Kylopro已正常退出
pause