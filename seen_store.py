"""Персистентная защита от дублей.

Храним обработанные ключи в JSON-файле вида {"-100123456_4567": true},
чтобы дубли не проходили после:
  - перезапуска скрипта;
  - перепоста сообщения в канале;
  - повторной обработки истории Telethon.

У каждого источника свой файл (processed_telegram.json и т.п.), чтобы
параллельные процессы не затирали записи друг друга.
"""

import json
import os
import threading


class SeenStore:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self._seen = self._load()

    def _load(self) -> dict:
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return dict(data) if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            # битый файл не должен ронять бота — начинаем с чистого листа
            return {}

    def seen(self, key: str) -> bool:
        return key in self._seen

    def add(self, key: str) -> None:
        with self._lock:
            if key in self._seen:
                return
            self._seen[key] = True
            self._save()

    def _save(self) -> None:
        # атомарно: пишем во временный файл и подменяем, чтобы не оставить
        # полузаписанный JSON при падении/прерывании.
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._seen, f, ensure_ascii=False)
        os.replace(tmp, self.path)
