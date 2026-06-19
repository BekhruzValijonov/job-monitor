"""Управляющий Телеграм-бот (мультиязычный: ru / uz / en).

Кнопки и команды для управления пайплайном вакансий:
  /start    — запустить мониторинг каналов (main.py)
  /stop     — остановить мониторинг
  /restart  — перезапустить мониторинг
  /status   — статус + статистика из БД
  /hh       — разовый прогон hh.py
  /remoteok — разовый прогон remoteok.py
  /help     — справка
  /cancel   — убрать клавиатуру
  /lang     — выбрать язык

Запуск: python bot.py  (нужен BOT_TOKEN от @BotFather в .env)
Доступ ограничен OWNER_ID (если задан). Язык выбирается кнопкой 🌐 и
хранится по пользователю в settings.json.
"""

import asyncio
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

PID_FILE = "reader.pid"
LOG_FILE = "logs/reader.log"
LANG_FILE = "settings.json"
DEFAULT_LANG = "ru"

bot = TelegramClient("vacancy_bot_session", API_ID, API_HASH)


# --- Локализация -----------------------------------------------------------

TR = {
    "ru": {
        "b_start": "▶️ Старт", "b_stop": "⏸ Стоп", "b_restart": "🔄 Рестарт",
        "b_status": "📊 Статус", "b_hh": "🔎 HH", "b_remoteok": "🔎 RemoteOK",
        "b_wwr": "🔎 WWR",
        "b_vac5": "📋 5", "b_vac10": "📋 10", "b_vac15": "📋 15",
        "b_help": "❓ Помощь", "b_cancel": "✖️ Отмена", "b_lang": "🌐 Язык",
        "vac_header": "📋 Последние вакансии:",
        "vac_empty": "📭 Вакансий пока нет.",
        "already_running": "✅ Мониторинг уже запущен.",
        "started": "▶️ Мониторинг запущен (pid {pid}).",
        "stopped": "⏸ Мониторинг остановлен.",
        "not_running": "⏸ Мониторинг не запущен.",
        "cancelled": "✖️ Отменено.",
        "running": "⏳ Запускаю {name}…",
        "done": "🔎 `{name}` завершён (код {code}):",
        "timeout": "⏱ {name}: превышено время ожидания.",
        "choose_lang": "🌐 Выберите язык:",
        "lang_set": "🌐 Язык: Русский",
        "st_monitoring": "Мониторинг", "st_on": "▶️ запущен", "st_off": "⏸ остановлен",
        "st_total": "Вакансий в БД", "st_last": "Последняя", "st_by_channel": "По каналам",
        "help": (
            "🤖 *Управление вакансий-ботом*\n\n"
            "▶️ Старт / /start — запустить мониторинг каналов\n"
            "⏸ Стоп / /stop — остановить мониторинг\n"
            "🔄 Рестарт / /restart — перезапустить мониторинг\n"
            "📊 Статус / /status — состояние и статистика\n"
            "🔎 HH / /hh — разовый поиск на HH\n"
            "🔎 RemoteOK / /remoteok — разовый поиск на RemoteOK\n"
            "🔎 WWR / /wwr — разовый поиск на WeWorkRemotely\n"
            "📋 5 / 10 / 15 — показать последние N вакансий\n"
            "❓ Помощь / /help — эта справка\n"
            "✖️ Отмена / /cancel — убрать клавиатуру\n"
            "🌐 Язык / /lang — сменить язык"
        ),
    },
    "uz": {
        "b_start": "▶️ Boshlash", "b_stop": "⏸ To'xtatish", "b_restart": "🔄 Qayta yuklash",
        "b_status": "📊 Holat", "b_hh": "🔎 HH", "b_remoteok": "🔎 RemoteOK",
        "b_wwr": "🔎 WWR",
        "b_vac5": "📋 5", "b_vac10": "📋 10", "b_vac15": "📋 15",
        "b_help": "❓ Yordam", "b_cancel": "✖️ Bekor qilish", "b_lang": "🌐 Til",
        "vac_header": "📋 Oxirgi vakansiyalar:",
        "vac_empty": "📭 Hozircha vakansiya yo'q.",
        "already_running": "✅ Monitoring allaqachon ishlamoqda.",
        "started": "▶️ Monitoring ishga tushdi (pid {pid}).",
        "stopped": "⏸ Monitoring to'xtatildi.",
        "not_running": "⏸ Monitoring ishlamayapti.",
        "cancelled": "✖️ Bekor qilindi.",
        "running": "⏳ {name} ishga tushyapti…",
        "done": "🔎 `{name}` tugadi (kod {code}):",
        "timeout": "⏱ {name}: kutish vaqti tugadi.",
        "choose_lang": "🌐 Tilni tanlang:",
        "lang_set": "🌐 Til: O'zbekcha",
        "st_monitoring": "Monitoring", "st_on": "▶️ ishlamoqda", "st_off": "⏸ to'xtagan",
        "st_total": "Bazadagi vakansiyalar", "st_last": "Oxirgi", "st_by_channel": "Kanallar bo'yicha",
        "help": (
            "🤖 *Vakansiya-botni boshqarish*\n\n"
            "▶️ Boshlash / /start — kanallar monitoringini ishga tushirish\n"
            "⏸ To'xtatish / /stop — monitoringni to'xtatish\n"
            "🔄 Qayta yuklash / /restart — monitoringni qayta ishga tushirish\n"
            "📊 Holat / /status — holat va statistika\n"
            "🔎 HH / /hh — HH bo'yicha bir martalik qidiruv\n"
            "🔎 RemoteOK / /remoteok — RemoteOK bo'yicha bir martalik qidiruv\n"
            "🔎 WWR / /wwr — WeWorkRemotely bo'yicha bir martalik qidiruv\n"
            "📋 5 / 10 / 15 — oxirgi N ta vakansiyani ko'rsatish\n"
            "❓ Yordam / /help — ushbu yordam\n"
            "✖️ Bekor qilish / /cancel — klaviaturani yashirish\n"
            "🌐 Til / /lang — tilni o'zgartirish"
        ),
    },
    "en": {
        "b_start": "▶️ Start", "b_stop": "⏸ Stop", "b_restart": "🔄 Restart",
        "b_status": "📊 Status", "b_hh": "🔎 HH", "b_remoteok": "🔎 RemoteOK",
        "b_wwr": "🔎 WWR",
        "b_vac5": "📋 5", "b_vac10": "📋 10", "b_vac15": "📋 15",
        "b_help": "❓ Help", "b_cancel": "✖️ Cancel", "b_lang": "🌐 Language",
        "vac_header": "📋 Latest vacancies:",
        "vac_empty": "📭 No vacancies yet.",
        "already_running": "✅ Monitoring is already running.",
        "started": "▶️ Monitoring started (pid {pid}).",
        "stopped": "⏸ Monitoring stopped.",
        "not_running": "⏸ Monitoring is not running.",
        "cancelled": "✖️ Cancelled.",
        "running": "⏳ Running {name}…",
        "done": "🔎 `{name}` finished (code {code}):",
        "timeout": "⏱ {name}: timed out.",
        "choose_lang": "🌐 Choose language:",
        "lang_set": "🌐 Language: English",
        "st_monitoring": "Monitoring", "st_on": "▶️ running", "st_off": "⏸ stopped",
        "st_total": "Vacancies in DB", "st_last": "Last", "st_by_channel": "By channel",
        "help": (
            "🤖 *Vacancy bot control*\n\n"
            "▶️ Start / /start — start channel monitoring\n"
            "⏸ Stop / /stop — stop monitoring\n"
            "🔄 Restart / /restart — restart monitoring\n"
            "📊 Status / /status — state and statistics\n"
            "🔎 HH / /hh — one-off HH search\n"
            "🔎 RemoteOK / /remoteok — one-off RemoteOK search\n"
            "🔎 WWR / /wwr — one-off WeWorkRemotely search\n"
            "📋 5 / 10 / 15 — show latest N vacancies\n"
            "❓ Help / /help — this help\n"
            "✖️ Cancel / /cancel — hide the keyboard\n"
            "🌐 Language / /lang — change language"
        ),
    },
}


def t(lang: str, key: str, **kwargs) -> str:
    strings = TR.get(lang, TR[DEFAULT_LANG])
    text = strings.get(key, TR[DEFAULT_LANG][key])
    return text.format(**kwargs) if kwargs else text


def keyboard(lang: str):
    b = lambda key: Button.text(t(lang, key), resize=True)
    return [
        # Управление мониторингом
        [b("b_start"), b("b_stop"), b("b_restart")],
        # Информация
        [b("b_status"), b("b_help")],
        # Вакансии (пагинация)
        [b("b_vac5"), b("b_vac10"), b("b_vac15")],
        # Источники
        [b("b_hh"), b("b_remoteok"), b("b_wwr")],
        # Прочее
        [b("b_lang"), b("b_cancel")],
    ]


LANG_BUTTONS = [
    [
        Button.inline("🇷🇺 Русский", b"lang_ru"),
        Button.inline("🇺🇿 O'zbek", b"lang_uz"),
        Button.inline("🇬🇧 English", b"lang_en"),
    ]
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


# --- Управление процессом ридера (main.py) ---------------------------------

READER_CMD = [sys.executable, "main.py"]
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


# --- Разовые фетчеры (hh.py / remoteok.py) ---------------------------------

async def run_script(name: str, lang: str) -> str:
    try:
        proc = await asyncio.to_thread(
            subprocess.run, [sys.executable, name, "--once"],
            capture_output=True, text=True, timeout=300,
        )
    except subprocess.TimeoutExpired:
        return t(lang, "timeout", name=name)

    out = (proc.stdout or "") + (proc.stderr or "")
    tail = out.strip().splitlines()[-15:]
    return t(lang, "done", name=name, code=proc.returncode) + "\n" + "\n".join(tail)


def vacancies_text(lang: str, count: int) -> str:
    rows = db.recent(count)
    if not rows:
        return t(lang, "vac_empty")
    lines = [t(lang, "vac_header")]
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


# --- Роутинг ---------------------------------------------------------------

def parse_action(text: str):
    """Определить действие. Эмодзи одинаковы во всех языках, поэтому роутинг
    не зависит от выбранного языка; источники различаем по токенам hh/remoteok."""
    raw = text.strip()
    low = raw.lower()

    if "🌐" in raw or low.startswith(("/lang", "/language")):
        return "lang"
    if "📋" in raw or low.startswith(("/vac", "/vacancies")):
        return "vac"
    if "remoteok" in low:
        return "remoteok"
    if "wwr" in low or "weworkremotely" in low:
        return "wwr"
    if "🔎" in raw and "hh" in low or low.startswith("/hh"):
        return "hh"
    for emoji, action in (
        ("🔄", "restart"), ("▶️", "start"), ("⏸", "stop"),
        ("📊", "status"), ("❓", "help"), ("✖️", "cancel"),
    ):
        if emoji in raw:
            return action
    if low.startswith("/restart"):
        return "restart"
    if low.startswith("/start"):
        return "start"
    if low.startswith("/stop"):
        return "stop"
    if low.startswith("/status"):
        return "status"
    if low.startswith("/help"):
        return "help"
    if low.startswith("/cancel"):
        return "cancel"
    return None


def parse_count(text: str) -> int:
    """Сколько вакансий показать: 5/10/15 из текста кнопки, по умолчанию 5."""
    m = re.search(r"\d+", text)
    n = int(m.group()) if m else 5
    return n if n in (5, 10, 15) else 5


def _authorized(event) -> bool:
    return OWNER_ID is None or event.sender_id == OWNER_ID


@bot.on(events.CallbackQuery(pattern=b"lang_"))
async def on_lang(event):
    if not _authorized(event):
        return
    lang = event.data.decode().split("_", 1)[1]
    if lang not in TR:
        lang = DEFAULT_LANG
    set_lang(event.sender_id, lang)
    await event.answer()
    await event.respond(t(lang, "lang_set"), buttons=keyboard(lang))


@bot.on(events.NewMessage(incoming=True))
async def handler(event):
    if not _authorized(event):
        return

    # Онбординг: пока язык не выбран — сначала показываем выбор языка.
    if not has_lang(event.sender_id):
        await event.respond(t(DEFAULT_LANG, "choose_lang"), buttons=LANG_BUTTONS)
        return

    lang = get_lang(event.sender_id)
    action = parse_action(event.raw_text or "")

    if action is None:
        return  # нераспознанные сообщения игнорируем (не спамим справкой)

    if action == "start":
        await event.respond(start_reader(lang), buttons=keyboard(lang))
    elif action == "stop":
        await event.respond(stop_reader(lang), buttons=keyboard(lang))
    elif action == "restart":
        stop_reader(lang)
        await event.respond(start_reader(lang), buttons=keyboard(lang))
    elif action == "status":
        await event.respond(status_text(lang), buttons=keyboard(lang))
    elif action == "hh":
        await event.respond(t(lang, "running", name="hh.py"))
        await event.respond(await run_script("hh.py", lang), buttons=keyboard(lang))
    elif action == "remoteok":
        await event.respond(t(lang, "running", name="remoteok.py"))
        await event.respond(await run_script("remoteok.py", lang), buttons=keyboard(lang))
    elif action == "wwr":
        await event.respond(t(lang, "running", name="weworkremotely.py"))
        await event.respond(await run_script("weworkremotely.py", lang), buttons=keyboard(lang))
    elif action == "vac":
        await event.respond(
            vacancies_text(lang, parse_count(event.raw_text or "")),
            buttons=keyboard(lang),
            link_preview=False,
        )
    elif action == "help":
        await event.respond(t(lang, "help"), buttons=keyboard(lang))
    elif action == "cancel":
        await event.respond(t(lang, "cancelled"), buttons=Button.clear())
    elif action == "lang":
        await event.respond(t(lang, "choose_lang"), buttons=LANG_BUTTONS)


def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN не задан в .env (получи у @BotFather).")
    bot.start(bot_token=BOT_TOKEN)
    print("Control bot started.")
    bot.run_until_disconnected()


if __name__ == "__main__":
    main()
