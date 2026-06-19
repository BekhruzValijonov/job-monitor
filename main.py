"""Точка входа проекта: запускает управляющий Телеграм-бот.

Чтение Telegram-каналов вынесено в channels.py — его запускает сам бот
по кнопке «Старт». Источники вакансий: channels.py (Telegram), remoteok.py,
weworkremotely.py, hh.py.
"""

from bot import main

if __name__ == "__main__":
    main()
