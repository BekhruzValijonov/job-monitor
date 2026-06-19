"""Хранилище вакансий в SQLite.

Чтобы потом отвечать на вопросы:
  - какие вакансии я уже видел?      -> SELECT * FROM vacancies;
  - какие каналы дают лучшие вакансии? -> SELECT channel, AVG(score), COUNT(*)
                                          FROM vacancies GROUP BY channel;

score/decision проставляет AI-агент в n8n. Python запишет их, только если
вебхук вернёт их в HTTP-ответе (см. parse_ai_result); иначе колонки = NULL.
"""

import sqlite3
import threading
from datetime import datetime, timezone

DB_PATH = "vacancies.db"
_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS vacancies (
            id         TEXT PRIMARY KEY,
            channel    TEXT,
            title      TEXT,
            url        TEXT,
            score      INTEGER,
            decision   TEXT,
            created_at TEXT
        )
        """
    )
    return conn


def save_vacancy(vacancy_id, channel, title, url, score=None, decision=None):
    """Сохранить вакансию. Повторный id игнорируется (INSERT OR IGNORE)."""
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO vacancies
                    (id, channel, title, url, score, decision, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    vacancy_id,
                    channel,
                    title,
                    url,
                    score,
                    decision,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()


def recent(limit: int):
    """Последние вакансии (для пагинации в боте): title, channel, url, score."""
    conn = _connect()
    try:
        return conn.execute(
            """
            SELECT title, channel, url, score, created_at
            FROM vacancies ORDER BY created_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        conn.close()


def stats() -> dict:
    """Сводка для команды /status: всего, по каналам, время последней записи."""
    conn = _connect()
    try:
        total = conn.execute("SELECT COUNT(*) FROM vacancies").fetchone()[0]
        by_channel = conn.execute(
            """
            SELECT channel, COUNT(*) AS cnt
            FROM vacancies GROUP BY channel ORDER BY cnt DESC LIMIT 10
            """
        ).fetchall()
        last = conn.execute(
            "SELECT created_at FROM vacancies ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        return {
            "total": total,
            "by_channel": by_channel,
            "last": last[0] if last else None,
        }
    finally:
        conn.close()


def parse_ai_result(response):
    """Достать (score, decision) из ответа вебхука n8n, если он их вернул.

    Терпимо к формату: объект {...}, либо массив [{...}] (как у n8n).
    Если ответ не JSON или полей нет — вернёт (None, None).
    """
    try:
        data = response.json()
    except Exception:
        return None, None

    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        return None, None

    score = data.get("score")
    try:
        score = int(score) if score is not None else None
    except (TypeError, ValueError):
        score = None

    decision = data.get("decision")
    return score, decision
