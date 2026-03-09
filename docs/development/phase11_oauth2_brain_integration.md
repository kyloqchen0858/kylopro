# Phase 11 开发方案
## 从"被动响应"到"主动干活"— OAuth2 凭证体系 + 脑体闭环收口

> **写作时间**: 2026-03-09  
> **文件用途**: 存档到 `docs/development/phase11_oauth2_brain_integration.md`  
> **依赖文件**: DEVLOG.md Phase 10.2, `brain/vault/.kylo_secrets.env`, `skills/kylobrain/`

---

## 一、现状诊断（为什么卡住了）

### 真实问题不是算法太简单

Jaccard 和布隆过滤器确实轻量，但它们够用。问题是：**这些算法没有在真实任务里被调用**。

当前数据流：
```
用户消息 → BrainHooks → 注入HOT记忆到prompt → LLM → 工具调用 → 结果
                                                              ↑
                                              ← 这条回流路径 90% 是空的
```

具体断裂点：

| 断裂点 | 现状 | 应有状态 |
|--------|------|---------|
| screen 操作 → 大脑 | 执行完即丢弃 | ActionResult 写入 WARM episodes |
| skill_evolution 验证通过 → 大脑 | on_skill_verified() 一行钩子 | 失败率 + 经验反向喂给 skill_evolution |
| OAuth2 外部操作 → 大脑 | 不存在 | 每次 API 调用结果写入 WARM，累积操作经验 |
| 每次对话 → 自知层更新 | BrainHooks 已记录 episode | ✅ 已完成，这块是好的 |

### 根本原因：缺少一个"生产锚点"

大脑需要真实任务才能积累经验。目前 Kylo 大部分时间在和你聊开发计划，而不是真的操作外部系统、产生成功/失败记录、让大脑学习。

**OAuth2 集成是对的下一步**，原因：
1. 它是生产任务（真实操作 Notion/飞书/推特）
2. 每次操作都是一个自然的 episode（成功/失败/token过期自愈）
3. 使用已有的 CredentialVault（Phase 10.2 已建）
4. 强制脑体协同：大脑存 token → 执行层调用 → 结果回流大脑

---

## 二、Phase 11 架构：三件事同时收口

```
┌─────────────────────────────────────────────────────────────┐
│                    Phase 11 目标                             │
│                                                              │
│  ① OAuth2 凭证体系   → Kylo 能自主操作外部平台              │
│  ② 脑体回流闭环     → 每次执行结果自动进大脑                │
│  ③ 自知层启动更新   → 每次开机知道自己更新了什么            │
└─────────────────────────────────────────────────────────────┘
```

**不新增算法，不重写大脑，只做连线。**

---

## 三、OAuth2 凭证体系（硬记忆区）

### 3.1 两区记忆的分工

```
软记忆区（WARM/ChromaDB）                硬记忆区（CredentialVault）
──────────────────────                   ──────────────────────────
· 话术、卖点、想法碎片                   · access_token
· 任务执行历史（episodes）               · refresh_token
· 技能模式（patterns）                   · expires_at（时间戳）
· 按语义相似度检索                       · 按平台名精确查找
                                         · 加密存储，绝不出现在对话/记忆正文
```

### 3.2 文件结构

```
Kylopro-Nexus/
└── skills/
    └── oauth2_vault/
        ├── SKILL.md             ← nanobot 技能定义
        ├── __init__.py
        ├── vault.py             ← 凭证保险箱（SQLite + AES-256 加密）
        ├── auth_middleware.py   ← 授权中间件（自动刷新）
        └── platforms/
            ├── notion.py        ← Notion OAuth2 适配器
            ├── feishu.py        ← 飞书 OAuth2 适配器
            └── twitter.py       ← Twitter OAuth2 适配器（第二批）
```

### 3.3 vault.py — 凭证保险箱

```python
"""
凭证保险箱：SQLite + 加密存储
绝不把 token 写进 WARM/HOT/COLD 记忆正文
绝不在 Telegram 回复中显示 token 明文
"""
import sqlite3
import os
from pathlib import Path
from cryptography.fernet import Fernet
import json
import time

VAULT_DIR  = Path(os.environ.get("KYLOPRO_DIR",
    Path.home() / "Kylopro-Nexus")) / "brain" / "vault"
VAULT_DB   = VAULT_DIR / "credentials.db"
KEY_FILE   = VAULT_DIR / ".vault_key"  # 256-bit key，不入 git

class CredentialVault:
    """
    硬记忆区 — 平台凭证精确查找
    
    操作：
      store(platform, creds)   — 加密存储
      get(platform)            — 解密读取 + 自动检测是否过期
      delete(platform)         — 清除
      list_platforms()         — 只返回平台名，不返回 token
    """
    
    def __init__(self):
        VAULT_DIR.mkdir(parents=True, exist_ok=True)
        self._key  = self._load_or_create_key()
        self._fernet = Fernet(self._key)
        self._init_db()

    def _load_or_create_key(self) -> bytes:
        if KEY_FILE.exists():
            return KEY_FILE.read_bytes()
        key = Fernet.generate_key()
        KEY_FILE.write_bytes(key)
        KEY_FILE.chmod(0o600)  # 只有 owner 可读
        return key

    def _init_db(self):
        with sqlite3.connect(VAULT_DB) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS credentials (
                    platform     TEXT PRIMARY KEY,
                    encrypted    BLOB NOT NULL,
                    updated_at   REAL NOT NULL
                )
            """)

    def store(self, platform: str, creds: dict) -> None:
        """
        creds 标准格式：
        {
          "access_token":  "...",
          "refresh_token": "...",   # 可选
          "expires_at":    1234567890.0,  # Unix 时间戳
          "scope":         "...",   # 可选
          "token_type":    "Bearer"
        }
        """
        payload = json.dumps(creds).encode()
        encrypted = self._fernet.encrypt(payload)
        with sqlite3.connect(VAULT_DB) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO credentials (platform, encrypted, updated_at)
                VALUES (?, ?, ?)
            """, (platform, encrypted, time.time()))

    def get(self, platform: str) -> dict | None:
        with sqlite3.connect(VAULT_DB) as conn:
            row = conn.execute(
                "SELECT encrypted FROM credentials WHERE platform = ?",
                (platform,)
            ).fetchone()
        if not row:
            return None
        return json.loads(self._fernet.decrypt(row[0]).decode())

    def is_expired(self, platform: str, buffer_sec: int = 300) -> bool:
        """提前 5 分钟视为过期（给刷新留余量）"""
        creds = self.get(platform)
        if not creds:
            return True
        expires_at = creds.get("expires_at", 0)
        return time.time() + buffer_sec > expires_at

    def delete(self, platform: str) -> None:
        with sqlite3.connect(VAULT_DB) as conn:
            conn.execute("DELETE FROM credentials WHERE platform = ?", (platform,))

    def list_platforms(self) -> list[str]:
        """只返回平台名列表，绝不返回 token"""
        with sqlite3.connect(VAULT_DB) as conn:
            rows = conn.execute(
                "SELECT platform, updated_at FROM credentials"
            ).fetchall()
        return [{"platform": r[0], "updated_at": r[1],
                 "expired": self.is_expired(r[0])} for r in rows]
```

### 3.4 auth_middleware.py — 授权中间件（自动驾驶核心）

```python
"""
授权中间件：Kylo 调用任何外部 API 前的必经中间层

底层逻辑：
  1. 从 Vault 取 token
  2. 检查是否过期
  3. 过期 → 用 refresh_token 换新 token → 存回 Vault → 继续
  4. 调用结果写入大脑 WARM episodes（让大脑积累操作经验）
"""
import time
import urllib.request
import json
from typing import Callable, Any

class AuthMiddleware:
    
    def __init__(self, vault: "CredentialVault", warm_memory=None):
        self.vault = vault
        self._warm = warm_memory  # WarmMemory 实例，用于写回 episodes
        self._refreshers: dict[str, Callable] = {}
    
    def register_refresher(self, platform: str, fn: Callable) -> None:
        """注册各平台的 token 刷新函数"""
        self._refreshers[platform] = fn
    
    def get_valid_token(self, platform: str) -> str | None:
        """
        获取有效 token：
        - 未过期 → 直接返回
        - 已过期 → 自动刷新 → 返回新 token
        - 刷新失败 → 返回 None（让 Skill 告诉用户重新授权）
        """
        if self.vault.is_expired(platform):
            print(f"[AuthMiddleware] {platform} token 已过期，尝试自动刷新...")
            success = self._auto_refresh(platform)
            if not success:
                return None
        
        creds = self.vault.get(platform)
        return creds.get("access_token") if creds else None
    
    def _auto_refresh(self, platform: str) -> bool:
        creds = self.vault.get(platform)
        if not creds or "refresh_token" not in creds:
            return False
        
        refresher = self._refreshers.get(platform)
        if not refresher:
            return False
        
        try:
            new_creds = refresher(creds["refresh_token"])
            self.vault.store(platform, new_creds)
            print(f"[AuthMiddleware] {platform} token 刷新成功")
            
            # 写入大脑：记录一次成功的 token 刷新事件
            if self._warm:
                self._warm.record_episode(
                    task=f"{platform} OAuth2 token 自动刷新",
                    steps=["check_expiry", "call_refresh_endpoint", "store_new_token"],
                    outcome="刷新成功",
                    duration_sec=0,
                    success=True,
                    tags=["oauth2", "auto_refresh", platform],
                )
            return True
        except Exception as e:
            print(f"[AuthMiddleware] {platform} 刷新失败: {e}")
            return False
    
    def execute_with_auth(
        self, platform: str, task_name: str,
        fn: Callable[[str], Any],
    ) -> dict:
        """
        带授权的执行包装器。
        fn: 接受 access_token，返回执行结果
        """
        start = time.time()
        token = self.get_valid_token(platform)
        if not token:
            result = {
                "success": False,
                "error": f"{platform} 未授权或 token 已失效，需要重新授权",
                "need_reauth": True,
            }
        else:
            try:
                output = fn(token)
                result = {"success": True, "output": output}
            except Exception as e:
                result = {"success": False, "error": str(e)}
        
        duration = time.time() - start
        
        # 写入大脑 episodes（无论成功失败）
        if self._warm:
            self._warm.record_episode(
                task=f"{platform}: {task_name}",
                steps=["get_token", "execute"],
                outcome=str(result.get("output") or result.get("error", ""))[:200],
                duration_sec=duration,
                success=result["success"],
                tags=["oauth2", platform, "external_action"],
            )
        
        return result
```

### 3.5 平台适配器示例 — Notion

```python
"""
platforms/notion.py — Notion OAuth2 适配器
"""
import json
import urllib.request
import urllib.parse

NOTION_CLIENT_ID     = ""  # 从 vault 读，不硬编码
NOTION_CLIENT_SECRET = ""  # 从 vault 读，不硬编码
NOTION_TOKEN_URL     = "https://api.notion.com/v1/oauth/token"
NOTION_API_BASE      = "https://api.notion.com/v1"

def refresh_notion_token(refresh_token: str) -> dict:
    """用 refresh_token 换取新的 access_token"""
    import base64
    credentials = base64.b64encode(
        f"{NOTION_CLIENT_ID}:{NOTION_CLIENT_SECRET}".encode()
    ).decode()
    
    req = urllib.request.Request(
        NOTION_TOKEN_URL,
        method="POST",
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
        },
        data=json.dumps({
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }).encode(),
    )
    
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read().decode())
    
    import time
    return {
        "access_token":  data["access_token"],
        "refresh_token": data.get("refresh_token", refresh_token),  # Notion 可能不返回新 refresh
        "expires_at":    time.time() + data.get("expires_in", 3600),
        "token_type":    "Bearer",
        "scope":         data.get("scope", ""),
    }

def update_page(token: str, page_id: str, properties: dict) -> dict:
    """更新 Notion 页面属性"""
    req = urllib.request.Request(
        f"{NOTION_API_BASE}/pages/{page_id}",
        method="PATCH",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        },
        data=json.dumps({"properties": properties}).encode(),
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())

def append_block(token: str, block_id: str, children: list) -> dict:
    """在 Notion 块中追加内容"""
    req = urllib.request.Request(
        f"{NOTION_API_BASE}/blocks/{block_id}/children",
        method="PATCH",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        },
        data=json.dumps({"children": children}).encode(),
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())
```

---

## 四、脑体回流闭环（让大脑真正学习）

### 4.1 screen 操作回流（一处修改）

在 `core/kylopro_tools.py` 的 `ScreenTool._execute()` 末尾加三行：

```python
# 在 ScreenTool 每次执行后加入（已有工具，最小修改）
if self._warm and action not in ("screenshot",):  # 截图不记录
    self._warm.record_episode(
        task=f"screen:{action}",
        steps=[action],
        outcome=str(result)[:100],
        duration_sec=elapsed,
        success="error" not in str(result).lower(),
        tags=["screen", action],
    )
```

### 4.2 skill_evolution ↔ 大脑双向连接

**现状**：verifier.py 验证通过 → `on_skill_verified()` → 大脑记录成就（单向）

**Phase 11 新增**：大脑失败率分析 → 喂给 skill_evolution（反向）

在 `skills/skill_evolution/experiment.py` 的实验选题逻辑中读取大脑数据：

```python
# experiment.py 中新增（不修改现有逻辑，只在选题时参考）
def get_brain_suggested_experiments(warm_memory) -> list[dict]:
    """
    从大脑的失败记录里挖掘值得实验的改进方向
    这是 skill_evolution 和 brain 的双向连接
    """
    patterns = warm_memory.read_all("patterns")
    # 找出成功率 < 60% 且有足够样本的任务类型
    weak_skills = [
        p for p in patterns
        if p.get("success_rate", 1.0) < 0.6 and p.get("sample_count", 0) >= 3
    ]
    
    suggestions = []
    for skill in sorted(weak_skills, key=lambda x: x["success_rate"]):
        suggestions.append({
            "task_type":    skill["task_type"],
            "success_rate": skill["success_rate"],
            "sample_count": skill["sample_count"],
            "suggestion":   f"改进 {skill['task_type']} 技能（当前成功率 {skill['success_rate']:.0%}）",
            "priority":     "high" if skill["success_rate"] < 0.4 else "medium",
        })
    
    return suggestions
```

### 4.3 OAuth2 操作 → 自动成为大脑最有价值的 episodes

每次真实的外部操作（更新 Notion、发飞书消息、发推）都通过 `auth_middleware.execute_with_auth()` 执行，自动写入 WARM。这些 episodes 的质量远高于当前的对话记录，因为它们有：
- 明确的成功/失败信号
- 真实的持续时间
- 具体的操作类型

30 次真实操作后，大脑就有了足够数据做有意义的模式分析。

---

## 五、自知层启动更新（每次开机知道自己更新了什么）

### 5.1 问题

当前 Kylo 开机后通过 BrainHooks 注入 HOT 记忆，但 HOT 记忆没有"版本感"——它不知道上次开机到现在有什么改变。

### 5.2 方案：启动差分注入

在 `core/brain_hooks.py` 的 `install_brain_hooks()` 中加入启动快照对比：

```python
def _build_startup_diff() -> str:
    """
    对比当前 DEVLOG.md 最后 Phase 与上次启动记录
    如果有新 Phase，生成一段"今天的更新摘要"注入 prompt
    """
    state_file = BRAIN_DIR / ".last_boot_phase"
    
    # 读取 DEVLOG 最新 Phase 标题
    devlog = DEVLOG_FILE.read_text(encoding="utf-8") if DEVLOG_FILE.exists() else ""
    phases = re.findall(r"## (Phase [^\n]+)", devlog)
    current_phase = phases[0] if phases else "unknown"  # 最新在最前
    
    if state_file.exists():
        last_phase = state_file.read_text(encoding="utf-8").strip()
        if last_phase != current_phase:
            state_file.write_text(current_phase, encoding="utf-8")
            return f"[启动更新] 自上次运行以来有新的开发迭代：{current_phase}"
    
    state_file.write_text(current_phase, encoding="utf-8")
    return ""
```

这样每次 Kylo 启动，如果有新 Phase，它的 system prompt 里会自动出现一行更新提示，让 Kylo 意识到"我昨晚被更新了什么"。

---

## 六、实施顺序（最小代价）

### 第一步（1-2天）：OAuth2 凭证体系基础
```
新建 skills/oauth2_vault/vault.py          ← 凭证保险箱
新建 skills/oauth2_vault/auth_middleware.py ← 授权中间件
新建 skills/oauth2_vault/SKILL.md          ← nanobot 技能定义
手动录入第一个 token：飞书（你最常用）
```

验收：用 `vault.list_platforms()` 能看到飞书，`get_valid_token("feishu")` 能返回有效 token。

### 第二步（1天）：脑体回流接线
```
修改 core/kylopro_tools.py  ← ScreenTool 3行回流代码
修改 skills/skill_evolution/experiment.py ← 读取大脑失败率
```

验收：做一次 screen 操作，`warm_memory.read_recent("episodes", days=1)` 能看到这条记录。

### 第三步（2-3天）：第一个真实外部技能
```
新建 skills/oauth2_vault/platforms/feishu.py  ← 飞书适配器
修改 skills/feishu/SKILL.md                   ← 引用 AuthMiddleware
```

验收：让 Kylo 发一条飞书消息，不需要你手动 token，Kylo 自己从 Vault 取，失败时自动刷新。

### 第四步（1天）：启动差分
```
修改 core/brain_hooks.py ← 加 _build_startup_diff()
```

验收：改一下 DEVLOG，重启 gateway，Kylo 的第一条 system prompt 里包含"启动更新"提示。

---

## 七、后续平台扩展计划

| 平台 | 优先级 | 难度 | 说明 |
|------|--------|------|------|
| 飞书 | P0 | ⭐⭐ | 你最常用，文档清晰，nanobot 已有 channel |
| Notion | P0 | ⭐⭐ | 知识管理，高价值 |
| Twitter/X | P1 | ⭐⭐⭐ | API v2 需要 OAuth2 PKCE |
| 小红书 | P2 | ⭐⭐⭐⭐ | 官方 API 受限，需要非官方方案或审批 |
| 微信公众号 | P2 | ⭐⭐⭐⭐ | 服务号需企业资质，订阅号受限 |
| Instagram | P2 | ⭐⭐⭐ | Meta Graph API，需要 Facebook App |

**先做飞书 + Notion，让 Kylo 在你最常用的平台上真正开始干活，积累 100 次真实操作后，大脑就有足够的经验数据了。**

---

## 八、关于"算法太简单"

问题不在算法，在于没有足够的真实数据喂进去。

Jaccard 在 100 条 episodes 时表现和向量检索差不多（数据量太小时语义检索反而噪音更多）。等 Kylo 完成 500+ 次真实外部操作，WARM 里有了密集的数据，这时候再评估是否需要替换 Jaccard 才有意义。

现阶段的正确优先级：**让大脑有数据 > 让算法更复杂**。

---

## 九、文件修改汇总

| 文件 | 操作 | 说明 |
|------|------|------|
| `skills/oauth2_vault/vault.py` | 新建 | 凭证保险箱 |
| `skills/oauth2_vault/auth_middleware.py` | 新建 | 授权中间件 + episode 回流 |
| `skills/oauth2_vault/platforms/feishu.py` | 新建 | 飞书适配器 |
| `skills/oauth2_vault/platforms/notion.py` | 新建 | Notion 适配器 |
| `skills/oauth2_vault/SKILL.md` | 新建 | nanobot 技能定义 |
| `core/kylopro_tools.py` | 修改（+3行）| ScreenTool 执行结果回流 |
| `skills/skill_evolution/experiment.py` | 修改（+20行）| 读取大脑失败率指导实验方向 |
| `core/brain_hooks.py` | 修改（+30行）| 启动差分注入 |
| `DEVELOPMENT_ROADMAP.md` | 修改 | 增加 Phase 11 进行中状态 |

**不修改 nanobot 核心文件，不修改 cloud_brain.py，只做连线。**

---

> **核心原则重申**：大脑和身体都不能脱离骨架（nanobot gateway）。
> 所有新增功能必须通过 SKILL.md + Tool 注册方式接入，不绕过 AgentLoop。
> 凭证只进 `brain/vault/credentials.db`，绝不出现在 WARM/HOT/COLD 记忆正文和任何对话输出。
