from openai import OpenAI
from datetime import datetime
import sys
from logger import logger
from typing import Optional, Dict
import re
sys.stdout.reconfigure(encoding='utf-8')

#OPENAI API KEY 
###############
#AI MODEL
GPT_MODEL = "gpt-5.1"  #"gpt-4-0613" #"gpt-4-turbo-preview" #"gpt-4-1106-preview" #"gpt-3.5-turbo-1106"
#SYSTEM PROMPT
systemPrompt = [{"role": "system", "content": """
                 我想你把輸入語句分析成 年月日時分開始結束及目的. 
                 例如"{2025,11,28,3:00,4:00, 開會}" 時間以 24小時制: 
                 語句前會寫出當前的年月日時分並以 Now 作開頭, 像 Now:2025-11-28 14:28.
                 然後會接著語句 Now:2025-11-28 14:28, 明天上午 10點到 11點開會.
                 這樣你應該用這種格式回應: {2025,11,29,10:00,11:00,開會}
                 如果語句不能完整編成 年月日時分開始結束及目的, 則回傳 {None}
                 其他語句依此類推.
                 """}]
#User Prompt
message = {"role": "user", "content": "Hello" }

def parse_schedule_from_text(text: str) -> Optional[Dict]:
    
    now = datetime.now()
    formatted = now.strftime("Now:%Y-%m-%d %H:%M")
    message["content"]= formatted +" , "+text
    conversation=systemPrompt.copy()
    conversation.append(message)
    response = client.chat.completions.create(model=GPT_MODEL, messages=conversation, temperature=0) 
    s = response.choices[0].message
    logger.info(f"[AINLP] raw AI text = {s!r}")
    
    # Extract the content string from the message object
    content_str = s.content
    
    match = re.search(r"\{(.+?)\}", content_str)
    if not match:
        print("No data found")
        logger.warning("[AINLP] empty text")
        return None

    content = match.group(1).strip()  # Extract content inside braces
    
    # Check if content is None, none, or empty
    if content.lower() == "none" or content == "":
        print("No valid schedule data")
        logger.warning("[AINLP] response indicates no valid schedule")
        return None

    parts = [part.strip() for part in content.split(",")]
    
    # Validate that we have at least 6 parts (year, month, day, start_time, end_time, title)
    if len(parts) < 6:
        print("Incomplete schedule data")
        logger.warning(f"[AINLP] incomplete data: {parts}")
        return None

    try:
        # Parse values
        year = int(parts[0])
        month = int(parts[1])
        day = int(parts[2])

        start_hour, start_min = map(int, parts[3].split(":"))
        end_hour, end_min = map(int, parts[4].split(":"))

        title = ",".join(parts[5:]).strip()  # Join remaining parts in case title contains commas

        # Compose datetime
        start_dt = datetime(year, month, day, start_hour, start_min)
        end_dt = datetime(year, month, day, end_hour, end_min)

        print(start_dt)
        print(end_dt)
        print("Title:", title)
        logger.info(f"[AINLP] extracted text = {start_dt!r} {end_dt!r} {title!r}")

        return {
            "start": start_dt,
            "end": end_dt,
            "title": title
        }
    except (ValueError, IndexError) as e:
        print(f"Error parsing schedule data: {e}")
        logger.error(f"[AINLP] parsing error: {e}, content: {content}")
        return None


if __name__ == "__main__":
    #Prepare user prompt   
    #old prompt
    """
    我明天很忙，那麼就再過一天下午三時到四時開會，啊說錯了，打麻將才對.
    Hello 你好呀, 今天實在太忙了, 你幫我記下三天後六點到七點要去看牙醫.
    明天三點去打藍球, 約兩個鐘才回來.
    明年一月給董事會做報告一個小時, 二號 2點半吧!
    明天下午三點到四點和 CEO 開會, 幫我以 CEO 的全寫做 Title.
    """
    new_text = "明天三點到四點和 CEO 開會, 幫我以 CEO 的全寫做 Title."
    # now = datetime.now()
    # formatted = now.strftime("Now:%Y-%m-%d %H:%M")
    # message["content"]= formatted +" , "+new_text
    # conversation=systemPrompt.copy()
    # conversation.append(message)
    # response = client.chat.completions.create(model=GPT_MODEL, messages=conversation, temperature=0) 
    # print(response.choices[0].message)
    result = parse_schedule_from_text(new_text)
    print(result['start'])
    print(result['end'])
    print(result['title'])
