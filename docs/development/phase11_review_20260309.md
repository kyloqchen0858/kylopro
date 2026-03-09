# Kylopro × OpenClaw 架构审查
## OAuth2 代码评估 · 全局开发观重置 · Phase 11+ 核心路线图

> **日期**：2026-03-09  
> **存档路径**：`docs/development/phase11_review_20260309.md`  
> **依赖**：DEVLOG.md Phase 10.2、`skills/oauth2_vault/`、`skills/kylobrain/`

---

## 一、OAuth2 实现评审

### 1.1 整体评分

| 模块 | 完成度 | 质量 | 与大脑的结合度 | 综合 |
|------|--------|------|---------------|------|
| `vault.py`（凭证保险箱） | ✅ 良好 | ✅ 良好 | ⚠️ 待改进 | 80 / 100 |
| `auth_middleware.py`（授权中间件） | ⚠️ 待改进 | ⚠️ 待改进 | ⚠️ 待改进 | 60 / 100 |
| `platforms/feishu.py` | ⚠️ 待改进 | ⚠️ 待改进 | ❌ 缺失 | 45 / 100 |
| `SKILL.md`（nanobot 接入） | ❌ 缺失 | ❌ 缺失 | ❌ 缺失 | 20 / 100 |
| episode 回流到 WARM | ❌ 缺失 | ❌ 缺失 | ❌ 缺失 | 0 / 100 |

---

### 1.2 vault.py — 做对了的部分

- **Fernet 对称加密 + SQLite 存储**：设计方向正确，比明文 JSON 安全 100 倍
- **`KEY_FILE.chmod(0o600)`**：Windows 上不生效，但意图正确，Linux/Mac 有效
- **`is_expired()` 提前 5 分钟缓冲**：细节到位，给 refresh 留了余量
- **`list_platforms()` 只返回平台名不返回 token**：安全意识很好

---

### 1.3 vault.py — 三个必须修复的问题

#### 问题 1：KEY_FILE 在 Windows 上无保护

`.vault_key` 是整个加密体系的根密钥，但在 Windows 上 `chmod(0o600)` 静默失败，任何进程都能读取它。

```python
# 当前（Windows 上无效）
KEY_FILE.write_bytes(key)
KEY_FILE.chmod(0o600)  # Windows 静默失败

# 修复：Windows 用 attrib 隐藏文件
import platform
if platform.system() == 'Windows':
    import subprocess
    subprocess.run(['attrib', '+H', str(KEY_FILE)], check=False)
else:
    KEY_FILE.chmod(0o600)
```

> 长期方案：Windows 上用 DPAPI（`win32crypt`）做系统级加密，密钥只对当前 Windows 用户可解密。

---

#### 问题 2：SQLite 没开 WAL 模式

nanobot 是异步多任务的，BrainHooks 的 episode 回流和 OAuth2 操作可能同时写 DB，会产生 `OperationalError: database is locked`。

```python
# 修复：在 _init_db() 里加两行
def _init_db(self):
    with sqlite3.connect(VAULT_DB) as conn:
        conn.execute('PRAGMA journal_mode=WAL')       # 允许并发读写
        conn.execute('PRAGMA synchronous=NORMAL')     # 性能和安全的平衡
        conn.execute("""
            CREATE TABLE IF NOT EXISTS credentials (...)
        """)
```

---

#### 问题 3：`cryptography` 包违反零额外依赖原则

你的一贯原则是 stdlib only。`Fernet` 来自 `cryptography` 包，需要额外安装。两个选项：

**选项 A（推荐）**：用 Python 3.10+ 自带的 `hashlib` + `secrets` 实现简化版加密，stdlib only

```python
import hashlib, secrets, hmac, base64

def _encrypt(self, data: bytes) -> bytes:
    """用 PBKDF2 + XOR 流加密，stdlib only"""
    salt   = secrets.token_bytes(16)
    key    = hashlib.pbkdf2_hmac('sha256', self._master_key, salt, 100_000)
    nonce  = secrets.token_bytes(16)
    stream = hashlib.pbkdf2_hmac('sha256', key, nonce, 1, dklen=len(data))
    ct     = bytes(a ^ b for a, b in zip(data, stream))
    mac    = hmac.new(key, salt + nonce + ct, 'sha256').digest()
    return base64.b64encode(salt + nonce + mac + ct)
```

**选项 B**：接受 `cryptography` 依赖，加入 `requirements.txt`，文档里明确标注这是保险箱的唯一外部依赖（推荐标注注释 `# vault only`）。

---

### 1.4 auth_middleware.py — 核心缺失：没有接入 WarmMemory

设计方案里 `auth_middleware` 的最关键价值是：**每次 OAuth2 操作自动写入 WARM episodes，让大脑积累真实外部操作经验**。但当前 `self._warm` 是可选参数且没有在 `tools_init.py` 里传入真实的 WarmMemory 实例。

```python
# 当前（大脑学不到任何东西）
class AuthMiddleware:
    def __init__(self, vault, warm_memory=None):  # None = 无效
        self._warm = warm_memory
```

```python
# 正确做法：在 tools_init.py 里显式接线
from skills.kylobrain.cloud_brain import MetaCogEngine
from skills.oauth2_vault.auth_middleware import AuthMiddleware
from skills.oauth2_vault.vault import CredentialVault

_vault = CredentialVault()
_brain = MetaCogEngine()
_auth  = AuthMiddleware(_vault, warm_memory=_brain.warm)  # 接通！
```

---

### 1.5 最重要的缺口：OAuth2 工具还没注册进 nanobot

目前 `oauth2_vault` 是一堆 Python 文件，但**没有 SKILL.md**，Kylo 不知道自己有这些能力，也无法通过工具调用来触发 OAuth2 操作。这是 Phase 11 最优先要补的。

需要在 `SKILL.md` 里定义至少三个工具：

- **`oauth2_status`** — 查看当前已授权的平台和 token 过期状态
- **`oauth2_action`** — 用授权身份在目标平台执行操作（传入 `platform + action + params`）
- **`oauth2_setup`** — 引导用户完成首次 OAuth2 授权流程

---

## 二、OpenClaw 架构分析 — 哪些值得吸收

OpenClaw 用 8 周从 0 到 196k+ stars，不是因为技术多高深，是因为它把 agent 做成了「**运维问题而非 prompt 工程问题**」。

| OpenClaw 设计 | Kylopro 当前状态 | 吸收价值 | 难度 |
|---------------|------------------|----------|------|
| 插件四槽：Channel/Memory/Tool/Provider | 工具注册分散在 `kylopro_tools.py` | ⭐⭐⭐⭐ | 中 |
| Session 压缩（Context Compaction） | 无，上下文会爆 | ⭐⭐⭐⭐⭐ | 中 |
| 凭证系统与记忆完全隔离 | CredentialVault 已建但未隔离 | ⭐⭐⭐⭐ | 低 |
| Tool Sandboxing（工具权限层级） | P0/P1/P2 层级有但无代码执行约束 | ⭐⭐⭐ | 中 |
| Plugin 自动发现（package.json 声明） | 无，手动 import 注册 | ⭐⭐ | 高 |
| 多 Agent 路由（A2A 通信协议） | SubAgent 已有，无消息路由协议 | ⭐⭐ | 高 |
| Memory 向量索引（SQLite + 嵌入） | Jaccard + ChromaDB 待接 | ⭐⭐⭐ | 低（已安装） |
| 启动差分（自知更新） | 未实现 | ⭐⭐⭐⭐ | 低 |

---

### 2.1 最值得立刻吸收：Session 压缩

这是 OpenClaw 最被低估的设计。nanobot 目前把完整对话历史存 JSONL，当 Telegram 会话累积到几千轮，context 会超 token 限制。

OpenClaw 的做法是定期把历史压缩成摘要，老对话不丢失但体积缩减 90%。

**Kylopro 的实现路径：**

```
1. BrainHooks 定时任务 → 触发 compress_old_sessions()
2. L0（qwen2.5:7b）本地跑压缩 → 零 API 成本
3. 压缩摘要存进 WARM → 原文归档到 COLD（GitHub Gist）
```

这不需要改 nanobot 核心，只需在 `brain_hooks.py` 加一个 cron 任务。

---

### 2.2 值得吸收：Tool Policy 代码执行约束

OpenClaw 的 tool sandboxing 不只是文档层面的权限描述，它在代码里有**真实的执行检查**：工具调用前查 session policy，不符合就拒绝并返回原因。

Kylopro 的 P0/P1/P2 目前只在 AGENTS.md 里，模型自觉遵守，没有代码层面的 hard block。

```python
# 建议在 kylopro_tools.py 的工具执行函数开头加
TOOL_POLICY = {
    "screen": {"click": "P1", "type": "P1", "screenshot": "P0"},
    "oauth2": {"action": "P1", "setup": "P1", "status": "P0"},
}

def policy_check(tool_name: str, action: str, session) -> tuple[bool, str]:
    level = TOOL_POLICY.get(tool_name, {}).get(action, "P2")
    if level == "P2" and not session.p2_granted:
        return False, f"{tool_name}.{action} 需要 P2 授权，请先说「我知道风险，允许你…」"
    if level == "P1" and not session.p1_granted:
        return False, f"{tool_name}.{action} 需要 P1 授权，请先说「允许/可以」"
    return True, ""
```

---

### 2.3 值得吸收但不急：技能自动发现

OpenClaw 用 `package.json` 的 `openclaw.extensions` 字段做插件自动发现，无需手动注册。Kylopro 现在规模不需要这个复杂度，但有一个**简化版**值得做：

在 `skills/` 里约定 `manifest.json`，让 `tools_init.py` 自动扫描所有有 `manifest.json` 的子目录并注册工具，不再需要手动 import 每个技能。

---

### 2.4 不要照搬的

- **全 TypeScript 技术栈**：OpenClaw 核心是 TypeScript/Node.js，切换语言栈的成本远大于收益，保持 Python 生态。
- **macOS 专属能力**（iMessage、菜单栏 App）：你在 Windows 上运行，这些直接跳过。
- **Docker 多容器沙箱**：OpenClaw 为工具执行做了 Docker 隔离，在你的场景里过度工程化。

---

## 三、全局开发观重置

### 3.1 根本问题的最终诊断

你自己说得很准：开发和生产脱节。背后有一个更深层的原因：

> **「系统做得越复杂，越难判断它是否真的在工作」**

大脑有三层记忆、四个算法、两个 Hook——但没有一个仪表盘能告诉你：Kylo 今天比昨天更聪明了吗？能做到以前做不到的事了吗？

OpenClaw 成功的核心不是技术，是它非常清楚地回答了一个问题：「这个东西能干什么？」然后真的让它去干。

---

### 3.2 新的全局开发原则（5 条）

#### 原则一：以任务为锚，不以技术为锚

每个开发 Phase 必须以「Kylo 能完成 X 任务」作为验收标准，而不是「X 模块实现了 Y 功能」。

- ❌ 错：「BrainHooks 成功把 HOT 记忆注入 prompt」
- ✅ 对：「Kylo 今天能在 Notion 里更新项目路线图，不需要我手动 token」

#### 原则二：生产优先，研发跟随

先让 Kylo 真实完成 10 次外部任务，再回来优化算法和架构。大脑需要真实数据，不是测试数据。

- 接下来 2 周的目标：飞书发消息 ✅、Notion 更新页面 ✅、推特发帖 ✅
- 这 30 次真实操作的 episodes 比重新设计算法更有价值

#### 原则三：大脑和身体都不能脱离骨架

所有能力必须通过 nanobot 骨架暴露：`SKILL.md` 定义 → `Tool` 注册 → `AgentLoop` 调用。不能绕过这个链路，即使是「临时测试」也不行。

原因：**绕过骨架的能力不会被 episode 记录，大脑学不到东西。**

#### 原则四：每次开机必须有认知更新

Kylo 每次启动时应该知道：「我上次更新了什么，今天能做什么新事情」。实现成本：30 行代码的启动差分注入（`brain_hooks.py` 对比 DEVLOG 最新 Phase）。

#### 原则五：凭证是硬边界，记忆是软边界

任何 token、密钥、API key 只进 `CredentialVault`，绝不出现在 WARM/HOT/COLD 正文、Telegram 消息、任何日志文件。这条规则需要在代码层面有对应的 guard，不能只靠模型自觉。

---

### 3.3 能力分层图（当前状态）

| 层级 | 组件 | 状态 | 下一步 |
|------|------|------|--------|
| L0 本地脑 | qwen2.5:7b via OllamaProvider | ✅ 已就绪 | 用于 session 压缩 |
| L1 主力 | deepseek-chat（日常/工具调用） | ✅ 已就绪 | 维持现状 |
| L2 深度 | deepseek-reasoner（via deep_think） | ✅ 已就绪 | 维持现状 |
| L3 备用 | minimax（429 fallback） | ✅ 已就绪 | 维持现状 |
| 大脑 HOT | MEMORY.md（最近 5 条） | ✅ 已就绪 | 加启动差分 |
| 大脑 WARM | JSONL + Jaccard + ChromaDB | ⚠️ 待改进 | 接入 episode 回流 |
| 大脑 COLD | GitHub Gist | ⚠️ 待改进 | 填入 GITHUB_TOKEN |
| 凭证保险箱 | CredentialVault（SQLite + Fernet） | ⚠️ 待改进 | 修复 3 个 bug |
| 授权中间件 | AuthMiddleware | ⚠️ 待改进 | 接入 WarmMemory |
| 外部技能 | 飞书 / Notion / Twitter | ❌ 缺失 | Phase 11 核心目标 |
| 工具注册 | oauth2_vault/SKILL.md | ❌ 缺失 | 最高优先级 |
| Session 压缩 | Context Compaction | ❌ 缺失 | Phase 12 |
| 启动差分 | boot diff injection | ❌ 缺失 | 3 天内可做 |

---

## 四、Phase 11 精修路线（2 周内完成）

### 第一周：让 Kylo 真正能用 OAuth2 干活

| 任务 | 文件 | 工时 | 验收标准 |
|------|------|------|---------|
| 修复 vault.py 3 个 bug | `skills/oauth2_vault/vault.py` | 半天 | `test_vault.py` 全通过 |
| 补 SKILL.md | `skills/oauth2_vault/SKILL.md` | 半天 | Kylo 能调用 `oauth2_status` |
| 接入 WarmMemory | `auth_middleware.py` + `tools_init.py` | 1 天 | 操作后 WARM 有 episode |
| 飞书 token 录入 | vault CLI 或手动脚本 | 1 小时 | `oauth2_status` 显示飞书已授权 |
| 第一次真实飞书发消息 | `tools_init.py` 注册飞书工具 | 1 天 | Kylo 通过 Telegram 命令发飞书 |
| 启动差分注入 | `core/brain_hooks.py` | 半天 | 重启后 prompt 里有更新提示 |

### 第二周：Notion 接入 + 脑体回流验证

| 任务 | 文件 | 工时 | 验收标准 |
|------|------|------|---------|
| Notion OAuth2 适配器 | `platforms/notion.py` | 1 天 | 能读写指定 Notion 页面 |
| screen 操作回流 | `core/kylopro_tools.py`（3 行） | 2 小时 | screen click 后 WARM 有记录 |
| skill_evolution 读大脑失败率 | `skill_evolution/experiment.py` | 半天 | 有 3 条失败记录时建议实验 |
| COLD 层激活 | 填 `GITHUB_TOKEN` env | 30 分钟 | `brain/cloud_config.json` 有 gist_id |
| 验证真实任务回流 | Telegram → Notion 更新 | — | WARM 里能看到 episode |

---

### Phase 12 预告（3-4 周后）

- **Session 压缩（Context Compaction）**：L0 本地跑，zero cost，解决上下文爆炸
- **Tool Policy 代码执行约束**：`policy_check()` 函数，P0/P1/P2 有 hard block
- **Twitter OAuth2 接入**：PKCE 流程，稍复杂
- **技能自动发现**：扫 `skills/*/manifest.json` 自动注册
- **第一次「Kylo 主动建议改进自身」验证**：基于 30+ episodes 的模式分析

---

## 五、一句话结论

> OAuth2 基础设计方向正确，但还没接通。修 3 个 bug + 补 `SKILL.md` + 接入 `WarmMemory`，这周内 Kylo 就能发第一条真正的飞书消息，大脑也开始学习。
>
> OpenClaw 最值得学的不是代码，是「**任务完成才算验收**」的产品观。
