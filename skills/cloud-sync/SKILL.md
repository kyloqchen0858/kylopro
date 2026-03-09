---
name: cloud-sync
description: "云端同步技能：对 GitHub/REST 平台执行增量文件同步、批量删改、仓库维护；同步模式可扩展至 Notion / Freelancer / Linear 等平台"
---

# Cloud Sync 技能

## 核心能力（当前可用）

**GitHub REST API 同步**（无需 `gh` CLI，纯 Python `urllib.request` + token）：

| 操作 | 实现方式 |
|------|---------|
| 获取仓库完整文件树+SHA | `GET /git/trees/{branch}?recursive=1` |
| 上传新文件 | `PUT /contents/{path}` + base64 content |
| 更新已有文件（增量，跳过无变化） | `PUT /contents/{path}` + 旧 SHA |
| 删除文件 | `DELETE /contents/{path}` + SHA |
| 批量同步（删旧+上传新） | 先 GET tree → 算 diff → 批量 DELETE/PUT |

**已验证场景**：Kylopro-Nexus 全量同步到 `kyloqchen0858/kylopro`，共处理 123 个文件，自动清理 46 个废旧文件。

---

## 操作规范（GitHub 同步）

### 标准流程

```
1. GET tree（获取远程 SHA 映射）
2. 计算 diff（哪些要删、哪些要加、哪些要更新）
3. 向用户说明操作范围（删 N 个 / 上传 M 个）
4. 执行 DELETE → 等待 1s → 刷新 SHA → 执行 PUT
5. 验证：再次 GET tree，输出最终文件数
```

### 安全规则

- **每次 API 请求后 sleep 0.2s**，避免触发 GitHub secondary rate limit（100 请求/分钟）
- **不上传敏感文件**：`.env`（含真实密钥）、`venv/`、`__pycache__`、`.pyc`、私钥文件
- **允许上传 `.env.example`**（无实际密钥的模板文件）
- **删除操作需要说明**被删文件列表，不静默批量删
- **token 存储**：统一从 `brain/vault/.kylo_secrets.env` + `CredentialVault` 读取，不再读取桌面 txt，也不在回复中回显明文 token

### 默认排除目录（任何平台）

```
venv/, .venv/, node_modules/, __pycache__/, *.pyc
.env（非 .env.example）
data/, logs/, sessions/, tasks/, workspace/
```

---

## 如何执行同步任务

收到"把文件上传到 GitHub"类请求时：

1. **确认目标**：哪个仓库？哪些目录？（ask if unclear）
2. **读取本地文件树**（用 `run_terminal` 的 PowerShell Get-ChildItem）
3. **读取远程文件树**（GET tree API）
4. **展示 diff 摘要**：
   ```
   将删除：X 个文件（列出路径）
   将上传/更新：Y 个文件
   将保留不变：Z 个文件
   ```
5. **等主人确认**（删除操作需明确许可，P1 层）
6. **执行**（Python `urllib.request`，不依赖 `requests` 库）
7. **验收**：GET tree 验证最终状态

---

## 平台扩展性分析

### 核心模式（平台无关）

所有 REST 平台换汤不换药，核心步骤一致：

```
① 获取认证 token（一次性，存入 data/local_config.json）
② GET 远程状态（读取已有实体列表）
③ 计算 diff（本地意图 vs 远程现状）
④ DELETE / POST / PUT / PATCH（执行变更）
⑤ 验证
```

### 平台可行性矩阵

| 平台 | API 类型 | 认证 | 能做什么 | 可落地性 |
|------|---------|------|---------|---------|
| **GitHub** | REST v3 | Personal Token | 文件/Issue/PR/Release | ✅ **已落地** |
| **Notion** | REST v1 | Integration token | 页面/数据库/属性 | ✅ 可直接落地（token 1步获取）|
| **Linear** | GraphQL | API key | Issue/项目/里程碑 | ✅ 可直接落地 |
| **Trello** | REST | API key + token | 卡片/看板/列表 | ✅ 可直接落地 |
| **Freelancer** | REST v1 | OAuth2 / Dev token | 项目/竞标/里程碑 | ⚠️ 需 OAuth 或开发者 token |
| **Upwork** | GraphQL | OAuth2 RSA key | 合同/工单/消息 | ⚠️ OAuth2 复杂，需主人操作 |
| **GitHub Issues** | REST v3 | Personal Token（同上）| 读写 Issue/Label/Milestone | ✅ 可直接落地（token 已有）|

### Freelancer 具体可行性

**Freelancer REST API** (`https://www.freelancer.com/api/projects/0.1/`)：

```python
# 创建项目（需要 OAuth token 或 Developer token）
POST https://www.freelancer.com/api/projects/0.1/projects/
Authorization: Bearer {FREELANCER_TOKEN}
{
  "title": "Python 自动化脚本开发",
  "description": "...",
  "budget": {"minimum": 100, "maximum": 300, "currency_id": 1},
  "jobs": [{"name": "Python"}],
  "type": "FIXED"
}
```

**可落地，但有一个前置条件**：需要主人登录 Freelancer 开发者中心获取 token 或完成 OAuth 授权。一旦 token 到位，创建/查询/更新项目都能用同样的 `urllib.request` 模式实现。

---

## 进化方向（尚未落地）

### F1 — GitHub Issues 双向同步（最近优先）

**优先级**: 🟡 高价值  
**前置**: GitHub token 已有  
**能做什么**:

```python
# 从 DEVLOG.md 中提取 TODO → 自动创建 GitHub Issue
# Issue 关闭 → 同步标记 DEVLOG.md 对应条目为完成
# 按 Phase 自动打 Label（phase-10, enhancement, bug 等）
```

**实现思路**:
- `GET /repos/{owner}/{repo}/issues` — 读取已有 Issues
- `POST /repos/{owner}/{repo}/issues` — 创建新 Issue
- `PATCH /repos/{owner}/{repo}/issues/{n}` — 修改/关闭 Issue
- 解析 DEVLOG.md 中 `- [ ]` / `- [x]` 标记 → 对应 Issue open/closed

### F2 — Notion 项目看板同步

**优先级**: 🟡 高价值（主人如果用 Notion 管项目）  
**前置**: 主人提供 Notion Integration token + 目标 Database ID  
**能做什么**: 把 `tasks/` 子目录的任务文件同步成 Notion 数据库行，支持状态双向更新

### F3 — Freelancer / Upwork 项目发布助手

**优先级**: 🟢 按需  
**前置**: 主人提供 Freelancer Developer Token（在 developers.freelancer.com 申请）  
**能做什么**:
- 根据 DEVLOG.md 中待完成的技术任务，自动起草 Freelancer 项目描述
- `deep_think` 生成 requirements，`local_think` 校对，最后提交 API 创建项目
- 拉取竞标列表，汇总摘要推送给主人决策

### F4 — 多仓库自动 diff 监控

**优先级**: 🟢 可选  
**前置**: 无（token 已有）  
**能做什么**:
- 定时（每周）对比本地 nanobot/ vs 上游 `jjleng/nanobot` 的差异
- 自动识别 upstream 有没有新增工具类 / 修复 / breaking change
- 输出 diff 报告推送给主人（替代目前手动 `docs/reports/` 轮回）

---

## 代码模板（可复用）

```python
# ============================================
# 通用 REST 平台同步模板（urllib.request，无外部依赖）
# ============================================
import re, json, base64, urllib.request, urllib.error, time
from pathlib import Path

class PlatformSync:
    """平台无关的 REST 同步基类，子类只需实现 list_remote / delete / upsert"""

    def __init__(self, token: str, base_url: str):
        self.headers = {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': 'Kylopro-Agent',
        }
        self.base_url = base_url

    def _req(self, method: str, path: str, data: dict = None, timeout=15):
        url = f'{self.base_url}/{path.lstrip("/")}'
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=body, headers=self.headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read()) if r.length != 0 else {}
        except urllib.error.HTTPError as e:
            raise RuntimeError(f'HTTP {e.code}: {e.read()[:200].decode("utf-8","replace")}')

    # GitHub 子类实现示例：
    # def list_remote(self, repo): → GET /git/trees/main?recursive=1
    # def delete(self, path, sha, repo): → DELETE /contents/{path}
    # def upsert(self, path, content, sha, repo): → PUT /contents/{path}
```

---

## token 读取约定

Kylo 从标准位置读 token，**不接受在对话中直接粘贴 token**（防止日志泄露）：

```python
# GitHub token
from pathlib import Path
import re
tokens = re.findall(r'ghp_[a-zA-Z0-9]+', 
    (Path.home()/'Desktop'/'Kylo技能进化.txt').read_text(encoding='utf-8'))
github_token = tokens[1] if len(tokens) >= 2 else tokens[0]

# 其他平台 token（主人提供后存入此文件）
import json
local_cfg = json.loads((Path(__file__).parent.parent/'data'/'local_config.json')
                       .read_text(encoding='utf-8'))
notion_token = local_cfg.get('notion_token', '')
freelancer_token = local_cfg.get('freelancer_token', '')
```
