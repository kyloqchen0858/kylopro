# Kylopro 开发入口

这个文件夹是后续继续开发 Kylopro 的统一入口。

## 建议阅读顺序

1. `CURRENT_STATUS.md`
2. `ROADMAP.md`
3. `REPO_HYGIENE_20260310.md`
4. `GITHUB_PR_NOTES_20260310.md`
5. `CHANNEL_SETUP_TELEGRAM_QQ.md`
6. `../gateway_channels_playbook.md`
7. `../../tasks/pending/`

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

- `REPO_HYGIENE_20260310.md`
  - 当前 Git 边界、忽略规则、哪些内容该进 GitHub
  - 继续整理仓库或准备推送前先读

- `GITHUB_PR_NOTES_20260310.md`
  - 本轮 clean 分支的 PR 标题与说明模板
  - 合并回 `main` 时直接复用

- `../gateway_channels_playbook.md`
  - 偏内部运维与排障
  - 解释单网关多通道、Telegram polling 冲突、WhatsApp bridge 等机制

## 当前结论

- Telegram 已验证可用
- QQ 已验证可用
- WhatsApp 已接入 bridge 链路，但账号当前存在风控与重连问题，暂不作为稳定生产通道
- 开发状态以 Phase 11.6b 为准，当前主线是交互层代码化（MessageCoalescer / Preemption / silent progress）
- GitHub 推送默认走 Git 原生安全分支，不直接覆盖 `main`
- 下次继续开发时，不要先翻散落文档；直接从这个文件夹开始即可