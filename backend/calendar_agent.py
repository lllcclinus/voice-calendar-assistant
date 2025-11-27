# backend/calendar_agent.py
import os
from datetime import datetime
from typing import Tuple
from playwright.async_api import async_playwright
from config import STORAGE_STATE_PATH

GOOGLE_CAL_URL = "https://calendar.google.com/"

async def _get_context_and_page():
    from playwright.async_api import async_playwright
    p = await async_playwright().start()
    if not os.path.exists(STORAGE_STATE_PATH):
        # 首次登录：打开真实浏览器
        browser = await p.chromium.launch(headless=False, slow_mo=100)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(GOOGLE_CAL_URL)
        print("请在新打开的浏览器窗口中完成 Google 登录和多因子认证。")
        input("登录完成后请在终端按回车继续...")
        await context.storage_state(path=STORAGE_STATE_PATH)
    else:
        # 复用登录状态，可以 headless=True
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=STORAGE_STATE_PATH)
        page = await context.new_page()
        await page.goto(GOOGLE_CAL_URL)
    return p, browser, context, page

async def _goto_date(page, date: datetime):
    """切换到指定日期，例如用 URL 参数或者点击日期选择器。这里给一个简化示意。"""
    # 方式1：直接修改 URL（Google Calendar 支持 ?pli=1&t=day&sd=YYYYMMDD）
    date_str = date.strftime("%Y%m%d")
    await page.goto(f"https://calendar.google.com/calendar/u/0/r/day/{date_str}")
    await page.wait_for_timeout(3000)

async def _has_conflict(page, start: datetime, end: datetime) -> Tuple[bool, str]:
    """
    简单示例：在日视图中查一下该时间段有没有已有事件块。
    实际要打开 DevTools 看元素，比如 aria-label 里会包含时间。
    """
    # 这里只给出一个非常粗略的示意逻辑：
    time_label = start.strftime("%-I:%M")  # 例如 '10:00'
    # 假设日视图中事件块 aria-label 里包含这个时间
    locator = page.locator(f"[aria-label*='{time_label}']")
    count = await locator.count()
    if count > 0:
        # 可以再拿第一个元素的 aria-label，当做“已有日程说明”
        label = await locator.nth(0).get_attribute("aria-label")
        return True, label or "已有日程"
    return False, ""

async def _create_event(page, start: datetime, end: datetime, title: str):
    """
    简化版：在日视图点击相应时间格子，打开“创建事件”弹窗，填标题并保存。
    具体选择器需要你自己调试。
    """
    # 一个方案是使用 "Create" 按钮，然后在弹窗中填入详情再修改时间。
    await page.get_by_text("创建").click()  # 可能是“Create”或其他，需要看当前语言
    await page.wait_for_timeout(1000)

    # 填标题
    title_input = page.locator("input[aria-label='事件标题'], input[aria-label='Event title']")
    await title_input.fill(title)

    # 这里可以再点击“更多选项”，进入详细编辑，设置精确的开始/结束时间。
    # 省略若干填写时间的步骤（需要你在 DevTools 看具体 DOM，调用 .fill(...))

    # 最后点“保存”
    await page.get_by_text("保存").click()  # 或 "Save"
    await page.wait_for_timeout(2000)

async def create_event_with_conflict_check(start: datetime, end: datetime, title: str):
    """
    对外暴露的主函数：
    - 打开 / 复用登录
    - 跳到指定日期
    - 检查冲突
    - 创建日程或返回冲突信息
    """
    p, browser, context, page = await _get_context_and_page()
    try:
        await _goto_date(page, start)
        has_conflict, conflict_info = await _has_conflict(page, start, end)
        if has_conflict:
            return False, conflict_info
        await _create_event(page, start, end, title)
        return True, ""
    finally:
        await context.close()
        await browser.close()
        await p.stop()
