# Kylopro 开发原则

> **核心理念**: 开发过程本身就是训练数据。每次排障、每次改动都在增强 Kylo 的自我认知。

---

## 原则一：开发即训练

每一次开发迭代都产生三类可复用知识：

1. **排障记录** → `docs/debug/` — 完整的思考过程、误判路径、最终根因
2. **技能沉淀** → `skills/*/` — 从排障中提炼出的可被 Kylo 直接调用的操作手册
3. **认知更新** → `SOUL.md` + `AGENTS.md` — 身体模型、物理限制、行为边界

```
Bug/Feature → [排障/开发] → Debug Log → Skill → Soul Update
                ↓                                    ↓
            DEVLOG.md                          Kylo 下一次更聪明
```

## 原则二：先理解再改动

- **读代码 before 改代码**: 不对未读过的文件提交修改
- **隔离测试法优先**: 关闭所有变量，逐个启用，二分定位
- **不要被时序相关性误导**: A 和 B 同时发生 ≠ A 导致了 B

## 原则三：身体认知

Kylo 必须理解自己的物理运行环境：

| 层级 | 含义 | 例子 |
|------|------|------|
| 大脑 | LLM 提供商 | DeepSeek / MiniMax / Ollama |
| 骨架 | nanobot gateway | asyncio event loop, 单进程 |
| 四肢 | tools + channels | 文件操作、终端、Telegram、QQ |
| 神经 | bus + session | MessageBus 消息路由 |
| 皮肤 | venv + 依赖 | Python 3.12 venv launcher 行为 |

**关键认知**: 
- Windows venv python.exe 是 launcher，spawn Python312 子进程是正常行为
- gateway 进程数 = 2（launcher + worker）是预期的
- `sys.executable` vs `sys._base_executable` 区别必须了解

## 原则四：文档即记忆

| 文档 | 更新频率 | 内容 |
|------|----------|------|
| `DEVLOG.md` | 每个 Phase | 开发日志，跨对话恢复上下文 |
| `DEVELOPMENT_ROADMAP.md` | Phase 完成时 | 宏观路线图 |
| `docs/debug/*.md` | 每次重大排障 | 排障全过程记录 |
| `skills/*/SKILL.md` | 新能力沉淀时 | Kylo 可直接调用的操作手册 |
| `SOUL.md` | 认知更新时 | 自我定义与物理约束 |

## 原则五：最小改动原则

- 不要在修 bug 时顺手重构
- 不要为假想的未来需求添加抽象
- 一个 PR 解决一个问题
- 如果 artifact/建议的前提不成立，不要盲目采纳

## 原则六：防御性运维

- 杀进程前必须理解进程树完整结构
- 不在 `sitecustomize.py` 中遗留调试代码
- watchdog 的杀进程逻辑必须考虑 launcher 委托场景
- `start_gateway.bat` 修改后必须实际测试完整启动流程
