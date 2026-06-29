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
    conn = sqlite3.connect(DB_PATH, timeout=30)
    # WAL + busy_timeout: бот (чтение для статуса/пагинации) и channels.py/
    # источники (запись) работают с БД параллельно из разных процессов —
    # иначе SQLite сразу кидает "database is locked".
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS vacancies (
            id          TEXT PRIMARY KEY,
            channel     TEXT,
            title       TEXT,
            url         TEXT,
            score       INTEGER,
            decision    TEXT,
            created_at  TEXT,
            message     TEXT,
            ai_score    INTEGER,
            ai_decision TEXT,
            ai_summary  TEXT,
            ai_reason   TEXT,
            ai_message  TEXT,
            ai_relevant INTEGER
        )
        """
    )
    # Миграция старых БД: добавляем недостающие колонки (ALTER идемпотентен).
    for col, typ in (
        ("message", "TEXT"),
        ("ai_score", "INTEGER"), ("ai_decision", "TEXT"),
        ("ai_summary", "TEXT"), ("ai_reason", "TEXT"),
        ("ai_message", "TEXT"), ("ai_relevant", "INTEGER"),
    ):
        try:
            conn.execute(f"ALTER TABLE vacancies ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass
    return conn


def save_vacancy(vacancy_id, channel, title, url, ai=None):
    """Сохранить вакансию вместе с результатом AI-анализа (один раз).

    ai — dict из parse_ai_result (score/decision/summary/reason/message/relevant)
    или None. Повторный id игнорируется (INSERT OR IGNORE) — AI повторно не
    вызывается и данные не перезаписываются.
    """
    ai = ai or {}
    relevant = ai.get("relevant")
    ai_relevant = None if relevant is None else (1 if relevant else 0)

    with _lock:
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO vacancies
                    (id, channel, title, url, created_at,
                     ai_score, ai_decision, ai_summary, ai_reason, ai_message, ai_relevant)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    vacancy_id,
                    channel,
                    title,
                    url,
                    datetime.now(timezone.utc).isoformat(),
                    ai.get("score"),
                    ai.get("decision"),
                    ai.get("summary"),
                    ai.get("reason"),
                    ai.get("message"),
                    ai_relevant,
                ),
            )
            conn.commit()
        finally:
            conn.close()


def recent(limit: int, prefix: str = None, after: str = None):
    """Вакансии для пагинации в боте: title, channel, url, score, message, created_at.

    prefix — фильтр по источнику через префикс id (telegram_/hh_/remoteok_/wwr_).
    after — курсор created_at: если задан, отдаём ТОЛЬКО записи новее курсора
    (created_at > after) по ВОЗРАСТАНИЮ, чтобы повторный запрос показывал лишь
    новые вакансии, а не повторял уже показанные. Без after — последние N по
    убыванию (новейшие первыми), как при первом запросе.

    created_at пишется через datetime.isoformat() в UTC — формат лексикографически
    сравним, поэтому сравнение/сортировка по TEXT эквивалентны хронологическим.
    """
    conn = _connect()
    try:
        # COALESCE: показываем ai_message/ai_score, для старых записей — старые
        # колонки. Форма строки не меняется → пагинация/format_vacancy не трогаем.
        cols = ("SELECT title, channel, url, "
                "COALESCE(ai_score, score), COALESCE(ai_message, message), created_at "
                "FROM vacancies")
        where = []
        params = []
        if prefix:
            where.append("id LIKE ?")
            params.append(prefix + "%")
        if after:
            where.append("created_at > ?")
            params.append(after)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        order = "ASC" if after else "DESC"
        params.append(limit)
        return conn.execute(
            f"{cols}{clause} ORDER BY created_at {order} LIMIT ?",
            params,
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
    """Разобрать ответ вебхука n8n с результатом AI-анализа.

    Ожидаемый JSON (терпимо к obj {...} и массиву [{...}]):
        {"relevant": true, "score": 87, "decision": "hot",
         "summary": "...", "reason": "...", "message": "🔥 ..."}

    Возвращает dict {score, decision, summary, reason, message, relevant}
    или None, если ответ не JSON. message также читается из text/output/...
    """
    try:
        data = response.json()
    except Exception:
        return None

    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        return None

    def _str(*keys):
        for k in keys:
            v = data.get(k)
            if isinstance(v, str) and v.strip():
                return v
        return None

    score = data.get("score")
    try:
        score = int(score) if score is not None else None
    except (TypeError, ValueError):
        score = None

    relevant = data.get("relevant")

    return {
        "score": score,
        "decision": data.get("decision"),
        "summary": _str("summary"),
        "reason": _str("reason"),
        "message": _str("message", "text", "output", "formatted", "telegram", "result"),
        "relevant": bool(relevant) if relevant is not None else None,
    }
