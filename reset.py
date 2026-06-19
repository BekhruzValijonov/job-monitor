"""Очистка локальных сохранённых данных проекта.

По умолчанию удаляет:
  - vacancies.db (+ WAL-спутники) — все сохранённые вакансии;
  - processed_*.json — состояние дедупа (ВНИМАНИЕ: после этого источники
    пришлют вакансии заново, т.к. «уже виденные» забыты);
  - settings.json — выбранный язык в боте;
  - reader.pid, logs/ — runtime-файлы.

НЕ трогает *.session (авторизацию Telegram), иначе придётся логиниться заново.
Чтобы снести и сессии тоже — флаг --sessions (полный сброс).

Запуск:
  python reset.py            # спросит подтверждение
  python reset.py --yes      # без подтверждения
  python reset.py --sessions # вместе с сессиями Telegram

Совет: сначала останови бота/слушатель (иначе файлы могут пересоздаться).
"""

import glob
import os
import shutil
import sys

FILES = ["vacancies.db", "vacancies.db-wal", "vacancies.db-shm",
         "settings.json", "reader.pid"]
GLOBS = ["processed_*.json"]
DIRS = ["logs"]
SESSION_GLOBS = ["*.session", "*.session-journal"]


def _remove_path(path, removed):
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
        removed.append(path + "/")
    elif os.path.exists(path):
        os.remove(path)
        removed.append(path)


def main():
    args = sys.argv[1:]
    yes = "--yes" in args or "-y" in args
    with_sessions = "--sessions" in args

    if not yes:
        what = "БД, дедуп, настройки и логи"
        if with_sessions:
            what += " + сессии Telegram (потребуется повторный вход)"
        ans = input(f"Удалить {what}? [y/N]: ").strip().lower()
        if ans not in ("y", "yes", "да"):
            print("Отменено.")
            return

    removed = []
    for f in FILES:
        _remove_path(f, removed)
    for g in GLOBS:
        for f in glob.glob(g):
            _remove_path(f, removed)
    for d in DIRS:
        _remove_path(d, removed)
    if with_sessions:
        for g in SESSION_GLOBS:
            for f in glob.glob(g):
                _remove_path(f, removed)

    print("Удалено:", ", ".join(removed) if removed else "ничего не найдено")
    print("Готово. Дедуп сброшен — при следующем запуске источников "
          "вакансии будут отправлены заново.")


if __name__ == "__main__":
    main()
