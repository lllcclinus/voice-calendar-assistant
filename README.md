# voice-calendar-assistant
voice-calendar-assistant

Install requirements:
cd voice-calendar-assistant
pip install -r requirements.txt
playwright install

Run app:
cd backend
uvicorn app:app --reload

Open index.html with chrome/edge browser

限制:
現只支持以下說法:
日期：今天 / 明天 / 后天
時間: 幾點 到 幾點
目的/Title: 幾點到幾點之後的語句作為 Title

例子: 明天  上午十点到十一点  和公司CEO会议。
