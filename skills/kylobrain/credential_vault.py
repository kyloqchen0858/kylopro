"""
KyloBrain · CredentialVault
============================
Kylo 专属账户凭据保险柜。

设计原则：
  1. brain/vault/accounts.json   — 只存元数据（账户名、服务类型、env_key）
  2. brain/vault/.kylo_secrets.env — 存凭据实际值（仅本机可读，gitignore）
  3. 凭据实际值优先读环境变量 → 再读 .kylo_secrets.env → 返回 None
  4. 所有对外输出（日志、Telegram、工具响应）一律用 get_masked()，绝不暴露原文
  5. vault 的 accounts.json 永远不推送到 COLD / Gist

安全分级：
  NEVER → 凭据原文出现在：tool 返回值、Telegram 消息、任何日志文件
  ALWAYS → 输出时调用 get_masked() 或 status()

账户命名规范（alias）：
  github_kylo        — Kylo 的 GitHub 账户
  google_kylo        — Kylo 的 Google 账户
  telegram_kylo      — 机器人 token（已在 nanobot config 中，此处作引用登记）
  twitter_kylo       — 未来的 Twitter/X 账户
  instagram_kylo     — 未来的 Instagram 账户（以此类推）
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

BASE_DIR  = Path(os.environ.get("KYLOPRO_DIR", Path.home() / "Kylopro-Nexus"))
VAULT_DIR = BASE_DIR / "brain" / "vault"
ACCOUNTS_FILE = VAULT_DIR / "accounts.json"
SECRETS_FILE  = VAULT_DIR / ".kylo_secrets.env"   # 绝不 git commit


# ══════════════════════════════════════════════
# 内部工具
# ══════════════════════════════════════════════

def _mask(value: str) -> str:
    """脱敏：前 6 + *** + 后 4。长度不足时全部遮盖。"""
    if not value:
        return "[空]"
    if len(value) < 14:
        return "***"
    return f"{value[:6]}***{value[-4:]}"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _load_secrets() -> dict:
    """读取 .kylo_secrets.env 文件，返回 {KEY: value} 字典。"""
    if not SECRETS_FILE.exists():
        return {}
    result = {}
    for line in SECRETS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result


def _save_secrets(data: dict) -> None:
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "# KyloBrain 凭据文件",
        "# ⚠️  绝不 git commit / 绝不发送到 Telegram / 绝不写入 Gist",
        f"# 最后更新: {_now()}",
        "",
    ]
    for k, v in data.items():
        lines.append(f"{k}={v}")
    SECRETS_FILE.write_text("\n".join(lines), encoding="utf-8")
    try:
        SECRETS_FILE.chmod(0o600)  # 仅文件所有者可读写
    except Exception:
        pass  # Windows 上 chmod 权限不同，静默跳过


# ══════════════════════════════════════════════
# CredentialVault
# ══════════════════════════════════════════════

class CredentialVault:
    """
    Kylo 账户凭据保险柜。

    示例用法：
        vault = CredentialVault()

        # 注册账户（只需一次）
        vault.register("github_kylo", service="github",
                       description="Kylo 专用 GitHub 账户",
                       username="kylo-autoagent",
                       email="kylo@yourmail.com")

        # 存入凭据（用户提供时调用）
        vault.set("github_kylo", "ghp_xxxx...")

        # 内部使用（获取原文）
        token = vault.get("github_kylo")

        # 对外输出（脱敏）— 永远用这个
        print(vault.get_masked("github_kylo"))   # ghp_***...5djJk

        # 汇报状态（不含凭据值）
        print(vault.status())
    """

    def __init__(self) -> None:
        VAULT_DIR.mkdir(parents=True, exist_ok=True)
        self._accounts: dict = {}
        self._reload()

    def _reload(self) -> None:
        if ACCOUNTS_FILE.exists():
            try:
                self._accounts = json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
            except Exception:
                self._accounts = {}

    def _persist(self) -> None:
        ACCOUNTS_FILE.write_text(
            json.dumps(self._accounts, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── 账户管理 ──

    def register(
        self,
        alias: str,
        service: str,
        description: str = "",
        username: str = "",
        email: str = "",
        env_key: str = "",
        notes: str = "",
    ) -> dict:
        """
        注册一个账户（不需要立即提供凭据值）。

        alias    — 内部标识符，字母数字下划线，如 github_kylo
        service  — 服务名，如 github / google / telegram / twitter
        env_key  — 凭据对应的环境变量键名（留空自动生成）
        """
        if not env_key:
            env_key = f"KYLO_{alias.upper().replace('-', '_')}"
        self._accounts[alias] = {
            "alias":       alias,
            "service":     service,
            "description": description,
            "username":    username,
            "email":       email,
            "env_key":     env_key,
            "notes":       notes,
            "has_secret":  alias in self._accounts and self._accounts[alias].get("has_secret", False),
            "registered":  self._accounts.get(alias, {}).get("registered", _now()),
            "updated":     _now(),
        }
        self._persist()
        return {"registered": alias, "env_key": env_key}

    def set(self, alias: str, credential_value: str) -> dict:
        """
        存储凭据原文到 .kylo_secrets.env。

        返回脱敏确认（不含原值）。
        """
        if alias not in self._accounts:
            raise KeyError(f"账户 '{alias}' 未注册，请先调用 register()")
        env_key = self._accounts[alias]["env_key"]
        secrets = _load_secrets()
        secrets[env_key] = credential_value
        _save_secrets(secrets)
        self._accounts[alias]["has_secret"] = True
        self._accounts[alias]["updated"] = _now()
        self._persist()
        return {
            "stored":   alias,
            "env_key":  env_key,
            "masked":   _mask(credential_value),
            "note":     "凭据已存入本地保险柜，可通过 vault.get() 取用",
        }

    def get(self, alias: str) -> Optional[str]:
        """
        获取凭据原文（内部逻辑使用）。

        优先顺序：
          1. 系统环境变量（最高优先级）
          2. brain/vault/.kylo_secrets.env
          3. None（未配置）

        ⚠️  此返回值绝不能直接发送到 Telegram / 写入日志 / 出现在 tool 响应正文。
        """
        if alias not in self._accounts:
            return None
        env_key = self._accounts[alias]["env_key"]
        # 优先系统环境变量
        v = os.environ.get(env_key)
        if v:
            return v
        # 其次本地密钥文件
        return _load_secrets().get(env_key)

    def get_masked(self, alias: str) -> str:
        """
        返回脱敏表示（安全输出）。

        这是唯一允许出现在工具响应 / 日志 / 消息中的凭据显示方式。
        """
        val = self.get(alias)
        if val is None:
            return f"[{alias}: 未配置]"
        return f"{self._accounts[alias]['service']}:{_mask(val)}"

    def update_notes(self, alias: str, notes: str) -> None:
        """更新账户备注（用于记录用途、关联项目等）。"""
        if alias in self._accounts:
            self._accounts[alias]["notes"] = notes
            self._accounts[alias]["updated"] = _now()
            self._persist()

    def list_accounts(self) -> list:
        """列出所有账户元数据（不含凭据值）。"""
        return [
            {
                "alias":       a,
                "service":     v.get("service", ""),
                "username":    v.get("username", ""),
                "email":       v.get("email", ""),
                "has_secret":  v.get("has_secret", False),
                "env_key":     v.get("env_key", ""),
                "notes":       v.get("notes", ""),
            }
            for a, v in self._accounts.items()
        ]

    def status(self) -> dict:
        """
        汇总保险柜状态（安全，不含凭据原文）。

        适合直接展示给用户或写入日志。
        """
        accounts = self.list_accounts()
        return {
            "total":      len(accounts),
            "configured": sum(1 for a in accounts if a["has_secret"]),
            "accounts":   accounts,
        }


# ══════════════════════════════════════════════
# 单例访问器
# ══════════════════════════════════════════════

_vault_instance: Optional[CredentialVault] = None


def get_vault() -> CredentialVault:
    """返回全局保险柜单例（惰性初始化）。"""
    global _vault_instance
    if _vault_instance is None:
        _vault_instance = CredentialVault()
    return _vault_instance
