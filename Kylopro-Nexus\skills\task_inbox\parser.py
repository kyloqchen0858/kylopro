"""
Kylopro 需求解析器 (Requirement Parser)
=======================================
将 Markdown 格式的需求文档解析为结构化任务清单（JSON）。

解析策略：
  优先：Ollama 本地 LLM 理解自然语言 → JSON
  降级：基于 Markdown 标题/列表结构的规则解析

输出格式：
  {
    "title":    "xxx",
    "summary":  "xxx",
    "workspace": "c:/xxx",   # 可选，需求中指定的工作目录
    "subtasks": [
      {"id": 1, "action": "create_file", "target": "hello.py",
       "detail": "print('Hello')", "skill": "ide_bridge"},
      ...
    ]
  }

action 枚举：
  create_file  — 创建文件（ide_bridge）
  modify_file  — 修改文件（ide_bridge）
  run_command  — 执行命令（ide_bridge）
  browse_url   — 浏览网页（web_pilot）
  rpa_action   — 桌面 RPA 截图（vision_rpa）
  rpa_agent    — 桌面全自动驾驶/控制软件/监督 Antigravity（vision_rpa）
  analyze      — 分析思考（provider.chat）
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from loguru import logger

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
except AttributeError:
    pass


# ===========================================================
# 规则解析器（降级方案，不依赖 LLM）
# ===========================================================

def _rule_based_parse(content: str) -> dict[str, Any]:
    """
    基于 Markdown 结构的规则解析（LLM 不可用时的降级方案）。

    解析逻辑：
      - # 标题 → title
      - 正文第一段 → summary
      - 有序/无序列表项 → subtasks
      - 关键词匹配 → action 推断
    """
    lines = content.strip().splitlines()

    title = "未命名任务"
    summary = ""
    subtasks: list[dict[str, Any]] = []
    task_id = 0

    for line in lines:
        stripped = line.strip()

        # 提取标题
        if stripped.startswith("# ") and title == "未命名任务":
            title = stripped.lstrip("# ").strip()
            continue

        # 提取摘要（标题后第一段非空文字）
        if not summary and stripped and not stripped.startswith("#") \
                and not stripped.startswith("-") and not re.match(r"^\d+\.", stripped):
            summary = stripped
            continue

        # 提取列表项 → subtask
        list_match = re.match(r"^(?:\d+\.\s*|-\s*|\*\s*)(.*)", stripped)
        if list_match:
            item_text = list_match.group(1).strip()
            if not item_text:
                continue

            task_id += 1
            action, skill = _infer_action(item_text)
            subtasks.append({
                "id":     task_id,
                "action": action,
                "target": "",
                "detail": item_text,
                "skill":  skill,
            })

    if not subtasks and summary:
        # 如果没解析到列表项，把整个文档当作一个分析任务
        subtasks.append({
            "id":     1,
            "action": "analyze",
            "target": "",
            "detail": content[:500],
            "skill":  "provider",
        })

    return {
        "title":    title,
        "summary":  summary or title,
        "subtasks": subtasks,
    }


def _infer_action(text: str) -> tuple[str, str]:
    """从任务描述文本推断 action 类型和对应 skill。"""
    t = text.lower()

    # 创建文件
    if any(kw in t for kw in ["创建", "新建", "create", "生成文件", "添加文件"]):
        return "create_file", "ide_bridge"

    # 修改文件
    if any(kw in t for kw in ["修改", "编辑", "更新", "改", "modify", "edit", "update"]):
        return "modify_file", "ide_bridge"

    # 运行命令
    if any(kw in t for kw in ["运行", "执行", "run", "exec", "安装", "install", "pip", "npm"]):
        return "run_command", "ide_bridge"

    # 浏览网页
    if any(kw in t for kw in ["浏览", "打开网页", "访问", "url", "http", "browse", "网站"]):
        return "browse_url", "web_pilot"
        
    # 桌面全自动驾驶 / 电脑操作 / 监督
    if any(kw in t for kw in ["自动驾驶", "操作电脑", "操作软件", "监督", "antigravity", "操控", "control", "operate"]):
        return "rpa_agent", "vision_rpa"

    # RPA 截图操作
    if any(kw in t for kw in ["点击", "输入", "拖拽", "click", "type", "rpa", "截图", "桌面"]):
        return "rpa_action", "vision_rpa"

    # 默认：分析任务
    return "analyze", "provider"


# ===========================================================
# LLM 解析器（优先方案，使用 Ollama 本地模型）
# ===========================================================

_PARSE_PROMPT = """你是一个需求分析专家。请将以下 Markdown 需求文档解析为 JSON 格式的任务清单。

=== 输出格式（严格 JSON，不要加 markdown 代码块标记）===
{
  "title": "项目/任务标题",
  "summary": "一句话概述",
  "subtasks": [
    {
      "id": 1,
      "action": "create_file",
      "target": "文件路径或目标",
      "detail": "具体描述（如果是创建文件，这里写文件的内容需求）",
      "skill": "ide_bridge"
    }
  ]
}

=== action 可选值 ===
- create_file  — 创建新文件（skill: ide_bridge）
- modify_file  — 修改已有文件（skill: ide_bridge）
- run_command  — 执行 shell 命令（skill: ide_bridge）
- browse_url   — 打开网页获取信息（skill: web_pilot）
- rpa_action   — 仅仅是桌面截图汇报（skill: vision_rpa）
- rpa_agent    — 桌面全自动控制，包含找按钮点击、控制其他软件、打开 Antigravity（skill: vision_rpa）
- analyze      — 需要 AI 分析思考（skill: provider）

=== 需求文档 ===
{content}

请直接输出 JSON，不要加任何解释文字。"""


class RequirementParser:
    """
    需求文档解析器。

    优先用 Ollama 本地 LLM 理解需求，
    失败则降级为规则解析。
    """

    def __init__(self) -> None:
        self._ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self._ollama_model = os.getenv("OLLAMA_MODEL", "deepseek-r1:latest")

    async def parse_file(self, file_path: str | Path) -> dict[str, Any]:
        """读取文件并解析为结构化任务。"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"需求文件不存在: {file_path}")

        content = path.read_text(encoding="utf-8", errors="replace")
        logger.info("[PARSER] 开始解析需求文件: {} ({} 字符)", path.name, len(content))
        return await self.parse_markdown(content)

    async def parse_markdown(self, content: str) -> dict[str, Any]:
        """将 Markdown 内容解析为结构化任务。"""
        if not content.strip():
            return {"title": "空文档", "summary": "文档内容为空", "subtasks": []}

        # 尝试 LLM 解析
        try:
            result = await self._llm_parse(content)
            if result and result.get("subtasks"):
                logger.info("[PARSER] LLM 解析成功：{} 个子任务", len(result["subtasks"]))
                return result
        except Exception as e:
            logger.warning("[PARSER] LLM 解析失败 ({}), 降级为规则解析", e)

        # 降级：规则解析
        result = _rule_based_parse(content)
        logger.info("[PARSER] 规则解析完成：{} 个子任务", len(result["subtasks"]))
        return result

    async def _llm_parse(self, content: str) -> dict[str, Any] | None:
        """使用 Ollama 本地 LLM 解析需求。"""
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key="ollama",
            base_url=f"{self._ollama_base}/v1",
        )

        prompt = _PARSE_PROMPT.replace("{content}", content[:3000])

        resp = await client.chat.completions.create(
            model=self._ollama_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0.1,
        )

        raw = resp.choices[0].message.content or ""

        # 清理 LLM 输出（可能包含 markdown 代码块标记或思考内容）
        raw = self._extract_json(raw)

        try:
            parsed = json.loads(raw)
            # 基本校验
            if "subtasks" not in parsed or not isinstance(parsed["subtasks"], list):
                logger.warning("[PARSER] LLM 输出缺少 subtasks 字段")
                return None
            # 规范化每个 subtask
            for i, st in enumerate(parsed["subtasks"]):
                st.setdefault("id", i + 1)
                st.setdefault("action", "analyze")
                st.setdefault("target", "")
                st.setdefault("detail", "")
                st.setdefault("skill", _infer_action(st.get("detail", ""))[1])
            return parsed
        except json.JSONDecodeError as e:
            logger.warning("[PARSER] LLM 输出不是有效 JSON: {}", e)
            return None

    @staticmethod
    def _extract_json(text: str) -> str:
        """从 LLM 输出中提取 JSON（去掉 markdown 代码块和思考标签）。"""
        # 去掉 <think>...</think> 标签
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)

        # 尝试提取 ```json ... ``` 代码块
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # 尝试提取第一个 { } 块
        start = text.find("{")
        if start >= 0:
            depth = 0
            for i in range(start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        return text[start:i + 1]

        return text.strip()
