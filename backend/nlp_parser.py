# backend/nlp_parser.py
import re
from datetime import datetime, timedelta
from typing import Optional, Dict

def parse_schedule_from_text(text: str) -> Optional[Dict]:
    """
    简单规则：
    - 识别：今天 / 明天 / 后天
    - 识别：上午 / 下午
    - 时间：例如 '10点到11点' 或 '10点到11点开会一个小时' 中的 10 和 11
    - 标题：简单地取“从时间段后面开始”的部分
    """
    text = text.replace(" ", "")
    now = datetime.now()

    # 日期
    if "今天" in text:
        base_date = now.date()
    elif "明天" in text:
        base_date = (now + timedelta(days=1)).date()
    elif "后天" in text:
        base_date = (now + timedelta(days=2)).date()
    else:
        # 简化：先只做这三种，否则返回 None
        return None

    is_am = "上午" in text or "早上" in text or "早晨" in text
    is_pm = "下午" in text or "晚上" in text or "傍晚" in text

    # 时间段：匹配 10点到11点 或 10:00-11:00
    m = re.search(r'(\d{1,2})[点:时]到(\d{1,2})', text)
    if not m:
        # 也可以支持 “十点到十一点” 的中文数字，这里先省略
        return None

    start_hour = int(m.group(1))
    if "十" in start_hour:
        start_hour = 10
    end_hour = int(m.group(2))
    if "十一" in end_hour:
        end_hour = 11

    if is_pm and start_hour < 12:
        start_hour += 12
    if is_pm and end_hour <= 12:
        end_hour += 12
    # 上午默认保持不变

    start_dt = datetime(
        year=base_date.year, month=base_date.month, day=base_date.day,
        hour=start_hour, minute=0
    )
    end_dt = datetime(
        year=base_date.year, month=base_date.month, day=base_date.day,
        hour=end_hour, minute=0
    )

    # 标题：取 “点” 后面的内容，示例：“明天上午十点到11点，和公司CEO会议”
    # 这里用一个简单分割：找到时间段的结束位置，后面的当标题
    title_start_idx = m.end()
    title = text[title_start_idx:]
    # 去掉可能存在的逗号、连接词
    title = title.lstrip("，,:。:").replace("加上一个日程安排", "").replace("加上一个日程", "")
    if not title:
        title = "未命名日程"

    return {
        "start": start_dt,
        "end": end_dt,
        "title": title
    }
