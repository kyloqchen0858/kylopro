@echo off
chcp 65001 > nul
setlocal
title Gateway Clean Restart

set NANOBOT_DIR=%~dp0..
set KYLOPRO_DIR=%~dp0

if exist "%NANOBOT_DIR%\venv\Scripts\python.exe" (
    set PYTHON=%NANOBOT_DIR%\venv\Scripts\python.exe
) else if exist "%NANOBOT_DIR%\.venv\Scripts\python.exe" (
    set PYTHON=%NANOBOT_DIR%\.venv\Scripts\python.exe
) else (
    echo [ERROR] nanobot source environment not found under %NANOBOT_DIR%
    goto :FAIL
)

echo ========================================
echo Gateway clean restart
echo All actions stay in this window
echo ========================================
echo [INFO] Python: %PYTHON%
echo [INFO] Workdir: %KYLOPRO_DIR%
echo.

echo [1/5] stopping scheduled gateway task...
schtasks /end /tn "Kylopro-Nexus-Gateway" >nul 2>&1
echo       done

echo [2/5] killing all gateway python processes...
powershell -NoProfile -Command "$procs = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*-m nanobot gateway*' }; foreach ($p in $procs) { try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop; Write-Output ('  KILLED: PID=' + $p.ProcessId + ' ' + $p.CommandLine) } catch { Write-Output ('  FAILED: PID=' + $p.ProcessId + ' ' + $p.CommandLine) } }; if (-not $procs) { Write-Output '  (no gateway python processes found)' }"

echo [3/5] killing wrapper cmd processes...
powershell -NoProfile -Command "$me = $PID; $parent = (Get-CimInstance Win32_Process -Filter \"ProcessId=$me\").ParentProcessId; $procs = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'cmd.exe' -and $_.ProcessId -ne $parent -and $_.CommandLine -like '*start_gateway.bat*' }; foreach ($p in $procs) { try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop; Write-Output ('  KILLED_CMD: PID=' + $p.ProcessId) } catch { Write-Output ('  FAILED_CMD: PID=' + $p.ProcessId) } }; if (-not $procs) { Write-Output '  (no wrapper cmd processes found)' }"

echo [4/5] verifying cleanup...
powershell -NoProfile -Command "$remaining = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*-m nanobot gateway*' }; if ($remaining) { foreach ($r in $remaining) { Write-Output ('  WARNING: still alive PID=' + $r.ProcessId + ' ' + $r.CommandLine) } } else { Write-Output '  OK - no gateway processes remaining' }"

echo.
echo [INFO] waiting 15 seconds for Telegram polling to fully release...
timeout /t 15 /nobreak > nul

echo.
echo [5/5] starting gateway in this window...
echo ========================================
cd /d "%KYLOPRO_DIR%"
echo [%date% %time%] Delegating startup to start_gateway.bat /ONESHOT /NODELAY
echo.

call "%KYLOPRO_DIR%start_gateway.bat" /ONESHOT /NODELAY

echo.
echo ========================================
echo [WARN] gateway exited with code: %errorlevel%
echo ========================================
echo.
echo Possible causes:
echo   1. invalid config in ~/.nanobot/config.json
echo   2. another process is still using the port or channel
echo   3. missing dependencies in the source environment
echo   4. inspect the runtime logs shown above
echo.

:FAIL
echo Press any key to close...
pause > nul
