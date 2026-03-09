"""
platforms/feishu.py — 飞书（Lark）OAuth2 平台适配器
====================================================

支持的操作：
  · get_app_access_token()     — 获取服务端 app_access_token（2h 有效期）
  · create_document()          — 在飞书云空间创建新文档
  · append_blocks()            — 向文档追加内容块
  · send_text_message()        — 向用户发送飞书消息（DM）
  · share_doc_to_chat()        — 在消息中分享文档链接卡片

授权模式：
  飞书企业自建应用（Server-to-server）
  · 不需要用户 OAuth2 流程
  · 用 app_id + app_secret → app_access_token（每 2 小时刷新一次）
  · 凭证存在 OAuth2VaultDB 中的 "feishu" platform

飞书 Vault 凭证格式：
  {
    "app_id":            "cli_xxxx",
    "app_secret":        "xxxx",
    "app_access_token":  "t-xxx",      # 自动管理
    "expires_at":        1234567890.0, # 自动管理
    "user_open_id":      "ou_xxx",     # 可选：发 DM 的目标用户 open_id
    "folder_token":      "fldxxxx",    # 可选：默认存放文档的文件夹
    "chat_id":           "oc_xxx",     # 可选：默认消息投递的群组 chat_id
    "tenant_url":        "https://xxx.feishu.cn",  # 必填：企业租户 URL，用于生成文档可访问链接
  }

API 文档参考：
  https://open.feishu.cn/document/server-docs/docs/docs/docx-v1/document/create
  https://open.feishu.cn/document/server-docs/im-v1/message/create_message
"""

from __future__ import annotations

import json
import time
import urllib.request
import urllib.error
from typing import Any, Optional

# ── API 端点 ──────────────────────────────────────────────────
FEISHU_BASE           = "https://open.feishu.cn/open-apis"
APP_TOKEN_URL         = f"{FEISHU_BASE}/auth/v3/app_access_token/internal"
CREATE_DOC_URL        = f"{FEISHU_BASE}/docx/v1/documents"
APPEND_BLOCKS_URL     = f"{FEISHU_BASE}/docx/v1/documents/{{doc_id}}/blocks/{{block_id}}/children"
SEND_MESSAGE_URL      = f"{FEISHU_BASE}/im/v1/messages"
BATCH_SEND_URL        = f"{FEISHU_BASE}/message/v4/batch_send/"
DOC_INFO_URL          = f"{FEISHU_BASE}/docx/v1/documents/{{doc_id}}"

REQUEST_TIMEOUT = 15


# ── HTTP 辅助 ─────────────────────────────────────────────────
def _feishu_request(
    method: str,
    url: str,
    token: str,
    data: Optional[dict] = None,
    params: Optional[dict] = None,
) -> dict:
    """通用飞书 API 请求，统一错误处理。"""
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{query}"

    req = urllib.request.Request(
        url,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    if data is not None:
        req.data = json.dumps(data, ensure_ascii=False).encode("utf-8")

    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"飞书 API HTTP {e.code}: {raw[:300]}")
    except Exception as e:
        raise RuntimeError(f"飞书 API 请求失败: {e}")

    code = body.get("code", -1)
    if code != 0:
        msg = body.get("msg", "unknown error")
        raise RuntimeError(f"飞书 API 业务错误 code={code}: {msg}")

    return body


# ── Token 刷新函数（注册到 AuthMiddleware） ───────────────────
def refresh_feishu_app_token(creds: dict) -> dict:
    """
    用 app_id + app_secret 换取新的 app_access_token。
    返回的 dict 包含 {app_access_token, expires_at}，用于 patch 回 vault。
    """
    app_id = creds.get("app_id", "")
    app_secret = creds.get("app_secret", "")
    if not app_id or not app_secret:
        raise ValueError("飞书凭证缺少 app_id 或 app_secret，请先 setup")

    req = urllib.request.Request(
        APP_TOKEN_URL,
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
        data=json.dumps({
            "app_id": app_id,
            "app_secret": app_secret,
        }, ensure_ascii=False).encode("utf-8"),
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        body = json.loads(resp.read().decode("utf-8"))

    code = body.get("code", -1)
    if code != 0:
        raise RuntimeError(f"飞书 app_access_token 获取失败 code={code}: {body.get('msg')}")

    expire_in = body.get("expire", 7200)
    return {
        "app_access_token": body["app_access_token"],
        # access_token 字段统一 alias，兼容 middleware 的 get_valid_token
        "access_token": body["app_access_token"],
        "expires_at": time.time() + expire_in - 60,  # 提前 60 秒标记过期
    }


# ── 文档内容：Markdown → 飞书块 ──────────────────────────────
def markdown_to_feishu_blocks(markdown: str) -> list[dict]:
    """
    稳定模式：Markdown 文本按行转换为普通段落块。
    说明：复杂 block schema 在不同租户容易触发 invalid param，
    这里优先保证可写入成功，再逐步扩展富文本能力。
    """
    blocks = []
    for line in markdown.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue

        # Strip lightweight markdown markers while preserving readable content.
        plain = stripped
        if plain.startswith("### "):
            plain = plain[4:]
        elif plain.startswith("## "):
            plain = plain[3:]
        elif plain.startswith("# "):
            plain = plain[2:]
        elif plain.startswith("- ") or plain.startswith("* "):
            plain = f"• {plain[2:]}"
        elif plain == "---":
            plain = "----------------"

        blocks.append(_text_block(plain))

    return blocks


def _text_block(text: str) -> dict:
    """普通段落块（block_type=2）"""
    return {
        "block_type": 2,
        "text": {
            "elements": [{"text_run": {"content": text, "text_element_style": {}}}],
            "style": {},
        },
    }


def _heading_block(text: str, level: int = 1) -> dict:
    """标题块：level 1→block_type 3, 2→4, 3→5"""
    block_type = 2 + level  # 1→3, 2→4, 3→5
    return {
        "block_type": block_type,
        "heading1" if level == 1 else f"heading{level}": {
            "elements": [{"text_run": {"content": text}}],
            "style": {},
        },
    }


def _bullet_block(text: str) -> dict:
    """无序列表项块（block_type=12）"""
    return {
        "block_type": 12,
        "bullet": {
            "elements": [{"text_run": {"content": text}}],
            "style": {},
        },
    }


# ── 核心飞书操作 ──────────────────────────────────────────────
class FeishuAdapter:
    """
    飞书操作集合。所有方法接受 app_access_token 作为第一参数，
    由 AuthMiddleware.execute_with_auth 统一注入。
    """

    @staticmethod
    def create_document(token: str, title: str, folder_token: str = "", tenant_url: str = "") -> dict:
        """
        在飞书云空间创建新文档。

        Args:
            tenant_url: 租户 URL，如 "https://xxx.feishu.cn"。设置后生成可点击链接。

        Returns:
            {
              "document_id": "...",
              "title": "...",
              "url": "https://xxx.feishu.cn/docx/...",
            }
        """
        body: dict = {"title": title}
        if folder_token:
            body["folder_token"] = folder_token

        resp = _feishu_request("POST", CREATE_DOC_URL, token, data=body)
        doc = resp.get("data", {}).get("document", {})
        doc_id = doc.get("document_id", "")
        # 飞书文档的用户可访问链接格式是 {tenant_url}/docx/{doc_id}
        # tenant_url 需要从 vault 配置读取，每个企业的 subdomain 不同
        if doc_id and tenant_url:
            doc_url = f"{tenant_url.rstrip('/')}/docx/{doc_id}"
        elif doc_id:
            # 如果未配置 tenant_url，返回 doc_id 和提示
            doc_url = f"(请配置 tenant_url 以生成链接) document_id={doc_id}"
        else:
            doc_url = ""
        return {
            "document_id": doc_id,
            "title": doc.get("title", title),
            "url": doc_url,
        }

    @staticmethod
    def append_content(token: str, document_id: str, markdown: str) -> dict:
        """
        向已有文档追加 Markdown 内容（转换为飞书 blocks）。
        block_id 使用 document_id（文档根块与文档 ID 相同）。
        """
        blocks = markdown_to_feishu_blocks(markdown)
        if not blocks:
            return {"status": "no_content"}

        url = APPEND_BLOCKS_URL.format(doc_id=document_id, block_id=document_id)
        # Feishu docx children API requires POST; PATCH may return route-level 404.
        resp = _feishu_request("POST", url, token, data={"index": -1, "children": blocks})
        count = len(resp.get("data", {}).get("children", []))
        return {"status": "ok", "blocks_written": count}

    @staticmethod
    def send_text_message(
        token: str,
        receive_id: str,
        text: str,
        receive_id_type: str = "open_id",
    ) -> dict:
        """
        向指定用户/群组发送文本消息。
        receive_id_type: "open_id" / "chat_id" / "user_id"
        """
        body = {
            "receive_id": receive_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }
        resp = _feishu_request(
            "POST", SEND_MESSAGE_URL, token,
            data=body,
            params={"receive_id_type": receive_id_type},
        )
        msg_id = resp.get("data", {}).get("message_id", "")
        return {"status": "sent", "message_id": msg_id}

    @staticmethod
    def share_doc_card(
        token: str,
        receive_id: str,
        doc_url: str,
        doc_title: str,
        note: str = "",
        receive_id_type: str = "open_id",
    ) -> dict:
        """
        发送包含文档链接的富文本卡片消息，方便用户点击审阅。
        """
        # 使用飞书互动卡片（简化版）
        card = {
            "config": {"wide_screen_mode": True},
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "content": note or f"📄 新文档「{doc_title}」已创建，请点击下方链接审阅。",
                        "tag": "lark_md",
                    },
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"content": "📖 打开文档", "tag": "plain_text"},
                            "type": "primary",
                            "url": doc_url,
                        }
                    ],
                },
            ],
            "header": {
                "title": {"content": f"✅ {doc_title}", "tag": "plain_text"},
                "template": "blue",
            },
        }
        body = {
            "receive_id": receive_id,
            "msg_type": "interactive",
            "content": json.dumps(card, ensure_ascii=False),
        }
        resp = _feishu_request(
            "POST", SEND_MESSAGE_URL, token,
            data=body,
            params={"receive_id_type": receive_id_type},
        )
        msg_id = resp.get("data", {}).get("message_id", "")
        return {"status": "sent", "message_id": msg_id}

    @staticmethod
    def get_doc_info(token: str, document_id: str) -> dict:
        """获取文档基本信息（标题、创建时间等）。"""
        url = DOC_INFO_URL.format(doc_id=document_id)
        resp = _feishu_request("GET", url, token)
        return resp.get("data", {}).get("document", {})


# ── 高层组合：创建文档 + 写内容 + 发通知 ─────────────────────
def create_and_notify(
    token: str,
    title: str,
    markdown_content: str,
    notify_open_id: str = "",
    notify_chat_id: str = "",
    folder_token: str = "",
    tenant_url: str = "",
) -> dict:
    """
    一站式：创建飞书文档 + 写入内容 + 发消息通知用户。
    返回文档 URL 和通知状态。
    """
    result: dict = {"success": False}

    try:
        # 1. 创建文档
        doc = FeishuAdapter.create_document(token, title, folder_token, tenant_url=tenant_url)
        result["document_id"] = doc["document_id"]
        result["document_url"] = doc["url"]
        result["title"] = doc["title"]

        # 2. 写入内容
        if markdown_content.strip():
            append_result = FeishuAdapter.append_content(
                token, doc["document_id"], markdown_content
            )
            result["blocks_written"] = append_result.get("blocks_written", 0)

        result["success"] = True

        # 3. 发通知（optional）
        if notify_open_id and doc["url"]:
            try:
                FeishuAdapter.share_doc_card(
                    token,
                    receive_id=notify_open_id,
                    doc_url=doc["url"],
                    doc_title=title,
                    receive_id_type="open_id",
                )
                result["notified"] = True
            except Exception as e:
                result["notify_error"] = str(e)
        elif notify_chat_id and doc["url"]:
            try:
                FeishuAdapter.share_doc_card(
                    token,
                    receive_id=notify_chat_id,
                    doc_url=doc["url"],
                    doc_title=title,
                    receive_id_type="chat_id",
                )
                result["notified"] = True
            except Exception as e:
                result["notify_error"] = str(e)

    except Exception as e:
        result["error"] = str(e)
        result["success"] = False

    return result


# ── 适配器单例 + refresher 注册 ───────────────────────────────
_adapter_registered = False


def ensure_feishu_registered() -> None:
    """确保飞书 refresher 已注册到 AuthMiddleware（幂等）。"""
    global _adapter_registered
    if _adapter_registered:
        return
    try:
        from skills.oauth2_vault.auth_middleware import get_middleware
        mw = get_middleware()
        mw.register_refresher("feishu", refresh_feishu_app_token)
        _adapter_registered = True
    except Exception:
        pass
