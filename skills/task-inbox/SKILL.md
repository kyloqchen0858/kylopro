---
name: task-inbox
description: "Kylopro 任务收件箱 — 管理异步任务队列，支持查看/添加/完成任务"
---

# 任务收件箱 (Task Inbox)

管理 `tasks/` 目录下的 Markdown 任务文件。

## 查看待处理任务

```bash
ls tasks/*.md 2>/dev/null || echo "无待处理任务"
```

或者在 Windows:
```bash
dir tasks\*.md 2>nul || echo "无待处理任务"
```

## 添加任务

用 `write_file` 在 `tasks/` 目录创建 `.md` 文件：

```
tasks/YYYYMMDD_HHMM_简短描述.md
```

任务文件格式：
```markdown
# 任务标题

## 优先级
P0/P1/P2/P3

## 描述
具体要做什么

## 验收标准
- [ ] 条件1
- [ ] 条件2
```

## 完成任务

完成后将任务文件移到 `tasks/done/` 目录：
```bash
mkdir -p tasks/done && mv tasks/任务文件.md tasks/done/
```

## TaskBridge 工具

长任务管理使用 TaskBridge 工具：
- `task_read` — 读取当前任务状态（进度、步骤、是否中断）
- `task_write` — 更新任务进度、摘要、当前步骤
- `task_interrupt` — 写入中断标志，子任务在下一步检测到后退出

状态文件位于 `workspace/tasks/active_task.json`。

## 原则
- 大任务拆成子任务，每个子任务一个文件
- 完成一个标记一个，不要攒着
- P0 优先处理
- 超过 30 秒的任务走 spawn + TaskBridge
