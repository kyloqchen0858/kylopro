@echo off
chcp 65001 > nul
:: ============================================================
:: 将 nanobot gateway 注册为 Windows 任务计划程序的开机自启任务
:: ============================================================

:: 检查管理员权限
>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"
if '%errorlevel%' NEQ '0' (
    echo [Kylopro] 正在请求管理员权限...
    goto UACPrompt
) else ( goto gotAdmin )
:UACPrompt
    echo Set UAC = CreateObject^("Shell.Application"^) > "%temp%\getadmin.vbs"
    echo UAC.ShellExecute "%~s0", "", "", "runas", 1 >> "%temp%\getadmin.vbs"
    "%temp%\getadmin.vbs"
    exit /B
:gotAdmin
    if exist "%temp%\getadmin.vbs" ( del "%temp%\getadmin.vbs" )
    pushd "%~dp0"

echo [Kylopro] 正在强制清理旧任务并注册新任务...

:: 1. 尝试通过各种可能的名字删除旧任务
schtasks /delete /tn "KyloproGateway" /f >nul 2>&1
schtasks /delete /tn "Kylopro" /f >nul 2>&1
schtasks /delete /tn "nanobot" /f >nul 2>&1
schtasks /delete /tn "Kylo" /f >nul 2>&1

:: 2. 注册新任务 (使用绝对路径和最简参数)
schtasks /create /tn "Kylopro-Nexus-Gateway" /tr "\"%~dp0start_gateway.bat\"" /sc ONLOGON /delay 0000:15 /rl HIGHEST /f

if %errorlevel% == 0 (
    echo [OK] 任务注册成功！
    echo.
    echo 任务名称: KyloproGateway
    echo 触发条件: 用户登录后 15 秒自动启动
    echo.
    echo 管理命令:
    echo   查看状态: schtasks /query /tn KyloproGateway
    echo   立即运行: schtasks /run /tn KyloproGateway
    echo   停止任务: schtasks /end /tn KyloproGateway
    echo   删除任务: schtasks /delete /tn KyloproGateway /f
) else (
    echo [ERROR] 注册失败，请以管理员身份重新运行此脚本
)

pause
