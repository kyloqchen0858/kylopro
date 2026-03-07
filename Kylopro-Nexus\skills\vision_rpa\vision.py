"""
Kylopro 全境飞行员 (Global Pilot) — 桌面视觉 RPA 技能
====================================================
截屏 → 本地 OCR/模板匹配 → 坐标 → PyAutoGUI 执行操作
省 Token 策略: 识别工作完全在本地(OpenCV/EasyOCR)完成，
只把"坐标/识别结果"发给 LLM 做决策，不传高清截图。

依赖安装（按需选择）：
  pip install pyautogui pillow  # 基础（必装）
  pip install opencv-python     # 模板匹配（推荐）
  pip install easyocr           # 文字识别（大模型，首次下载较慢）
  # 或轻量OCR: pip install pytesseract + 安装 Tesseract
"""

from __future__ import annotations

import asyncio
import io
import sys
import time
from pathlib import Path
from typing import Any

from loguru import logger

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
except AttributeError:
    pass

# --- 依赖导入（优雅降级，缺包时给出指引而非崩溃）---
try:
    import pyautogui
    pyautogui.FAILSAFE = True   # 鼠标移到左上角触发紧急停止
    pyautogui.PAUSE = 0.05      # 操作间隔，防止过快
    PYAUTOGUI_OK = True
except ImportError:
    PYAUTOGUI_OK = False
    logger.warning("pyautogui 未安装: pip install pyautogui")

try:
    from PIL import Image, ImageGrab
    PIL_OK = True
except ImportError:
    PIL_OK = False
    logger.warning("Pillow 未安装: pip install pillow")

try:
    import cv2
    import numpy as np
    OPENCV_OK = True
except ImportError:
    OPENCV_OK = False
    logger.warning("OpenCV 未安装: pip install opencv-python")

try:
    import easyocr
    EASYOCR_OK = True
except ImportError:
    EASYOCR_OK = False
    logger.warning("EasyOCR 未安装: pip install easyocr（首次运行会下载模型~300MB）")


# ===========================================================
# 截图工具
# ===========================================================

def capture_screen(region: tuple[int, int, int, int] | None = None) -> "Image.Image":
    """
    截取全屏或指定区域。
    region: (left, top, width, height)
    """
    assert PIL_OK, "请安装 Pillow: pip install pillow"
    if region:
        left, top, width, height = region
        return ImageGrab.grab(bbox=(left, top, left + width, top + height))
    return ImageGrab.grab()


def image_to_bytes(img: "Image.Image", fmt: str = "PNG") -> bytes:
    """PIL Image 转字节（用于 Telegram 推送）。"""
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


# ===========================================================
# 模板匹配（OpenCV）—— 在屏幕上找图标
# ===========================================================

def find_template_on_screen(
    template_path: str | Path,
    threshold: float = 0.8,
    region: tuple[int, int, int, int] | None = None,
) -> tuple[int, int] | None:
    """
    在屏幕上找到模板图片的位置，返回中心坐标 (x, y)。
    省 Token 策略: 识别完全本地，只把坐标结果发给 LLM。

    Args:
        template_path: 模板图片路径（你想找的图标截图）
        threshold:     匹配阈值 0~1，越高越严格（默认 0.8）
        region:        只在屏幕指定区域查找 (left, top, width, height)

    Returns:
        (x, y) 中心坐标，未找到返回 None
    """
    assert OPENCV_OK, "请安装 OpenCV: pip install opencv-python"
    assert PIL_OK,   "请安装 Pillow: pip install pillow"

    # 截取屏幕（或区域）
    screen_img = capture_screen(region)
    screen_np  = cv2.cvtColor(np.array(screen_img), cv2.COLOR_RGB2BGR)

    # 读取模板
    template = cv2.imread(str(template_path))
    if template is None:
        logger.error("[VISION] 模板图片不存在: {}", template_path)
        return None

    # 模板匹配
    result     = cv2.matchTemplate(screen_np, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)

    if max_val < threshold:
        logger.debug("[VISION] 模板未找到 (max_val={:.3f} < {})", max_val, threshold)
        return None

    # 计算中心坐标
    h, w = template.shape[:2]
    cx   = max_loc[0] + w // 2
    cy   = max_loc[1] + h // 2

    # 如果有区域偏移，加上偏移量
    if region:
        cx += region[0]
        cy += region[1]

    logger.info("[VISION] 找到模板 @ ({}, {})，置信度 {:.3f}", cx, cy, max_val)
    return (cx, cy)


# ===========================================================
# OCR 文字识别（EasyOCR）—— 把截图转为文字
# ===========================================================

_ocr_reader = None

def get_ocr_reader(langs: list[str] | None = None) -> Any:
    """获取 EasyOCR reader（单例，延迟初始化）。"""
    global _ocr_reader
    assert EASYOCR_OK, "请安装 EasyOCR: pip install easyocr"
    if _ocr_reader is None:
        _langs = langs or ["ch_sim", "en"]
        logger.info("[VISION] 初始化 EasyOCR ({}), 首次加载需耗时...", _langs)
        _ocr_reader = easyocr.Reader(_langs, gpu=False)
    return _ocr_reader


def ocr_image(
    img: "Image.Image | None" = None,
    region: tuple[int, int, int, int] | None = None,
    langs: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    OCR 识别屏幕文字，返回识别结果列表。
    省 Token 策略: 返回 [{text, box, confidence}]，只把文字发给 LLM。

    Args:
        img:    PIL Image（传入则不截屏）
        region: 截屏区域 (left, top, width, height)
        langs:  识别语言列表（默认 ["ch_sim", "en"]）

    Returns:
        [{"text": "...", "box": [(x,y),...], "confidence": 0.95}, ...]
    """
    reader = get_ocr_reader(langs)
    target = img or capture_screen(region)
    img_np = np.array(target)

    raw_results = reader.readtext(img_np)
    results = []
    for box, text, confidence in raw_results:
        # box 是 4 个角的坐标，取中心点
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        cx = int(sum(xs) / 4)
        cy = int(sum(ys) / 4)
        # 若有区域偏移，加上偏移
        if region:
            cx += region[0]
            cy += region[1]
        results.append({
            "text":       text,
            "center":     (cx, cy),
            "confidence": round(confidence, 3),
            "box":        box,
        })

    logger.info("[VISION] OCR 识别到 {} 个文字块", len(results))
    return results


def ocr_to_plain_text(
    img: "Image.Image | None" = None,
    region: tuple[int, int, int, int] | None = None,
) -> str:
    """把 OCR 结果转为纯文本（适合发给 LLM）。"""
    results = ocr_image(img=img, region=region)
    return " ".join(r["text"] for r in results if r["confidence"] > 0.5)


# ===========================================================
# PyAutoGUI 操作接口
# ===========================================================

class VisionRPA:
    """
    全境飞行员执行器。
    将截图、识别、操作三合一，提供简洁接口。
    """

    def __init__(self) -> None:
        if not PYAUTOGUI_OK:
            raise RuntimeError("请安装 pyautogui: pip install pyautogui")
        if not PIL_OK:
            raise RuntimeError("请安装 Pillow: pip install pillow")

    # --- 鼠标操作 ---

    def move_to(self, x: int, y: int, duration: float = 0.3) -> None:
        """平滑移动鼠标到坐标（duration 秒）。"""
        logger.info("[RPA] 移动鼠标 -> ({}, {})", x, y)
        pyautogui.moveTo(x, y, duration=duration)

    def click(self, x: int | None = None, y: int | None = None, button: str = "left") -> None:
        """点击鼠标（可省略坐标，在当前位置点击）。"""
        if x is not None and y is not None:
            logger.info("[RPA] 点击 ({}, {})", x, y)
            pyautogui.click(x, y, button=button)
        else:
            pyautogui.click(button=button)

    def double_click(self, x: int, y: int) -> None:
        """双击。"""
        logger.info("[RPA] 双击 ({}, {})", x, y)
        pyautogui.doubleClick(x, y)

    def right_click(self, x: int, y: int) -> None:
        """右键点击。"""
        pyautogui.rightClick(x, y)

    def drag_to(self, x: int, y: int, duration: float = 0.5) -> None:
        """拖拽到指定位置。"""
        pyautogui.dragTo(x, y, duration=duration)

    # --- 键盘操作 ---

    def type_text(self, text: str, interval: float = 0.02) -> None:
        """输入文字（模拟真实键盘输入）。"""
        logger.info("[RPA] 输入文字: {}", text[:30])
        pyautogui.write(text, interval=interval)

    def hotkey(self, *keys: str) -> None:
        """按快捷键，如 hotkey('ctrl', 'c')。"""
        logger.info("[RPA] 快捷键: {}", "+".join(keys))
        pyautogui.hotkey(*keys)

    def press(self, key: str) -> None:
        """按单个键，如 press('enter')。"""
        pyautogui.press(key)

    # --- 视觉操作（组合接口）---

    async def find_and_click(
        self,
        template_path: str | Path,
        threshold: float = 0.8,
        region: tuple[int, int, int, int] | None = None,
    ) -> bool:
        """
        找到屏幕上的模板图片并点击它。
        返回 True 表示找到并点击，False 表示未找到。
        """
        assert OPENCV_OK, "需要 OpenCV: pip install opencv-python"
        coords = find_template_on_screen(template_path, threshold, region)
        if coords:
            self.move_to(*coords)
            await asyncio.sleep(0.2)
            self.click(*coords)
            return True
        logger.warning("[RPA] 未在屏幕上找到模板: {}", template_path)
        return False

    async def screenshot_ocr(
        self,
        region: tuple[int, int, int, int] | None = None,
    ) -> str:
        """
        截图并 OCR 识别，返回纯文本。
        本地完成，零 Token 消耗。
        """
        assert EASYOCR_OK, "需要 EasyOCR: pip install easyocr"
        return ocr_to_plain_text(region=region)

    async def screenshot_to_telegram(
        self,
        caption: str = "桌面截图",
        region: tuple[int, int, int, int] | None = None,
    ) -> bool:
        """截图并推送 Telegram（不走 LLM，直接推图片）。"""
        from skills.telegram_notify.notify import TelegramNotifier
        import httpx

        img   = capture_screen(region)
        img_bytes = image_to_bytes(img)

        notifier = TelegramNotifier()
        if not notifier._configured:
            logger.warning("[RPA] Telegram 未配置")
            return False

        url = f"https://api.telegram.org/bot{notifier.token}/sendPhoto"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, data={
                    "chat_id": notifier.chat_id,
                    "caption": caption,
                }, files={"photo": ("screen.png", img_bytes, "image/png")})
                resp.raise_for_status()
                logger.info("[RPA] 桌面截图已推送 Telegram")
                return True
        except Exception as e:
            logger.error("[RPA] 截图推送失败: {}", e)
            return False

    def screen_size(self) -> tuple[int, int]:
        """返回屏幕分辨率 (width, height)。"""
        return pyautogui.size()

    def get_cursor_pos(self) -> tuple[int, int]:
        """返回当前鼠标坐标。"""
        return pyautogui.position()


# ===========================================================
# CLI 测试入口（pyautogui + screenshot）
# ===========================================================

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    async def demo() -> None:
        rpa = VisionRPA()
        w, h = rpa.screen_size()
        print(f"[GLOBAL PILOT] 屏幕分辨率: {w}x{h}")
        print(f"[GLOBAL PILOT] 当前鼠标: {rpa.get_cursor_pos()}")

        print("[GLOBAL PILOT] 截图并推 Telegram...")
        ok = await rpa.screenshot_to_telegram("Kylopro 全境飞行员 - 桌面截图测试")
        print(f"[GLOBAL PILOT] Telegram 推送: {'OK' if ok else 'FAIL'}")

    asyncio.run(demo())
