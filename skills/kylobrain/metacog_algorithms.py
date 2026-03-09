"""
KyloBrain · metacog_algorithms.py
===================================
元认知核心算法库

1. ConfidenceCalibrator  – 置信校准器（Brier Score）
2. FailureBloomFilter    – 失败模式检测（稀疏布隆过滤器）
3. PatternGraph          – 技能依赖图 + 工作流编排
4. AlgorithmResearcher   – 算法自研引擎（Kylo给自己升级认知工具）
5. ReActMonitor          – ReAct循环质量监控（解决"思考折叠"问题）

设计原则：
  算法1-3：零API，全本地计算
  算法4：少量API（只在评估和生成原型时）
  算法5：零API，规则检测
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Callable, Optional
import urllib.request

BASE_DIR   = Path(os.environ.get("KYLOPRO_DIR", Path.home() / "Kylopro-Nexus"))
BRAIN_DIR  = BASE_DIR / "brain"
SKILLS_DIR = BASE_DIR / "skills"


def _ensure(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


# ══════════════════════════════════════════════
# 1. 置信校准器（Confidence Calibrator）
# ══════════════════════════════════════════════

class ConfidenceCalibrator:
    """
    Brier Score 校准：Kylo说"我确定"时到底有多准？

    工作原理：
      · 每次Kylo给出一个预测置信度（0-1）和实际结果（0/1）
      · 滚动计算 Brier Score = mean( (confidence - outcome)^2 )
      · 输出"校准后置信度"= 修正过高/过低估计的实际可信度

    Brier Score解读：
      0.00 = 完美校准  0.25 = 无差别猜测  >0.25 = 比猜测还差（反校准）
    """

    def __init__(self, window: int = 100) -> None:
        self.window = window
        self._path  = BRAIN_DIR / "calibration_log.jsonl"
        _ensure(BRAIN_DIR)

    def record(self, predicted_conf: float, actual_outcome: bool,
               context: str = "") -> dict:
        """记录一次预测结果"""
        entry = {
            "ts":         time.time(),
            "predicted":  round(predicted_conf, 3),
            "outcome":    int(actual_outcome),
            "error_sq":   (predicted_conf - float(actual_outcome)) ** 2,
            "context":    context[:100],
        }
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        return entry

    def brier_score(self, n: int = None) -> float:
        """计算最近n条记录的 Brier Score"""
        records = self._load(n or self.window)
        if not records:
            return 0.25  # 默认：无差别猜测水平
        return sum(r["error_sq"] for r in records) / len(records)

    def calibration_factor(self) -> float:
        """
        返回校准系数（0-1）：
          0.9+ = 高度可靠  0.7-0.9 = 一般  <0.7 = 需要降低自信
        """
        bs = self.brier_score()
        # Brier Score 越低，校准越准，系数越高
        return max(0.1, 1.0 - bs * 2)

    def adjust_confidence(self, raw_conf: float) -> float:
        """把Kylo的主观置信度调整为校准后的实际置信度"""
        factor = self.calibration_factor()
        # 校准差时向 0.5 回归，校准好时保持原值
        adjusted = raw_conf * factor + 0.5 * (1 - factor)
        return round(adjusted, 3)

    def report(self) -> dict:
        records = self._load(self.window)
        if not records:
            return {"status": "no_data", "records": 0}
        outcomes = [r["outcome"] for r in records]
        predicted = [r["predicted"] for r in records]
        # 过度自信检测：预测平均 > 实际平均 + 0.15
        over_confident = (sum(predicted) / len(predicted) - sum(outcomes) / len(outcomes)) > 0.15
        return {
            "brier_score":          round(self.brier_score(), 4),
            "calibration_factor":   round(self.calibration_factor(), 3),
            "over_confident":       over_confident,
            "sample_count":         len(records),
            "actual_success_rate":  round(sum(outcomes) / len(outcomes), 3),
            "predicted_avg":        round(sum(predicted) / len(predicted), 3),
        }

    def _load(self, n: int) -> list[dict]:
        if not self._path.exists():
            return []
        lines = self._path.read_text(encoding="utf-8").strip().splitlines()
        records = []
        for line in lines[-n:]:
            try:
                records.append(json.loads(line))
            except Exception:
                pass
        return records


# ══════════════════════════════════════════════
# 2. 失败模式检测（Failure Bloom Filter）
# ══════════════════════════════════════════════

class FailureBloomFilter:
    """
    稀疏布隆过滤器：在失败前识别"这类情况我见过"

    为什么不用向量数据库？
    · 布隆过滤器：<1KB内存，零依赖，O(1)查询
    · 适合"见没见过"的二元判断，不需要精确相似度
    · 误报率可控（约5%），漏报率为零（见过的一定能检测到）

    与 WarmMemory.find_similar_failure 的关系：
    · 布隆过滤器：极快的"第一道过滤"（毫秒级）
    · Jaccard检索：如果布隆命中，再做精确匹配（慢但准）
    """

    def __init__(self, size: int = 10000, num_hashes: int = 3) -> None:
        self.size       = size
        self.num_hashes = num_hashes
        self._path      = BRAIN_DIR / "failure_bloom.json"
        self.bits: list[bool] = self._load()

    def _hashes(self, text: str) -> list[int]:
        """生成多个哈希位置，用不同seed模拟多个哈希函数"""
        seeds = [7, 31, 97, 137, 251]
        return [
            int(hashlib.md5(f"{seeds[i % len(seeds)]}{text}".encode()).hexdigest(), 16) % self.size
            for i in range(self.num_hashes)
        ]

    def _signature(self, task: str) -> str:
        """把任务转换成特征签名（去除具体数字/路径，保留结构）"""
        t = task.lower()
        t = re.sub(r"\d+", "NUM", t)           # 数字泛化
        t = re.sub(r"[/\\]\w+", "/PATH", t)    # 路径泛化
        t = re.sub(r"\s+", " ", t).strip()
        return t

    def remember_failure(self, task: str) -> None:
        sig = self._signature(task)
        for i in self._hashes(sig):
            self.bits[i] = True
        self._save()

    def seen_before(self, task: str) -> float:
        """返回0-1的"似曾相识"概率"""
        sig = self._signature(task)
        hits = sum(1 for i in self._hashes(sig) if self.bits[i])
        return hits / self.num_hashes

    def might_fail(self, task: str, threshold: float = 0.67) -> bool:
        """是否可能是历史失败类型（2/3以上哈希命中）"""
        return self.seen_before(task) >= threshold

    def false_positive_rate(self) -> float:
        """当前误报率"""
        filled = sum(self.bits) / self.size
        return (1 - math.exp(-self.num_hashes * sum(self.bits) / self.size)) ** self.num_hashes

    def _save(self) -> None:
        _ensure(BRAIN_DIR)
        self._path.write_text(json.dumps({
            "size": self.size, "num_hashes": self.num_hashes,
            "bits": [i for i, b in enumerate(self.bits) if b],  # 稀疏存储
        }))

    def _load(self) -> list[bool]:
        bits = [False] * self.size
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
                for i in data.get("bits", []):
                    if 0 <= i < self.size:
                        bits[i] = True
            except Exception:
                pass
        return bits


# ══════════════════════════════════════════════
# 3. 技能依赖图（Pattern Graph）
# ══════════════════════════════════════════════

class PatternGraph:
    """
    把孤立的 Skill 变成可组合的工作流图。

    节点 = 一个 Skill/任务类型
    边   = "A成功后通常执行B"（从历史episodes中挖掘）

    应用：
    · 给定目标，自动找出最优执行路径
    · 发现哪些Skill之间有强依赖（经验复用）
    · "这个任务之前都是先做X再做Y再做Z，不用重新规划"
    """

    def __init__(self) -> None:
        self._path = BRAIN_DIR / "pattern_graph.json"
        self.graph: dict[str, dict[str, int]] = self._load()

    def record_sequence(self, tasks: list[str]) -> None:
        """记录一个成功的任务序列，更新边权重"""
        for i in range(len(tasks) - 1):
            a = self._normalize(tasks[i])
            b = self._normalize(tasks[i + 1])
            self.graph.setdefault(a, {})
            self.graph[a][b] = self.graph[a].get(b, 0) + 1
        self._save()

    def suggest_next(self, current_task: str, top_k: int = 3) -> list[dict]:
        """给定当前任务，推荐最可能的下一步"""
        key = self._normalize(current_task)
        neighbors = self.graph.get(key, {})
        if not neighbors:
            return []
        sorted_n = sorted(neighbors.items(), key=lambda x: x[1], reverse=True)
        return [{"next_task": k, "frequency": v} for k, v in sorted_n[:top_k]]

    def find_workflow(self, goal: str, max_steps: int = 6) -> list[str]:
        """
        从图中找出达成目标的最频繁路径（贪心）
        不依赖LLM，从历史经验中直接提取"直觉工作流"
        """
        path = [self._normalize(goal)]
        visited = set(path)
        for _ in range(max_steps - 1):
            nexts = self.suggest_next(path[-1])
            if not nexts:
                break
            candidate = next((n for n in nexts if n["next_task"] not in visited), None)
            if not candidate:
                break
            path.append(candidate["next_task"])
            visited.add(candidate["next_task"])
        return path

    def _normalize(self, task: str) -> str:
        """任务类型标准化"""
        t = task.lower().strip()
        if any(w in t for w in ["代码","code","写","fix","bug"]): return "coding"
        if any(w in t for w in ["测试","test","验证"]):            return "testing"
        if any(w in t for w in ["部署","deploy","启动"]):          return "deploy"
        if any(w in t for w in ["调试","debug","断点"]):           return "debug"
        if any(w in t for w in ["搜索","search","查找"]):          return "search"
        if any(w in t for w in ["分析","analyze","总结"]):         return "analysis"
        if any(w in t for w in ["vscode","ide","编辑器"]):         return "ide_ops"
        if any(w in t for w in ["记忆","memory","存储"]):          return "memory_ops"
        return t[:20]

    def _save(self) -> None:
        _ensure(BRAIN_DIR)
        self._path.write_text(json.dumps(self.graph, ensure_ascii=False, indent=2))

    def _load(self) -> dict:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}


# ══════════════════════════════════════════════
# 4. 算法自研引擎（Algorithm Researcher）
# ══════════════════════════════════════════════

class AlgorithmResearcher:
    """
    Kylo 像下载 Skill 一样主动研究并集成新算法。

    流程：
      1. 检测能力缺口（哪类任务失败率高）
      2. 搜索可信输入库（arXiv/Papers with Code/GitHub）
      3. LLM评估实现可行性（只在这步调API）
      4. 生成概念验证代码
      5. 写入 skill_evolution/researcher.py 格式
      6. 人工确认后集成

    可信输入库（不访问随机网站，只访问白名单）：
      · paperswithcode.com/sota
      · huggingface.co/papers
      · github.com/trending/python
      · arxiv.org/search（关键词查询）
    """

    TRUSTED_SOURCES = {
        "papers_with_code": "https://paperswithcode.com/search?q_meta=&q_type=&q={query}",
        "hf_papers":        "https://huggingface.co/papers?q={query}",
        "github_trending":  "https://api.github.com/search/repositories?q={query}+language:python&sort=stars",
    }

    def __init__(self, llm_caller: Optional[Callable] = None) -> None:
        self.llm_caller = llm_caller
        self._output_dir = _ensure(SKILLS_DIR / "kylobrain_research")

    def detect_capability_gaps(self, warm_memory) -> list[dict]:
        """
        从失败记录中自动检测能力缺口：
        哪类任务失败率>40%且样本>3次 = 能力缺口
        """
        patterns = warm_memory.read_all("patterns")
        gaps = []
        for p in patterns:
            rate = p.get("success_rate", 1.0)
            count = p.get("sample_count", 0)
            if rate < 0.6 and count >= 3:
                gaps.append({
                    "task_type":    p["task_type"],
                    "success_rate": rate,
                    "gap":          f"{p['task_type']}任务成功率仅{rate:.0%}，需要改进算法",
                    "priority":     "high" if rate < 0.4 else "medium",
                })
        return sorted(gaps, key=lambda g: g["success_rate"])

    def search_algorithms(self, capability_gap: str) -> list[dict]:
        """
        在可信库中搜索相关算法（只读标题和摘要，不执行代码）
        返回候选算法列表供LLM评估
        """
        query = capability_gap.replace(" ", "+")[:50]
        candidates = []
        # GitHub 代码搜索（最实用）
        url = f"https://api.github.com/search/repositories?q={query}+language:python&sort=stars&per_page=5"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "KyloBrain/2.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read().decode())
                for item in data.get("items", [])[:5]:
                    candidates.append({
                        "source":      "github",
                        "name":        item.get("name", ""),
                        "description": item.get("description", ""),
                        "stars":       item.get("stargazers_count", 0),
                        "url":         item.get("html_url", ""),
                        "language":    item.get("language", ""),
                    })
        except Exception as e:
            candidates.append({"source": "search_failed", "error": str(e)})
        return candidates

    def evaluate_and_prototype(self, gap: dict, candidates: list[dict]) -> dict:
        """
        用LLM评估候选算法，生成概念验证代码
        这是整个流程唯一消耗API的步骤
        """
        if not self.llm_caller:
            return {"status": "no_llm", "gap": gap["gap"]}

        prompt = f"""
你是 Kylopro 的算法研究助手。分析以下能力缺口并给出解决方案：

能力缺口：{gap['gap']}
当前成功率：{gap['success_rate']:.0%}
找到的候选库：
{json.dumps(candidates[:3], ensure_ascii=False, indent=2)}

请：
1. 推荐最适合集成的算法/库（考虑零依赖优先）
2. 写出概念验证代码（<30行Python，标准库优先）
3. 说明如何集成到现有 KyloBrain

回复格式：
ALGORITHM: [算法名]
RATIONALE: [选择理由，1句话]
CODE:
```python
[代码]
```
INTEGRATION: [集成步骤，2-3行]
"""
        response = self.llm_caller(prompt)
        result = self._parse_llm_response(response, gap)
        self._save_research(gap, candidates, result)
        return result

    def _parse_llm_response(self, response: str, gap: dict) -> dict:
        result = {"gap": gap["gap"], "raw_response": response}
        # 提取算法名
        m = re.search(r"ALGORITHM:\s*(.+)", response)
        if m:
            result["algorithm"] = m.group(1).strip()
        # 提取代码
        m = re.search(r"```python\n(.+?)```", response, re.DOTALL)
        if m:
            result["prototype_code"] = m.group(1).strip()
        # 提取集成建议
        m = re.search(r"INTEGRATION:\s*(.+?)(?=\n[A-Z]+:|$)", response, re.DOTALL)
        if m:
            result["integration"] = m.group(1).strip()
        return result

    def _save_research(self, gap: dict, candidates: list, result: dict) -> None:
        ts = int(time.time())
        out = self._output_dir / f"research_{ts}_{gap['task_type']}.json"
        out.write_text(json.dumps({
            "timestamp": ts, "gap": gap,
            "candidates": candidates, "result": result,
        }, ensure_ascii=False, indent=2))

    def full_research_cycle(self, warm_memory) -> list[dict]:
        """完整自研周期：检测缺口→搜索→评估→保存草稿"""
        gaps = self.detect_capability_gaps(warm_memory)
        if not gaps:
            return [{"status": "no_gaps", "message": "所有技能成功率良好，无需研究新算法"}]
        results = []
        for gap in gaps[:2]:  # 每次最多处理2个缺口，避免API过载
            candidates = self.search_algorithms(gap["gap"])
            result = self.evaluate_and_prototype(gap, candidates)
            results.append(result)
        return results


# ══════════════════════════════════════════════
# 5. ReAct 循环质量监控
# ══════════════════════════════════════════════

class ReActMonitor:
    """
    监控 ReAct 循环质量，解决"思考被折叠"问题。

    问题根源：nanobot 的 responder.py 在 tool_call 模式下，
    Thought 字段被折叠进 tool_call 结构体，不显示在对话中，
    用户看不到推理过程，Kylo 也缺少自我检查的机会。

    检测逻辑：
    · 检查响应中是否包含 Thought/思考/分析 等推理标记
    · 检查是否有"直接行动"而没有推理前置
    · 检测"滑跪模式"：认错词汇 + 用户未提供新证据

    修复建议：
    · SOUL.md 追加强化推理指令
    · responder.py 后处理：检测滑跪并拦截
    """

    THINKING_MARKERS = [
        "思考", "分析", "考虑", "判断", "因为", "所以",
        "thought:", "thinking:", "reason:", "because", "therefore",
        "[分析]", "[思考]", "让我想想", "首先分析",
    ]
    CAPITULATION_MARKERS = [
        "你说得对", "我错了", "对不起，我之前错了", "你是对的",
        "我承认错误", "我之前的回答有误", "您说得有道理",
        "you're right", "i was wrong", "i apologize for the error",
    ]
    EVIDENCE_MARKERS = [
        "根据", "文档显示", "实验结果", "查看了", "运行结果",
        "according to", "the result shows", "i tested",
    ]

    def analyze_response(self, response: str, user_message: str = "") -> dict:
        """分析一条响应的质量"""
        resp_lower = response.lower()
        user_lower = user_message.lower()

        has_thinking    = any(m in resp_lower for m in self.THINKING_MARKERS)
        is_capitulation = any(m in resp_lower for m in self.CAPITULATION_MARKERS)
        has_evidence    = any(m in user_lower for m in self.EVIDENCE_MARKERS)
        false_surrender = is_capitulation and not has_evidence

        issues = []
        if not has_thinking:
            issues.append("缺少推理过程（Thought 被折叠或跳过）")
        if false_surrender:
            issues.append("检测到无证据认错（滑跪模式）")

        quality = "good"
        if len(issues) == 1:
            quality = "warning"
        elif len(issues) >= 2:
            quality = "poor"

        return {
            "quality":          quality,
            "has_thinking":     has_thinking,
            "is_capitulation":  is_capitulation,
            "false_surrender":  false_surrender,
            "issues":           issues,
        }

    def generate_soul_patch(self) -> str:
        """生成要追加到 SOUL.md 的强化推理指令"""
        return """
---
## 核心原则：推理诚信

### 思考过程
每次回答前，我都会：
1. 先在心里明确"我现在知道什么、不知道什么"
2. 如果使用工具，先说明"我要用这个工具因为..."
3. 把推理链路显式化：[分析] → [判断] → [行动]

### 立场坚守
当用户对我的结论提出质疑时：
- ✅ 用户提供了新证据 → 我认真评估，可能改变立场
- ❌ 用户只是重复或表达不满 → 我礼貌坚持，并说明依据
- 公式："我理解你的看法，但我的判断依据是X，
         除非你能指出X的具体错误，否则我暂时维持这个结论。"
- 绝对禁止：没有新证据就说"你说得对我错了"

### 不确定性处理
- 确定知道的：直接陈述
- 不确定的：明确说"我的把握约X%，原因是..."
- 完全不知道的：说"我不知道，但我可以帮你找"
---"""

    def patch_responder_hint(self) -> str:
        """返回可以加入 responder.py 的后处理建议代码片段"""
        return '''
# 在 responder.py 的响应后处理中添加：
def post_process_response(response: str, user_msg: str) -> str:
    """检测并处理质量问题"""
    from metacog_algorithms import ReActMonitor
    monitor = ReActMonitor()
    analysis = monitor.analyze_response(response, user_msg)
    
    if analysis["false_surrender"]:
        # 不直接修改响应（可能破坏语义），记录到大脑警告层
        # 让Kylo在下一轮意识到这个问题
        import warnings
        warnings.warn(f"[ReActMonitor] 检测到无证据认错，建议review此响应")
    
    return response  # 返回原响应，监控而不干预
'''


# ══════════════════════════════════════════════
# 综合元认知接口
# ══════════════════════════════════════════════

class MetaCogAlgorithms:
    """统一入口，把所有算法组合起来"""

    def __init__(self, llm_caller: Optional[Callable] = None) -> None:
        self.calibrator  = ConfidenceCalibrator()
        self.bloom       = FailureBloomFilter()
        self.graph       = PatternGraph()
        self.researcher  = AlgorithmResearcher(llm_caller)
        self.react_mon   = ReActMonitor()

    def pre_task_check(self, task: str, confidence: float) -> dict:
        """任务前综合检查（零API）"""
        bloom_hit    = self.bloom.might_fail(task)
        adj_conf     = self.calibrator.adjust_confidence(confidence)
        next_suggest = self.graph.suggest_next(task)
        return {
            "bloom_warning":        bloom_hit,
            "adjusted_confidence":  adj_conf,
            "raw_confidence":       confidence,
            "calibration_factor":   round(self.calibrator.calibration_factor(), 3),
            "workflow_hint":        next_suggest[:2] if next_suggest else [],
        }

    def post_task_update(
        self, task: str, success: bool,
        predicted_conf: float, sequence: list[str] = None,
    ) -> None:
        """任务后更新所有算法（零API）"""
        self.calibrator.record(predicted_conf, success, context=task[:80])
        if not success:
            self.bloom.remember_failure(task)
        if sequence and len(sequence) >= 2:
            self.graph.record_sequence(sequence)

    def full_status(self) -> dict:
        return {
            "calibration":   self.calibrator.report(),
            "bloom_fpr":     round(self.bloom.false_positive_rate(), 4),
            "graph_nodes":   len(self.graph.graph),
        }

    def apply_soul_patches(self) -> dict:
        """生成所有需要加进 SOUL.md 的补丁"""
        return {
            "react_patch":    self.react_mon.generate_soul_patch(),
            "responder_hint": self.react_mon.patch_responder_hint(),
        }


# ══════════════════════════════════════════════
# CLI 测试
# ══════════════════════════════════════════════

if __name__ == "__main__":
    print("🔬 MetaCog Algorithms — 单元测试")
    print("=" * 48)

    algos = MetaCogAlgorithms()

    print("\n[1] 置信校准器测试...")
    algos.calibrator.record(0.9, True,  "预测成功-实际成功")
    algos.calibrator.record(0.9, True,  "预测成功-实际成功")
    algos.calibrator.record(0.9, False, "预测成功-实际失败")
    algos.calibrator.record(0.5, True,  "预测50%-实际成功")
    report = algos.calibrator.report()
    print(f"    Brier Score: {report['brier_score']}")
    print(f"    校准系数: {report['calibration_factor']}")
    print(f"    过度自信: {report['over_confident']}")
    adj = algos.calibrator.adjust_confidence(0.9)
    print(f"    90%置信度校准后: {adj}")

    print("\n[2] 失败布隆过滤器测试...")
    algos.bloom.remember_failure("修复Python环境依赖问题")
    algos.bloom.remember_failure("安装pip包时权限错误")
    print(f"    'Python环境'命中: {algos.bloom.seen_before('调试Python虚拟环境'):.2f}")
    print(f"    '全新任务'命中: {algos.bloom.seen_before('写一个天气查询脚本'):.2f}")
    print(f"    当前误报率: {algos.bloom.false_positive_rate():.4f}")

    print("\n[3] 技能依赖图测试...")
    algos.graph.record_sequence(["coding", "testing", "debug", "deploy"])
    algos.graph.record_sequence(["coding", "testing", "deploy"])
    algos.graph.record_sequence(["search", "analysis", "coding"])
    nexts = algos.graph.suggest_next("coding")
    print(f"    coding之后推荐: {[n['next_task'] for n in nexts]}")
    workflow = algos.graph.find_workflow("实现新功能并部署")
    print(f"    推荐工作流: {' → '.join(workflow)}")

    print("\n[4] ReAct监控测试...")
    good_resp = "让我分析一下这个问题：[分析] 这里涉及到Python路径配置..."
    bad_resp  = "你说得对，我之前的回答确实有误，抱歉。"
    g = algos.react_mon.analyze_response(good_resp)
    b = algos.react_mon.analyze_response(bad_resp, user_message="我觉得你错了")
    print(f"    好响应质量: {g['quality']} (思考:{g['has_thinking']})")
    print(f"    滑跪响应: {b['quality']} 问题: {b['issues']}")

    print("\n[5] 综合任务前检查...")
    check = algos.pre_task_check("修复Python环境依赖问题", confidence=0.85)
    print(f"    布隆警告: {check['bloom_warning']}")
    print(f"    校准后置信度: {check['adjusted_confidence']}")

    print("\n✅ 所有算法测试通过")
