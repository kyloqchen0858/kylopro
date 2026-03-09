# GitHub PR Notes · 2026-03-10

本文件用于记录本轮仓库整理后，推荐提交到 GitHub 的两个 clean PR 分支及其建议说明。

## 1. 顶层仓库 PR

### 分支

- `sync-20260310-top-level-clean-v2`

### 建议标题

- `chore: harden repo boundaries and MCP startup handling`

### 建议说明

```
## Summary

- tighten top-level ignore rules to keep local Kylopro workspace artifacts out of the parent repo
- add runtime constraints file for validated local dependency pinning
- harden MCP startup handling in the agent loop so connection failures do not block the main loop
- reduce Telegram transient network noise and keep MCP connection failures non-fatal

## Included Files

- .gitignore
- constraints-runtime.txt
- nanobot/agent/loop.py
- nanobot/agent/tools/mcp.py
- nanobot/channels/telegram.py

## Safety Notes

- excludes local-only Kylopro workspace directories and IDE files from the parent repo
- does not include .env, logs, runtime data, or nested-repo source trees
```

## 2. Kylopro-Nexus PR

### 分支

- `sync-20260310-kylopro-nexus-clean`

### 建议标题

- `feat: sync phase 11.6b runtime, docs, skills, and safe GitHub sync workflow`

### 建议说明

```
## Summary

- sync Phase 11.6b runtime and architecture updates across brain hooks, tools, OAuth2 vault, and runtime docs
- add freelance-hub skill, tracker implementation, and focused workflow test coverage
- align CURRENT_STATUS / ROADMAP / DEVELOPMENT_ROADMAP with the latest verified state
- document repo hygiene and GitHub sync boundaries for nested-repo workflows
- refine cloud-sync skill so Git-native safe-branch push becomes the default GitHub workflow

## Included Areas

- core/
- kylo_tools/
- nanobot/
- skills/
- docs/development/
- tests/

## Safety Notes

- keeps .env, brain/, data/, logs/, sessions/, tasks/, output/ local-only
- explicitly excludes one-off Feishu diagnostic scripts from version control
- uses clean branch workflow because remote main is ahead and should not be force-pushed
```

## 3. 合并提醒

- 顶层仓库和 `Kylopro-Nexus` 是两个独立 Git 边界，应分别审查、分别合并
- 如果远端 `main` 在审查期间继续前进，优先 rebase / cherry-pick 到最新主线，不强推覆盖
- 本轮未纳入仓库的本地调试文件：`debug_feishu.py`、`feishu_diagnostic.py`、`test_feishu_api.py`