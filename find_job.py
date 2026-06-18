from telethon import TelegramClient
import os
from dotenv import load_dotenv

load_dotenv()

client = TelegramClient(
    "vacancy_session",
    int(os.getenv("API_ID")),
    os.getenv("API_HASH"),
)

async def main():
    entity = await client.get_entity("Remoteit")
    print(entity)

with client:
    client.loop.run_until_complete(main())