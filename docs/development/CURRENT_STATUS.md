# 当前状态

## 已验证能力

- `nanobot gateway` 已作为唯一生产入口稳定使用
- Telegram 通道已验证
- QQ 通道已验证
- Kylo 自知层、向量 WARM 检索、BrainHooks 已接入运行时
- `Kylopro-Nexus` 当前生产 Python 环境已确认装有 `chromadb`，向量检索链路可实际工作，不再只是 Jaccard 回退

## 当前通道状态

- Telegram
  - 已连接并实际收发成功
  - 主要风险点是 polling 单实例冲突

- QQ
  - 已通过 `channels.qq` 配置启用
  - 已完成私聊验证
  - 主要风险点是 QQ 开放平台沙箱成员与私聊权限

- WhatsApp
  - bridge、gateway、配置链路都已打通
  - 当前问题不是代码主路径，而是账号风控 / 旧认证会话 / 重连稳定性
  - 先不视为稳定生产通道，后续单独排查

## 敏感信息策略

- `~/.nanobot/config.json` 是真实运行配置源，但不进入仓库
- 任何配置备份一律放到 `~/.nanobot/backups/`
- 工作区仓库里不保留 token、secret、AppSecret 副本

## 下次开发前先确认

1. 当前需要改的是功能，还是运行配置
2. 当前需要看的是真实进度，还是历史开发记录
3. 如果是通道相关，先看 `CHANNEL_SETUP_TELEGRAM_QQ.md` 和 `../gateway_channels_playbook.md`
4. 如果是记忆相关，先看向量状态是否为 `vector_enabled=true`，再区分是真向量命中还是回退检索