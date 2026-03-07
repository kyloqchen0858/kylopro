# 🤖 Kylopro-Nexus

**Kylopro-Nexus** 是一个基于 `nanobot-ai` 框架构建的高度自治数字分身（Digital Twin）系统。它集成了双核大脑路由、全境视觉 RPA、IDE 深度集成以及自主进化机制，旨在打造一个能够自我学习、自我实验并持续进化的 AI 代理。

---

## ✨ 核心特性

- **🧠 双核大脑路由**: 智能切换云端 DeepSeek (Reasoner/Chat) 与本地 Ollama，兼顾高智商与隐私。
- **👁️ 全境视觉 RPA**: 通过 OCR 和图像识别感知屏幕，像真人一样操作鼠标和键盘。
- **🛠️ IDE 深度集成**: 直接读写项目文件、执行终端命令，具备完整的代码开发能力。
- **🚀 自主进化引擎**: 主动研究 GitHub 前沿项目，自动生成优化提案并投入异步任务队列。
- **🧪 自主实验沙盒**: 在独立的实验环境中运行测试代码，验证逻辑后再部署到核心库。
- **📥 任务收件箱 (Task Inbox)**: 异步处理长达数小时的复杂开发任务。

---

## 🛠️ 快速开始

### 1. 环境准备
- Python 3.10+
- [Ollama](https://ollama.com/) (可选，用于本地运行)
- Windows 操作系统 (RPA 优化)

### 2. 初始化
```bash
git clone https://github.com/your-username/Kylopro-Nexus.git
cd Kylopro-Nexus
setup.bat
```

### 3. 配置
复制 `.env.example` 为 `.env` 并填入你的 API 密钥。

### 4. 运行
```bash
python -m core.engine
```

---

## 📂 项目结构

- `core/`: 系统核心（Provider, Engine, Tools）
- `skills/`: 模块化技能（RPA, IDE Bridge, Evolution, etc.）
- `data/`: 任务队列、实验沙盒与持久化数据
- `SOUL.md`: Kylopro 的核心宪法与行为准则

---

## 🐈 关于 Kylopro
Kylopro 不仅仅是一个 AI 助手，它是一个具备高度自治权的开发者。它的目标是实现“递归进化”，通过不断优化自己的代码来实现数字化生命的自我提升。

---

## ⚖️ 许可证
[MIT License](LICENSE)
