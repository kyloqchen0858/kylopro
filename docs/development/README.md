# Kylopro 开发入口

这个文件夹是后续继续开发 Kylopro 的统一入口。

## 建议阅读顺序

1. `CURRENT_STATUS.md`
2. `ROADMAP.md`
3. `CHANNEL_SETUP_TELEGRAM_QQ.md`
4. `../gateway_channels_playbook.md`
5. `../../tasks/pending/`

## 文件职责

- `CURRENT_STATUS.md`
  - 当前已经验证通过的能力
  - 当前阻塞项
  - 继续开发前需要先知道的运行事实

- `ROADMAP.md`
  - 当前阶段目标
  - 下一步优先级
  - 进入下一轮开发时应该从哪里下手

- `CHANNEL_SETUP_TELEGRAM_QQ.md`
  - 给别人看的 Telegram / QQ 接入说明
  - 尽量不夹带内部排障细节

- `../gateway_channels_playbook.md`
  - 偏内部运维与排障
  - 解释单网关多通道、Telegram polling 冲突、WhatsApp bridge 等机制

## 当前结论

- Telegram 已验证可用
- QQ 已验证可用
- WhatsApp 已接入 bridge 链路，但账号当前存在风控与重连问题，暂不作为稳定生产通道
- 下次继续开发时，不要先翻散落文档；直接从这个文件夹开始即可