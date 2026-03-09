---
name: oauth2_vault
description: "OAuth2 凭证保险箱 + 飞书集成操作：存储/刷新平台 token，创建飞书文档，发送飞书消息"
metadata: {"nanobot":{"always":false}}
---

# oauth2_vault — OAuth2 凭证保险箱技能

## 技能描述

管理外部平台（飞书、Notion 等）的 OAuth2 凭证，提供：
- 加密存储（SQLite + Fernet AES-256）
- 自动 token 刷新（提前 5 分钟检测过期）
- 飞书文档创建 + 消息通知一体化
- 每次执行结果自动写入 KyloBrain WARM episodes

## 核心原则

- **token 绝不出现在回复或 WARM 记忆正文中**：只显示脱敏摘要（前4***后4）
- 所有凭证存储在 `brain/vault/oauth2_credentials.db`（本机加密，不入 git）
- 执行失败时给出 `need_reauth` 信号，让用户重新提供 app_id/app_secret

## 工具调用方式

通过 nanobot Tool 调用 `oauth2_vault`：

```json
{
  "action": "...",
  ...
}
```

## Actions 列表

### `setup` — 配置平台凭证（首次使用必须执行）

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

- `user_open_id`：接收审阅通知的飞书用户 open_id（可选）
- `folder_token`：存放文档的飞书文件夹 token（可选，不填则存根目录）
- `chat_id`：群组 chat_id（可选，用于向群发通知）

### `status` — 查看已配置平台状态

```json
{"action": "status"}
```

返回：各平台配置状态、token 是否过期（token 值脱敏）

### `get_token` — 获取有效 access_token（内部使用）

```json
{
  "action": "get_token",
  "platform": "feishu"
}
```

token 已过期时自动刷新。返回脱敏摘要，不返回明文。

### `feishu_create_doc` — 在飞书创建文档

```json
{
  "action": "feishu_create_doc",
  "title": "AI技术周报 2026-03-09",
  "content": "# 标题\n\n正文...",
  "notify": true
}
```

- `content`：支持简单 Markdown（# ## ### 标题，普通段落，---分割线，- 列表项）
- `notify`：是否发飞书消息通知用户审阅（需配置 `user_open_id` 或 `chat_id`）
- 返回：`document_url`、`document_id`、`notified` 状态

### `feishu_send_message` — 发飞书文本消息

```json
{
  "action": "feishu_send_message",
  "text": "消息内容",
  "receive_id": "ou_xxx",
  "receive_id_type": "open_id"
}
```

`receive_id_type`：`open_id`（默认）/ `chat_id` / `user_id`

### `delete` — 删除平台凭证

```json
{
  "action": "delete",
  "platform": "feishu"
}
```

## 飞书企业自建应用配置说明

**如何获取 app_id 和 app_secret：**

1. 进入飞书开放平台：`https://open.feishu.cn/app`
2. 创建一个「企业自建应用」
3. 应用凭证 → 复制 `App ID` 和 `App Secret`
4. 权限管理 → 开启：
   - 查看、评论、编辑和管理云空间中所有文件 (`drive:drive`)
   - 以应用身份发送消息 (`im:message:send_as_bot`)
   - 创建文档 (`docx:document`)
5. 版本管理 → 发布应用

**如何获取 user_open_id：**

方法一：飞书机器人发送 `/info` 命令
方法二：飞书管理后台 → 成员管理 → 找到用户 → User ID

**如何获取 folder_token：**

1. 进入飞书云空间，找到目标文件夹
2. URL 中的 `folder/` 之后的字符串即为 folder_token
   例：`https://xxxx.feishu.cn/drive/folder/Abc123DEF` → `folder_token = Abc123DEF`

## 错误处理规则

| 错误 | 处理方式 |
|------|---------|
| `need_reauth: true` | 告知用户重新调用 `setup` 配置 app_id/app_secret |
| 飞书 API code=99991663 | app 未安装到企业，让用户发布应用 |
| 飞书 API code=99991400 | app_id/app_secret 错误，重新获取 |
| 网络超时 | 重试一次，仍失败则报告 |

## 与 KyloBrain 的集成

每次飞书操作（创建文档、发送消息、token 刷新）都自动写入 WARM episodes：
- `tags: ["oauth2", "feishu", "external_action"]`
- 包含成功/失败信号和执行时长
- 30次真实操作后，大脑有足够数据进行模式分析
