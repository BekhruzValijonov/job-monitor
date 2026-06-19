"""Управляющий Телеграм-бот (мультиязычный: ru / uz / en) с вложенным меню.

Навигация (inline-кнопки):
  /start → Главное меню
    ├─ 🛠 Управление ботом → Старт / Стоп / Рестарт / Статус
    ├─ 📋 Вакансии → источник (Каналы / RemoteOK / WWR / HH)
    │                  └─ источник → пагинация 5 / 10 / 15 → список вакансий
    ├─ 🌐 Язык
    └─ ❓ Помощь

Запуск: python bot.py  (или python main.py). Нужен BOT_TOKEN от @BotFather.
Доступ ограничен OWNER_ID (если задан). Чтение Telegram-каналов — channels.py,
его запускает кнопка «Старт» (pid в reader.pid, лог в logs/reader.log).
"""

import json
import os
import signal
import subprocess
import sys

from dotenv import load_dotenv
from telethon import Button, TelegramClient, events
from telethon.errors import MessageNotModifiedError

import db

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID")) if os.getenv("OWNER_ID") else None

PID_FILE = "reader.pid"
LOG_FILE = "logs/reader.log"
LANG_FILE = "settings.json"
DEFAULT_LANG = "ru"
READER_CMD = [sys.executable, "channels.py"]

# Источники вакансий: ключ -> (подпись, префикс id в БД)
SOURCES = {
    "channels": ("src_channels", "telegram_"),
    "remoteok": ("src_remoteok", "remoteok_"),
    "wwr": ("src_wwr", "wwr_"),
    "hh": ("src_hh", "hh_"),
}

bot = TelegramClient("vacancy_bot_session", API_ID, API_HASH)


# --- Локализация -----------------------------------------------------------

TR = {
    "ru": {
        "m_title": "🤖 Главное меню",
        "b_control": "🛠 Управление ботом", "b_sources": "📋 Вакансии",
        "b_lang": "🌐 Язык", "b_help": "❓ Помощь", "b_back": "⬅️ Назад",
        "b_start": "▶️ Старт", "b_stop": "⏸ Стоп",
        "b_restart": "🔄 Рестарт", "b_status": "📊 Статус",
        "src_channels": "📨 Каналы", "src_remoteok": "🌐 RemoteOK",
        "src_wwr": "💼 WWR", "src_hh": "🔎 HH",
        "sources_title": "📋 Выберите источник:",
        "page_title": "📋 {source}: сколько вакансий показать?",
        "vac_header": "📋 Последние вакансии — {source}:",
        "vac_empty": "📭 Вакансий пока нет.",
        "already_running": "✅ Мониторинг уже запущен.",
        "started": "▶️ Мониторинг запущен (pid {pid}).",
        "stopped": "⏸ Мониторинг остановлен.",
        "not_running": "⏸ Мониторинг не запущен.",
        "choose_lang": "🌐 Выберите язык:",
        "st_monitoring": "Мониторинг", "st_on": "▶️ запущен", "st_off": "⏸ остановлен",
        "st_total": "Вакансий в БД", "st_last": "Последняя", "st_by_channel": "По каналам",
        "help": (
            "🤖 *Меню бота*\n\n"
            "🛠 Управление ботом — запуск/стоп/рестарт/статус мониторинга\n"
            "📋 Вакансии — выбрать источник и посмотреть последние вакансии\n"
            "🌐 Язык — сменить язык\n\n"
            "Команды: /start — меню, /stop — стоп, /status — статус, "
            "/restart — рестарт, /help — справка, /lang — язык"
        ),
    },
    "uz": {
        "m_title": "🤖 Asosiy menyu",
        "b_control": "🛠 Botni boshqarish", "b_sources": "📋 Vakansiyalar",
        "b_lang": "🌐 Til", "b_help": "❓ Yordam", "b_back": "⬅️ Orqaga",
        "b_start": "▶️ Boshlash", "b_stop": "⏸ To'xtatish",
        "b_restart": "🔄 Qayta yuklash", "b_status": "📊 Holat",
        "src_channels": "📨 Kanallar", "src_remoteok": "🌐 RemoteOK",
        "src_wwr": "💼 WWR", "src_hh": "🔎 HH",
        "sources_title": "📋 Manbani tanlang:",
        "page_title": "📋 {source}: nechta vakansiya ko'rsatilsin?",
        "vac_header": "📋 Oxirgi vakansiyalar — {source}:",
        "vac_empty": "📭 Hozircha vakansiya yo'q.",
        "already_running": "✅ Monitoring allaqachon ishlamoqda.",
        "started": "▶️ Monitoring ishga tushdi (pid {pid}).",
        "stopped": "⏸ Monitoring to'xtatildi.",
        "not_running": "⏸ Monitoring ishlamayapti.",
        "choose_lang": "🌐 Tilni tanlang:",
        "st_monitoring": "Monitoring", "st_on": "▶️ ishlamoqda", "st_off": "⏸ to'xtagan",
        "st_total": "Bazadagi vakansiyalar", "st_last": "Oxirgi", "st_by_channel": "Kanallar bo'yicha",
        "help": (
            "🤖 *Bot menyusi*\n\n"
            "🛠 Botni boshqarish — monitoringni ishga tushirish/to'xtatish/holat\n"
            "📋 Vakansiyalar — manbani tanlab oxirgi vakansiyalarni ko'rish\n"
            "🌐 Til — tilni o'zgartirish\n\n"
            "Buyruqlar: /start — menyu, /stop — to'xtatish, /status — holat, "
            "/restart — qayta yuklash, /help — yordam, /lang — til"
        ),
    },
    "en": {
        "m_title": "🤖 Main menu",
        "b_control": "🛠 Bot control", "b_sources": "📋 Vacancies",
        "b_lang": "🌐 Language", "b_help": "❓ Help", "b_back": "⬅️ Back",
        "b_start": "▶️ Start", "b_stop": "⏸ Stop",
        "b_restart": "🔄 Restart", "b_status": "📊 Status",
        "src_channels": "📨 Channels", "src_remoteok": "🌐 RemoteOK",
        "src_wwr": "💼 WWR", "src_hh": "🔎 HH",
        "sources_title": "📋 Choose a source:",
        "page_title": "📋 {source}: how many vacancies to show?",
        "vac_header": "📋 Latest vacancies — {source}:",
        "vac_empty": "📭 No vacancies yet.",
        "already_running": "✅ Monitoring is already running.",
        "started": "▶️ Monitoring started (pid {pid}).",
        "stopped": "⏸ Monitoring stopped.",
        "not_running": "⏸ Monitoring is not running.",
        "choose_lang": "🌐 Choose language:",
        "st_monitoring": "Monitoring", "st_on": "▶️ running", "st_off": "⏸ stopped",
        "st_total": "Vacancies in DB", "st_last": "Last", "st_by_channel": "By channel",
        "help": (
            "🤖 *Bot menu*\n\n"
            "🛠 Bot control — start/stop/restart/status of monitoring\n"
            "📋 Vacancies — pick a source and view the latest vacancies\n"
            "🌐 Language — change language\n\n"
            "Commands: /start — menu, /stop — stop, /status — status, "
            "/restart — restart, /help — help, /lang — language"
        ),
    },
}


def t(lang: str, key: str, **kwargs) -> str:
    strings = TR.get(lang, TR[DEFAULT_LANG])
    text = strings.get(key, TR[DEFAULT_LANG][key])
    return text.format(**kwargs) if kwargs else text


LANG_BUTTONS = [
    [
        Button.inline("🇷🇺 Русский", b"lang_ru"),
        Button.inline("🇺🇿 O'zbek", b"lang_uz"),
        Button.inline("🇬🇧 English", b"lang_en"),
    ]
]


# --- Меню (inline) ---------------------------------------------------------

def menu_main(lang):
    buttons = [
        [Button.inline(t(lang, "b_control"), b"m_control")],
        [Button.inline(t(lang, "b_sources"), b"m_sources")],
        [Button.inline(t(lang, "b_lang"), b"m_lang"),
         Button.inline(t(lang, "b_help"), b"m_help")],
    ]
    return t(lang, "m_title"), buttons


def menu_control(lang):
    buttons = [
        [Button.inline(t(lang, "b_start"), b"c_start"),
         Button.inline(t(lang, "b_stop"), b"c_stop")],
        [Button.inline(t(lang, "b_restart"), b"c_restart"),
         Button.inline(t(lang, "b_status"), b"c_status")],
        [Button.inline(t(lang, "b_back"), b"m_main")],
    ]
    return f"{t(lang, 'b_control')}\n\n{status_text(lang)}", buttons


def menu_sources(lang):
    buttons = [
        [Button.inline(t(lang, "src_channels"), b"s_channels"),
         Button.inline(t(lang, "src_remoteok"), b"s_remoteok")],
        [Button.inline(t(lang, "src_wwr"), b"s_wwr"),
         Button.inline(t(lang, "src_hh"), b"s_hh")],
        [Button.inline(t(lang, "b_back"), b"m_main")],
    ]
    return t(lang, "sources_title"), buttons


def _pagination_rows(source):
    return [
        Button.inline("📋 5", f"p_{source}_5".encode()),
        Button.inline("📋 10", f"p_{source}_10".encode()),
        Button.inline("📋 15", f"p_{source}_15".encode()),
    ]


def menu_pagination(lang, source):
    label = t(lang, SOURCES[source][0])
    buttons = [
        _pagination_rows(source),
        [Button.inline(t(lang, "b_back"), b"m_sources")],
    ]
    return t(lang, "page_title", source=label), buttons


def view_vacancies(lang, source, count):
    label = t(lang, SOURCES[source][0])
    text = vacancies_text(lang, count, label, SOURCES[source][1])
    buttons = [
        _pagination_rows(source),
        [Button.inline(t(lang, "b_back"), b"m_sources")],
    ]
    return text, buttons


def menu_help(lang):
    return t(lang, "help"), [[Button.inline(t(lang, "b_back"), b"m_main")]]


# --- Выбор языка (персистентно, по пользователю) ---------------------------

def _load_langs() -> dict:
    try:
        with open(LANG_FILE) as f:
            data = json.load(f)
            return data.get("lang", {}) if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def get_lang(user_id) -> str:
    return _load_langs().get(str(user_id), DEFAULT_LANG)


def has_lang(user_id) -> bool:
    return str(user_id) in _load_langs()


def set_lang(user_id, lang: str) -> None:
    langs = _load_langs()
    langs[str(user_id)] = lang
    tmp = LANG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"lang": langs}, f, ensure_ascii=False)
    os.replace(tmp, LANG_FILE)


# --- Управление процессом ридера (channels.py) -----------------------------

_reader_proc = None  # Popen текущей сессии бота (для корректной reaping зомби)


def _read_pid():
    try:
        with open(PID_FILE) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def reader_running() -> bool:
    global _reader_proc
    if _reader_proc is not None:
        if _reader_proc.poll() is None:
            return True
        _reader_proc = None
    pid = _read_pid()
    return bool(pid and _alive(pid))


def start_reader(lang: str) -> str:
    global _reader_proc
    if reader_running():
        return t(lang, "already_running")

    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    log = open(LOG_FILE, "a")
    _reader_proc = subprocess.Popen(
        READER_CMD, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
    )
    with open(PID_FILE, "w") as f:
        f.write(str(_reader_proc.pid))
    return t(lang, "started", pid=_reader_proc.pid)


def stop_reader(lang: str) -> str:
    global _reader_proc

    if _reader_proc is not None and _reader_proc.poll() is None:
        _reader_proc.terminate()
        try:
            _reader_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _reader_proc.kill()
        _reader_proc = None
        _cleanup_pid()
        return t(lang, "stopped")

    pid = _read_pid()
    if pid and _alive(pid):
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except OSError:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        _cleanup_pid()
        _reader_proc = None
        return t(lang, "stopped")

    _cleanup_pid()
    _reader_proc = None
    return t(lang, "not_running")


def _cleanup_pid():
    try:
        os.remove(PID_FILE)
    except OSError:
        pass


# --- Тексты ----------------------------------------------------------------

def vacancies_text(lang: str, count: int, source_label: str, prefix: str) -> str:
    rows = db.recent(count, prefix)
    if not rows:
        return t(lang, "vac_empty")
    lines = [t(lang, "vac_header", source=source_label)]
    for i, (title, channel, url, score, _created) in enumerate(rows, 1):
        star = f" ⭐ {score}" if score is not None else ""
        lines.append(f"{i}. {title or '—'} — {channel or '—'}{star}\n{url or ''}")
    return "\n\n".join(lines)


def status_text(lang: str) -> str:
    running = t(lang, "st_on") if reader_running() else t(lang, "st_off")
    s = db.stats()
    lines = [f"*{t(lang, 'st_monitoring')}:* {running}", f"*{t(lang, 'st_total')}:* {s['total']}"]
    if s["last"]:
        lines.append(f"*{t(lang, 'st_last')}:* {s['last']}")
    if s["by_channel"]:
        lines.append(f"\n*{t(lang, 'st_by_channel')}:*")
        lines += [f"  {ch or '—'}: {cnt}" for ch, cnt in s["by_channel"]]
    return "\n".join(lines)


# --- Хендлеры --------------------------------------------------------------

def _authorized(event) -> bool:
    return OWNER_ID is None or event.sender_id == OWNER_ID


async def _edit(event, text, buttons):
    try:
        await event.edit(text, buttons=buttons, link_preview=False)
    except MessageNotModifiedError:
        pass


@bot.on(events.CallbackQuery)
async def on_callback(event):
    if not _authorized(event):
        return

    data = event.data.decode()

    # Выбор языка
    if data.startswith("lang_"):
        lang = data.split("_", 1)[1]
        if lang not in TR:
            lang = DEFAULT_LANG
        set_lang(event.sender_id, lang)
        await event.answer()
        await _edit(event, *menu_main(lang))
        return

    lang = get_lang(event.sender_id)

    if data == "m_main":
        await _edit(event, *menu_main(lang))
    elif data == "m_control":
        await _edit(event, *menu_control(lang))
    elif data == "m_sources":
        await _edit(event, *menu_sources(lang))
    elif data == "m_lang":
        await _edit(event, t(lang, "choose_lang"), LANG_BUTTONS)
    elif data == "m_help":
        await _edit(event, *menu_help(lang))
    elif data == "c_start":
        await event.answer(start_reader(lang))
        await _edit(event, *menu_control(lang))
    elif data == "c_stop":
        await event.answer(stop_reader(lang))
        await _edit(event, *menu_control(lang))
    elif data == "c_restart":
        stop_reader(lang)
        await event.answer(start_reader(lang))
        await _edit(event, *menu_control(lang))
    elif data == "c_status":
        await event.answer()
        await _edit(event, *menu_control(lang))
    elif data.startswith("s_"):
        source = data[2:]
        if source in SOURCES:
            await event.answer()
            await _edit(event, *menu_pagination(lang, source))
    elif data.startswith("p_"):
        _, source, count = data.split("_", 2)
        if source in SOURCES:
            await event.answer()
            await _edit(event, *view_vacancies(lang, source, int(count)))


@bot.on(events.NewMessage(incoming=True))
async def handler(event):
    if not _authorized(event):
        return

    # Онбординг: пока язык не выбран — сначала выбор языка.
    if not has_lang(event.sender_id):
        await event.respond(t(DEFAULT_LANG, "choose_lang"), buttons=LANG_BUTTONS)
        return

    lang = get_lang(event.sender_id)
    text = (event.raw_text or "").strip().lower()

    if text.startswith(("/start", "/menu")):
        m_text, m_buttons = menu_main(lang)
        await event.respond(m_text, buttons=m_buttons)
    elif text.startswith("/help"):
        m_text, m_buttons = menu_help(lang)
        await event.respond(m_text, buttons=m_buttons)
    elif text.startswith("/stop"):
        msg = stop_reader(lang)
        m_text, m_buttons = menu_control(lang)
        await event.respond(f"{msg}\n\n{m_text}", buttons=m_buttons)
    elif text.startswith("/restart"):
        stop_reader(lang)
        msg = start_reader(lang)
        m_text, m_buttons = menu_control(lang)
        await event.respond(f"{msg}\n\n{m_text}", buttons=m_buttons)
    elif text.startswith("/status"):
        m_text, m_buttons = menu_control(lang)
        await event.respond(m_text, buttons=m_buttons)
    elif text.startswith(("/lang", "/language")):
        await event.respond(t(lang, "choose_lang"), buttons=LANG_BUTTONS)
    # остальное игнорируем (без спама справкой)


def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN не задан в .env (получи у @BotFather).")
    bot.start(bot_token=BOT_TOKEN)
    print("Control bot started.")
    # Авто-старт слушателя каналов: новые вакансии форвардятся в n8n как раньше,
    # не дожидаясь нажатия «Старт». Если уже запущен — ничего не делает.
    print(start_reader(DEFAULT_LANG))
    bot.run_until_disconnected()


if __name__ == "__main__":
    main()
