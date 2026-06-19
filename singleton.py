"""Single-instance lock через flock + запись PID в lock-файл.

Используется источниками (channels/weworkremotely/remoteok/hh), чтобы:
  - не запускалось два экземпляра одного слушателя (дубли в n8n, гонки за БД);
  - бот мог прочитать PID из lock-файла и остановить процесс.
"""

import fcntl
import os

_held = []  # держим открытые хэндлы, чтобы flock не снялся до конца процесса


def acquire(lockfile: str, label: str = None):
    """Захватить lock. Если занят другим процессом — выйти с понятным текстом."""
    fh = open(lockfile, "a+")  # не "w" — чтобы не затереть PID владельца при неудаче
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.seek(0)
        holder = fh.read().strip() or "?"
        name = label or lockfile
        raise SystemExit(f"{name} уже запущен (PID {holder}). Останови: kill {holder}")
    fh.seek(0)
    fh.truncate()
    fh.write(str(os.getpid()))
    fh.flush()
    _held.append(fh)
    return fh
