import fcntl
import os
import requests
from telethon import TelegramClient, events
from dotenv import load_dotenv

import db
from filters import garbage_reason
from seen_store import SeenStore

load_dotenv()

seen_store = SeenStore("processed_telegram.json")

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

    key = f"{message.chat_id}_{message.id}"
    if seen_store.seen(key):
        return
    seen_store.add(key)

    reason = garbage_reason(text)
    if reason:
        print("Skip garbage:", reason, "::", text[:80].replace("\n", " "))
        return

    chat = await message.get_chat()
    username = getattr(chat, "username", None)

    title = text.strip().splitlines()[0][:120]

    payload = {
        "source": "telegram",
        "channel": f"@{username}" if username else str(message.chat_id),
        "title": title,
        "text": text,
        "text_preview": text[:500],
        "url": f"https://t.me/{username}/{message.id}" if username else "",
        "posted_at": message.date.isoformat(),
    }

    ai = None
    try:
        response = requests.post(N8N_WEBHOOK_URL, json=payload, timeout=60)
        print("Sent to n8n:", response.status_code, payload["channel"], text[:120])
        ai = db.parse_ai_result(response)
    except Exception as e:
        print("Error sending to n8n:", e)

    db.save_vacancy(
        vacancy_id=f"telegram_{message.chat_id}_{message.id}",
        channel=payload["channel"],
        title=title,
        url=payload["url"],
        ai=ai,
    )


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


def _ensure_single_instance():
    """Не дать запустить второй экземпляр слушателя (его уже авто-стартует бот):
    иначе два процесса дерутся за сессию Telethon → 'database is locked'."""
    lock = open("channels.lock", "w")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        raise SystemExit(
            "channels.py уже запущен (его поднимает бот).\n"
            "Останови старый процесс: pkill -f channels.py"
        )
    return lock  # держим открытым, чтобы flock не снялся


if __name__ == "__main__":
    _instance_lock = _ensure_single_instance()
    with client:
        client.loop.run_until_complete(main())