"""
OAuth2VaultDB — SQLite + Fernet 加密凭证保险箱
================================================

职责：
  · 存储平台 OAuth2 凭证（access_token / refresh_token / expires_at）
  · 使用 Fernet 对称加密，密钥存放在 brain/vault/.oauth2_vault_key（600 权限）
  · 绝不把 token 写进 WARM/HOT/COLD 记忆正文，绝不在对话中显示明文

与 kylobrain/credential_vault.py 的分工：
  · credential_vault.py  → 账户元信息 + API Key（静态凭据，env 文件格式）
  · this file            → OAuth2 动态 token（有到期时间，需要自动刷新，SQLite存储）

用法：
    from skills.oauth2_vault.vault import OAuth2VaultDB
    vault = OAuth2VaultDB()
    vault.store("feishu", {
        "app_id": "cli_xxx",
        "app_secret": "secret",
        "app_access_token": "t-xxx",
        "expires_at": time.time() + 7200,
    })
    creds = vault.get("feishu")
    expired = vault.is_expired("feishu")
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import platform
import secrets
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Optional

try:
    from cryptography.fernet import Fernet, InvalidToken
    _FERNET_AVAILABLE = True
except ImportError:
    _FERNET_AVAILABLE = False


# ── 路径配置 ──────────────────────────────────────────────────
def _resolve_base_dir() -> Path:
    """Resolve Kylopro root robustly so restart command differences do not cause amnesia."""
    env_dir = os.environ.get("KYLOPRO_DIR", "").strip()
    if env_dir:
        return Path(env_dir).expanduser().resolve()

    # skills/oauth2_vault/vault.py -> Kylopro-Nexus/
    repo_guess = Path(__file__).resolve().parents[2]
    cwd = Path.cwd().resolve()
    home_guess = Path.home() / "Kylopro-Nexus"
    for candidate in (repo_guess, cwd, home_guess):
        if (candidate / "brain").exists() and (candidate / "skills").exists():
            return candidate
    return repo_guess


BASE_DIR  = _resolve_base_dir()
VAULT_DIR = BASE_DIR / "brain" / "vault"
VAULT_DB  = VAULT_DIR / "oauth2_credentials.db"
KEY_FILE  = VAULT_DIR / ".oauth2_vault_key"   # 256-bit Fernet key，不入 git

TOKEN_REFRESH_BUFFER_SEC = 300   # 提前 5 分钟视为过期，给刷新留余量


# ── 密钥文件保护 ──────────────────────────────────────────────
def _protect_key_file(path: Path) -> None:
    """跨平台保护密钥文件：Linux/Mac 用 chmod 600，Windows 用 attrib +H。"""
    try:
        if platform.system() == 'Windows':
            subprocess.run(['attrib', '+H', str(path)], check=False,
                           capture_output=True, timeout=5)
        else:
            path.chmod(0o600)
    except Exception:
        pass


# ── stdlib-only 加解密（无 cryptography 依赖时使用） ──────────
def _stdlib_encrypt(master_key: bytes, data: bytes) -> bytes:
    """PBKDF2 派生密钥 + XOR 流加密 + HMAC 完整性校验。stdlib only。"""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac('sha256', master_key, salt, 100_000)
    nonce = secrets.token_bytes(16)
    stream = hashlib.pbkdf2_hmac('sha256', dk, nonce, 1, dklen=len(data))
    ct = bytes(a ^ b for a, b in zip(data, stream))
    mac = hmac.new(dk, salt + nonce + ct, 'sha256').digest()
    return base64.b64encode(salt + nonce + mac + ct)


def _stdlib_decrypt(master_key: bytes, blob: bytes) -> bytes:
    """解密 _stdlib_encrypt 产生的密文。"""
    raw = base64.b64decode(blob)
    if len(raw) < 64:  # 16 salt + 16 nonce + 32 mac
        raise ValueError("密文数据损坏（长度不足）")
    salt, nonce, mac_stored, ct = raw[:16], raw[16:32], raw[32:64], raw[64:]
    dk = hashlib.pbkdf2_hmac('sha256', master_key, salt, 100_000)
    mac_computed = hmac.new(dk, salt + nonce + ct, 'sha256').digest()
    if not hmac.compare_digest(mac_stored, mac_computed):
        raise ValueError("凭证解密失败，可能密钥已更换或数据损坏")
    stream = hashlib.pbkdf2_hmac('sha256', dk, nonce, 1, dklen=len(ct))
    return bytes(a ^ b for a, b in zip(ct, stream))


# ── 内部工具 ─────────────────────────────────────────────────
def _mask_token(value: str) -> str:
    """脱敏：前4 + *** + 后4"""
    if not value or len(value) < 12:
        return "***"
    return f"{value[:4]}***{value[-4:]}"


class OAuth2VaultDB:
    """
    SQLite + Fernet 加密的 OAuth2 凭证保险箱。

    存储字段：
      platform     — 平台名，主键（如 "feishu", "notion"）
      encrypted    — Fernet 加密后的 JSON bytes
      updated_at   — 最后更新时间戳（float）

    凭证 dict 标准格式（store 时传入）：
      {
        "app_id":           "cli_xxx",         # 服务端应用: app_id
        "app_secret":       "xxx",             # 服务端应用: app_secret
        "access_token":     "t-xxx",           # OAuth2 access token（可选）
        "refresh_token":    "xxx",             # refresh token（可选）
        "expires_at":       1234567890.0,      # Unix 时间戳，0 表示永不过期
        "token_type":       "Bearer",
        "scope":            "...",             # 可选
        # 平台特有字段（如飞书 user_open_id、folder_token）也可以放这里
      }
    """

    def __init__(self) -> None:
        VAULT_DIR.mkdir(parents=True, exist_ok=True)
        self._fernet: Optional["Fernet"] = None
        raw_key = self._load_or_create_key()
        self._master_key = base64.urlsafe_b64decode(raw_key)  # 32 bytes
        if _FERNET_AVAILABLE:
            self._fernet = Fernet(raw_key)
        self._init_db()

    # ── 密钥管理 ─────────────────────────────────────────────

    def _load_or_create_key(self) -> bytes:
        if KEY_FILE.exists():
            return KEY_FILE.read_bytes()
        if _FERNET_AVAILABLE:
            key = Fernet.generate_key()
        else:
            # stdlib fallback: 32-byte random key, base64 encoded
            key = base64.urlsafe_b64encode(secrets.token_bytes(32))
        KEY_FILE.write_bytes(key)
        _protect_key_file(KEY_FILE)
        return key

    # ── 数据库初始化 ──────────────────────────────────────────

    def _init_db(self) -> None:
        with sqlite3.connect(VAULT_DB) as conn:
            conn.execute('PRAGMA journal_mode=WAL')       # 允许并发读写
            conn.execute('PRAGMA synchronous=NORMAL')     # 性能和安全的平衡
            conn.execute("""
                CREATE TABLE IF NOT EXISTS credentials (
                    platform    TEXT PRIMARY KEY,
                    encrypted   BLOB NOT NULL,
                    updated_at  REAL NOT NULL
                )
            """)

    # ── 加解密 ───────────────────────────────────────────────

    def _encrypt(self, data: dict) -> bytes:
        payload = json.dumps(data, ensure_ascii=False).encode()
        if self._fernet:
            return self._fernet.encrypt(payload)
        return _stdlib_encrypt(self._master_key, payload)

    def _decrypt(self, blob: bytes) -> dict:
        if self._fernet:
            try:
                return json.loads(self._fernet.decrypt(blob).decode())
            except Exception:
                raise ValueError("凭证解密失败，可能密钥已更换或数据损坏")
        return json.loads(_stdlib_decrypt(self._master_key, blob).decode())

    # ── CRUD ─────────────────────────────────────────────────

    def store(self, platform: str, creds: dict) -> None:
        """加密存储平台凭证（覆盖已有）。"""
        # 安全校验：禁止 token 出现在 print/log 之外的位置
        encrypted = self._encrypt(creds)
        with sqlite3.connect(VAULT_DB) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO credentials (platform, encrypted, updated_at)
                VALUES (?, ?, ?)
            """, (platform, encrypted, time.time()))

    def get(self, platform: str) -> Optional[dict]:
        """解密读取凭证，不存在返回 None。"""
        with sqlite3.connect(VAULT_DB) as conn:
            row = conn.execute(
                "SELECT encrypted FROM credentials WHERE platform = ?",
                (platform,)
            ).fetchone()
        if not row:
            return None
        return self._decrypt(row[0])

    def patch(self, platform: str, updates: dict) -> None:
        """只更新指定字段（用于刷新 token 后写回）。"""
        creds = self.get(platform) or {}
        creds.update(updates)
        self.store(platform, creds)

    def delete(self, platform: str) -> bool:
        with sqlite3.connect(VAULT_DB) as conn:
            cur = conn.execute(
                "DELETE FROM credentials WHERE platform = ?", (platform,)
            )
        return cur.rowcount > 0

    def list_platforms(self) -> list[dict]:
        """只返回平台名 + 更新时间 + 过期状态，绝不返回 token 明文。"""
        with sqlite3.connect(VAULT_DB) as conn:
            rows = conn.execute(
                "SELECT platform, updated_at FROM credentials ORDER BY updated_at DESC"
            ).fetchall()
        result = []
        for platform, updated_at in rows:
            result.append({
                "platform":   platform,
                "updated_at": updated_at,
                "expired":    self.is_expired(platform),
            })
        return result

    # ── Token 过期检查 ────────────────────────────────────────

    def is_expired(self, platform: str, buffer_sec: int = TOKEN_REFRESH_BUFFER_SEC) -> bool:
        """
        检查 access_token 是否过期（或即将过期）。
        expires_at == 0 → 永不过期（如服务端静态 token）。
        """
        creds = self.get(platform)
        if not creds:
            return True
        expires_at = creds.get("expires_at", 0)
        if expires_at == 0:
            return False
        return time.time() + buffer_sec > expires_at

    def has_platform(self, platform: str) -> bool:
        with sqlite3.connect(VAULT_DB) as conn:
            row = conn.execute(
                "SELECT 1 FROM credentials WHERE platform = ?", (platform,)
            ).fetchone()
        return row is not None

    # ── 安全摘要（用于日志/回复） ────────────────────────────

    def safe_summary(self, platform: str) -> str:
        """返回脱敏摘要，安全用于 Telegram 或日志输出。"""
        creds = self.get(platform)
        if not creds:
            return f"[{platform}] 未配置"
        token = creds.get("access_token") or creds.get("app_access_token", "")
        expires_at = creds.get("expires_at", 0)
        if expires_at:
            remaining = max(0, expires_at - time.time())
            exp_str = f"剩余 {remaining/60:.0f} 分钟" if remaining > 0 else "已过期"
        else:
            exp_str = "长期有效"
        masked = _mask_token(token) if token else "（无 token）"
        return f"[{platform}] token={masked} | {exp_str}"


# ── 进程内单例 ────────────────────────────────────────────────
_vault_instance: Optional[OAuth2VaultDB] = None


def get_oauth2_vault() -> OAuth2VaultDB:
    global _vault_instance
    if _vault_instance is None:
        _vault_instance = OAuth2VaultDB()
    return _vault_instance
