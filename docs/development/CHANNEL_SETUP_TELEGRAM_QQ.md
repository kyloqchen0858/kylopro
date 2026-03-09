# Telegram 与 QQ 接入说明

这份文档是给别人看的接入说明，重点是如何正确连上机器人，而不是内部排障细节。

## 总原则

- 使用的是同一个 `nanobot gateway`
- Telegram 和 QQ 不是两个独立机器人后端，而是同一个网关下的两个 channel
- 配置统一写在 `~/.nanobot/config.json`

## 这个接法是不是 nanobot 官方路径

是。

- nanobot README 对 Telegram 的说明就是 long polling + `nanobot gateway`
- nanobot README 对 QQ 的说明就是 `qq-botpy` WebSocket + `nanobot gateway`
- 当前 Kylopro 只是把这些原生通道接入到同一个工作区，不是另造一套平行机器人框架

## Telegram 接入

### 准备步骤

1. 在 Telegram 中找到 `@BotFather`
2. 创建一个 bot
3. 拿到 bot token
4. 先和机器人发起一次对话，确认你自己的账号能找到它

### 配置示例

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "<telegram_bot_token>",
      "allowFrom": ["<your_telegram_user_id>"],
      "replyToMessage": true,
      "dropPendingUpdates": true
    }
  }
}
```

### 启动

```bash
start_gateway.bat
```

### 成功标志

- 日志出现 `Telegram channel enabled`
- 日志出现 `Telegram bot connected`
- 你给机器人发消息后，能收到回复

### 常见问题

- 收到 `409 Conflict`
  - 说明同一个 bot token 被另一个 polling 实例占用
  - 处理方式是：清掉旧实例，等待十几秒，再启动新实例

## QQ 接入

### 准备步骤

1. 进入 `https://q.qq.com`
2. 注册并创建机器人应用
3. 进入开发设置，拿到 `AppID` 与 `AppSecret`
4. 在沙箱配置中，把自己的 QQ 号加入测试成员
5. 用手机 QQ 扫机器人二维码，并从 QQ 侧发起私聊

### 配置示例

```json
{
  "channels": {
    "qq": {
      "enabled": true,
      "appId": "<qq_app_id>",
      "secret": "<qq_app_secret>",
      "allowFrom": []
    }
  }
}
```

### 启动

```bash
start_gateway.bat
```

### 成功标志

- 日志出现 `QQ channel enabled`
- 日志出现 `QQ bot started`
- 日志出现 `QQ bot ready`
- 从 QQ 私聊机器人后，能收到回复

### 常见问题

- 能启动但不回话
  - 先查 QQ 开放平台的沙箱成员是否已经加对
- 日志里没有 `QQ bot ready`
  - 先查 `AppID` / `AppSecret` 是否正确
- Telegram 正常、QQ 不正常
  - 优先判断为 QQ 平台配置或权限问题，不要先怀疑 nanobot 总体架构