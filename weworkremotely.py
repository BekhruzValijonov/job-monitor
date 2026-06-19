import os
import re
import time
import html
import xml.etree.ElementTree as ET

import requests
from dotenv import load_dotenv

import db
from filters import garbage_reason
from seen_store import SeenStore

load_dotenv()

N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")
DRY_RUN = os.getenv("DRY_RUN") == "1"  # 1 — не слать в n8n, только печатать

USER_AGENT = "vacancy-bot/1.0 (sxmebytes@gmail.com)"

# RSS-фиды релевантных категорий WeWorkRemotely.
FEEDS = [
    "https://weworkremotely.com/categories/remote-front-end-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
]

# Отбор по должности (как в remoteok.py): категория широкая и тянет QA/SDET/бэкенд.
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


def _txt(item, tag: str) -> str:
    el = item.find(tag)
    return (el.text or "").strip() if el is not None and el.text else ""


def clean_html(raw: str) -> str:
    text = _HTML_TAG_RX.sub(" ", raw or "")
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:1500]


def fetch_feed(url: str):
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=25)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    return root.findall(".//item")


def parse_item(item) -> dict:
    # title у WWR в формате "Компания: Должность"
    title = _txt(item, "title")
    if ":" in title:
        company, position = title.split(":", 1)
        company, position = company.strip(), position.strip()
    else:
        company, position = "", title

    return {
        "guid": _txt(item, "guid") or _txt(item, "link"),
        "company": company,
        "position": position,
        "url": _txt(item, "link"),
        "region": _txt(item, "region"),
        "type": _txt(item, "type"),
        "posted_at": _txt(item, "pubDate"),
        "description": clean_html(_txt(item, "description")),
    }


def is_relevant(job: dict) -> bool:
    return bool(_POS_RX.search(job["position"]))


def send_to_n8n(job: dict):
    payload = {
        "source": "weworkremotely",
        "channel": "weworkremotely.com",
        "title": job["position"],
        "text": f"""
{job["position"]}

Компания: {job["company"]}
Регион: {job["region"] or "Remote"}
Тип: {job["type"]}

{job["description"]}
""",
        "url": job["url"],
        "posted_at": job["posted_at"],
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
        vacancy_id=f"wwr_{job['guid']}",
        channel=payload["channel"],
        title=payload["title"],
        url=payload["url"],
        score=score,
        decision=decision,
    )


def main():
    store = SeenStore("processed_weworkremotely.json")
    total = 0
    relevant = 0

    for url in FEEDS:
        items = fetch_feed(url)
        total += len(items)

        for item in items:
            job = parse_item(item)

            if not is_relevant(job):
                continue

            key = f"wwr_{job['guid']}"
            if store.seen(key):
                continue
            store.add(key)

            relevant += 1
            send_to_n8n(job)
            time.sleep(0.3)

    print(f"Done. Total: {total}, relevant new: {relevant}")


if __name__ == "__main__":
    main()
