# backend/calendar_agent.py
import os
from datetime import datetime
from typing import Tuple
from playwright.sync_api import sync_playwright
from config import STORAGE_STATE_PATH, GOOGLE_CAL_URL
import re
import time
from re import compile as re_compile

def dismiss_workspace_popups(page):
    """
    嘗試關掉 Google Workspace / Cookie / 訂閱相關的彈窗，
    讓畫面回到真正的 Calendar 主 UI。
    """
    # 先處理常見的按鈕文字
    for text in ["Agree", "No thanks", "Manage cookies"]:
        btn = page.get_by_role("button", name=text)
        try:
            if btn.count() > 0:
                print(f"[calendar_agent] clicking popup button: {text}")
                btn.first.click()
                page.wait_for_timeout(500)
        except Exception as e:
            print(f"[calendar_agent] failed clicking {text}:", repr(e))

    # 再嘗試關閉 generic 的 Close 按鈕
    try:
        close_btns = page.get_by_role("button", name="Close")
        if close_btns.count() > 0:
            print("[calendar_agent] closing popup via Close button")
            close_btns.first.click()
            page.wait_for_timeout(500)
    except Exception as e:
        print("[calendar_agent] failed closing via Close:", repr(e))

def _goto_date(page, start: datetime):
    # 正確的 Google Calendar 日視圖 URL：/day/YYYY/MM/DD
    target_url = f"{GOOGLE_CAL_URL}/u/0/r/day/{start.year}/{start.month}/{start.day}"
    print("[calendar_agent] goto:", target_url)

    page.goto(target_url, wait_until="networkidle")
    page.wait_for_timeout(2000)

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

def _has_conflict(page, start: datetime, end: datetime) -> Tuple[bool, str]:
    """
    檢查指定時間段是否已有事件。
    這裡用 day view 上事件卡片的顯示方式：
      - 事件卡片顯示 '上午10點 - 11點'
      - 我們用 '上午10點' 這個關鍵字去找 role='button' 的元素
    """
    start_hour_label = format_tw_hour_label(start)  # 例如 '上午10點'
    print("[calendar_agent] check conflict with hour label:", start_hour_label)

    # 先列出一些候選，用來 debug 看看有哪些 button 是事件
    all_buttons = page.locator("[role='button']")
    total = all_buttons.count()
    print(f"[calendar_agent] debug: [role=button] total = {total}")
    for i in range(min(total, 5)):
        try:
            text = all_buttons.nth(i).inner_text()
            aria = all_buttons.nth(i).get_attribute("aria-label")
            print(f"  [btn {i}] text={text!r}, aria-label={aria!r}")
        except Exception:
            pass

    # 真正用來判斷衝突：按鈕文字中包含 '上午10點'
    conflict_locator = page.locator("[role='button']", has_text=start_hour_label)
    conflict_count = conflict_locator.count()
    print("[calendar_agent] conflict candidates with hour label:", conflict_count)

    if conflict_count > 0:
        # 優先用 aria-label 當成回報文字，沒有就用 inner_text
        label = conflict_locator.nth(0).get_attribute("aria-label")
        print(f"Label: {label}")
        if not label:
            try:
                label = conflict_locator.nth(0).inner_text().split("\n")[0]
            except Exception:
                label = "指定時間已有日程"
        return True, label

    return False, ""

def debug_buttons(page):
    buttons = page.locator("button").all()
    print(f"\n找到 {len(buttons)} 個按鈕:")
    for i, btn in enumerate(buttons[:30]):  # 看多一點
        try:
            text = btn.inner_text(timeout=1000)
            aria_label = btn.get_attribute("aria-label")
            print(f"{i}: text={text!r}, aria-label={aria_label!r}")
        except:
            pass


def debug_menuitems(page):
    items = page.locator("[role='menuitem']").all()
    print(f"\n找到 {len(items)} 個 menuitem:")
    for i, it in enumerate(items[:20]):
        try:
            text = it.inner_text(timeout=1000)
            print(f"{i}: '{text}'")
        except:
            pass

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

def debug_dialog_inputs(page):
    dialog = page.get_by_role("dialog").first
    inputs = dialog.locator("input").all()
    print(f"\n[debug] dialog 裡找到 {len(inputs)} 個 input:")
    for i, inp in enumerate(inputs):
        try:
            aria = inp.get_attribute("aria-label")
            try:
                value = inp.input_value()
            except Exception:
                value = "<no input_value>"
            print(f"{i}: aria-label={aria!r}, value={value!r}")
        except Exception:
            pass

def _create_event(page, start: datetime, end: datetime, title: str):
    print("[calendar_agent] creating event:", title)
    # 1. 點「建立」按鈕
    create_btn = page.locator("button:has-text('建立')").first
    create_btn.click()
    print("[calendar_agent] clicked 建立 button")
    page.wait_for_timeout(800)

    # 2. 點「活動」選單項
    try:
        event_item = page.get_by_role("menuitem", name=re_compile("活動"))
        event_item.click()
        print("[calendar_agent] clicked 活動 via role=menuitem")
    except Exception as e:
        print("[calendar_agent] failed to click 活動 via role=menuitem:", repr(e))
        event_item = page.locator("[role='menuitem']:has-text('活動')").first
        event_item.click()
        print("[calendar_agent] clicked 活動 via [role='menuitem']:has-text('活動')")

    page.wait_for_timeout(1000)

    # 3. 找「標題」輸入框
    title_input = None
    for selector in [
        "input[aria-label*='標題']",   # 繁中介面 (標題 / 新增標題)
        "input[aria-label*='标题']",   # 簡中介面
        "input[aria-label*='Title']", # 英文介面
    ]:
        loc = page.locator(selector)
        if loc.count() > 0:
            title_input = loc.first
            print(f"[calendar_agent] found title input by selector: {selector}")
            break

    if title_input is None:
        # 再退一步：抓對話框裡第一個 textbox
        try:
            dialog = page.get_by_role("dialog").nth(0)
            title_input = dialog.get_by_role("textbox").first
            print("[calendar_agent] fallback: use first textbox in dialog as title input")
        except Exception as e:
            print("[calendar_agent] cannot find title input:", repr(e))
            raise RuntimeError("找不到標題輸入框") from e

    #clean_title = title.lstrip("点我").lstrip("點我")
    clean_title = title
    print("[calendar_agent] fill title =", clean_title)
    title_input.fill(clean_title)
    page.wait_for_timeout(500)

    # 先 debug 看看有哪些欄位
    debug_dialog_inputs(page)

    # 3.5 設定開始 / 結束時間
    start_str = format_tw_12h_time(start)  # 上午10:00
    end_str   = format_tw_12h_time(end)    # 上午11:00
    print("[calendar_agent] set time:", start_str, "->", end_str)

    dialog = page.get_by_role("dialog").first

    start_box = None
    end_box   = None

    # 直接用 aria-label 精準抓 input
    try:
        start_box = dialog.locator("input[aria-label='開始時間']").first
        end_box   = dialog.locator("input[aria-label='結束時間']").first
        print("[calendar_agent] found time inputs via aria-label='開始時間'/'結束時間'")
    except Exception as e:
        print("[calendar_agent] aria-label selector failed, fallback to index:", repr(e))
        try:
            inputs = dialog.locator("input")
            # 根據 debug：2 = 開始時間, 3 = 結束時間
            start_box = inputs.nth(2)
            end_box   = inputs.nth(3)
            print("[calendar_agent] fallback: use dialog input index 2/3 for start/end time")
        except Exception as e2:
            print("[calendar_agent] still cannot find time inputs:", repr(e2))

    if start_box and end_box:
        print("[calendar_agent] setting time via JS evaluate")

        # 直接用 JS 改 value，並觸發 input / change 事件
        start_box.evaluate(
            """(el, v) => {
                el.value = v;
                el.dispatchEvent(new Event('input',  { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }""",
            start_str,
        )

        end_box.evaluate(
            """(el, v) => {
                el.value = v;
                el.dispatchEvent(new Event('input',  { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }""",
            end_str,
        )

        page.wait_for_timeout(500)
    else:
        print("[calendar_agent] WARNING: 找不到開始/結束時間欄位，使用預設時間")




    # 4. 點「儲存 / 保存 / Save」按鈕
    save_clicked = False
    for name_pattern in ["儲存", "保存", "Save"]:
        try:
            btn = page.get_by_role("button", name=re_compile(name_pattern))
            if btn.count() > 0:
                btn.first.click()
                print(f"[calendar_agent] clicked save button via name pattern: {name_pattern}")
                save_clicked = True
                break
        except Exception:
            pass

    if not save_clicked:
        # 再退一步，用文字搜尋
        for text in ["儲存", "保存", "Save"]:
            try:
                page.get_by_text(text, exact=False).first.click()
                print(f"[calendar_agent] clicked save button via text: {text}")
                save_clicked = True
                break
            except Exception:
                continue

    if not save_clicked:
        raise RuntimeError("找不到儲存/保存/Save 按鈕")

    page.wait_for_timeout(2000)
    print("[calendar_agent] event creation flow finished (標題+儲存)")

    

def create_event_with_conflict_check_sync(start: datetime, end: datetime, title: str):
    print("[debug] incoming title =", title)
    print("[calendar_agent] create_event_with_conflict_check_sync called")
    print("[calendar_agent] STORAGE_STATE_PATH =", STORAGE_STATE_PATH)

    try:
        with sync_playwright() as p:
            need_login = not os.path.exists(STORAGE_STATE_PATH)
            print("[calendar_agent] need_login =", need_login)

            #browser = p.chromium.launch(headless=False, slow_mo=100)
            CHROME_PATH = r"C:\\Program Files\\Google\\Chrome\Application\\chrome.exe"  
            # 如果你的 Chrome 在別的地方，我可以幫你查路徑

            browser = p.chromium.launch(
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



            if need_login:
                context = browser.new_context()
                page = context.new_page()
                print("[calendar_agent] 打开 Google Calendar 登录页...")
                page.goto(GOOGLE_CAL_URL)
                print("请在新打开的浏览器窗口中完成 Google 登录和多因子认证。")
                input("登录完成后，请回到终端按回车继续...")
                context.storage_state(path=STORAGE_STATE_PATH)
                print("[calendar_agent] 登录状态已保存到 storage_state.json")
            else:
                print("[calendar_agent] 使用已存在的 storage_state.json 复用登录状态")
                context = browser.new_context(storage_state=STORAGE_STATE_PATH)
                page = context.new_page()
                page.goto(GOOGLE_CAL_URL)

            try:
                _goto_date(page, start)
                has_conflict, conflict_info = _has_conflict(page, start, end)
                if has_conflict:
                    print("[calendar_agent] conflict1:", conflict_info)
                    return False, conflict_info

                dismiss_workspace_popups(page)

                _create_event(page, start, end, title)
                return True, ""
            finally:
                pass
                #context.close()
                #browser.close()
            # 后面你的原始逻辑都放在这个 with 里面
    except Exception as e:
        import traceback
        print("========== Playwright traceback ==========")
        traceback.print_exc()
        print("========== Playwright traceback ==========")
        # 继续把异常抛给上层，让 voice_bot 返回給前端
        raise

def xxxcreate_event_with_conflict_check_sync(start: datetime, end: datetime, title: str):
    """
    同步版本：
    - 打开 / 复用 Google 登录
    - 切到指定日期
    - 检查冲突
    - 如空闲则创建日程
    返回:
        (created: bool, conflict_info: str)
    """
    print("[calendar_agent] create_event_with_conflict_check_sync called")
    print("[calendar_agent] STORAGE_STATE_PATH =", STORAGE_STATE_PATH)

    with sync_playwright() as p:
        need_login = not os.path.exists(STORAGE_STATE_PATH)
        print("[calendar_agent] need_login =", need_login)

        # 调试阶段统一 headless=False，方便你看浏览器情况
        browser = p.chromium.launch(headless=False, slow_mo=100)
        if need_login:
            context = browser.new_context()
            page = context.new_page()
            print("[calendar_agent] 打开 Google Calendar 登录页...")
            page.goto(GOOGLE_CAL_URL)
            print("请在新打开的浏览器窗口中完成 Google 登录和多因子认证。")
            input("登录完成后，请回到终端按回车继续...")
            context.storage_state(path=STORAGE_STATE_PATH)
            print("[calendar_agent] 登录状态已保存到 storage_state.json")
        else:
            print("[calendar_agent] 使用已存在的 storage_state.json 复用登录状态")
            context = browser.new_context(storage_state=STORAGE_STATE_PATH)
            page = context.new_page()
            page.goto(GOOGLE_CAL_URL)

        try:
            _goto_date(page, start)
            has_conflict, conflict_info = _has_conflict(page, start, end)
            if has_conflict:
                print("[calendar_agent] conflict2:", conflict_info)
                return False, conflict_info

            _create_event(page, start, end, title)
            return True, ""
        finally:
            pass
            # context.close()
            # browser.close()
