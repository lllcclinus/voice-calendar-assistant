# backend/voice_bot.py
from typing import Optional, Dict, Any
from fastapi.concurrency import run_in_threadpool

from nlp_parser import parse_schedule_from_text
from calendar_agent import create_event_with_conflict_check_sync
import re
from datetime import datetime, timedelta

welcome_text = "您好，我是您的日程助手，你要记录什么日程？"


# 简单全局状态（正式可以用 session / redis）
state: Dict[str, Any] = {
    "pending_event": None,   # {"start": datetime, "end": datetime, "title": str}
    "waiting_new_time": False,
}

async def handle_user_message(text: str) -> str:
    global state

    # 第一步：解析日程
    if state["pending_event"] is None or not state["waiting_new_time"]:
        event = parse_schedule_from_text(text)
        if event is None:
            return "我没有听清楚具体的时间或标题，请再说一遍，例如：明天上午十点到十一点，和公司CEO会议。"

        state["pending_event"] = event
    else:
        # 用户正在重新提供时间，只更新时间，不改标题
        event = parse_schedule_from_text(text)
        if event is None:
            return "我还是没听清时间，请再说一次新的时间。"
        event["title"] = state["pending_event"]["title"]
        state["pending_event"] = event

    event = state["pending_event"]
    start = event["start"]
    end = event["end"]
    title = event["title"]

    # 调用 Playwright Agent 检查冲突并创建日程
    try:
        # 用线程池调用同步的 Playwright 函数，避免 async 在 Windows 上的问题
        created, conflict_info = await run_in_threadpool(
            create_event_with_conflict_check_sync, start, end, title
        )
    except Exception as e:
        err_text = f"Playwright 出错: {repr(e)}"
        print(err_text)
        state["waiting_new_time"] = False
        state["pending_event"] = None
        return err_text

    if created:
        date_str = f"{start.month}月{start.day}日 {start.hour}点"
        end_str = f"{end.hour}点"
        return f"好的，已经在 {date_str} 到 {end_str} 为您创建日程：{title}。"

    # 有冲突
    state["waiting_new_time"] = True
    date_str = f"{start.month}月{start.day}日 {start.hour}点"
    end_str = f"{end.hour}点"
    return f"您在 {date_str} 到 {end_str} 已有日程安排：{conflict_info}，请说一个新的时间。"
