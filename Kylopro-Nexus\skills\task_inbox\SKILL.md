---
name: task_inbox
description: "任务收件箱 — 接收 Markdown 需求文档，解析为结构化任务，分发给已有技能执行"
version: "1.0.0"
dependencies:
  - file_monitor    # watchdog 文件监控
  - ide_bridge      # 代码读写和命令执行
  - telegram_notify # 进度推送
  - web_pilot       # 网页操作（可选）
  - vision_rpa      # 桌面操作（可选）
---

# 任务收件箱 (Task Inbox)

> 让 Kylo 拥有"手脚和眼睛"——接收 Markdown 需求文档并自动执行开发任务。

## 能力

| 能力 | 说明 |
|------|------|
| 📥 热目录监控 | 监控 `data/inbox/` 目录，发现新 `.md` / `.txt` 文件 |
| 🧠 需求解析   | 用 Ollama 本地 LLM 将自然语言需求转为结构化任务清单 |
| 🦶 任务调度   | 将子任务分发给 ide_bridge / web_pilot / vision_rpa 执行 |
| 📊 进度跟踪   | 任务状态机 + Telegram 进度推送 + 结果归档 |

## 使用方式

### 方式 1：热目录投递
将 `.md` 文件拖入 `data/inbox/` 目录，自动触发处理。

### 方式 2：CLI 命令
```
/task start              # 启动 inbox 监控
/task submit path/to/需求.md  # 手动投递需求文件
/task status             # 查看任务队列
/task history            # 查看已完成任务
```

### 方式 3：代码调用
```python
from skills.task_inbox.inbox import TaskInbox
inbox = TaskInbox(workspace="c:/MyProject")
await inbox.submit_file("requirements.md")
```

## 需求文档格式

支持自由格式 Markdown，LLM 会自动理解。推荐结构：

```markdown
# 项目名称

## 需求描述
简述你要做什么。

## 任务清单
1. 创建 xxx 文件
2. 实现 xxx 功能
3. 运行测试验证
```

## 任务状态流转

```
pending → parsing → executing → done
                              → failed
```
