"""
Kylopro 进化研究员 (Evolution Researcher)
=========================================
自主学习系统核心。
主动在 GitHub 检索前沿 AI/Agent 架构项目，
下载核心概念与文档交由 DeepSeek 分析，
一旦发现可复用的能力（如 Semantic Snapshot, Memory System 等），
自动编写 `.md` 需求文档投入任务收件箱 (Inbox) 以供自主迭代。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from core.provider import KyloproProvider

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
except AttributeError:
    pass


class EvolutionResearcher:
    """
    自主在 GitHub 上挖掘进化点子的"数字分析师"。
    """

    def __init__(self, inbox_dir: str | Path | None = None) -> None:
        self.provider = KyloproProvider()
        # 默认把想到的主意存入 inbox 供日后消化
        workspace = Path(__file__).resolve().parent.parent.parent
        self.inbox_dir = Path(inbox_dir) if inbox_dir else (workspace / "data" / "inbox")
        self.inbox_dir.mkdir(parents=True, exist_ok=True)

    async def _search_github_repos(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        """调用 GitHub API 搜索高分开源库。"""
        url = "https://api.github.com/search/repositories"
        params = {
             "q": query,
             "sort": "stars",
             "order": "desc",
             "per_page": limit,
        }
        headers = {
             "Accept": "application/vnd.github+json",
             "User-Agent": "Kylopro-Evolution-Researcher",
        }
        
        # 尝试使用 GitHub Token 可以防止限流，未提供也可匿名访问
        gh_token = os.getenv("GITHUB_TOKEN")
        if gh_token:
            headers["Authorization"] = f"Bearer {gh_token}"
            
        logger.info("[Researcher] 开始在 GitHub 搜索: {}", query)
            
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, params=params, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                return data.get("items", [])
        except Exception as e:
            logger.error("[Researcher] GitHub 搜索失败: {}", e)
            return []

    async def _fetch_repo_readme(self, full_name: str, branch: str = "main") -> str:
        """获取目标仓库的 README。"""
        urls = [
            f"https://raw.githubusercontent.com/{full_name}/{branch}/README.md",
            f"https://raw.githubusercontent.com/{full_name}/master/README.md",
        ]
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            for url in urls:
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        return resp.text
                except Exception:
                    continue
        return ""

    async def _analyze_for_evolution(self, repo: dict[str, Any], readme: str) -> str | None:
        """
        让 DeepSeek 分析该仓库对 Kylo 的进化价值。
        如果认为有价值，要求输出带有 `markdown` 格式的需求文档；否则返回 None。
        """
        repo_name = repo.get("full_name", "Unknown")
        stars = repo.get("stargazers_count", 0)
        desc = repo.get("description", "")
        
        logger.info("[Researcher] 正在分析仓库: {} (⭐{})", repo_name, stars)
        
        # 截断 README 防止 Token 爆炸
        readme_snippet = readme[:6000] if readme else "无 README 内容"
        
        prompt = f"""你现在是 Kylopro 系统的“首席进化架构师”。
你的任务是评估目前 GitHub 上优秀的开源AI项目，看是否有可以直接借鉴融入到 Kylopro 架构中的特性。

当前分析的目标仓库: {repo_name}
简介: {desc}
Star数量: {stars}

仓库 README 片段:
{readme_snippet}

由于 Kylopro 本身就是一个 Python 编写的 Agent，她当前拥有：
1. Task Inbox (热目录解析 Markdown 执行)
2. Desktop Agent (基于 OCR 和 PyAutoGUI 的桌面自动驾驶)
3. 协同进化引擎 (可动态热插拔 Python 模块技能)
4. 多模态 Provider (DeepSeek Reasoner 核心处理)
5. SOUL.md (灵魂宪法，定义了自治权与行为准则)

请仔细分析该目标仓库的理念或架构。
如果该项目包含极具价值的机制，你有两种方式推动 Kylopro 进化：

方式 A: **新功能开发需求文档**
撰写一份 Markdown 格式的需求文档，投递到 Task Inbox 供后续自动开发。

方式 B: **灵魂宪法 (SOUL.md) 更新建议**
如果该项目提出了某种极其深刻的 Agent 行为准则或交互哲学，请输出一段建议追加到 SOUL.md 的内容。

如果该项目提升不大，请直接回复：`SKIP`

若决定吸收，请根据以下格式输出：
---
type: [INBOX_TASK | SOUL_UPDATE]
target: [文件名, 比如 data/inbox/new_skill.md 或 SOUL.md]
---
# 标题
(此处开始是具体的 Markdown 需求内容)
"""

        result = await self.provider.chat(
            messages=[{"role": "user", "content": prompt}],
            task_type="reason", # 使用 reasoner 模型仔细推断
            max_tokens=2000,
        )
        content = result.get("content", "") if isinstance(result, dict) else str(result)
        
        if "SKIP" in content.upper()[:20] or not content.strip():
            logger.info("[Researcher] 经过评估，认为 {} 暂无特殊借鉴价值，跳过。", repo_name)
            return None
            
        return content

    def _save_evolution_result(self, md_content: str) -> None:
        """解析 LLM 输出并保存进化结果。"""
        import re
        
        # 提取元数据
        meta_match = re.search(r"---(.*?)---", md_content, re.DOTALL)
        if not meta_match:
            # Fallback 到任务模式
            self._save_requirement("unknown_evolution", md_content)
            return
            
        meta_str = meta_match.group(1)
        evo_type = "INBOX_TASK"
        if "SOUL_UPDATE" in meta_str:
            evo_type = "SOUL_UPDATE"
            
        # 提取正文
        body = md_content.split("---")[-1].strip()
        
        if evo_type == "SOUL_UPDATE":
            # 投递一个修改 SOUL.md 的任务到 Inbox，而不是直接修改，保证安全
            soul_task = f"# 更新灵魂宪法\n\n1. 修改 SOUL.md\n2. 追加以下准则：\n\n{body}"
            self._save_requirement("soul_evolution", soul_task)
        else:
            self._save_requirement("feature_evolution", body)

    def _save_requirement(self, prefix: str, clean_content: str) -> None:
        """将生成的进化需求文档存入 Inbox 热目录。"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{prefix}_{timestamp}.md"
        filepath = self.inbox_dir / filename
        
        filepath.write_text(clean_content, encoding="utf-8")
        logger.info("[Researcher] 💡 发现进化点子！已生成需求文档并投递至 Inbox: {}", filename)

    async def explore(self, keywords: str, max_repos: int = 2) -> int:
        """开始一次完整的定向进化研究循环。"""
        repos = await self._search_github_repos(keywords, limit=max_repos)
        count = 0
        
        for repo in repos:
            readme = await self._fetch_repo_readme(repo["full_name"])
            evo_doc = await self._analyze_for_evolution(repo, readme)
            if evo_doc:
                self._save_evolution_result(evo_doc)
                count += 1
        return count
