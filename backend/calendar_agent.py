# backend/calendar_agent.py
import os
from datetime import datetime
from typing import Tuple
from playwright.async_api import async_playwright
from config import STORAGE_STATE_PATH
from re import compile as re_compile
from logger import logger

GOOGLE_CAL_URL = "https://calendar.google.com/calendar"

async def _get_context_and_page():
    p = await async_playwright().start()

    CHROME_PATH = r"C:\\Program Files\\Google\\Chrome\Application\\chrome.exe"

    browser = await p.chromium.launch(
        executable_path=CHROME_PATH,
        headless=False,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-infobars",
            "--start-maximized",
        ],
    )

    if not os.path.exists(STORAGE_STATE_PATH):
        # 首次登入
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(GOOGLE_CAL_URL)
        print("请在新打开的浏览器窗口中完成 Google 登录和多因子认证。")
        logger.info("[CAL] first login, please auth manually ...")
        input("登录完成后请在终端按回车继续...")
        await context.storage_state(path=STORAGE_STATE_PATH)
    else:
        # 復用登入狀態，不要再 launch 一次 browser
        logger.info("[CAL] reuse storage_state.json")
        context = await browser.new_context(storage_state=STORAGE_STATE_PATH)
        page = await context.new_page()
        await page.goto(GOOGLE_CAL_URL)

    return p, browser, context, page

async def _goto_date(page, start: datetime):
    target_url = f"{GOOGLE_CAL_URL}/u/0/r/day/{start.year}/{start.month}/{start.day}"
    logger.info(f"[CAL] goto: {target_url}")
    print("[calendar_agent] goto:", target_url)
    await page.goto(target_url)
    await page.wait_for_timeout(2000)

def format_tw_hour_label(dt: datetime) -> str:
    """把 datetime 轉成像 '上午10點' 這種字串，用來在 day view 找事件卡片。"""
    hour = dt.hour
    if hour == 0:
        period = "上午"; h12 = 12
    elif 1 <= hour < 12:
        period = "上午"; h12 = hour
    elif hour == 12:
        period = "下午"; h12 = 12
    else:
        period = "下午"; h12 = hour - 12
    return f"{period}{h12}點"

def format_tw_12h_time(dt: datetime) -> str:
    hour = dt.hour
    minute = dt.minute
    if hour == 0:
        period = "上午"; h12 = 12
    elif 1 <= hour < 12:
        period = "上午"; h12 = hour
    elif hour == 12:
        period = "下午"; h12 = 12
    else:
        period = "下午"; h12 = hour - 12
    return f"{period}{h12}:{minute:02d}"

async def _has_conflict(page, start: datetime, end: datetime) -> Tuple[bool, str]:
    """
    檢查指定時間段是否已有事件。
    改成 async 版正確用法：所有 Playwright 操作都要 await。
    """
    start_hour_label = format_tw_hour_label(start)  # 例如 '上午10點'
    print("[calendar_agent] check conflict with hour label:", start_hour_label)

    # --- debug: 列出前幾個 [role=button] ---
    all_buttons = page.locator("[role='button']")
    total = await all_buttons.count()  
    print(f"[calendar_agent] debug: [role=button] total = {total}")
    for i in range(min(total, 5)):
        btn = all_buttons.nth(i)
        try:
            text = await btn.inner_text()                 
            aria = await btn.get_attribute("aria-label")  
            print(f"  [btn {i}] text={text!r}, aria-label={aria!r}")
        except Exception:
            pass

    # --- 真正用來判斷衝突 ---
    conflict_locator = page.locator("[role='button']", has_text=start_hour_label)
    conflict_count = await conflict_locator.count()      
    print("[calendar_agent] conflict candidates with hour label:", conflict_count)

    if conflict_count > 0:
        btn0 = conflict_locator.nth(0)
        label = await btn0.get_attribute("aria-label")   
        print(f"Label: {label}")
        if not label:
            try:
                text = await btn0.inner_text()           
                label = text.split("\n")[0]
            except Exception:
                label = "指定時間已有日程"
        return True, label

    return False, ""

async def debug_dialog_inputs(page):
    """列出對話框裡的 input 欄位，幫忙確認索引與 aria-label。"""
    dialog = page.get_by_role("dialog").first
    inputs = dialog.locator("input")
    count = await inputs.count()
    print(f"\n[debug] dialog 裡找到 {count} 個 input:")
    for i in range(count):
        inp = inputs.nth(i)
        try:
            aria = await inp.get_attribute("aria-label")
            value = await inp.input_value()
            print(f"{i}: aria-label={aria!r}, value={value!r}")
        except Exception:
            pass





async def _create_event(page, start: datetime, end: datetime, title: str):
    print("[calendar_agent] creating event:", title)
    logger.info(f"[CAL] creating event: {title!r}")
    # 1. 點「建立」按鈕
    create_btn = page.locator("button:has-text('建立')").first
    await create_btn.click()
    logger.info("[CAL] clicked 建立")
    print("[calendar_agent] clicked 建立 button")
    await page.wait_for_timeout(800)

    # 2. 點「活動」選單項
    try:
        event_item = page.get_by_role("menuitem", name=re_compile("活動"))
        await event_item.click()
        print("[calendar_agent] clicked 活動 via role=menuitem")
        logger.info("[CAL] clicked 活動 (menuitem)")
    except Exception as e:
        logger.warning("[CAL] fail click 活動 via role, fallback selector", exc_info=True)
        print("[calendar_agent] failed to click 活動 via role=menuitem:", repr(e))
        event_item = page.locator("[role='menuitem']:has-text('活動')").first
        await event_item.click()
        logger.info("[CAL] clicked 活動 via fallback")
        print("[calendar_agent] clicked 活動 via [role='menuitem']:has-text('活動')")
    await page.wait_for_timeout(1000)

    # 3. 找「標題」輸入框
    title_input = None
    for selector in [
        "input[aria-label*='標題']",   # 繁中介面 (標題 / 新增標題)
        "input[aria-label*='标题']",   # 簡中介面
        "input[aria-label*='Title']",  # 英文介面
    ]:
        loc = page.locator(selector)
        if await loc.count() > 0:
            title_input = loc.first
            logger.info(f"[CAL] found title input via {selector}")
            print(f"[calendar_agent] found title input by selector: {selector}")
            break

    if title_input is None:
        # 再退一步：抓對話框裡第一個 textbox
        try:
            dialog = page.get_by_role("dialog").nth(0)
            title_input = dialog.get_by_role("textbox").first
            print("[calendar_agent] fallback: use first textbox in dialog as title input")
            logger.info("[CAL] fallback: dialog first textbox as title")
        except Exception as e:
            print("[calendar_agent] cannot find title input:", repr(e))
            raise RuntimeError("找不到標題輸入框") from e

    clean_title = title
    print("[calendar_agent] fill title =", clean_title)
    await title_input.fill(clean_title)
    await page.wait_for_timeout(500)

    # 先 debug 看看有哪些欄位
    await debug_dialog_inputs(page)

    # 3.5 設定開始 / 結束時間
    start_str = format_tw_12h_time(start)  # 例如：上午10:00
    end_str   = format_tw_12h_time(end)    # 例如：上午11:00
    logger.info(f"[CAL] set time: {start_str} -> {end_str}")
    print("[calendar_agent] set time:", start_str, "->", end_str)

    dialog = page.get_by_role("dialog").first

    start_box = None
    end_box   = None

    # 直接用 aria-label 精準抓 input
    try:
        start_box = dialog.locator("input[aria-label='開始時間']").first
        end_box   = dialog.locator("input[aria-label='結束時間']").first
        if await start_box.count() == 0 or await end_box.count() == 0:
            raise RuntimeError("time input not found by aria-label")
        print("[calendar_agent] found time inputs via aria-label='開始時間'/'結束時間'")
    except Exception as e:
        print("[calendar_agent] aria-label selector failed, fallback to index:", repr(e))
        try:
            inputs = dialog.locator("input")
            # 根據 debug：2 = 開始時間, 3 = 結束時間
            if await inputs.count() >= 4:
                start_box = inputs.nth(2)
                end_box   = inputs.nth(3)
                print("[calendar_agent] fallback: use dialog input index 2/3 for start/end time")
            else:
                start_box = None
                end_box   = None
        except Exception as e2:
            print("[calendar_agent] still cannot find time inputs:", repr(e2))
            start_box = None
            end_box   = None

    if start_box and end_box:
        print("[calendar_agent] setting time via JS evaluate")

        # JS 改 value + 觸發事件
        await start_box.evaluate(
            """(el, v) => {
                el.value = v;
                el.dispatchEvent(new Event('input',  { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }""",
            start_str,
        )

        await end_box.evaluate(
            """(el, v) => {
                el.value = v;
                el.dispatchEvent(new Event('input',  { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }""",
            end_str,
        )

        await page.wait_for_timeout(500)
    else:
        print("[calendar_agent] WARNING: 找不到開始/結束時間欄位，使用預設時間")

    # 4. 點「儲存 / 保存 / Save」按鈕
    save_clicked = False
    for name_pattern in ["儲存", "保存", "Save"]:
        try:
            btn = page.get_by_role("button", name=re_compile(name_pattern))
            if await btn.count() > 0:
                await btn.first.click()
                logger.info(f"[CAL] click Save via pattern={name_pattern}")
                print(f"[calendar_agent] clicked save button via name pattern: {name_pattern}")
                save_clicked = True
                break
        except Exception:
            pass

    if not save_clicked:
        # 再退一步，用文字搜尋
        for text in ["儲存", "保存", "Save"]:
            try:
                loc = page.get_by_text(text, exact=False)
                if await loc.count() > 0:
                    await loc.first.click()
                    print(f"[calendar_agent] clicked save button via text: {text}")
                    logger.info(f"[CAL] click Save via text={text}")
                    save_clicked = True
                    break
            except Exception:
                continue

    if not save_clicked:
        logger.error("[CAL] cannot find Save button")
        raise RuntimeError("找不到儲存/保存/Save 按鈕")

    await page.wait_for_timeout(2000)
    logger.info("[CAL] event creation finished")
    print("[calendar_agent] event creation flow finished (標題+儲存)")


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
    except Exception:
        logger.error("[CAL] create_event_with_conflict_check failed", exc_info=True)
        # 截圖幫助 debug
        try:
            await page.screenshot(path="calendar_error.png", full_page=True)
            logger.info("[CAL] screenshot saved: calendar_error.png")
        except Exception:
            logger.warning("[CAL] screenshot failed", exc_info=True)
        return False, "操作日历时发生内部错误。"
    finally:
        await context.close()
        await browser.close()
        await p.stop()