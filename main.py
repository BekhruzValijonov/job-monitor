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
    "Remoteit",
    # сюда потом добавишь ещё каналы
]


async def send_to_n8n(message):
    text = message.raw_text or ""

    if not text.strip():
        return

    chat = await message.get_chat()
    username = getattr(chat, "username", None)

    payload = {
        "source": "telegram",
        "channel": f"@{username}" if username else str(message.chat_id),
        "text": text,
        "url": f"https://t.me/{username}/{message.id}" if username else "",
        "posted_at": message.date.isoformat(),
    }

    try:
        response = requests.post(N8N_WEBHOOK_URL, json=payload, timeout=15)
        print("Sent to n8n:", response.status_code, payload["channel"], text[:120])
    except Exception as e:
        print("Error sending to n8n:", e)


@client.on(events.NewMessage(chats=CHANNELS))
async def handler(event):
    await send_to_n8n(event.message)


async def backfill(limit=30):
    """Временно: прогнать последние посты каналов, чтобы не ждать новый.
    Убери вызов в main() после проверки."""
    for channel in CHANNELS:
        async for message in client.iter_messages(channel, limit=limit):
            await send_to_n8n(message)


async def main():
    await client.start()
    print("Vacancy reader started. Listening:", ", ".join(CHANNELS))

    await backfill(limit=3)  # TODO: убрать после проверки

    await client.run_until_disconnected()


with client:
    client.loop.run_until_complete(main())