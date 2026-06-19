import os
import sys
import time
import requests
from dotenv import load_dotenv

import db
import singleton
from filters import garbage_reason
from seen_store import SeenStore

load_dotenv()

N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "600"))  # период опроса, сек

# HH блокирует "обобщённые"/известные UA (job-monitor/* отдаёт bad_user_agent).
# Нужен уникальный, идентифицирующий приложение + контакт.
USER_AGENT = "vacancy-bot/1.0 (sxmebytes@gmail.com)"

HEADERS = {
    "User-Agent": USER_AGENT,
    "HH-User-Agent": USER_AGENT,
}

SEARCH_QUERIES = [
    "React TypeScript",
    "Frontend React",
    "Next.js",
    "React Native",
    "Electron",
]


def search_hh(query: str):
    params = {
        "text": query,
        "per_page": 20,
        "page": 0,
        "search_field": "name",
        "schedule": "remote",
    }

    response = requests.get(
        "https://api.hh.ru/vacancies",
        params=params,
        headers=HEADERS,
        timeout=20,
    )
    response.raise_for_status()
    return response.json().get("items", [])


def send_to_n8n(vacancy: dict):
    salary = vacancy.get("salary") or {}
    employer = vacancy.get("employer") or {}
    snippet = vacancy.get("snippet") or {}

    payload = {
        "source": "hh",
        "channel": "hh.ru",
        "title": vacancy.get("name", ""),
        "text": f"""
{vacancy.get("name", "")}

Компания: {employer.get("name", "")}
Зарплата: {salary.get("from") or ""} - {salary.get("to") or ""} {salary.get("currency") or ""}

{snippet.get("requirement") or ""}
{snippet.get("responsibility") or ""}
""",
        "url": vacancy.get("alternate_url", ""),
    }
    payload["text_preview"] = payload["text"].strip()[:500]

    reason = garbage_reason(payload["text"])
    if reason:
        print("Skip garbage:", reason, "::", payload["title"])
        return

    ai = None
    try:
        res = requests.post(N8N_WEBHOOK_URL, json=payload, timeout=60)
        print("Sent to n8n:", res.status_code, payload["title"])
        ai = db.parse_ai_result(res)
    except Exception as e:
        print("Error sending to n8n:", e)

    db.save_vacancy(
        vacancy_id=f"hh_{vacancy.get('id')}",
        channel=payload["channel"],
        title=payload["title"],
        url=payload["url"],
        ai=ai,
    )


def run_once():
    store = SeenStore("processed_hh.json")

    for query in SEARCH_QUERIES:
        vacancies = search_hh(query)

        for vacancy in vacancies:
            key = f"hh_{vacancy.get('id')}"

            if store.seen(key):
                continue

            store.add(key)
            send_to_n8n(vacancy)
            time.sleep(0.5)


def main():
    # Разовый прогон: python hh.py --once
    if "--once" in sys.argv:
        run_once()
        return

    # По умолчанию — слушаем в цикле, дубли отсекает seen_store.
    singleton.acquire("hh.lock", "hh.py")
    print(f"HH listener started (каждые {POLL_INTERVAL}s).")
    while True:
        try:
            run_once()
        except Exception as e:
            print("Cycle error:", e)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
