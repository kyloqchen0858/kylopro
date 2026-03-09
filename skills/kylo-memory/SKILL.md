---
name: kylo-memory
description: "Kylo 向量记忆使用规范：何时存、何时取、如何调用 memory_manager.py CLI"
metadata: {"nanobot":{"always":true}}
---

# Kylo Memory

## 定位

Kylo 向量记忆由 `memory/memory_manager.py` CLI 工具提供。Kylo 的职责是：

- 判断什么值得记住
- 在合适时机调用 store / search
- 遵守集合分类与标签规范

**两层记忆体系：**
- `memory/MEMORY.md` + `memory/HISTORY.md` — nanobot 原生文本记忆（由框架自动维护）
- `memory/vector_store/` — 向量记忆（ChromaDB，由 `memory_manager.py` 管理）

两者不冲突，向量记忆补充语义检索能力。

## 集合（Collection）分类

| 集合名 | 存什么 | 示例 |
|--------|--------|------|
| `preference` | 用户偏好、操作习惯 | "用户喜好竖排代码注释" |
| `decision` | 技术决策与架构选择 | "选择 ChromaDB 而非 Pinecone，因为可本地运行" |
| `project_fact` | 项目事实、配置细节 | "DeepSeek key 在 config.json providers.deepseek" |
| `code` | 可复用代码片段、模式 | "asyncio retry 装饰器实现方式" |

## CLI 命令规范

所有命令通过 `run_terminal` 执行：

### store — 存储一条记忆

```bash
python memory/memory_manager.py store --text "内容" --collection preference --tag "tag1,tag2"
```

### search — 语义检索（返回 JSON 数组，含 id/text/score/tags）

```bash
python memory/memory_manager.py search --query "检索词" --collection decision --top-k 5
```

### list — 列出集合全部记忆

```bash
python memory/memory_manager.py list --collection project_fact --limit 20
```

### delete — 按 ID 删除

```bash
python memory/memory_manager.py delete --id abc12345
```

## 存储时机

- 用户明确说出偏好或习惯 → `preference`
- 做出架构或技术决策时 → `decision`
- 获得项目关键事实（key/配置/路径/约束） → `project_fact`
- 完成可复用代码片段 → `code`
- 完成重要任务后的关键结论 → `decision` 或 `project_fact`

## 检索时机

- 新对话第一轮，搜 `project_fact` 恢复项目上下文
- 用户问"你还记得…"时，搜对应集合
- 遇到技术问题时，搜 `code` 和 `decision` 找既往经验

## 规则

- 不存临时废话或单轮对话内容
- 每条记忆要有至少一个有意义的标签
- 如果 `memory_manager.py` 执行报错（chromadb/sentence-transformers 未安装），先向用户说明依赖
- 不要在对话中临时发明接口——始终通过 CLI 工具操作

## 依赖安装

```bash
c:\Users\qianchen\Desktop\nanobot\venv\Scripts\pip.exe install chromadb sentence-transformers
```