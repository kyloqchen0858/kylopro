---
name: oauth2-vault
description: "OAuth2 凭证保险箱 + 飞书集成：加密存储/刷新平台 token，创建飞书文档，发送飞书消息，结果回流大脑"
metadata: {"nanobot":{"always":true}}
---

# oauth2-vault — OAuth2 凭证管理与外部平台操作

## 技能描述

管理外部平台（飞书、Notion 等）的 OAuth2 凭证，提供：
- 加密存储（SQLite + Fernet / PBKDF2+HMAC stdlib fallback）
- 自动 token 刷新（提前 5 分钟检测过期）
- 飞书文档创建 + 消息通知一体化
- 每次执行结果自动写入 KyloBrain WARM episodes

## 核心安全规则

- **token 绝不出现在回复或 WARM 记忆正文中**：只显示脱敏摘要（前4***后4）
- 所有凭证存储在 `brain/vault/oauth2_credentials.db`（本机加密，不入 git）
- 密钥文件在 Windows 上设置隐藏属性保护
- 执行失败时给出 `need_reauth` 信号

## 工具一：`oauth2_vault` — 凭证管理

| action | 说明 | 必填参数 |
|--------|------|---------|
| `setup` | 配置平台凭证（首次必须执行） | `platform`, `app_id`, `app_secret` |
| `status` | 查看已配置平台和过期状态 | 无 |
| `get_token` | 获取有效 token（自动刷新，返回脱敏摘要） | `platform` |
| `delete` | 删除平台凭证 | `platform` |

setup 可选参数：`user_open_id`, `folder_token`, `chat_id`（飞书专用）

### 配置示例

```json
{
  "action": "setup",
  "platform": "feishu",
  "app_id": "cli_xxxx",
  "app_secret": "your_app_secret",
  "user_open_id": "ou_xxxx",
  "folder_token": "fldxxxx",
  "chat_id": "oc_xxxx"
}
```

## 工具二：`feishu` — 飞书文档与消息

| action | 说明 | 必填参数 |
|--------|------|---------|
| `create_doc` | 创建飞书文档并写入 Markdown 内容 | `title`, `content` |
| `send_message` | 发送飞书文本消息 | `text` |
| `status` | 检查飞书 token 状态 | 无 |

### `create_doc` 创建文档

```json
{
  "action": "create_doc",
  "title": "AI技术周报 2026-03-09",
  "content": "# 标题\n\n正文段落...\n\n## 二级标题\n\n- 列表项1\n- 列表项2\n\n---\n\n分割线下方内容",
  "notify": true
}
```

- `content`：支持简单 Markdown（# ## ### 标题，段落，--- 分割线，- 列表项）
- `notify`：创建后发飞书消息通知用户审阅（需配置 user_open_id 或 chat_id，默认 true）
- 返回：document_url、blocks_written、notified 状态

### `send_message` 发送消息

```json
{
  "action": "send_message",
  "text": "消息内容"
}
```

可选：`receive_id`（不填则使用 setup 时配置的 user_open_id）、`receive_id_type`（open_id/chat_id/user_id）

## 首次配置流程

```
Step 1: oauth2_vault(action="setup", platform="feishu", app_id="cli_xxx", app_secret="xxx")
Step 2: oauth2_vault(action="get_token", platform="feishu")  ← 验证 token 获取
Step 3: feishu(action="send_message", text="Hello from Kylo!")  ← 验证端到端
```

## 飞书企业自建应用获取凭据

1. `https://open.feishu.cn/app` → 创建企业自建应用
2. 应用凭证 → 复制 App ID 和 App Secret
3. 权限管理开启：`drive:drive`、`im:message:send_as_bot`、`docx:document`
4. 版本管理 → 发布应用
5. user_open_id：飞书管理后台成员管理中获取
6. folder_token：飞书云空间 URL 中 `folder/` 后的字符串

## 错误处理

| 错误 | 处理方式 |
|------|---------|
| `need_reauth: true` | 让用户重新 `setup` |
| 飞书 code=99991663 | app 未发布到企业 |
| 飞书 code=99991400 | app_id/app_secret 错误 |
| 网络超时 | 重试一次，仍失败报告 |

## 失败经验沉淀算法（输出侧）

每次 `feishu`/`oauth2_vault` 调用后，AuthMiddleware 会执行如下回流：

1. 记录 episode：`brain/warm/episodes.jsonl`
2. 生成失败签名：例如 `feishu.doc_api_404` / `feishu.auth_missing_or_expired`
3. 写入失败库：`brain/warm/failures.jsonl`，字段包括 `task/error/recovery`
4. 更新模式成功率：`brain/warm/patterns.jsonl` 中 `feishu:create_doc`、`feishu:send_message`
5. 把下一步建议注入输出：失败回复追加 `建议: ...`，直接给用户可执行动作

这样下一轮重启后，`kylobrain(pre_task)` 可以在执行前命中历史失败并提示规避方案，而不是从零开始试错。

## 重启防失忆要求

- 必须保证 `KYLOPRO_DIR` 指向当前 `Kylopro-Nexus` 根目录
- 即使未设置环境变量，模块也会回退到仓库根路径探测，不再默认漂移到 `~/Kylopro-Nexus`
- 启动建议统一使用 `start_gateway.bat` / `clean_restart_gateway.bat`

## 与 KyloBrain 集成

每次外部操作自动写入 WARM episodes：
- tags: `["oauth2", "feishu", "external_action"]`
- 包含成功/失败信号和执行时长
- outcome 截断为 200 字符，不含 token 明文
