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

import time
from typing import Any, Callable, Optional

from skills.oauth2_vault.vault import get_oauth2_vault, OAuth2VaultDB


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
        - 未过期 → 直接返回
        - 已过期 → 自动刷新 → 返回新 token
        - 刷新失败 → 返回 None
        """
        if self._vault.is_expired(platform):
            ok = self._auto_refresh(platform)
            if not ok:
                return None
        creds = self._vault.get(platform)
        if not creds:
            return None
        # 优先返回 access_token，其次 app_access_token（飞书服务端）
        return creds.get("access_token") or creds.get("app_access_token")

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
              "need_reauth": bool,    # 是否需要重新授权
            }
        """
        start = time.time()
        extra_tags = tags or []

        token = self.get_valid_token(platform)
        if not token:
            result: dict = {
                "success": False,
                "error": f"{platform} 未配置授权或 token 已失效，请先调用 oauth2_vault(action='setup') 配置凭证",
                "need_reauth": True,
            }
        else:
            try:
                output = fn(token)
                result = {"success": True, "output": output, "need_reauth": False}
            except Exception as e:
                result = {
                    "success": False,
                    "error": str(e),
                    "need_reauth": False,
                }

        duration = time.time() - start

        # 写入 WARM episodes（outcome 不含 token 原文）
        warm = _get_warm()
        if warm:
            outcome = str(result.get("output") or result.get("error") or "")[:200]
            warm.record_episode(
                task=f"{platform}:{task_name}",
                steps=["get_token", "execute"],
                outcome=outcome,
                duration_sec=duration,
                success=result["success"],
                tags=["oauth2", platform, "external_action"] + extra_tags,
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
