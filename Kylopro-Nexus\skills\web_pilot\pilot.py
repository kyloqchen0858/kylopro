"""
Kylopro 网页触角 (Web Pilot) — Playwright 浏览器自动化技能
==========================================================
让 Kylopro 直接读取并操控网页，无需"看"截图。

省 Token 策略：
  - 提取 DOM 简报（不发整个 HTML）
  - 只把关键文字/链接/表单结构发给 LLM
  - 截图用 Telegram 传输，不走 LLM token

依赖安装：
  pip install playwright beautifulsoup4
  playwright install chromium
"""

from __future__ import annotations

import asyncio
import base64
import sys
from pathlib import Path
from typing import Any

from loguru import logger

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
except AttributeError:
    pass

try:
    from playwright.async_api import async_playwright, Browser, Page
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("Playwright 未安装: pip install playwright && playwright install chromium")

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False


def _extract_dom_brief(html: str, max_chars: int = 2000) -> str:
    """
    把复杂 HTML 提炼成 LLM 可消化的简报。
    省 Token 核心：不发原始 HTML，只发结构化简报。
    """
    if not BS4_AVAILABLE:
        # 没有 bs4 就做基础截断
        import re
        text = re.sub(r"<[^>]+>", " ", html)
        text = " ".join(text.split())
        return text[:max_chars]

    soup = BeautifulSoup(html, "html.parser")

    # 移除无用标签
    for tag in soup(["script", "style", "meta", "link", "noscript"]):
        tag.decompose()

    lines = []

    # 提取标题
    title = soup.find("title")
    if title:
        lines.append(f"[标题] {title.get_text().strip()}")

    # 提取 h1-h3
    for h in soup.find_all(["h1", "h2", "h3"])[:5]:
        text = h.get_text().strip()
        if text:
            lines.append(f"[{h.name.upper()}] {text}")

    # 提取所有链接（限 10 个）
    links = soup.find_all("a", href=True)[:10]
    if links:
        lines.append("\n[链接]")
        for a in links:
            text = a.get_text().strip()
            href = a["href"]
            if text:
                lines.append(f"  - {text}: {href}")

    # 提取表单字段
    forms = soup.find_all("form")
    for i, form in enumerate(forms[:2]):
        lines.append(f"\n[表单 {i+1}]")
        for inp in form.find_all(["input", "textarea", "select"])[:8]:
            name    = inp.get("name", inp.get("id", "?"))
            inp_type = inp.get("type", inp.name)
            lines.append(f"  - {inp_type} name={name}")

    # 提取正文（前 800 个字符）
    body = soup.find("body")
    if body:
        text = body.get_text(separator=" ", strip=True)
        text = " ".join(text.split())[:800]
        lines.append(f"\n[正文片段]\n{text}")

    result = "\n".join(lines)
    return result[:max_chars]


class WebPilot:
    """
    网页触角执行器。

    用法：
        async with WebPilot(headless=True) as pilot:
            brief = await pilot.navigate_and_brief("https://example.com")
            await pilot.click("button#submit")
    """

    def __init__(
        self,
        headless: bool = True,
        browser_type: str = "chromium",   # chromium | firefox | webkit
        timeout_ms: int = 30_000,
    ) -> None:
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("请先: pip install playwright && playwright install chromium")
        self.headless = headless
        self.browser_type = browser_type
        self.timeout_ms = timeout_ms
        self._playwright = None
        self._browser: Browser | None = None
        self._page: Page | None = None

    async def __aenter__(self) -> "WebPilot":
        self._playwright = await async_playwright().start()
        browser_launcher = getattr(self._playwright, self.browser_type)
        self._browser = await browser_launcher.launch(headless=self.headless)
        self._page = await self._browser.new_page()
        self._page.set_default_timeout(self.timeout_ms)
        logger.info("[WEB PILOT] 浏览器已启动 ({})", self.browser_type)
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("[WEB PILOT] 浏览器已关闭")

    @property
    def page(self) -> Page:
        assert self._page, "未初始化，请在 async with 块内使用"
        return self._page

    # -----------------------------------------------------------
    # 核心操作接口
    # -----------------------------------------------------------

    async def navigate(self, url: str) -> None:
        """导航到指定 URL，等待页面加载完成。"""
        logger.info("[WEB PILOT] 导航 -> {}", url)
        await self.page.goto(url, wait_until="domcontentloaded")

    async def navigate_and_brief(self, url: str) -> str:
        """
        导航并返回 DOM 简报（省 Token 核心接口）。
        适合发给 LLM 做分析，不传原始 HTML。
        """
        await self.navigate(url)
        html = await self.page.content()
        brief = _extract_dom_brief(html)
        logger.info("[WEB PILOT] DOM 简报已生成 ({} 字符)", len(brief))
        return brief

    async def click(self, selector: str) -> None:
        """点击指定元素（CSS 选择器或 XPath）。"""
        logger.info("[WEB PILOT] 点击: {}", selector)
        await self.page.click(selector)

    async def fill(self, selector: str, value: str) -> None:
        """清除并填写输入框。"""
        logger.info("[WEB PILOT] 填写 {}: {}", selector, value[:20] + "..." if len(value) > 20 else value)
        await self.page.fill(selector, value)

    async def get_text(self, selector: str) -> str:
        """获取元素的文字内容。"""
        return await self.page.inner_text(selector)

    async def wait_for(self, selector: str, timeout_ms: int | None = None) -> None:
        """等待元素出现。"""
        await self.page.wait_for_selector(selector, timeout=timeout_ms or self.timeout_ms)

    async def screenshot_bytes(self, region: dict[str, int] | None = None) -> bytes:
        """截图并返回字节数据（区域可选）。"""
        kwargs: dict[str, Any] = {}
        if region:
            kwargs["clip"] = region
        return await self.page.screenshot(**kwargs)

    async def screenshot_to_telegram(self, caption: str = "页面截图") -> bool:
        """
        截图并通过 Telegram 推送（不经过 LLM，省 Token）。
        """
        from skills.telegram_notify.notify import TelegramNotifier
        import httpx, json, os

        img_bytes = await self.screenshot_bytes()
        img_b64   = base64.b64encode(img_bytes).decode()

        # 通过 Telegram sendPhoto API 发送
        notifier  = TelegramNotifier()
        if not notifier._configured:
            logger.warning("[WEB PILOT] Telegram 未配置，跳过截图推送")
            return False

        url = f"https://api.telegram.org/bot{notifier.token}/sendPhoto"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, data={
                    "chat_id": notifier.chat_id,
                    "caption": caption,
                }, files={"photo": ("screenshot.png", img_bytes, "image/png")})
                resp.raise_for_status()
                logger.info("[WEB PILOT] 截图已推送 Telegram")
                return True
        except Exception as e:
            logger.error("[WEB PILOT] 截图推送失败: {}", e)
            return False

    async def evaluate(self, js: str) -> Any:
        """在页面上下文执行 JavaScript，返回结果。"""
        return await self.page.evaluate(js)

    # -----------------------------------------------------------
    # 高阶组合方法
    # -----------------------------------------------------------

    async def login(
        self,
        url: str,
        username_selector: str,
        password_selector: str,
        submit_selector: str,
        username: str,
        password: str,
    ) -> str:
        """
        通用登录流程：导航 → 填用户名 → 填密码 → 点提交 → 返回结果页简报。
        """
        await self.navigate(url)
        await self.fill(username_selector, username)
        await self.fill(password_selector, password)
        await self.click(submit_selector)
        await self.page.wait_for_load_state("networkidle")
        html = await self.page.content()
        return _extract_dom_brief(html)

    async def extract_table(self, selector: str = "table") -> list[list[str]]:
        """
        提取页面中的表格数据为二维列表。
        适合把网页数据导出到 Excel 或发给 LLM 分析。
        """
        rows = await self.page.query_selector_all(f"{selector} tr")
        result = []
        for row in rows:
            cells = await row.query_selector_all("td, th")
            row_data = []
            for cell in cells:
                row_data.append(await cell.inner_text())
            result.append(row_data)
        return result


# ===========================================================
# CLI 快速测试入口
# ===========================================================

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    async def demo() -> None:
        async with WebPilot(headless=True) as pilot:
            print("[WEB PILOT] 测试导航 -> bing.com")
            brief = await pilot.navigate_and_brief("https://www.bing.com")
            print("DOM 简报:", brief[:500])
            await pilot.screenshot_to_telegram("Bing 截图测试 -- Kylopro Web Pilot")
            print("[WEB PILOT] 测试完成")

    asyncio.run(demo())
