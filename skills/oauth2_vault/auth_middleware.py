"""
AuthMiddleware — OAuth2 授权中间件
===================================

功能：
  1. 从 OAuth2VaultDB 获取有效 token（自动检查过期）
  2. 过期 → 调用平台注册的 refresher 函数 → 写回 Vault → 继续
  3. 刷新失败 → 返回 need_reauth=True（让 Skill 告知用户重新授权）
  4. 所有执行结果自动写回 WarmMemory episodes（让大脑积累真实操作经验）

设计：
  · 零 nanobot 核心修改，通过 Skill + Tool 接入
  · WarmMemory 依赖懒加载（brain 不可用时降级静默，不阻断执行）
  · 凭证永远不出现在 episode 文本正文（outcome 字段过滤 token）

用法：
    from skills.oauth2_vault.auth_middleware import get_middleware
    mw = get_middleware()

    # 注册平台的 token 刷新函数
    mw.register_refresher("feishu", feishu_platform.refresh_app_token)

    # 带授权执行
    result = mw.execute_with_auth(
        platform="feishu",
        task_name="创建飞书文档",
        fn=lambda token: feishu_platform.create_doc(token, title, content),
    )
"""

from __future__ import annotations

import re
import time
from typing import Any, Callable, Optional

from skills.oauth2_vault.vault import get_oauth2_vault, OAuth2VaultDB


# ── Token 脱敏：防止 token 泄漏到 episode 正文 ───────────────
_TOKEN_PATTERNS = re.compile(
    r'(t-[A-Za-z0-9_-]{20,})'       # 飞书 app_access_token
    r'|(Bearer\s+[A-Za-z0-9_.-]{20,})'  # Bearer token
    r'|(secret_[A-Za-z0-9_-]{20,})'     # Notion integration secret
    r'|([A-Za-z0-9_-]{40,})',          # 长随机串（通用 token 特征）
    re.ASCII,
)


def _scrub_tokens(text: str) -> str:
    """移除可能的 token 值，替换为 [REDACTED]。"""
    return _TOKEN_PATTERNS.sub('[REDACTED]', text)


def _is_retryable_error(exc: Exception) -> bool:
    """判断是否属于可自动重试一次的暂态错误。"""
    msg = str(exc).lower()
    # 网络波动/超时/连接中断
    transient_keywords = (
        "timeout",
        "timed out",
        "connection reset",
        "temporarily unavailable",
        "connection aborted",
        "name or service not known",
    )
    if any(k in msg for k in transient_keywords):
        return True

    # API 层限流/服务端错误（429 / 5xx）
    if "http 429" in msg or "too many requests" in msg:
        return True
    if re.search(r"http\s+5\d\d", msg):
        return True

    return False


def _classify_platform_failure(platform: str, task_name: str, error_text: str) -> tuple[str, str]:
    """Return (failure_signature, recovery_hint) for reuse by pre_task and operator outputs."""
    err = (error_text or "").lower()
    task = (task_name or "").lower()

    if platform == "feishu":
        if "http 404" in err and ("docx" in err or "document" in task):
            return (
                "feishu.doc_api_404",
                "检查文档接口路径与应用权限（docx/document），确认租户已发布并具备云文档权限。",
            )
        if "need_reauth" in err or "未配置" in err or "token" in err and "失效" in err:
            return (
                "feishu.auth_missing_or_expired",
                "先执行 oauth2_vault setup 并验证 get_token，再重试飞书动作。",
            )
        if "open_id" in err or "receive_id" in err:
            return (
                "feishu.invalid_receive_id",
                "校验 user_open_id/chat_id 的真实格式，优先使用 open_id=ou_xxx。",
            )
        if any(k in err for k in ("timeout", "timed out", "connection", "temporarily unavailable", "http 429", "http 5")):
            return (
                "feishu.transient_network_or_rate_limit",
                "属于暂态异常，已自动重试一次；如持续失败建议稍后重试并保留错误码。",
            )

    return (f"{platform}.generic_failure", "记录错误码与上下文，先做最小动作验证（status/get_token/send_message）。")


def _task_type_for_pattern(platform: str, task_name: str) -> str:
    action = (task_name or "").split(":", 1)[0] or "action"
    return f"{platform}:{action}"


# ── WarmMemory 懒加载（brain 不可用时不崩溃） ─────────────────
def _get_warm():
    try:
        from skills.kylobrain.cloud_brain import WarmMemory
        return WarmMemory()
    except Exception:
        return None


class AuthMiddleware:
    """
    OAuth2 授权中间件。

    · 每个平台只需注册一次 refresher（在平台 adapter 初始化时）
    · execute_with_auth 是所有外部 API 调用的统一入口
    · 执行结果自动写入 WARM episodes（成功/失败都记录）
    """

    def __init__(self, vault: Optional[OAuth2VaultDB] = None) -> None:
        self._vault = vault or get_oauth2_vault()
        self._refreshers: dict[str, Callable[[dict], dict]] = {}

    def register_refresher(self, platform: str, fn: Callable[[dict], dict]) -> None:
        """
        注册平台的 token 刷新函数。
        fn 接受完整 creds dict，返回包含新 token 的 dict。
        """
        self._refreshers[platform] = fn

    # ── Token 获取（带自动刷新） ──────────────────────────────

    def get_valid_token(self, platform: str) -> Optional[str]:
        """
        获取有效 access_token：
        - 有 token 且未过期 → 直接返回
        - 无 token 或已过期 → 自动刷新 → 返回新 token
        - 刷新失败 → 返回 None
        """
        creds = self._vault.get(platform)
        if not creds:
            return None

        token = creds.get("access_token") or creds.get("app_access_token")
        need_refresh = not token or self._vault.is_expired(platform)

        if need_refresh:
            ok = self._auto_refresh(platform)
            if not ok:
                return None
            creds = self._vault.get(platform)
            if not creds:
                return None
            token = creds.get("access_token") or creds.get("app_access_token")

        return token

    def _auto_refresh(self, platform: str) -> bool:
        """尝试刷新 token，成功返回 True，失败返回 False。"""
        creds = self._vault.get(platform)
        if not creds:
            return False

        refresher = self._refreshers.get(platform)
        if not refresher:
            return False

        start = time.time()
        try:
            new_creds = refresher(creds)
            # 合并更新（保留 app_id / app_secret 等静态字段）
            creds.update(new_creds)
            self._vault.store(platform, creds)
            duration = time.time() - start

            warm = _get_warm()
            if warm:
                warm.record_episode(
                    task=f"oauth2:{platform}:auto_refresh",
                    steps=["check_expiry", "call_refresh", "store_new_token"],
                    outcome="token 刷新成功",
                    duration_sec=duration,
                    success=True,
                    tags=["oauth2", "auto_refresh", platform],
                )
            return True
        except Exception as e:
            warm = _get_warm()
            if warm:
                warm.record_episode(
                    task=f"oauth2:{platform}:auto_refresh",
                    steps=["check_expiry", "call_refresh"],
                    outcome=f"刷新失败: {type(e).__name__}",
                    duration_sec=time.time() - start,
                    success=False,
                    tags=["oauth2", "auto_refresh", platform, "failure"],
                )
            return False

    # ── 带授权执行 ────────────────────────────────────────────

    def execute_with_auth(
        self,
        platform: str,
        task_name: str,
        fn: Callable[[str], Any],
        tags: Optional[list[str]] = None,
    ) -> dict:
        """
        带授权的统一执行入口。

        Args:
            platform:  平台名（"feishu", "notion" 等）
            task_name: 任务描述，写入 episode（不含 token）
            fn:        接受 access_token str，返回任意执行结果
            tags:      附加 episode 标签

        Returns:
            {
              "success": bool,
              "output":  ...,         # 成功时的返回值
              "error":   str,         # 失败时的错误描述
              "operator_hint": str,   # 失败时给用户/操作者的下一步建议
              "need_reauth": bool,    # 是否需要重新授权
                            "retried": bool,        # 是否自动重试过一次
                            "terminal": bool,       # 是否应当停止继续尝试
            }
        """
        start = time.time()
        extra_tags = tags or []

        token = self.get_valid_token(platform)
        if not token:
            result: dict = {
                "success": False,
                "error": f"{platform} 未配置授权或 token 已失效，请先调用 oauth2_vault(action='setup') 配置凭证",
                "operator_hint": "先 setup，再 get_token 验证；通过后再执行外部动作。",
                "need_reauth": True,
                "retried": False,
                "terminal": True,
            }
        else:
            retried = False
            try:
                output = fn(token)
                result = {
                    "success": True,
                    "output": output,
                    "operator_hint": "",
                    "need_reauth": False,
                    "retried": False,
                    "terminal": True,
                }
            except Exception as e:
                if _is_retryable_error(e):
                    retried = True
                    try:
                        output = fn(token)
                        result = {
                            "success": True,
                            "output": output,
                            "operator_hint": "",
                            "need_reauth": False,
                            "retried": True,
                            "terminal": True,
                        }
                    except Exception as e2:
                        signature, hint = _classify_platform_failure(platform, task_name, str(e2))
                        result = {
                            "success": False,
                            "error": f"{e2}（已自动重试 1 次）",
                            "error_signature": signature,
                            "operator_hint": hint,
                            "need_reauth": False,
                            "retried": True,
                            "terminal": True,
                        }
                else:
                    signature, hint = _classify_platform_failure(platform, task_name, str(e))
                    result = {
                        "success": False,
                        "error": str(e),
                        "error_signature": signature,
                        "operator_hint": hint,
                        "need_reauth": False,
                        "retried": retried,
                        "terminal": True,
                    }

        duration = time.time() - start

        # 写入 WARM episodes（outcome 不含 token 原文）
        warm = _get_warm()
        if warm:
            outcome = str(result.get("output") or result.get("error") or "")[:200]
            outcome = _scrub_tokens(outcome)
            warm.record_episode(
                task=f"{platform}:{task_name}",
                steps=["get_token", "execute"],
                outcome=outcome,
                duration_sec=duration,
                success=result["success"],
                tags=["oauth2", platform, "external_action"] + extra_tags,
            )

            # Structured learning loop: convert tool outcomes into reusable failure/pattern memory.
            task_type = _task_type_for_pattern(platform, task_name)
            warm.upsert_pattern(task_type, "oauth2_auth_middleware", bool(result.get("success")), sample_weight=0.25)
            if not result.get("success"):
                signature = str(result.get("error_signature") or "")
                hint = str(result.get("operator_hint") or "")
                error_text = _scrub_tokens(str(result.get("error") or ""))[:240]
                warm.record_failure(
                    task=f"{platform}:{task_name}",
                    error=signature or error_text,
                    recovery=hint,
                )

        return result

    # ── 平台状态摘要 ──────────────────────────────────────────

    def platform_status(self) -> list[dict]:
        return self._vault.list_platforms()


# ── 进程内单例 ────────────────────────────────────────────────
_middleware_instance: Optional[AuthMiddleware] = None


def get_middleware() -> AuthMiddleware:
    global _middleware_instance
    if _middleware_instance is None:
        _middleware_instance = AuthMiddleware()
    return _middleware_instance
