import os
import requests
from telethon import TelegramClient, events
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")

client = TelegramClient("vacancy_session", API_ID, API_HASH)

CHANNELS = [
    # сюда потом добавишь каналы
    # "frontend_jobs",
    # "javascript_jobs",
]

@client.on(events.NewMessage(chats=CHANNELS))
async def handler(event):
    text = event.raw_text or ""

    if not text.strip():
        return

    chat = await event.get_chat()
    username = getattr(chat, "username", None)

    url = ""
    if username:
        url = f"https://t.me/{username}/{event.message.id}"

    payload = {
        "source": "telegram",
        "channel": f"@{username}" if username else str(event.chat_id),
        "text": text,
        "url": url,
        "posted_at": event.message.date.isoformat(),
    }

    try:
        response = requests.post(N8N_WEBHOOK_URL, json=payload, timeout=15)
        print("Sent:", response.status_code, payload["channel"], text[:80])
    except Exception as e:
        print("Error sending to n8n:", e)

async def main():
    await client.start()
    print("Vacancy reader started...")
    await client.run_until_disconnected()

with client:
    client.loop.run_until_complete(main())
