# backend/voice_bot.py
from datetime import datetime
from typing import Optional, Dict, Any
from nlp_parser import parse_schedule_from_text
from calendar_agent import create_event_with_conflict_check
from logger import logger

welcome_text = "您好，我是您的日程助手，你要记录什么日程？"

# 简单全局状态（正式可以用 session / redis）
state = {
    "pending_event": None,
    "waiting_new_time": False,
    
}

async def handle_user_message(text: str) -> str:
    logger.info(f"[BOT] raw user text = {text!r}")
    global state

    # if not state["greeted"]:
    #     state["greeted"] = True
    #     return "您好，我是您的日程助手，請問需要記錄什麼日程？"
    
    # 第一步：解析日程
    event = parse_schedule_from_text(text)
    if event is None:
            logger.info("[BOT] NLP failed on first try")
            return "我没有听清楚具体的时间或标题，请再说一遍，例如：明天上午十点到十一点，和公司CEO会议。"
    start = event["start"]
    end = event["end"]
    title = event["title"]

    logger.info(
        f"[BOT] event ready: date={start.date()}, "
        f"{start.hour}:00-{end.hour}:00, title={title!r}"
    )

    # 调用 Playwright Agent 检查冲突并创建日程
    try:
        created, conflict_info = await create_event_with_conflict_check(start, end, title)
    except Exception as e:
        logger.error("[BOT] calendar agent exception", exc_info=True)
        print("Error in calendar agent:", e)
        return "在操作谷歌日历时发生错误，请稍后再试。"

    if created:
        date_str = f"{start.month}月{start.day}日 {start.hour}点"
        end_str = f"{end.hour}点"
        return f"好的，已经在 {date_str} 到 {end_str} 为您创建日程：{title}。"

    # 有冲突
    logger.info(f"[BOT] conflict: {conflict_info}")
    state["waiting_new_time"] = True
    date_str = f"{start.month}月{start.day}日 {start.hour}点"
    end_str = f"{end.hour}点"
    return f"您在 {date_str} 到 {end_str} 已有日程安排：{conflict_info}，请说一个新的时间。"
