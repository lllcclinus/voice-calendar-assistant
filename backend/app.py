# backend/app.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from voice_bot import handle_user_message, welcome_text
from logger import logger

app = FastAPI(
    title="Voice Calendar Assistant",
    description="语音驱动 Google Calendar 日程助手（FastAPI + Playwright）",
    version="0.1.0",
)

# 开发阶段允许本机前端访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 正式环境建议收紧
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Message(BaseModel):
    text: str

class BotReply(BaseModel):
    text: str

@app.get("/api/welcome", response_model=BotReply)
async def get_welcome():
    logger.info("[HTTP] /api/welcome")
    return BotReply(text=welcome_text)

@app.post("/api/message", response_model=BotReply)
async def post_message(msg: Message):
    logger.info(f"[HTTP] /api/message text={msg.text!r}")
    try:
        reply = await handle_user_message(msg.text)
        logger.info(f"[HTTP] reply={reply!r}")
        return BotReply(text=reply)
    except Exception as e:
        logger.error("[HTTP] /api/message error", exc_info=True)
        # 回傳一個穩定的錯誤訊息，前端會唸出來
        return {"text": "在操作谷歌日历时发生错误，请稍后再试。"}
