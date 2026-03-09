# Skill: Windows Gateway 排障与进程管理

> **作用域**: nanobot gateway 在 Windows 上的运行时行为
> **触发词**: gateway 崩溃、进程重复、Python312、双进程、launcher、venv

## 核心认知

### Python 3.12 venv launcher 机制
- Windows 上 `venv\Scripts\python.exe` 是一个 **launcher stub**（约 270KB）
- 它通过 C runtime `CreateProcess` 启动 `sys._base_executable`（系统 Python312）
- WMI 中看到 **两个** `python.exe -m nanobot gateway` 是 **正常行为**
- 进程链：`venv\python.exe (launcher)` → `Python312\python.exe (worker)`
- **永远不要** 杀掉 Python312 子进程——它就是真正运行代码的进程

### 正确的进程判断方法
```powershell
# 获取所有 gateway 进程及其父子关系
Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -match "nanobot.*gateway"
} | Select-Object ProcessId, ParentProcessId, CommandLine
```
- 如果看到 2 个进程且 ParentProcessId 匹配 → 正常（launcher + worker）
- 如果看到 3+ 个进程且有独立的 Parent → 真正的重复启动

### 排障工具箱

#### 1. WMI 实时进程创建监控（比轮询精准 10x）
```powershell
$query = "SELECT * FROM __InstanceCreationEvent WITHIN 0.1 WHERE TargetInstance ISA 'Win32_Process'"
Register-CimIndicationEvent -Query $query -SourceIdentifier "ProcCreate"
# 然后 Wait-Event -SourceIdentifier "ProcCreate" 来捕获
```

#### 2. 隔离测试法（最高效的 debug 策略）
```
Step 1: 关闭所有 channels + heartbeat → 测试
Step 2: 逐个启用 channel → 定位触发源
Step 3: 在触发源 channel 内进一步缩小范围（import vs start）
```

#### 3. Monkey-patch 金字塔（从高层到低层）
```
Level 1: subprocess.Popen.__init__
Level 2: asyncio.create_subprocess_shell/exec
Level 3: os.system / os.spawn* / os.exec*
Level 4: _winapi.CreateProcess
Level 5: 如果全部未触发 → 行为在 Python 解释器 C runtime 之下
```
如果 Level 1-4 全部未触发，最可能的原因是 **venv launcher C 代码**。

#### 4. start_gateway.bat pre-check
当前已修复为识别 launcher → Python312 的父子关系，不误杀 worker 进程。

## 常见故障模式

| 症状 | 根因 | 修复 |
|------|------|------|
| Gateway 反复崩溃循环 | watchdog 杀 Python312 worker | 移除 watchdog 或修正杀进程逻辑 |
| Telegram 409 Conflict | 两个独立 gateway 同时轮询 | 杀掉多余实例，等 15 秒再重启 |
| QQ botpy WebSocket 断连 | 网络问题或 token 过期 | botpy 有内置重连，通常自恢复 |
| 进程存在但无响应 | bus 队列堵塞或 asyncio 死锁 | 检查 `task_manager.status()` 和 asyncio 任务状态 |

## 禁止事项
- ❌ 在 `start_gateway.bat` 中杀掉 CommandLine 包含 `Python312` 的 gateway 进程
- ❌ 使用 `subprocess.Popen(sys.executable, ...)` 来派生 gateway 实例
- ❌ 在 sitecustomize.py 中遗留调试代码
- ❌ 假设 WMI 中只有 1 个 gateway 进程才是正常的
