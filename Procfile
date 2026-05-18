web: uvicorn webhook:app --host 0.0.0.0 --port $PORT & uvicorn admin_api:app --host 0.0.0.0 --port 7788
worker: python discord_bot.py
