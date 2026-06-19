import os
import re
import time
import html
import requests
from dotenv import load_dotenv

import db
from filters import garbage_reason
from seen_store import SeenStore

load_dotenv()

N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")
DRY_RUN = os.getenv("DRY_RUN") == "1"  # 1 — не слать в n8n, только печатать

# RemoteOK блокирует запросы без внятного User-Agent.
USER_AGENT = "vacancy-bot/1.0 (sxmebytes@gmail.com)"
API_URL = "https://remoteok.com/api"

# Отбираем релевантные вакансии по ДОЛЖНОСТИ (position), а не по тегам:
# RemoteOK набивает каждую вакансию десятками SEO-тегов (у «Executive Assistant»
# есть тег "react"), поэтому теги для фильтрации бесполезны.
RELEVANT_PATTERNS = [
    r"\breact\b",
    r"front[\s-]?end",
    r"\btypescript\b",
    r"\bjavascript\b",
    r"next\.?js",
    r"\belectron\b",
    r"\bvue(?:\.js)?\b",
    r"\bweb\s+developer\b",
    r"\bui\s+(?:developer|engineer)\b",
    r"full[\s-]?stack",
]

_POS_RX = re.compile("|".join(RELEVANT_PATTERNS), re.IGNORECASE)
_HTML_TAG_RX = re.compile(r"<[^>]+>")


def fetch_remoteok():
    response = requests.get(API_URL, headers={"User-Agent": USER_AGENT}, timeout=25)
    response.raise_for_status()
    data = response.json()
    # Первый элемент — служебный (legal/last_updated), вакансии идут дальше.
    return [item for item in data if item.get("id")]


def is_relevant(job: dict) -> bool:
    return bool(_POS_RX.search(job.get("position", "")))


def clean_html(raw: str) -> str:
    text = _HTML_TAG_RX.sub(" ", raw or "")
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:1500]


def send_to_n8n(job: dict):
    salary_min = job.get("salary_min") or 0
    salary_max = job.get("salary_max") or 0
    salary = f"{salary_min} - {salary_max} USD" if (salary_min or salary_max) else ""
    tags = ", ".join(job.get("tags") or [])

    payload = {
        "source": "remoteok",
        "channel": "remoteok.com",
        "title": job.get("position", ""),
        "text": f"""
{job.get("position", "")}

Компания: {job.get("company", "")}
Локация: {job.get("location") or "Remote"}
Зарплата: {salary}
Теги: {tags}

{clean_html(job.get("description", ""))}
""",
        "url": job.get("url", ""),
    }
    payload["text_preview"] = payload["text"].strip()[:500]

    reason = garbage_reason(payload["text"])
    if reason:
        print("Skip garbage:", reason, "::", payload["title"])
        return

    if DRY_RUN:
        print("[dry-run] would send:", payload["title"])
        return

    score, decision = None, None
    try:
        res = requests.post(N8N_WEBHOOK_URL, json=payload, timeout=20)
        print("Sent to n8n:", res.status_code, payload["title"])
        score, decision = db.parse_ai_result(res)
    except Exception as e:
        print("Error sending to n8n:", e)

    db.save_vacancy(
        vacancy_id=f"remoteok_{job.get('id')}",
        channel=payload["channel"],
        title=payload["title"],
        url=payload["url"],
        score=score,
        decision=decision,
    )


def main():
    jobs = fetch_remoteok()
    store = SeenStore("processed_remoteok.json")
    relevant = 0

    for job in jobs:
        if not is_relevant(job):
            continue

        key = f"remoteok_{job.get('id')}"
        if store.seen(key):
            continue
        store.add(key)

        relevant += 1
        send_to_n8n(job)
        time.sleep(0.3)

    print(f"Done. Total: {len(jobs)}, relevant new: {relevant}")


if __name__ == "__main__":
    main()
