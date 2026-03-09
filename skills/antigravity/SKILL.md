---
name: antigravity
description: "IDE 与 GUI 控制策略：MCP first，命令行 second，GUI automation last"
---

# Antigravity — IDE/GUI 控制技能

## 定位

Antigravity 不是"让 Kylo 到处手写 pyautogui"，而是 IDE/GUI 控制的**协议桥接层**。

**三级降级策略（严格按顺序）：**

```
1. MCP filesystem/editor tools
   ↓ MCP 不可用
2. exec + PowerShell / cmd
   ↓ 命令行无法完成
3. pyautogui bridge（最后兜底）
```

## 第一优先：MCP Tools

当 nanobot config.json 中配置了 MCP IDE server 时，优先使用：

| 操作 | MCP 工具 |
|------|---------|
| 读文件 | `mcp__filesystem__read_file` 或原生 `read_file` |
| 写文件 | `mcp__filesystem__write_file` 或原生 `write_file` |
| 打开文件 | `mcp__editor__open_file` |
| 定位代码 | `mcp__editor__go_to_definition` |
| 搜索符号 | `mcp__editor__search_symbol` |
| 执行 VS Code 命令 | `mcp__vscode__execute_command` |

**MCP 配置模板**（添加到 `~/.nanobot/config.json` 的 `tools.mcp_servers`）：

```json
{
  "tools": {
    "mcp_servers": [
      {
        "name": "filesystem",
        "type": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "C:\\Users\\qianchen\\Desktop\\nanobot\\Kylopro-Nexus"]
      }
    ]
  }
}
```

## 第二优先：命令行（run_terminal）

对于大多数 IDE 操作，命令行足够：

| 需求 | 命令 |
|------|------|
| 打开 VS Code | `code .` 或 `code <file>` |
| 打开指定行 | `code -g <file>:<line>` |
| 安装 VS Code 扩展 | `code --install-extension <ext-id>` |
| 搜索代码 | `grep -r "pattern" .` 或 `Select-String` |
| 运行测试 | `python -m pytest tests/` |
| 格式化代码 | `black src/` 或 `ruff format` |
| Git 操作 | `git status`, `git diff`, `git log --oneline` |

## 第三优先：GUI Automation Bridge（兜底）

**只在以下情况使用：**

- 软件没有 API 或 CLI 接口
- 必须观察真实渲染界面
- 必须操作 IDE 内部 UI 元素（如自定义 dialog）

**接口规范**（由 IDE 订阅生成实现，Kylo 只调用）：

```bash
# 截图
python antigravity_bridge.py screenshot --output screenshot.png

# 点击坐标
python antigravity_bridge.py click --x 100 --y 200

# 输入文字
python antigravity_bridge.py type --text "hello"

# 查找元素（基于图像）
python antigravity_bridge.py find --template template.png

# 等待元素出现
python antigravity_bridge.py wait --template template.png --timeout 10
```

GUI bridge 文件：如存在，位于 `tools/antigravity_bridge.py`；不存在时先记录接口规范，不在对话中临时手写。

## 规则

- **不要把 GUI 自动化作为默认实现路径**
- MCP 或文件工具能完成的，不走视觉/RPA
- 如果只是读取/修改代码，优先 `read_file`/`write_file`
- GUI bridge 不存在时，记录需求但不在对话中临时生成低质量自动化代码
- 截图操作会消耗较多 token，仅在必要时使用

## 常见场景决策

| 场景 | 用什么 |
|------|--------|
| 读取 Kylopro-Nexus 下的代码 | `read_file`（原生工具） |
| 修改代码 | `write_file`（原生工具） |
| 在 VS Code 中打开文件 | `run_terminal`: `code -g file.py:42` |
| 搜索代码 | `run_terminal`: `Select-String` 或 grep |
| 安装 VS Code 插件 | `run_terminal`: `code --install-extension` |
| 操作 Cursor/Copilot chat | MCP IDE tools（需配置 MCP server） |
| 点击 GUI 按钮 | pyautogui bridge（最后手段） |