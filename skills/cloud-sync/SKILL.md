---
name: cloud-sync
description: "云端同步技能：优先用 Git 原生工作流安全推送 GitHub 仓库；必要时再走 REST API 增量同步，模式可扩展至 Notion / Freelancer / Linear 等平台"
---

# Cloud Sync 技能

## 核心能力（当前可用）

### 模式 A：Git 原生推送（当前默认推荐）

当目标本身已经是一个 Git 仓库时，**优先使用 Git 原生流程**，不要先走 REST 全量覆盖。

适用场景：
- 工作区本地已有 `.git/`
- 需要保留提交历史、分支、PR、冲突信息
- 需要区分顶层仓库和嵌套仓库

标准动作：

| 操作 | 推荐命令 / 规则 |
|------|----------------|
| 识别仓库边界 | `git rev-parse --show-toplevel` |
| 检查是否嵌套仓库 | 发现子目录内存在独立 `.git/` 时，必须分仓处理 |
| 检查远端 | `git remote -v` |
| 检查范围 | `git status --short` + `git diff --stat` |
| 精准纳入文件 | 只 `git add` 明确筛过的源码/文档/测试 |
| 本地提交 | 小而明确的 commit message |
| 安全推送 | 先推 `sync-YYYYMMDD-*` 分支，再走 PR 合并 |

### 模式 B：GitHub REST API 同步

**GitHub REST API 同步**（无需 `gh` CLI，纯 Python `urllib.request` + token）：

| 操作 | 实现方式 |
|------|---------|
| 获取仓库完整文件树+SHA | `GET /git/trees/{branch}?recursive=1` |
| 上传新文件 | `PUT /contents/{path}` + base64 content |
| 更新已有文件（增量，跳过无变化） | `PUT /contents/{path}` + 旧 SHA |
| 删除文件 | `DELETE /contents/{path}` + SHA |
| 批量同步（删旧+上传新） | 先 GET tree → 算 diff → 批量 DELETE/PUT |

**已验证场景**：Kylopro-Nexus 全量同步到 `kyloqchen0858/kylopro`，共处理 123 个文件，自动清理 46 个废旧文件。

**当前经验修正**：
- 对已有 Git 仓库，REST 模式只适合作为补充同步，不再作为默认上传方式
- 对双仓库结构（例如顶层仓库 + `Kylopro-Nexus/` 嵌套仓库），REST 全量同步容易误伤边界，优先走 Git 分仓提交

---

## 操作规范（Git 原生推送）

### 标准流程

```
1. 识别仓库根目录（git rev-parse --show-toplevel）
2. 检查是否存在嵌套仓库；有则分别处理
3. 检查远端（git remote -v）与当前分支（git branch --show-current）
4. 检查 working tree（git status --short, git diff --stat）
5. 只 stage 明确要上传的文件，不要 git add .
6. 提交前做密钥扫描和忽略规则检查
7. 先推到安全分支 `sync-YYYYMMDD-<topic>`
8. 成功后输出 PR 链接和 merge 建议
```

### 安全规则

- **已有 Git 仓库时，默认不用 REST 覆盖式同步**
- **发现嵌套仓库时必须分开提交和推送**，不能把子仓库内容混进父仓库
- **不要盲目 `git add .`**，只添加经过筛选的源码、文档、测试
- **优先推送到安全分支，不直接覆盖 `main`**
- 如果 `main` 推送被拒绝（non-fast-forward），**不要强推**；改为新建分支推送并走 PR
- 如果仓库 `origin` 无效或不存在，先检查其他可用远端；必要时推到可访问远端的新分支并明确告知用户
- 推送前必须确认 `.env`、`brain/`、`data/`、`logs/`、`tasks/`、`output/` 等未被 stage
- 必须先做一次密钥扫描，重点检查 `api_key`、`app_secret`、`GITHUB_TOKEN`、`sk-`、私钥头

### 合并回 `main` 的建议路径

#### 情况 1：远端 `main` 比本地新

```
1. fetch 远端 main
2. 比较 `remote/main...safe-branch`
3. 如果只是本轮新提交，优先走 PR
4. 如需手工落地，使用 cherry-pick 本轮 commit，而不是整支强推
```

#### 情况 2：本地仓库历史与远端主线差异很大

- 不直接推本地 `main`
- 只把本轮整理出的 commit 推到安全分支
- 在 PR 描述里明确：本次只包含哪几个 commit、哪些文件范围、哪些本地文件故意未上传

#### 情况 3：双仓库结构

- 顶层仓库和嵌套仓库分别出 PR
- 不在父仓库 PR 里描述子仓库源码细节，反之亦然

---

## 操作规范（GitHub REST 同步）

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
- **token 存储**：统一从 `CredentialVault`、本地安全环境变量或专用 secrets 文件读取，不再读取桌面 txt，也不在回复中回显明文 token

### 默认排除目录（任何平台）

```
venv/, .venv/, node_modules/, __pycache__/, *.pyc
.env（非 .env.example）
data/, logs/, sessions/, tasks/, workspace/, output/, brain/
```

---

## 如何执行同步任务

收到"把文件上传到 GitHub"类请求时：

1. **先判断模式**：目标是 Git 仓库，还是仅能走 REST API 的远端目录镜像
2. **确认目标**：哪个仓库？哪个远端？哪些目录？是否存在嵌套仓库
3. **本地检查**：`git status --short`、`git diff --stat`、忽略规则、敏感文件范围
4. **展示摘要**：
    ```
    将提交：X 个源码/文档文件
    将排除：Y 个本地运行态/密钥/日志文件
    将推送到：safe branch 或 main
    ```
5. **如果 main 有风险**：改推 `sync-YYYYMMDD-*` 分支
6. **执行**：
    - Git 模式：`git add` → `git commit` → `git push remote HEAD:refs/heads/<safe-branch>`
    - REST 模式：GET tree → diff → DELETE/PUT
7. **验收**：输出 commit、branch、PR 链接或远端最终状态

### 最近两次真实经验（2026-03-10）

#### 经验 1：双仓库边界必须先认清

- 顶层 `nanobot/` 和 `Kylopro-Nexus/` 是两个独立 Git 仓库
- 推 GitHub 前必须先看各自 `git remote -v` 和 `git status`
- 父仓库需要忽略子仓库目录，子仓库需要忽略本地运行态目录

#### 经验 2：`main` 被拒绝时改推安全分支

- 远端 `main` 已领先时，不能硬推覆盖
- 正确做法：把本轮 commit 推到 `sync-YYYYMMDD-*` 新分支
- 输出 PR 链接给用户，由用户决定如何合并

#### 经验 3：远端失效要自动降级

- 如果仓库 `origin` 不存在或报 `Repository not found`，先检查其他远端
- 找到可访问远端后，仍然优先推安全分支，不假装已经完成主线合并

#### 经验 4：本地调试文件默认不上传

- `debug_*.py`、`diagnostic_*.py`、一次性测试脚本先留本地
- 除非它们已经升格为正式测试或文档，否则不纳入同步范围

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

Kylo 从标准安全位置读 token，**不接受在对话中直接粘贴 token**（防止日志泄露）：

```python
# GitHub token: 优先从 CredentialVault 或环境变量读取
import os

github_token = os.environ.get('GITHUB_TOKEN', '')

# 其他平台 token: 同样优先走保险箱或本地安全环境变量
notion_token = os.environ.get('NOTION_TOKEN', '')
freelancer_token = os.environ.get('FREELANCER_TOKEN', '')
```

如果环境变量为空：
- 优先去 `CredentialVault` 查对应平台凭证
- 其次读取本地专用 secrets 文件
- 不再从桌面 txt、聊天记录、普通文档中提取 token

---

## 对 GitHub 推送类请求的默认回答模板

```
已检查仓库边界与远端状态。

本次会：
1. 只提交筛过的源码/文档/测试
2. 排除 .env、brain、data、logs、tasks、output 等本地运行态内容
3. 先推到安全分支，再给出 PR 链接

如果远端 main 有新提交，不会强推覆盖。
```
