# vacancy-bot

Читает сообщения из заданных Telegram-каналов через [Telethon](https://docs.telethon.dev/)
и отправляет их вебхуком в [n8n](https://n8n.io/) для дальнейшей обработки.

## Установка

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Настройка

1. Получи `API_ID` и `API_HASH` на https://my.telegram.org → *API development tools*.
2. Скопируй `.env.example` в `.env` и заполни значения:

   ```bash
   cp .env.example .env
   ```

3. Добавь нужные каналы в список `CHANNELS` в `main.py` (можно указывать
   username канала, например `"frontend_jobs"`).

## Запуск

```bash
python main.py
```

При первом запуске Telethon попросит ввести номер телефона и код
подтверждения — после этого авторизация сохранится в файле
`vacancy_session.session` (он в `.gitignore`, коммитить его нельзя).
