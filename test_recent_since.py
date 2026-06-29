"""Тест пагинации «только новые с прошлого раза».

Проверяет db.recent(limit, prefix, after=cursor):
  - без after — последние N (как раньше);
  - с after — только записи новее курсора, по возрастанию created_at,
    чтобы повторный запрос не повторял уже показанные вакансии.
"""

import os
import tempfile

import db


def _seed(rows):
    """rows: список (id, created_at). Пишем напрямую с заданным created_at."""
    conn = db._connect()
    try:
        for vid, created in rows:
            conn.execute(
                "INSERT OR IGNORE INTO vacancies (id, channel, title, url, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (vid, "ch", vid, "u", created),
            )
        conn.commit()
    finally:
        conn.close()


def test_recent_since():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db.DB_PATH = path
    try:
        _seed([
            ("remoteok_1", "2026-06-01T00:00:00+00:00"),
            ("remoteok_2", "2026-06-02T00:00:00+00:00"),
            ("remoteok_3", "2026-06-03T00:00:00+00:00"),
            ("remoteok_4", "2026-06-04T00:00:00+00:00"),
        ])

        # Без курсора — последние 2 (новейшие первыми).
        rows = db.recent(2, "remoteok_")
        ids = [r[0] for r in rows]  # title == id в сидере
        assert ids == ["remoteok_4", "remoteok_3"], ids
        cursor = max(r[5] for r in rows)  # created_at новейшей показанной
        assert cursor == "2026-06-04T00:00:00+00:00", cursor

        # Повторный запрос с тем же курсором — новых нет.
        assert db.recent(2, "remoteok_", after=cursor) == []

        # Появилась новая вакансия позже курсора.
        _seed([("remoteok_5", "2026-06-05T00:00:00+00:00")])
        rows2 = db.recent(2, "remoteok_", after=cursor)
        assert [r[0] for r in rows2] == ["remoteok_5"], rows2

        print("OK test_recent_since")
    finally:
        os.remove(path)


if __name__ == "__main__":
    test_recent_since()
