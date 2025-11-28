#nlp_parser.py
import re
from datetime import datetime, timedelta
from typing import Optional, Dict
from logger import logger

# 中文数字映射
CN_NUM = {
    "零": 0, "〇": 0,
    "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}

def _cn_hour_to_int(word: str) -> Optional[int]:
    """
    把“十、十一、十二、二十、一点半里的前半段”等中文数词转成整数小时（0–24 范围内）
    支持：
      十    -> 10
      十一  -> 11
      二十  -> 20
      二十三 -> 23
      一    -> 1
      九    -> 9
      两    -> 2
    """
    if not word:
        return None

    # 标准化“两” -> “二”
    word = word.replace("两", "二")

    # 情况1：只有一位数字（如 "一", "九"）
    if "十" not in word:
        if word in CN_NUM:
            return CN_NUM[word]
        # 理论上不会到这里，如果到这里就先返回 None
        return None

    # 情况2：包含“十”
    # 例如 "十"、"十一"、"二十"、"二十三"
    parts = word.split("十")
    high = parts[0]   # 十前面
    low = parts[1]    # 十后面

    # 十前面为空：例如 "十一" -> high=""，默认 1 十
    if high == "":
        high_v = 1
    else:
        high_v = CN_NUM.get(high, None)
        if high_v is None:
            return None

    # 十后面为空：例如 "二十" -> low=""
    if low == "":
        low_v = 0
    else:
        # low 一般是一位，如 "一"；如果不是，就简单逐位累加（冗余安全）
        low_v = 0
        for ch in low:
            v = CN_NUM.get(ch, None)
            if v is None:
                return None
            low_v = low_v * 10 + v

    value = high_v * 10 + low_v
    # 简单限制到 0–24 之间
    if 0 <= value <= 24:
        return value
    return None


def _parse_hour(word: str) -> Optional[int]:
    """
    同时支持中文 & 阿拉伯数字的小时时间：
      - '五'   -> 5
      - '十一' -> 11
      - '6'    -> 6
      - '06'   -> 6
    """
    if not word:
        return None
    word = word.strip()

    # 只要里面有数字，就优先当数字处理
    m = re.search(r'\d{1,2}', word)
    if m:
        try:
            return int(m.group())
        except ValueError:
            return None

    # 否则当成纯中文数字处理
    return _cn_hour_to_int(word)


def parse_schedule_from_text(text: str) -> Optional[Dict]:
    """
    从中文语音文本中提取：
    - 日期：今天 / 明天 / 后天
    - 时间段：
        - 数字：10点到11点、9:00到10:00
        - 中文：十点到十一点、九点到十点
        - 混合：五点到6点、5点到六点
    - 标题：时间段之后的内容

    返回:
        {
            "start": datetime,
            "end": datetime,
            "title": str
        }
        或 None（解析失败）
    """
    if not text:
        logger.warning("[NLP] empty text")
        return None

    raw = text
    logger.info(f"[NLP] raw text = {raw!r}")
    # 去掉空格，语音识别经常会插入空格
    text = raw.replace(" ", "")

    now = datetime.now()

    # === 1. 解析日期 ===
    if "今天" in text:
        base_date = now.date()
    elif "明天" in text:
        base_date = (now + timedelta(days=1)).date()
    elif "后天" in text or "後天" in text:
        base_date = (now + timedelta(days=2)).date()
    else:
        # TODO: 可以扩展支持具体日期，如“5月20号”
        return None

    # === 2. 上午/下午/晚上 ===
    is_am = any(k in text for k in ["上午", "早上", "早晨", "清晨"])
    is_pm = any(k in text for k in ["下午", "中午"])
    is_night = any(k in text for k in ["晚上", "傍晚", "夜里", "夜裏"])

    # === 3. 解析时间段（混合：支持中文+数字） ===
    start_hour: Optional[int] = None
    end_hour: Optional[int] = None
    match_obj = None

    # 一個統一的正则：
    #   - 小时部分允许：中文数字 或 数字
    #   - “点/點/时/時/:” 都接受
    time_pattern = re.compile(
        r'([零一二三四五六七八九十两兩〇0-9]{1,3})[点點:时時](?:\d{0,2})?到([零一二三四五六七八九十两兩〇0-9]{1,3})[点點时時]?',
    )

    m = time_pattern.search(text)
    if m:
        h1 = _parse_hour(m.group(1))
        h2 = _parse_hour(m.group(2))
        if h1 is None or h2 is None:
            return None
        start_hour, end_hour = h1, h2
        match_obj = m

    if match_obj is None or start_hour is None or end_hour is None:
        logger.warning(f"[NLP] fail to parse time range, text={text!r}")
        # 没有识别到时间段
        return None

    # === 4. 处理 12/24 小时制 ===
    if (is_pm or is_night) and start_hour < 12:
        start_hour += 12
    if (is_pm or is_night) and end_hour <= 12:
        end_hour += 12


    

    start_dt = datetime(
        year=base_date.year,
        month=base_date.month,
        day=base_date.day,
        hour=start_hour,
        minute=0,
    )
    end_dt = datetime(
        year=base_date.year,
        month=base_date.month,
        day=base_date.day,
        hour=end_hour,
        minute=0,
    )

    # === 5. 从时间段后面截取标题 ===
    # 例如：“明天上午五点到6点打乒乓球”
    # match_obj.end() 是“6点”的后面，我们从这里往后都当标题
    title_start_idx = match_obj.end()
    title = text[title_start_idx:]

    # 清理一些常见前缀
    for prefix in ["，", ",", "。", ":", "：",
                   "加上一个日程安排", "加上一个日程",
                   "點", "点"]:
        if title.startswith(prefix):
            title = title[len(prefix):]

    title = title.strip()

    # 去掉結尾句號、驚嘆號、問號等
    title = title.rstrip("。．.!！?？;； ")

    if not title:
        title = "未命名日程"

    logger.info(
        f"[NLP] parsed: date={base_date}, "
        f"start_hour={start_hour}, end_hour={end_hour}, title={title!r}"
    )


    return {
        "start": start_dt,
        "end": end_dt,
        "title": title
    }
