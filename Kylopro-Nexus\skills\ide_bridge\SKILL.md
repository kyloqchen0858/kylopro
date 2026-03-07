---
name: ide_bridge
description: 连接 IDE（Antigravity/Trae/VSCode），读写代码文件，运行命令，让 Kylopro 拥有 IDE 能力
always: false
---

# 🌟 Kylopro 新技能：[代码神经元 (Code Neuron)]

## ⚙️ 这个技能能做什么？

把 Kylopro 变成一个真正的**编程助手**，不依赖任何 IDE：
- 直接读写项目的任意代码文件
- 在项目目录执行命令（测试、构建、运行）
- 通过 MCP 协议与 Antigravity / Trae 通信，作为"第二大脑"协作
- 用 Vision RPA 操控 IDE 界面（点击按钮、读取错误信息）

## 🧩 三层接入方式

### 层 1：文件系统直读（最直接，零依赖）
直接读写代码文件 + 运行 shell 命令。
Kylopro = 你的代码编辑器，不需要开 IDE。

### 层 2：MCP 协议对接（最优雅）
Antigravity 和很多现代 IDE/工具暴露 MCP Server。
Kylopro 作为 MCP Client 连接，获得：
- Workspace 文件树扫描
- 语法检查结果
- 调试信息读取

### 层 3：Vision RPA 接管（覆盖一切）
当层1/层2不够用时，直接截图 → OCR → 点击 IDE 界面。
适合操控没有 API 的老旧软件。

## 💡 指挥官，你学到了什么？

IDE 只是一个"文件编辑 + 命令运行"的外壳。
Kylopro 可以做同样的事，而且做得更智能：
- 她能**理解代码**，不只是显示它
- 她能**主动发现问题**，不等你按 F5
- 她能**跨工具操作**，不被任何一个 IDE 锁定

## 使用方法

```python
from skills.ide_bridge.bridge import IDEBridge

bridge = IDEBridge(workspace="c:/Users/qianchen/Desktop/MyProject")

# 读取文件结构
tree = await bridge.get_file_tree()

# 读取文件内容
code = await bridge.read_file("src/main.py")

# 写入/修改代码
await bridge.write_file("src/main.py", new_code)

# 运行命令（测试/构建）
result = await bridge.run_command("python -m pytest tests/")

# MCP 连接 Antigravity
await bridge.connect_mcp("http://localhost:8765")
```
