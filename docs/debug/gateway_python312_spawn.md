# Debug 排障记录：Gateway Python312 双进程之谜

> **日期**: 2026-03-09
> **耗时**: ~3 小时
> **严重等级**: P1（Gateway 反复崩溃，无法稳定运行）
> **根因**: Python 3.12 venv launcher 机制 + 错误的 watchdog 杀进程逻辑

---

## 1. 症状

启动 `nanobot gateway` 后，观察到：
- WMI 中出现 **两个** `python.exe -m nanobot gateway` 进程
- 一个路径是 `venv\Scripts\python.exe`（launcher）
- 另一个路径是 `Python312\python.exe`（system Python）
- 两者 Parent-Child 关系：venv PID → Python312 PID
- Gateway 在 2-4 秒内崩溃，Telegram 报 `409 Conflict`

## 2. 误判路径（耗时最长）

### 误判 1：某处代码 subprocess.Popen 派生了第二个 gateway
- **排查方法**: 用 `sys.addaudithook` 注入审计钩子到 `sitecustomize.py`
- **结果**: 审计钩子 **未捕获** 任何 `subprocess.Popen` 或 `os.system` 调用
- **教训**: 审计钩子只能捕获 Python 层的调用，无法捕获 C 层的 `CreateProcess`

### 误判 2：botpy（QQ SDK）通过 pywin32/ctypes 直接调用 CreateProcess
- **排查方法**: 搜索 botpy 全部源码，只找到 `os.system("")`（ANSI 颜色 hack）
- **结果**: botpy 没有进程创建代码
- **教训**: 不要因为时序相关性（botpy import 时出现 Python312）就断言因果关系

### 误判 3：WMI 事件订阅或 Windows 服务自动启动
- **排查方法**: 查询 `root\subscription` 命名空间的所有事件消费者
- **结果**: 只有系统默认的 SCM Event Log Consumer
- **教训**: 排除低概率假设也有价值，但应该先排查高概率路径

### 误判 4：_winapi.CreateProcess 被第三方库劫持
- **排查方法**: Monkey-patch `_winapi.CreateProcess` + `os.spawn*` + `os.exec*` + `subprocess.Popen`
- **结果**: **所有 patch 都未触发**，但 Python312 仍然出现
- **关键发现**: 这证明进程创建发生在 Python 解释器层面之下（C runtime 级别）

## 3. 突破口

### 隔离测试法
```
channels 全关 → 无 Python312         ✅
只开 Telegram  → 无 Python312        ✅
只开 QQ        → 出现 Python312      ❌  ← 误导！
```

但随后发现 **任何命令** 都会产生 Python312 子进程：
```powershell
# 即使只是 sleep，也会产生:
venv\python.exe -c "import time; time.sleep(5)"
  → 子进程: Python312\python.exe -c "import time; time.sleep(5)"
```

### 最终确认
```
venv python.exe 大小: 270KB  ← 这是 launcher！
system python.exe 大小: 103KB

pyvenv.cfg:
  executable = C:\...\Python312\python.exe
```

**Python 3.12 venv 在 Windows 上的 `python.exe` 是一个 launcher stub**，它通过 C runtime 级别的 `CreateProcess` 将执行委托给 `sys._base_executable`（系统 Python312）。这是 Python 标准行为，不是 bug。

## 4. 根因链

```
start_gateway.bat 
  → venv\python.exe -m nanobot gateway     (PID A, launcher)
  → CreateProcess at C runtime level
  → Python312\python.exe -m nanobot gateway (PID B, 真正的 worker)

start_gateway.bat 内的 watchdog:
  → 每 30 秒扫描 "非 venv 路径" 的 nanobot gateway
  → 发现 PID B (Python312) 不匹配 venv 路径
  → 杀掉 PID B ← 这就是崩溃原因！
  → PID A (launcher) 检测到子进程退出，也退出
  → restart loop 重启，进入无限循环
```

## 5. 修复

1. **移除 watchdog**：不再杀 Python312 子进程（它就是真正的 gateway）
2. **修复 pre-check**：识别 Python312 子进程为 venv launcher 的合法子进程
3. **清理调试产物**：移除 `sitecustomize.py`

## 6. Kylo 应学到的经验

### 关于 venv
- Windows Python 3.12 venv 的 `python.exe` 是 **launcher**，ALWAYS 创建 Python312 子进程
- `sys.executable` 指向 venv，但 `sys._base_executable` 指向系统 Python
- WMI 中看到两个进程是正常的，不需要杀掉其中任何一个

### 关于 debug 方法论
- **隔离测试法**（binary search）是最有效的：先关闭所有功能，逐个启用
- **Monkey-patch 无效时**：说明行为发生在 Python 解释器之下（C runtime / venv launcher）
- **WMI 实时事件订阅**比轮询更可靠：`Register-CimIndicationEvent` + `WITHIN 0.1`
- **不要被时序相关性误导**：QQ channel 导致 Python312 出现不是因为 botpy 创建了进程，而是因为 botpy import 触发了更多 Python 代码执行，给了 WMI 更多时间捕获早已在运行的 launcher 子进程

### 关于 watchdog 设计
- 在写"杀进程"逻辑前，必须理解进程树的完整结构
- venv launcher → system Python 的 parent-child 关系在 Windows 上是标准行为
- 杀"错误环境"进程的逻辑必须考虑 launcher 委托场景

## 7. 关联文件

- `Kylopro-Nexus/start_gateway.bat` — 修复了 watchdog 和 pre-check
- `venv/pyvenv.cfg` — 记录了 venv 与 system Python 的关系
- `_nanobot_ai.pth` — 存在于两处 site-packages，使 nanobot 在 venv 和 system Python 中都可导入
