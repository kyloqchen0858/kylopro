# 当前路线图

## 第一优先级

1. 稳定 Kylo 的脑体协同与自知层
2. 保持 Telegram / QQ 双通道稳定
3. 将 WhatsApp 留在单独排查分支，不影响主链路

## 第二优先级

1. 完成向量记忆在 WARM 中的长期稳定验证
2. 补一套网关 / 通道自检能力，让 Kylo 自己汇报在线状态
3. 继续把运行规则写回自知层，而不是只写在聊天记录里

## 当前建议执行顺序

1. 做网关 / 多通道自检能力
2. 完成向量记忆路径的大样本稳定性验证
3. 单独回到 WhatsApp 风控与重连问题

## 向量记忆当前结论

1. `chromadb` 已在当前生产 Python 环境中可用
2. KyloBrain WARM 已走真实向量检索，不再只是 Jaccard 回退
3. `status()` 与 `health_check()` 已能直接显示 `vector_operational`、`retrieval_mode` 与 `fallback_reason`

## 进入下一轮时怎么做

1. 先读 `CURRENT_STATUS.md`
2. 查看 `tasks/pending/`
3. 如果涉及通道，优先检查 `~/.nanobot/config.json`、`python -m nanobot channels status` 和 gateway 日志
4. 不要把 WhatsApp 的临时问题误判成整个 nanobot 网关架构问题