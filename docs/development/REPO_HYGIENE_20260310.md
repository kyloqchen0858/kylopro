# 仓库整理与 GitHub 同步说明

> 日期：2026-03-10
> 目标：明确哪些内容应该进 Git，哪些内容必须继续留在本地，避免把运行态数据和凭证一起推上 GitHub。

## 一、仓库边界

当前工作区实际上有两个 Git 边界：

1. 顶层仓库 `nanobot/`
2. 嵌套仓库 `Kylopro-Nexus/`

这两个仓库必须分别提交、分别推送。不要在顶层仓库里直接接管 `Kylopro-Nexus/` 内容，也不要把运行中的工作区副本推到上游 `HKUDS/nanobot`。

## 二、应该进入 GitHub 的内容

- 源码：`core/`、`kylo_tools/`、`skills/`、`nanobot/`
- 文档：`docs/`、`README.md`、`AGENTS.md`、`SOUL.md`
- 测试：`tests/`
- 启动与部署脚本：`start_gateway.bat`、`clean_restart_gateway.bat`、`setup.bat`
- 示例配置：`.env.example`

## 三、必须继续留在本地的内容

- 凭证与环境：`.env`、`brain/vault/`、`~/.nanobot/config.json`
- 运行时数据：`brain/`、`data/`、`memory/`、`sessions/`
- 日志与产物：`logs/`、`task_logs/`、`task_states/`、`output/`
- 临时任务与调试副本：`tasks/`、`*.bak`、本地上传/校验脚本产物

## 四、本次整理结论

- 顶层仓库已补充忽略规则，避免误把 `Kylopro-Nexus/`、`_kylopro_publish/`、本地 IDE 配置推到上游仓库
- `Kylopro-Nexus/.gitignore` 已补充 `output/` 和 `*.bak`，避免把输出快照和备份文件带进 Git
- `debug_feishu.py`、`feishu_diagnostic.py`、`test_feishu_api.py` 已明确归类为本地联调脚本，不纳入 Git
- `CURRENT_STATUS.md`、`ROADMAP.md`、`DEVELOPMENT_ROADMAP.md` 已同步到 Phase 11.6b 现状

## 五、推送前安全检查

1. 先检查 `git status --short`
2. 再做一次密钥扫描，重点看 `api_key`、`app_secret`、`GITHUB_TOKEN`、`sk-`
3. 确认 `.env`、`brain/`、`data/`、`output/` 没被 stage
4. 只向目标仓库推送：
   - 顶层 `nanobot/` 不要误推到上游 `origin`
   - `Kylopro-Nexus/` 优先推到它自己的 `origin`

## 六、当前建议的 GitHub 同步顺序

1. 在 `Kylopro-Nexus/` 内完成提交与推送
2. 如需保留顶层仓库的本地整理改动，只提交忽略规则等低风险文件
3. 不处理 `_kylopro_publish/` 这类发布副本目录，保持本地忽略或单独归档

## 七、本轮推荐合并分支

- 顶层仓库：`sync-20260310-top-level-clean-v2`
- Kylopro-Nexus：`sync-20260310-kylopro-nexus-clean`

这两个分支都基于可访问远端 `userrepo/main` 做了最小化整理，更适合直接发 PR。避免继续使用早期的中间同步分支作为最终合并入口。