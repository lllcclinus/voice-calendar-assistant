# backend/config.py
import os

# 当前 backend 目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 保存 Google 登录状态的文件路径
STORAGE_STATE_PATH = os.path.join(BASE_DIR, "storage_state.json")

# Google Calendar 的入口 URL
GOOGLE_CAL_URL = "https://calendar.google.com/calendar"