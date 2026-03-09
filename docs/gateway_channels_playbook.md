# nanobot 网关与多通道操作手册

## 1. 先理解架构

当前不是“每个聊天软件一个独立网关”，而是：

```text
nanobot gateway
  ├── MessageBus
  ├── AgentLoop
  └── ChannelManager
       ├── telegram
       ├── whatsapp
       ├── qq
       ├── discord
       ├── slack
       ├── matrix
       └── ...
```

也就是说：

- **网关只有一个**：`python -m nanobot gateway`
- **通道可以有多个**：由 `~/.nanobot/config.json` 的 `channels` 段决定启用哪些
- **冲突不是“多通道导致”的**：这次的 `409 Conflict` 是 Telegram polling 的单实例约束，不是 nanobot 整体架构冲突

## 2. 为什么会有两个启动脚本

不是两个“启动程序”，而是两个职责不同的包装脚本：

- `start_gateway.bat`
  - 正式生产启动器
  - 负责判断是否已有正确环境下的网关在跑
  - 负责等待 15 秒，避开 Telegram polling 释放窗口
  - 默认常驻，退出后会自动重试

- `clean_restart_gateway.bat`
  - 维修工具，不是另一套生产入口
  - 负责停计划任务、杀残留进程、做人工清场
  - 清场完成后，**再委托给 `start_gateway.bat /ONESHOT /NODELAY` 启动**

因此真正应该让 Kylo 学会的是：

- 日常运行 → `start_gateway.bat`
- 排障重启 → `clean_restart_gateway.bat`
- 真正唯一入口始终是 `nanobot gateway`

## 3. Telegram 冲突和网关架构的关系

### 结论

- **和 nanobot 的“单网关多通道”架构本身关系不大**
- **和 Telegram 通道的 polling 机制关系很大**

### 原因

Telegram 当前实现使用的是 long polling：

- 同一个 bot token 在同一时刻只能有一个活跃的 `getUpdates`
- 如果旧实例刚退出，Telegram 服务器端可能还没完全释放轮询
- 这时新实例立刻上线，就会收到 `telegram.error.Conflict`

### 规范处理方法

1. 先杀掉所有旧的 `-m nanobot gateway` 进程
2. 等待约 15 秒，让 Telegram 释放旧 polling
3. 再启动新实例

这个问题主要影响 Telegram polling，不代表 WhatsApp、QQ、Slack、Matrix 都会以同样方式冲突。

## 4. 配置入口在哪里

nanobot 的通道配置单一来源是：

```text
~/.nanobot/config.json
```

Kylo 后续如果要启用、切换、关闭通道，应该优先改这里，而不是在工作区里再造一份平行配置。

对应的 Python schema 在：

- `nanobot/config/schema.py`
- `nanobot/channels/manager.py`

## 5. 建议的通道配置方式

### Telegram

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "<telegram_bot_token>",
      "allowFrom": ["8534144265"],
      "replyToMessage": false,
      "dropPendingUpdates": true
    }
  }
}
```

说明：

- `dropPendingUpdates=true` 可以避免离线期间的旧消息淤积
- 但它**不能**解决双实例 polling 冲突，那个要靠单实例启动纪律

### WhatsApp

```json
{
  "channels": {
    "whatsapp": {
      "enabled": true,
      "bridgeUrl": "ws://localhost:3001",
      "bridgeToken": "<shared_bridge_token>",
      "allowFrom": []
    }
  }
}
```

说明：

- WhatsApp 不是 Python 直接连官方接口
- 它走 Node.js bridge，bridge 代码在 `bridge/` 和 `bridge/src/whatsapp.ts`
- 首次登录通常需要执行：
  - `python -m nanobot channels login`
  - 扫桥接终端里的二维码
- 如果桥接窗口**没有二维码**，先不要立刻判断失败：
  - 很可能是 `~/.nanobot/whatsapp-auth` 里已经存在历史认证会话
  - bridge 会优先复用旧会话，因此不一定再次显示二维码
  - 若必须重新配对或刷新设备名，应先在 WhatsApp 的 Linked Devices 里断开旧设备，再运行 `relink_whatsapp_bridge.bat` 生成新二维码

### QQ

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

说明：

- QQ 走 botpy SDK 和 WebSocket
- 它的约束更偏向凭据和 SDK 可用性，不是 Telegram 那种 polling 单实例冲突
- 当前生产环境已确认安装 `qq-botpy 1.2.1`
- QQ 单聊接入前，Kylo 应先提醒用户完成腾讯 QQ 开放平台的沙箱配置：
  - 进入 `https://q.qq.com`
  - 创建机器人应用
  - 复制 `AppID` 与 `AppSecret`
  - 在“沙箱配置”里把你的 QQ 号加进测试成员
  - 用手机 QQ 扫机器人二维码并发起私聊

### QQ 接入固定流程

以后 Kylo 处理“接入 QQ 作为备选通道”时，固定步骤应是：

1. 向用户索要 QQ 机器人的 `AppID` 和 `AppSecret`
2. 读取并备份 `~/.nanobot/config.json`
3. 仅修改 `channels.qq`：

```json
{
  "channels": {
    "qq": {
      "enabled": true,
      "appId": "<QQ_APP_ID>",
      "secret": "<QQ_APP_SECRET>",
      "allowFrom": []
    }
  }
}
```

4. 运行 `python -m nanobot channels status`，确认 QQ 显示为已配置
5. 运行 `start_gateway.bat`
6. 查看日志中是否出现：
   - `QQ channel enabled`
   - `QQ bot started`
   - `QQ bot ready`
7. 让用户从 QQ 给机器人发一条私聊消息，验证收发链路

### QQ 故障优先级

- 启动即失败：先查 `appId/secret` 是否为空或填错
- 没收到消息：先查 QQ 开放平台沙箱成员是否包含当前 QQ 号
- 能连上但不回复：再查 `allowFrom` 是否限制了 openid
- 只有 QQ 不通、Telegram 正常：优先怀疑 QQ 配置或平台权限，不先怀疑 nanobot 总网关

## 6. Kylo 修改通道配置时的标准动作

以后 Kylo 遇到“加一个聊天软件”这类任务，顺序应固定为：

1. 先读取 `~/.nanobot/config.json`
2. 备份原配置到 `~/.nanobot/backups/config_<timestamp>.json`
3. 只修改 `channels.<name>` 这一段
4. 如涉及 WhatsApp，检查 bridge 是否已构建，并在需要时执行 `python -m nanobot channels login`
5. 用 `python -m nanobot channels status` 检查配置是否生效
6. 用 `start_gateway.bat` 或 `clean_restart_gateway.bat` 重启网关
7. 启动后检查日志里是否出现 `"<channel> channel enabled"`

## 7. 多通道建议

如果后面要做“Telegram + QQ + WhatsApp 备选”，建议是：

- **保留单一网关进程**
- **同时启用多个 channel**
- **不要为每个通道单独再起一个 nanobot gateway**

正确方式是一个 `config.json` 里同时开多个通道，例如：

```json
{
  "channels": {
    "telegram": { "enabled": true, "token": "<...>" },
    "whatsapp": { "enabled": true, "bridgeUrl": "ws://localhost:3001" },
    "qq": { "enabled": true, "appId": "<...>", "secret": "<...>" }
  }
}
```

这样 ChannelManager 会在同一个网关里同时启动这些通道。

## 8. Kylo 必须记住的运行判断

- 没有前台窗口，不代表网关没运行
- 先查计划任务，再查 `nanobot gateway` 进程，再查具体通道日志
- Telegram 冲突优先怀疑重复 polling，不要先怀疑整个网关架构
- 扩新通道时优先改 `~/.nanobot/config.json`，不要再造平行配置中心
- 涉及 token / secret / appId / AppSecret 的配置副本，一律不落入工作区仓库内