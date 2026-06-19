"""Управляющий Телеграм-бот (мультиязычный: ru / uz / en).

Навигация — reply-клавиатурой (кнопки в нижней панели у поля ввода):
  /start → Главное меню
    ├─ 🛠 Управление ботом → Старт / Стоп / Рестарт / Статус / ⬅️ Назад
    ├─ 📋 Вакансии → источник (Каналы / RemoteOK / WWR / HH) / ⬅️ Назад
    │                  └─ источник → 📋 5 / 10 / 15 → список вакансий / ⬅️ Назад
    ├─ 🌐 Язык
    └─ ❓ Помощь

Запуск: python bot.py (или python main.py). Нужен BOT_TOKEN от @BotFather.
Слушатель каналов (channels.py) авто-стартует — вакансии форвардятся в n8n.
Пагинация показывает вакансии из БД: если n8n вернул готовый текст в ответе
вебхука — дословно, иначе формат собирается из сохранённых полей.
"""

import fcntl
import json
import os
import re
import signal
import subprocess
import sys

from dotenv import load_dotenv
from telethon import Button, TelegramClient, events

import db

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID")) if os.getenv("OWNER_ID") else None

LANG_FILE = "settings.json"
DEFAULT_LANG = "ru"
LOG_DIR = "logs"

# Источники-слушатели, которые бот поднимает/останавливает разом.
# (name, script): PID каждого лежит в <name>.lock (пишет singleton.acquire).
LISTENERS = [
    ("channels", "channels.py"),
    ("weworkremotely", "weworkremotely.py"),
    ("remoteok", "remoteok.py"),
    ("hh", "hh.py"),
]

# Источники: ключ -> (ключ подписи, префикс id в БД)
SOURCES = {
    "channels": ("src_channels", "telegram_"),
    "remoteok": ("src_remoteok", "remoteok_"),
    "wwr": ("src_wwr", "wwr_"),
    "hh": ("src_hh", "hh_"),
}

# Навигационное состояние по пользователю (в памяти): {uid: {"menu":..,"source":..}}
nav = {}

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
        "vac_empty": "📭 Вакансий пока нет.",
        "f_score": "⭐️ Оценка: {score}/100",
        "f_link": "🔗 Ссылка:", "f_channel": "📢 Канал:",
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
        "vac_empty": "📭 Hozircha vakansiya yo'q.",
        "f_score": "⭐️ Baho: {score}/100",
        "f_link": "🔗 Havola:", "f_channel": "📢 Kanal:",
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
        "vac_empty": "📭 No vacancies yet.",
        "f_score": "⭐️ Score: {score}/100",
        "f_link": "🔗 Link:", "f_channel": "📢 Channel:",
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


# --- Reply-клавиатуры ------------------------------------------------------

def kb_main(lang):
    return [
        [Button.text(t(lang, "b_control"), resize=True)],
        [Button.text(t(lang, "b_sources"), resize=True)],
        [Button.text(t(lang, "b_lang"), resize=True), Button.text(t(lang, "b_help"), resize=True)],
    ]


def kb_control(lang):
    return [
        [Button.text(t(lang, "b_start"), resize=True), Button.text(t(lang, "b_stop"), resize=True)],
        [Button.text(t(lang, "b_restart"), resize=True), Button.text(t(lang, "b_status"), resize=True)],
        [Button.text(t(lang, "b_back"), resize=True)],
    ]


def kb_sources(lang):
    return [
        [Button.text(t(lang, "src_channels"), resize=True), Button.text(t(lang, "src_remoteok"), resize=True)],
        [Button.text(t(lang, "src_wwr"), resize=True), Button.text(t(lang, "src_hh"), resize=True)],
        [Button.text(t(lang, "b_back"), resize=True)],
    ]


def kb_pagination(lang):
    return [
        [Button.text("📋 5", resize=True), Button.text("📋 10", resize=True), Button.text("📋 15", resize=True)],
        [Button.text(t(lang, "b_back"), resize=True)],
    ]


def kb_lang():
    return [
        [Button.text("🇷🇺 Русский", resize=True),
         Button.text("🇺🇿 O'zbek", resize=True),
         Button.text("🇬🇧 English", resize=True)],
    ]


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


# --- Управление источниками (channels/weworkremotely/remoteok/hh) ----------

_procs = {}  # name -> Popen текущей сессии бота (для reaping зомби)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _lock_pid(name: str):
    """PID процесса-слушателя из его lock-файла <name>.lock (пишет singleton)."""
    try:
        with open(f"{name}.lock") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def _running(name: str) -> bool:
    pid = _lock_pid(name)
    return bool(pid and _alive(pid))


def running_count() -> int:
    return sum(1 for name, _ in LISTENERS if _running(name))


def start_listeners() -> list:
    """Поднять все источники, которые ещё не работают. Дубли отсекает их lock."""
    os.makedirs(LOG_DIR, exist_ok=True)
    started = []
    for name, script in LISTENERS:
        if _running(name):
            continue
        log = open(os.path.join(LOG_DIR, f"{name}.log"), "a")
        _procs[name] = subprocess.Popen(
            [sys.executable, script],
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        )
        started.append(name)
    return started


def stop_listeners() -> list:
    """Остановить все источники: и детей этой сессии, и осиротевших (по lock-PID)."""
    stopped = []
    for name, _ in LISTENERS:
        was = _running(name) or name in _procs
        p = _procs.pop(name, None)
        if p is not None and p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        pid = _lock_pid(name)
        if pid and _alive(pid):
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except OSError:
                try:
                    os.kill(pid, signal.SIGTERM)
                except OSError:
                    pass
        if was:
            stopped.append(name)
    return stopped


# --- Тексты ----------------------------------------------------------------

def short_status(lang: str) -> str:
    n = running_count()
    total = len(LISTENERS)
    state = t(lang, "st_on") if n else t(lang, "st_off")
    return f"{t(lang, 'st_monitoring')}: {state} ({n}/{total})"


def format_vacancy(lang: str, row) -> str:
    """Богатый формат вакансии для пагинации.

    row = (title, channel, url, score, message, created_at). Если есть готовый
    текст из n8n (message) — отдаём его дословно (как приходит автоматически),
    иначе собираем формат из сохранённых полей.
    """
    title, channel, url, score, message, _created = row
    if message and message.strip():
        return message

    parts = [f"🔥 {title or '—'}"]
    if score is not None:
        parts.append(t(lang, "f_score", score=score))
    if url:
        parts.append(f"{t(lang, 'f_link')}\n{url}")
    if channel:
        parts.append(f"{t(lang, 'f_channel')}\n{channel}")
    return "\n\n".join(parts)


# --- Роутинг ---------------------------------------------------------------

def parse_nav(text: str):
    """(token, arg) для навигации. Эмодзи одинаковы во всех языках."""
    raw = text.strip()
    low = raw.lower()

    if low.startswith(("/start", "/menu")):
        return ("menu", None)
    if low.startswith("/help"):
        return ("help", None)
    if low.startswith("/stop"):
        return ("c_stop", None)
    if low.startswith("/restart"):
        return ("c_restart", None)
    if low.startswith("/status"):
        return ("c_status", None)
    if low.startswith(("/lang", "/language")):
        return ("lang", None)

    # выбор языка
    if "🇷🇺" in raw or "русск" in low:
        return ("setlang", "ru")
    if "🇺🇿" in raw or "o'zbek" in low or "ozbek" in low or "узбек" in low:
        return ("setlang", "uz")
    if "🇬🇧" in raw or "english" in low:
        return ("setlang", "en")

    if "⬅️" in raw or "назад" in low or "orqaga" in low or "back" in low:
        return ("back", None)

    # пагинация: 📋 + число
    if "📋" in raw and any(c.isdigit() for c in raw):
        m = re.search(r"\d+", raw)
        n = int(m.group()) if m else 5
        return ("page", n if n in (5, 10, 15) else 5)

    # источники
    if "📨" in raw or "канал" in low or "kanal" in low or "channel" in low:
        return ("src_channels", None)
    if "remoteok" in low:
        return ("src_remoteok", None)
    if "💼" in raw or "wwr" in low or "weworkremotely" in low:
        return ("src_wwr", None)
    if "🔎" in raw:
        return ("src_hh", None)

    # управление
    if "🔄" in raw or "рестарт" in low or "restart" in low or "qayta" in low:
        return ("c_restart", None)
    if "▶️" in raw or "старт" in low or "boshlash" in low:
        return ("c_start", None)
    if "⏸" in raw or "стоп" in low or "to'xtat" in low:
        return ("c_stop", None)
    if "📊" in raw or "статус" in low or "status" in low or "holat" in low:
        return ("c_status", None)

    # меню
    if "🛠" in raw or "управлен" in low or "boshqar" in low or "control" in low:
        return ("control", None)
    if "🌐" in raw or "язык" in low or "language" in low or low == "til":
        return ("lang", None)
    if "📋" in raw or "ваканс" in low or "vacanc" in low or "vakans" in low:
        return ("sources", None)
    if "❓" in raw or "помощ" in low or "yordam" in low or "help" in low:
        return ("help", None)

    return (None, None)


def _authorized(event) -> bool:
    return OWNER_ID is None or event.sender_id == OWNER_ID


def _state(uid):
    st = nav.setdefault(uid, {"menu": "main", "source": None, "msg": None})
    st.setdefault("msg", None)
    return st


async def _del_user(event):
    try:
        await event.delete()
    except Exception:
        pass


async def _del_msg(chat_id, msg_id):
    if msg_id:
        try:
            await bot.delete_messages(chat_id, msg_id)
        except Exception:
            pass


async def _render(event, st, text, buttons):
    """Показать меню без мусора. Порядок важен: удаляем нажатие, шлём НОВОЕ меню
    (с клавиатурой) и ТОЛЬКО ПОТОМ удаляем прошлое — иначе при удалении сообщения
    с reply-клавиатурой она пропадает и приходится жать /start заново."""
    await _del_user(event)
    prev = st.get("msg")
    m = await event.respond(text, buttons=buttons)
    st["msg"] = m.id
    await _del_msg(event.chat_id, prev)


@bot.on(events.NewMessage(incoming=True))
async def handler(event):
    if not _authorized(event):
        return

    uid = event.sender_id
    st = _state(uid)
    token, arg = parse_nav(event.raw_text or "")

    # Выбор языка обрабатываем ПЕРВЫМ — в т.ч. на онбординге.
    if token == "setlang":
        set_lang(uid, arg)
        st["menu"] = "main"
        await _render(event, st, t(arg, "m_title"), kb_main(arg))
        return

    # Онбординг: пока язык не выбран — показываем выбор языка.
    if not has_lang(uid):
        await _render(event, st, t(DEFAULT_LANG, "choose_lang"), kb_lang())
        return

    lang = get_lang(uid)

    if token is None:
        # неизвестный ввод — просто убираем его, чтобы не мусорил в чате
        try:
            await event.delete()
        except Exception:
            pass
        return

    if token == "menu":
        st["menu"] = "main"
        await _render(event, st, t(lang, "m_title"), kb_main(lang))
    elif token == "control":
        st["menu"] = "control"
        await _render(event, st, t(lang, "b_control"), kb_control(lang))
    elif token == "sources":
        st["menu"] = "sources"
        await _render(event, st, t(lang, "sources_title"), kb_sources(lang))
    elif token == "lang":
        await _render(event, st, t(lang, "choose_lang"), kb_lang())
    elif token == "help":
        await _render(event, st, t(lang, "help"), kb_main(lang))
    elif token == "c_start":
        st["menu"] = "control"
        start_listeners()
        await _render(event, st, short_status(lang), kb_control(lang))
    elif token == "c_stop":
        st["menu"] = "control"
        stop_listeners()
        await _render(event, st, short_status(lang), kb_control(lang))
    elif token == "c_restart":
        st["menu"] = "control"
        stop_listeners()
        start_listeners()
        await _render(event, st, short_status(lang), kb_control(lang))
    elif token == "c_status":
        st["menu"] = "control"
        await _render(event, st, short_status(lang), kb_control(lang))
    elif token in ("src_channels", "src_remoteok", "src_wwr", "src_hh"):
        source = token[4:]
        st["source"] = source
        st["menu"] = "pagination"
        label = t(lang, SOURCES[source][0])
        await _render(event, st, t(lang, "page_title", source=label), kb_pagination(lang))
    elif token == "page":
        source = st.get("source")
        if not source:
            st["menu"] = "sources"
            await _render(event, st, t(lang, "sources_title"), kb_sources(lang))
        else:
            await _del_user(event)
            prev = st.get("msg")
            st["msg"] = None
            rows = db.recent(arg, SOURCES[source][1])
            if not rows:
                m = await event.respond(t(lang, "vac_empty"), buttons=kb_pagination(lang))
                st["msg"] = m.id
            else:
                # Клавиатуру вешаем на ПОСЛЕДНЮЮ вакансию, чтобы reply-кнопки не
                # пропали (сообщения вакансий не удаляем — это контент).
                last = len(rows) - 1
                for i, row in enumerate(rows):
                    await event.respond(
                        format_vacancy(lang, row),
                        buttons=kb_pagination(lang) if i == last else None,
                        link_preview=False,
                        parse_mode=None,  # текст n8n/URL не парсим как markdown
                    )
            await _del_msg(event.chat_id, prev)
    elif token == "back":
        if st.get("menu") == "pagination":
            st["menu"] = "sources"
            await _render(event, st, t(lang, "sources_title"), kb_sources(lang))
        else:
            st["menu"] = "main"
            await _render(event, st, t(lang, "m_title"), kb_main(lang))


_instance_lock = None  # держим открытый файл, чтобы flock не снялся


def _ensure_single_instance():
    """Не дать запустить второй экземпляр бота: иначе два процесса дерутся
    за файл сессии Telethon → 'database is locked'.

    Важно: main.py и bot.py запускают ОДНОГО И ТОГО ЖЕ бота (main.py делает
    `from bot import main`), поэтому они делят этот lock — запускать нужно
    что-то одно.
    """
    global _instance_lock
    # "a+" (не "w") — чтобы при неудачном захвате не затереть PID владельца.
    _instance_lock = open("bot.lock", "a+")
    try:
        fcntl.flock(_instance_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        _instance_lock.seek(0)
        holder = _instance_lock.read().strip() or "?"
        raise SystemExit(
            f"Бот уже запущен — его держит процесс PID {holder} "
            "(это python main.py или python bot.py — это один и тот же бот).\n"
            f"Останови его: kill {holder}\n"
            "или все разом: pkill -f 'main.py'; pkill -f 'bot.py'"
        )
    # Мы владелец — записываем свой PID, чтобы следующий показал, кого убивать.
    _instance_lock.seek(0)
    _instance_lock.truncate()
    _instance_lock.write(str(os.getpid()))
    _instance_lock.flush()


def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN не задан в .env (получи у @BotFather).")
    _ensure_single_instance()
    bot.start(bot_token=BOT_TOKEN)
    print("Control bot started.")
    # Авто-старт всех источников: вакансии форвардятся в n8n без ручного запуска.
    started = start_listeners()
    print("Источники запущены:", ", ".join(started) if started else "(уже работали)")
    bot.run_until_disconnected()


if __name__ == "__main__":
    main()
