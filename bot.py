import os
import logging
import random
import json

from datetime import datetime
from functools import wraps
from pathlib import Path
from zoneinfo import ZoneInfo  # Python 3.9+
from io import BytesIO
from collections import Counter
from PIL import Image, ImageDraw, ImageFont

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    BotCommand,
    BotCommandScopeChat,
    InputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
)

from dotenv import load_dotenv

# Загрузка .env
load_dotenv()

# Логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Файл для активности пользователей
USER_FILE = Path("user_activity.json")
# файл для предложений пользователей
SUGGESTIONS_FILE = Path("suggestions.json")
# админ айди
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

async def set_commands(app):
    
    await app.bot.set_my_commands(
        [
            BotCommand("start",         "Показать приветствие"),
            BotCommand("play",          "Начать новую игру"),
            BotCommand("hint",    "Подсказка"),
            BotCommand("reset",         "Сбросить игру"),
            BotCommand("notification",         "Включить/Отключить уведомления"),
            BotCommand("my_stats",      "Ваша статистика"),
            BotCommand("global_stats",  "Глобальная статистика"),
            BotCommand("feedback", "Жалоба на слово"),
            BotCommand("dict_file",  "Посмотреть словарь"),
            BotCommand("dump_activity", "Скачать user_activity.json"),
            BotCommand("suggestions_view", "Посмотреть фидбек юзеров"),
            BotCommand("suggestions_move", "Переместить слово из белого списка в add список"),
            BotCommand("suggestions_remove", "Удалить что-то из фидбека"),
            BotCommand("suggestions_approve", "Внести изменения в словарь"),
            BotCommand("broadcast", "Отправить сообщение всем юзерам"),
            BotCommand("broadcast_cancel", "Отменить отправку"),
            BotCommand("ban", "Заблокировать пользователя"),
            BotCommand("unban", "Разблокировать пользователя"),
        ],
        scope=BotCommandScopeChat(chat_id=ADMIN_ID)
    )


def load_suggestions() -> dict[str, set[str]]:
    """Возвращает {'black': set(...), 'white': set(...), 'add': set(...)} без дубликатов."""
    if not SUGGESTIONS_FILE.exists():
        return {"black": set(), "white": set(), "add": set()}
    raw = SUGGESTIONS_FILE.read_text("utf-8").strip()
    if not raw:
        return {"black": set(), "white": set(), "add": set()}
    try:
        data = json.loads(raw)
        return {
            "black": set(data.get("black", [])),
            "white": set(data.get("white", [])),
            "add": set(data.get("add", [])),
        }
    except json.JSONDecodeError:
        return {"black": set(), "white": set(), "add": set()}



def save_suggestions(sugg: dict[str, set[str]]):
    """
    Сохраняет suggestions, конвертируя множества в отсортированные списки.
    """
    out = {
        "black": sorted(sugg["black"]),
        "white": sorted(sugg["white"]),
        "add": sorted(sugg["add"]),
    }
    with SUGGESTIONS_FILE.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


# загружаем один раз при старте
suggestions = load_suggestions()

def load_store() -> dict:
    """
    Загружает user_activity.json.
    Если файла нет или он пуст/битый — возвращает чистый шаблон:
    {
      "users": {},
      "global": { "total_games":0, "total_wins":0, "total_losses":0, "win_rate":0.0 }
    }
    """
    template = {
        "users": {},
        "global": {
            "total_games": 0,
            "total_wins": 0,
            "total_losses": 0,
            "win_rate": 0.0
        }
    }
    if not USER_FILE.exists():
        return template

    raw = USER_FILE.read_text("utf-8").strip()
    if not raw:
        return template

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return template

    # Убедимся, что структура корректна
    if not isinstance(data, dict):
        return template

    # Проверим разделы
    if not isinstance(data.get("users"), dict):
        data["users"] = {}
    if not isinstance(data.get("global"), dict):
        data["global"] = template["global"].copy()

    # Подставим недостающие ключи в global
    for key, val in template["global"].items():
        data["global"].setdefault(key, val)

    return data

def save_store(store: dict) -> None:
    """
    Сохраняет переданный store в USER_FILE в JSON-формате с отступами.
    Ожидаем, что store имеет формат:
    {
      "users": { ... },
      "global": { ... }
    }
    """
    USER_FILE.write_text(
        json.dumps(store, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

def update_user_activity(user) -> None:
    """
    Создает или обновляет запись user в store['users'], добавляя:
    - first_name, last_name, username
    - is_bot, is_premium, language_code
    - last_seen_msk (по московскому времени)
    - stats (если еще нет): games_played, wins, losses, win rate
    - banned: флаг бана пользователя (если не установлен, то False)
    """
    store = load_store()
    uid = str(user.id)
    users = store["users"]

    # Если пользователь впервые — создаем базовую запись
    if uid not in users:
        users[uid] = {
            "first_name": user.first_name,
            "suggested_words": [],  # Список слов, предложенных пользователем
            "stats": {
                "games_played": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0
            },
            "banned": False  # По умолчанию пользователь не забанен
        }

    u = users[uid]
    # Обновляем поля профиля
    u["first_name"]    = user.first_name
    u["last_name"]     = user.last_name
    u["username"]      = user.username
    u["is_bot"]        = user.is_bot
    u["is_premium"]    = getattr(user, "is_premium", False)
    u["language_code"] = user.language_code
    u["last_seen_msk"] = datetime.now(ZoneInfo("Europe/Moscow")).isoformat()

    save_store(store)


def clear_notification_flag(user_id: str):
    store = load_store()
    u = store["users"].get(user_id)
    if u and u.get("notified"):
        u["notified"] = False
        save_store(store)


def normalize(text: str) -> str:
    # переводим все в нижний регистр и убираем «е»
    return text.strip().lower().replace("ё", "е")


def compute_letter_status(secret: str, guesses: list[str]) -> dict[str, str]:
    """
    Для каждой буквы возвращает:
      - "green"  если была 🟩
      - "yellow" если была 🟨 (и не была 🟩)
      - "red"    если была ⬜ (и не была ни 🟩, ни 🟨)
    """
    status: dict[str,str] = {}
    for guess in guesses:
        fb = [] 
        s_chars = list(secret)
        # сначала зеленые
        for i,ch in enumerate(guess):
            if secret[i] == ch:
                fb.append("🟩")
                s_chars[i] = None
            else:
                fb.append(None)
        # затем желтые/красные
        for i,ch in enumerate(guess):
            if fb[i] is None:
                if ch in s_chars:
                    fb[i] = "🟨"
                    s_chars[s_chars.index(ch)] = None
                else:
                    fb[i] = "⬜"
        # обновляем глобальный статус
        for ch,sym in zip(guess, fb):
            prev = status.get(ch)
            if sym == "🟩":
                status[ch] = "green"
            elif sym == "🟨" and prev != "green":
                status[ch] = "yellow"
            elif sym == "⬜" and prev not in ("green","yellow"):
                status[ch] = "red"
    return status


# Русская раскладка виртуальной клавиатуры
KB_LAYOUT = [
    list("йцукенгшщзхъ"),
    list("фывапролджэ"),
    list("ячсмитьбю")
]

def render_full_board_with_keyboard(
    guesses: list[str],
    secret: str,
    total_rows: int = 6,
    max_width_px: int = 1080
) -> BytesIO:
    # --- антиалиасинг: рендерим в 3x размере, потом уменьшаем ---
    scale = 3
    padding   = 6 * scale
    board_def = 80 * scale
    cols      = len(secret)
    total_pad = (cols + 1) * padding

    # размер квадратика доски
    board_sq = min(board_def, (max_width_px * scale - total_pad) // cols)
    board_sq = max(20 * scale, board_sq)

    board_w = cols * board_sq + total_pad
    board_h = total_rows * board_sq + (total_rows + 1) * padding

    # выбираем масштаб клавиш по длине слова
    if cols >= 8:
        factor = 0.6
    elif cols == 7:
        factor = 0.5
    elif cols == 6:
        factor = 0.4
    elif cols == 5:
        factor = 0.3
    elif cols == 4:
        factor = 0.25

    kb_sq   = max(12 * scale, int(board_sq * factor))
    kb_rows = len(KB_LAYOUT)
    img_h   = board_h + kb_rows * kb_sq + (kb_rows + 1) * padding

    img        = Image.new("RGB", (board_w, img_h), (24, 24, 32))  # почти чёрный фон
    draw       = ImageDraw.Draw(img)
    font_board = ImageFont.truetype("DejaVuSans-Bold.ttf", int(board_sq * 0.6))
    font_kb    = ImageFont.truetype("DejaVuSans-Bold.ttf", int(kb_sq * 0.6))

    # --- игровая доска (6 строк) ---
    for r in range(total_rows):
        y0 = padding + r * (board_sq + padding)
        if r < len(guesses):
            guess = guesses[r]
            fb    = make_feedback(secret, guess)
        else:
            guess = None
            fb    = [None] * cols

        for c in range(cols):
            x0 = padding + c * (board_sq + padding)
            x1 = x0 + board_sq
            y1 = y0 + board_sq

            color = fb[c]
            if color == GREEN:
                bg = (121,184,81)  # #79b851
            elif color == YELLOW:
                bg = (243,194,55)  # #f3c237
            elif color == WHITE:
                bg = (72,73,84)  # #484954
            else:
                bg = (211,214,218)  # #d3d6da (неактивная)

            draw.rectangle([x0,y0,x1,y1], fill=bg, outline=(40,40,50), width=2)

            if guess:
                ch = guess[c].upper()
                tc = (255,255,255)  # белые буквы всегда
                bbox = draw.textbbox((0,0), ch, font=font_board)
                w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
                # Смещение по y для всех, кроме Щ, Ц, Д, Й
                special_letters = {'щ', 'ц', 'д', 'й'}
                if ch.lower() in special_letters:
                    y_offset = -board_sq * 0.05  # специальные буквы чуть выше (5%)
                else:
                    y_offset = -board_sq * 0.10  # остальные буквы выше (10%)
                draw.text(
                    (x0 + (board_sq-w)/2, y0 + (board_sq-h)/2 + y_offset),
                    ch, font=font_board, fill=tc
                )

    # --- мини-клавиатура ---
    letter_status = compute_letter_status(secret, guesses)
    for ri, row in enumerate(KB_LAYOUT):
        y0      = board_h + padding + ri * (kb_sq + padding)
        row_len = len(row)
        row_pad = (row_len + 1) * padding
        row_w   = row_len * kb_sq + row_pad
        x_off   = (board_w - row_w) // 2

        for i, ch in enumerate(row):
            x0 = x_off + padding + i * (kb_sq + padding)
            x1 = x0 + kb_sq
            y1 = y0 + kb_sq

            st = letter_status.get(ch)
            if st == "green":
                bg = (121,184,81)  # #79b851
            elif st == "yellow":
                bg = (243,194,55)  # #f3c237
            elif st == "red":
                bg = (72,73,84)  # #484954
            else:
                bg = (129,130,155)  # #81829b — обычные буквы на клавиатуре

            draw.rectangle([x0,y0,x1,y1], fill=bg, outline=(40,40,50), width=1)
            tc = (255,255,255)  # белые буквы всегда
            letter = ch.upper()
            bbox   = draw.textbbox((0,0), letter, font=font_kb)
            w, h   = bbox[2]-bbox[0], bbox[3]-bbox[1]
            # Смещение по y для всех, кроме Щ, Ц, Д, Й
            special_letters = {'щ', 'ц', 'д', 'й'}
            if ch in special_letters:
                y_offset = -kb_sq * 0.05  # специальные буквы чуть выше (5%)
            else:
                y_offset = -kb_sq * 0.10  # остальные буквы выше (10%)
            draw.text(
                (x0 + (kb_sq-w)/2, y0 + (kb_sq-h)/2 + y_offset),
                letter, font=font_kb, fill=tc
            )

    # уменьшение до нормального размера с антиалиасингом
    final_img = img.resize((board_w // scale, img_h // scale), Image.LANCZOS)
    final_buf = BytesIO()
    final_img.save(final_buf, format="PNG")
    final_buf.seek(0)
    return final_buf

# --- Константы и словарь ---
ASK_LENGTH, GUESSING, FEEDBACK_CHOOSE, FEEDBACK_WORD, REMOVE_INPUT, BROADCAST= range(6)

# --- Загрузка и сортировка списка слов ---
BASE_FILE = Path("base_words.json")

# Читаем список слов из base_words.json
with BASE_FILE.open("r", encoding="utf-8") as f:
    base_words = json.load(f)
    main_words = base_words.get("main", [])
    additional_words = base_words.get("additional", [])

# Фильтруем по критериям: только буквы, длина 4–11 символов
# и нормализуем слова (нижний регистр, замена ё на е)
filtered_main = [normalize(w) for w in main_words if w.isalpha() and 4 <= len(w) <= 11]
filtered_additional = [normalize(w) for w in additional_words if w.isalpha() and 4 <= len(w) <= 11]

# Удаляем дубликаты, которые могли появиться после нормализации
filtered_main = list(dict.fromkeys(filtered_main))
filtered_additional = list(dict.fromkeys(filtered_additional))

# Сортируем списки
WORDLIST = sorted(filtered_main)
with BASE_FILE.open("w", encoding="utf-8") as f:
    json.dump({"main": WORDLIST, "additional": sorted(filtered_additional)}, f, ensure_ascii=False, indent=2)

GREEN, YELLOW, WHITE = "🟩", "🟨", "⬜"

def make_feedback(secret: str, guess: str) -> str:
    fb = [None] * len(guess)
    secret_chars = list(secret)
    # 1) зеленые
    for i, ch in enumerate(guess):
        if secret[i] == ch:
            fb[i] = GREEN
            secret_chars[i] = None
    # 2) желтые/красные
    for i, ch in enumerate(guess):
        if fb[i] is None:
            if ch in secret_chars:
                fb[i] = YELLOW
                secret_chars[secret_chars.index(ch)] = None
            else:
                fb[i] = WHITE
    return "".join(fb)


# --- Обработчики команд ---

def check_ban_status(handler):
    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = str(update.effective_user.id)
        store = load_store()
        user_data = store["users"].get(user_id, {})
        
        if user_data.get("banned", False):
            try:
                # Проверяем, не отправляли ли мы уже сообщение в этом обновлении
                if context.user_data.get("last_ban_update_id") != update.update_id:
                    if update.callback_query:
                        await update.callback_query.answer("❌ Вы заблокированы в этом боте.", show_alert=True)
                    else:
                        await update.message.reply_text("❌ Вы заблокированы в этом боте.")
                    # Запоминаем ID обновления
                    context.user_data["last_ban_update_id"] = update.update_id
                return ConversationHandler.END
            except Exception as e:
                logger.warning(f"Error handling banned user {user_id}: {e}")
                return
        else:
            # Если пользователь был разбанен, очищаем его состояние при первом сообщении
            if user_data.get("was_banned"):
                context.user_data.clear()
                # Удаляем флаг разбана из базы данных
                user_data.pop("was_banned", None)
                save_store(store)
        return await handler(update, context, *args, **kwargs)
    return wrapper


async def is_banned(user_id: str) -> bool:
    """Проверяет, забанен ли пользователь"""
    store = load_store()
    user_data = store["users"].get(str(user_id), {})
    return user_data.get("banned", False)


async def send_activity_periodic(context: ContextTypes.DEFAULT_TYPE):
    """
    Периодически (и сразу при старте) шлет user_activity.json администратору.
    Если файл слишком большой, шлет его как документ.
    """
    ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
    activity_path = USER_FILE
    if not activity_path.exists():
        return

    content = activity_path.read_text(encoding="utf-8")
    # Ограничение Telegram — примерно 4096 символов
    MAX_LEN = 4000

    if len(content) <= MAX_LEN:
        # Можно втиснуть в одно сообщение
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📋 Текущий user_activity.json:\n<pre>{content}</pre>",
            parse_mode="HTML"
        )
    else:
        # Слишком длинное — отправляем как файл
        with activity_path.open("rb") as f:
            await context.bot.send_document(
                chat_id=ADMIN_ID,
                document=InputFile(f, filename="user_activity.json"),
                caption="📁 user_activity.json (слишком большой для текста)"
            )


async def send_unfinished_games(context: ContextTypes.DEFAULT_TYPE):
    """
    Шлёт напоминание тем, у кого включены уведомления о незавершённой игре,
    но только если после последнего напоминания пользователь ни разу не отреагировал.
    После отправки ставит флаг, чтобы больше не присылать, пока пользователь не сыграет/не напишет.
    """
    store = load_store()

    for uid, udata in store["users"].items():
        # уведомления выключены
        if not udata.get("notify_on_wakeup", True):
            continue
        # у пользователя нет незаконченной игры
        if "current_game" not in udata:
            continue
        # если уже отправляли и пользователь не отреагировал — пропускаем
        if udata.get("notified", False):
            continue

        # Отправляем напоминание
        cg = udata["current_game"]
        length = len(cg["secret"])
        attempts = cg["attempts"]
        text = (
            "Я вернулся из спячки!\n"
            f"⏳ У вас есть незавершённая игра:\n"
            f"{length}-буквенное слово, вы на попытке {attempts}.\n"
            "Нажмите /play или /start, чтобы продолжить!"
        )
        try:
            await context.bot.send_message(chat_id=int(uid), text=text)
        except Exception as e:
            logger.warning(f"Не смогли напомнить {uid}: {e}")
            continue

        # Запоминаем время отправки
        udata["notified"] = True
        save_store(store)



@check_ban_status
async def unknown_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_notification_flag(str(update.effective_user.id))
    # если сейчас в игре или в фидбеке — молчим
    if context.user_data.get("game_active") or context.user_data.get("in_feedback") or context.user_data.get("in_remove"):
        return
    if context.user_data.pop("just_done", False):
        return
    await update.message.reply_text(
        "Я не обрабатываю слова просто так😕\n"
        "Чтобы начать игру, введи /play."
    )


@check_ban_status
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_user_activity(update.effective_user)
    store = load_store()
    u = store["users"].get(str(update.effective_user.id), {})
    clear_notification_flag(str(update.effective_user.id))
    if "current_game" in u:
        cg = u["current_game"]
        # заполняем context.user_data из cg:
        context.user_data.update({
            "secret": cg["secret"],
            "length": len(cg["secret"]),
            "attempts": cg["attempts"],
            "guesses": cg["guesses"],
        })
        await update.message.reply_text(
            f"Продолжаем игру: {len(cg['secret'])}-буквенное слово, ты на попытке {cg['attempts']}. Вводи догадку:"
        )
        return GUESSING

    
    await update.message.reply_text(
        "Привет! Я Wordle Bot — угадай слово за 6 попыток.\n"
        "https://github.com/sqwirex/wordle-bot - ссылка на репозиторий с кодом бота\n\n"
        "/play — начать или продолжить игру\n"
        "/hint — дает слово в подсказку, если вы затрудняетесь ответить " \
        "(случайное слово в котором совпадают некоторые буквы с загаданным)\n"
        "/reset — сбросить текущую игру\n"
        "/notification — включить/отключить уведомления при пробуждении бота\n"
        "/my_stats — посмотреть свою статистику\n"
        "/global_stats — посмотреть глобальную статистику за все время\n"
        "/feedback — если ты встретил слово, которое не должно быть в словаре или не существует, введи его в Черный список, " \
        "если же наоборот, ты вбил слово, а бот его не признает, но ты уверен что оно существует, отправляй его в Белый список. " \
        "Администратор бота рассмотрит твое предложение и добавит в ближайшем обновлении, если оно действительно подходит!\n\n"
        "Только не забывай: я еще учусь и не знаю некоторых слов!\n"
        "Не расстраивайся, если я ругаюсь на твое слово — мне есть чему учиться :)\n\n"
        "Кстати, иногда я могу «выключаться», потому что живу в контейнере!\n"
        "Если я не отвечаю — попробуй позже и нажми /play или /start, чтобы продолжить прервавшуюся игру.\n\n"
    )


@check_ban_status
async def ask_length(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["state"] = ASK_LENGTH
    update_user_activity(update.effective_user)
    clear_notification_flag(str(update.effective_user.id))
    context.user_data["game_active"] = True
    store = load_store()
    u = store["users"].get(str(update.effective_user.id), {})
    if "current_game" in u:
        cg = u["current_game"]
        # заполняем context.user_data из cg:
        context.user_data.update({
            "secret": cg["secret"],
            "length": len(cg["secret"]),
            "attempts": cg["attempts"],
            "guesses": cg["guesses"],
        })
        await update.message.reply_text(
            f"Продолжаем игру: {len(cg['secret'])}-буквенное слово, ты на попытке {cg['attempts']}. Вводи догадку:"
        )
        return GUESSING
    
    await update.message.reply_text("Сколько букв в слове? (4–11)")
    return ASK_LENGTH


@check_ban_status
async def receive_length(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_user_activity(update.effective_user)
    text = update.message.text.strip()
    if not text.isdigit() or not 4 <= int(text) <= 11:
        await update.message.reply_text("Нужно число от 4 до 11.")
        return ASK_LENGTH

    length = int(text)
    candidates = [w for w in WORDLIST if len(w) == length]
    if not candidates:
        await update.message.reply_text("Не нашел слов такой длины. Попробуй еще:")
        return ASK_LENGTH

    secret = random.choice(candidates)
    
    store = load_store()
    u = store["users"].setdefault(str(update.effective_user.id), {"stats": {"games_played":0,"wins":0,"losses":0}})
    # Запись текущей игры
    u["current_game"] = {
        "secret": secret,
        "attempts": 0,
        "guesses": [],
    }
    save_store(store)

    context.user_data["secret"] = secret
    context.user_data["length"] = length
    context.user_data["attempts"] = 0
    context.user_data["guesses"] = []
    context.user_data["state"] = GUESSING

    await update.message.reply_text(
        f"Я загадал слово из {length} букв. У тебя 6 попыток. Введи первую догадку:"
    )
    
    return GUESSING


@check_ban_status
async def handle_guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    store   = load_store()
    user    = store["users"].setdefault(user_id, {
        "first_name": update.effective_user.first_name,
        "stats": {"games_played": 0, "wins": 0, "losses": 0}
    })

    # Обновляем время последнего визита
    user["last_seen_msk"] = datetime.now(ZoneInfo("Europe/Moscow")).isoformat()

    # Проверяем активную игру
    if "current_game" not in user:
        await update.message.reply_text("Нет активной игры, начни /play")
        return ConversationHandler.END

    cg     = user["current_game"]
    guess = normalize(update.message.text)
    secret = cg["secret"]
    length = len(secret)

    # Нормализуем слово для проверки (приводим к нижний регистр и заменяем ё на е)
    normalized_guess = normalize(guess)
    
    # Проверяем на пробелы до проверки длины
    if " " in guess:
        await update.message.reply_text("Пожалуйста, введите слово без пробелов.")
        return GUESSING
    
    # Валидация длины
    if len(guess) != length:
        await update.message.reply_text(f"Введите слово из {length} букв.")
        return GUESSING
    
    # Проверяем, не предлагал ли пользователь это слово ранее
    user_id = str(update.effective_user.id)
    user = store["users"].get(user_id, {})
    suggested_words = user.get("suggested_words", [])
    
    if normalized_guess in suggested_words and normalized_guess not in WORDLIST:
        await update.message.reply_text(
            "Извините, это слово уже было предложено вами, но еще не добавлено в словарь.\n"
            "Пожалуйста, дождитесь его проверки администратором."
        )
        return GUESSING
    
    # Проверяем слово в основном и дополнительном списках
    with BASE_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
        main_words = set(data.get("main", []))
        additional_words = set(data.get("additional", []))
        all_words = main_words | additional_words
    
    if normalized_guess not in all_words:
        # Предлагаем добавить слово в белый список
        keyboard = [
            [
                InlineKeyboardButton(
                    "Предложить добавить слово",
                    callback_data=f"suggest_white:{guess}"
                )
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"Слово «{normalized_guess}» не найдено в словаре.",
            reply_markup=reply_markup
        )
        return GUESSING

    if " " in guess:
        await update.message.reply_text("Пожалуйста, введите слово без пробелов.")
        return GUESSING

    # Сохраняем ход
    cg["guesses"].append(guess)
    cg["attempts"] += 1
    save_store(store)

    # Рендерим доску из 6 строк + мини-клавиатуру снизу.
    # Клавиатура будет крупнее для слов ≥8 букв, чуть меньше для 7 и еще меньше для 4–5.
    img_buf = render_full_board_with_keyboard(
        guesses=cg["guesses"],
        secret=secret,
        total_rows=6,
        max_width_px=1080
    )
    await update.message.reply_photo(
        photo=InputFile(img_buf, filename="wordle_board.png"),
        caption=f"Попытка {cg['attempts']} из 6"
    )

    # —— Победа ——
    if guess == secret:
        stats = user["stats"]
        stats["games_played"] += 1
        stats["wins"] += 1
        stats["win_rate"] = stats["wins"] / stats["games_played"]

        g = store["global"]
        g["total_games"] += 1
        g["total_wins"] += 1
        g["win_rate"] = g["total_wins"] / g["total_games"]

        top_uid, top_data = max(
            store["users"].items(),
            key=lambda kv: kv[1]["stats"]["wins"]
        )
        store["global"]["top_player"] = {
            "user_id":  top_uid,
            "username": top_data.get("username") or top_data.get("first_name", ""),
            "wins":     top_data["stats"]["wins"]
        }

        await update.message.reply_text(
            f"🎉 Поздравляю! Угадал за {cg['attempts']} "
            f"{'попытка' if cg['attempts']==1 else 'попытки' if 2<=cg['attempts']<=4 else 'попыток'}.\n"
            "Чтобы сыграть вновь, введи /play."
        )
        del user["current_game"]
        context.user_data.pop("game_active", None)
        context.user_data["just_done"] = True
        save_store(store)
        return ConversationHandler.END

    # —— Поражение ——
    if cg["attempts"] >= 6:
        stats = user["stats"]
        stats["games_played"] += 1
        stats["losses"] += 1
        stats["win_rate"] = stats["wins"] / stats["games_played"]

        g = store["global"]
        g["total_games"] += 1
        g["total_losses"] += 1
        g["win_rate"] = g["total_wins"] / g["total_games"]

        await update.message.reply_text(
            f"💔 Попытки закончились. Было слово «{secret}».\n"
            "Чтобы начать новую игру, введи /play."
        )
        del user["current_game"]
        context.user_data.pop("game_active", None)
        context.user_data["just_done"] = True
        save_store(store)
        return ConversationHandler.END

    # Игра продолжается
    return GUESSING


@check_ban_status
async def suggest_white_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатия на кнопку предложения слова в белый список"""
    query = update.callback_query
    await query.answer()
    
    # Извлекаем слово из callback_data и нормализуем его
    word = normalize(query.data.split(':', 1)[1])
    user_id = str(update.effective_user.id)
    
    # Загружаем текущие предложения и основной словарь
    current_suggestions = load_suggestions()
    with BASE_FILE.open("r", encoding="utf-8") as f:
        base_words = set(json.load(f))
    
    # Загружаем данные пользователя
    store = load_store()
    user = store["users"].get(user_id, {})
    
    # Добавляем слово в предложения для белого списка, если его там еще нет
    if word not in current_suggestions["white"] and word not in base_words:
        current_suggestions["white"].add(word)
        save_suggestions(current_suggestions)
        # Обновляем глобальную переменную
        global suggestions
        suggestions = current_suggestions
    
    # Добавляем слово в список предложенных пользователем, если его там еще нет
    if "suggested_words" not in user:
        user["suggested_words"] = []
    
    if word not in user["suggested_words"]:
        user["suggested_words"].append(word)
        save_store(store)
    
    # Обновляем сообщение, убирая кнопку
    await query.edit_message_text(
        f"✅ Слово «{word}» добавлено в предложения для белого списка.\n"
        "Спасибо за ваш вклад! Администратор рассмотрит ваше предложение."
    )
    
    return GUESSING


@check_ban_status
async def ignore_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Команды /start и /play не работают во время игры — сначала /reset.")
    return ASK_LENGTH


@check_ban_status
async def ignore_guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Команды /start и /play не работают во время игры — сначала /reset.")
    return GUESSING


@check_ban_status
async def hint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    store = load_store()
    user_entry = store["users"].setdefault(user_id, {
        "stats": {"games_played": 0, "wins": 0, "losses": 0}
    })

    # Проверяем, есть ли активная игра
    if "current_game" not in user_entry:
        await update.message.reply_text("Эту команду можно использовать только во время игры.")
        return ConversationHandler.END

    cg = user_entry["current_game"]

    # Если подсказка уже взята — не даем еще одну
    if cg.get("hint_used", False):
        await update.message.reply_text("Подсказка уже использована в этой игре.")
        return GUESSING

    secret = cg["secret"]
    length = len(secret)

    # Сколько букв нужно подсказать
    hint_counts = {4:1, 5:2, 6:2, 7:3, 8:3, 9:4, 10:4, 11:5}
    num_letters = hint_counts.get(length, 1)

    # Считаем буквы в secret
    secret_counter = Counter(secret)

    # Выбираем кандидатов: разная позиция, но >= num_letters общих символов
    candidates = []
    for w in WORDLIST:
        if len(w) != length or w == secret:
            continue
        w_counter = Counter(w)
        # пересечение счетчиков по минимуму
        common = sum(min(secret_counter[ch], w_counter[ch]) for ch in w_counter)
        if common == num_letters:
            candidates.append(w)

    if not candidates:
        await update.message.reply_text("К сожалению, подходящих подсказок нет.")
        return GUESSING

    hint_word = random.choice(candidates)

    # Отмечаем в JSON, что подсказка взята
    cg["hint_used"] = True
    save_store(store)

    await update.message.reply_text(f"🔍 Подсказка: {hint_word}")
    return GUESSING


@check_ban_status
async def hint_not_allowed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сообщение, если /hint вызвали не во время игры."""
    clear_notification_flag(str(update.effective_user.id))
    await update.message.reply_text("Эту команду можно использовать только во время игры.")
    # если сейчас выбираем длину — останемся в ASK_LENGTH, иначе в GUESSING
    return context.user_data.get("state", ASK_LENGTH)


@check_ban_status
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_user_activity(update.effective_user)

    store = load_store()
    uid = str(update.effective_user.id)
    user = store["users"].get(uid)
    if user and "current_game" in user:
        del user["current_game"]
        save_store(store)

    context.user_data.clear()
    await update.message.reply_text("Прогресс сброшен. Жду /play для новой игры.")
    return ConversationHandler.END


@check_ban_status
async def reset_global(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_user_activity(update.effective_user)
    clear_notification_flag(str(update.effective_user.id))
    await update.message.reply_text("Сейчас нечего сбрасывать — начните игру: /play")


@check_ban_status
async def notification_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    store = load_store()
    user = store["users"].setdefault(uid, {"stats": {...}})
    clear_notification_flag(str(update.effective_user.id))
    # Переключаем
    current = user.get("notify_on_wakeup", True)
    user["notify_on_wakeup"] = not current
    save_store(store)
    state = "включены" if not current else "отключены"
    await update.message.reply_text(f"Уведомления при пробуждении бота {state}.")


@check_ban_status
async def my_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает личную статистику — только вне игры."""
    update_user_activity(update.effective_user)
    store = load_store()
    uid = str(update.effective_user.id)
    user = store["users"].get(uid)
    if not user or "current_game" in user:
        await update.message.reply_text("Эту команду можно использовать только вне игры.")
        return
    s = user.get("stats", {})
    await update.message.reply_text(
        "```"
        f"🧑 Ваши результаты:\n\n"
        f"🎲 Всего игр: {s.get('games_played',0)}\n"
        f"🏆 Побед: {s.get('wins',0)}\n"
        f"💔 Поражений: {s.get('losses',0)}\n"
        f"📊 Процент: {s.get('win_rate',0.0)*100:.2f}%"
        "```",
        parse_mode="Markdown"
    )


@check_ban_status
async def global_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_user_activity(update.effective_user)
    """Показывает глобальную статистику — только вне игры."""
    store = load_store()
    g = store["global"]
    # если во время партии — запрет
    uid = str(update.effective_user.id)
    user = store["users"].get(uid)
    if user and "current_game" in user:
        await update.message.reply_text("Эту команду можно использовать только вне игры.")
        return
    
    tp = g.get("top_player", {})
    if tp:
        top_line = f"Сильнейший: @{tp['username']} ({tp['wins']} побед)\n\n"
    else:
        top_line = ""
    
    await update.message.reply_text(
        "```"
        f"🌐 Глобальная статистика:\n\n"
        f"🎲 Всего игр: {g['total_games']}\n"
        f"🏆 Побед: {g['total_wins']}\n"
        f"💔 Поражений: {g['total_losses']}\n"
        f"📊 Процент: {g['win_rate']*100:.2f}%\n\n"
        f"{top_line}"
        "```",
        parse_mode="Markdown"
    )


@check_ban_status
async def only_outside_game(update, context):
    clear_notification_flag(str(update.effective_user.id))
    await update.message.reply_text("Эту команду можно использовать только вне игры.")
    # вернем то состояние, в котором сейчас юзер:
    return context.user_data.get("state", ConversationHandler.END)


@check_ban_status
async def feedback_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # запретим во время игры
    store = load_store()
    u = store["users"].get(str(update.effective_user.id), {})
    clear_notification_flag(str(update.effective_user.id))
    if "current_game" in u or context.user_data.get("game_active"):
        await update.message.reply_text(
            "Нельзя отправлять фидбек пока идет игра или после перезапуска.\n"
            "Сначала продолжи играть /play, а потом либо закончи игру, либо сбрось /reset",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END

    # предлагаем выбрать список
    keyboard = [
        ["Черный список", "Белый список"],
        ["Отмена"]
    ]
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Куда добавить слово?", reply_markup=markup)

    # запомним текущее состояние
    context.user_data["feedback_state"] = FEEDBACK_CHOOSE
    context.user_data["in_feedback"] = True
    return FEEDBACK_CHOOSE


@check_ban_status
async def feedback_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "Отмена":
        await update.message.reply_text("Отменено.", reply_markup=ReplyKeyboardRemove())
        context.user_data.pop("in_feedback", None)
        context.user_data["just_done"] = True
        return ConversationHandler.END

    if text not in ("Черный список", "Белый список"):
        await update.message.reply_text("Пожалуйста, нажимайте одну из кнопок.")
        return FEEDBACK_CHOOSE

    # куда кладем
    context.user_data["fb_target"] = "black" if text == "Черный список" else "white"
    # убираем клавиатуру и спрашиваем слово
    await update.message.reply_text(
        "Введите слово для предложения:", reply_markup=ReplyKeyboardRemove()
    )

    context.user_data["feedback_state"] = FEEDBACK_WORD
    return FEEDBACK_WORD


@check_ban_status
async def feedback_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    word = normalize(update.message.text)
    target = context.user_data["fb_target"]

    if SUGGESTIONS_FILE.exists() and SUGGESTIONS_FILE.stat().st_size >= 1_000_000:
        await update.message.reply_text(
            "Прости, сейчас нельзя добавить новое слово — файл предложений уже слишком большой."
        )
        context.user_data.pop("in_feedback", None)
        context.user_data["just_done"] = True
        return ConversationHandler.END

    if " " in word:
        await update.message.reply_text("Пожалуйста, введите слово без пробелов.")
        return FEEDBACK_WORD

    suggestions = load_suggestions()

    # Черный список: добавляем, только если слово есть в словаре
    if target == "black":
        if word in WORDLIST:
            suggestions["black"].add(word)
            save_suggestions(suggestions)
            
            # Добавляем слово в профиль пользователя
            store = load_store()
            user_id = str(update.effective_user.id)
            if user_id not in store["users"]:
                store["users"][user_id] = {}
            if "suggested_words" not in store["users"][user_id]:
                store["users"][user_id]["suggested_words"] = []
            if word not in store["users"][user_id]["suggested_words"]:
                store["users"][user_id]["suggested_words"].append(word)
                save_store(store)
                
            resp = "Спасибо, добавил в предложения для чёрного списка."
        else:
            resp = "Нельзя: слово должно быть в основном словаре."

    # Белый список: добавляем, только если слова нет в словаре и длина 4–11
    else:
        if 4 <= len(word) <= 11 and word not in WORDLIST:
            suggestions["white"].add(word)
            save_suggestions(suggestions)
            
            # Добавляем слово в профиль пользователя
            store = load_store()
            user_id = str(update.effective_user.id)
            if user_id not in store["users"]:
                store["users"][user_id] = {}
            if "suggested_words" not in store["users"][user_id]:
                store["users"][user_id]["suggested_words"] = []
            if word not in store["users"][user_id]["suggested_words"]:
                store["users"][user_id]["suggested_words"].append(word)
                save_store(store)
                
            resp = "Спасибо, добавил в предложения для белого списка."
        else:
            if word in WORDLIST:
                resp = "Нельзя: такое слово уже есть в основном словаре."
            elif not (4 <= len(word) <= 11):
                resp = "Нельзя: длина слова должна быть от 4 до 11 символов."
            else:
                resp = "Нельзя: слово должно быть вне основного словаря и из 4–11 букв."

    await update.message.reply_text(resp)
    context.user_data.pop("in_feedback", None)
    context.user_data["just_done"] = True
    return ConversationHandler.END


@check_ban_status
async def feedback_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    await update.message.reply_text("Отменено.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


@check_ban_status
async def block_during_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # любой посторонний ввод заглушаем
    await update.message.reply_text(
        "Сейчас идет ввод для фидбека, нельзя использовать команды."
    )
    # возвращаемся в текущее состояние
    return context.user_data.get("feedback_state", FEEDBACK_CHOOSE)


@check_ban_status
async def feedback_not_allowed_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Нельзя отправлять фидбек пока вы выбираете длину слова. "
        "Сначала укажите длину (4–11)."
    )
    return ASK_LENGTH


@check_ban_status
async def feedback_not_allowed_guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Нельзя отправлять фидбек во время игры. "
        "Сначала закончите игру или /reset."
    )
    return GUESSING


async def dict_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Только админу
    if update.effective_user.id != ADMIN_ID:
        return

    # Читаем свежий словарь из base_words.json
    with BASE_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
        main_words = data.get("main", [])
        additional_words = data.get("additional", [])

    total_main = len(main_words)
    total_additional = len(additional_words)
    total = total_main + total_additional

    # Считаем количество слов каждой длины (4–11)
    main_length_counts = Counter(len(w) for w in main_words)
    additional_length_counts = Counter(len(w) for w in additional_words)

    stats_lines = []
    for length in range(4, 12):
        main_count = main_length_counts.get(length, 0)
        additional_count = additional_length_counts.get(length, 0)
        stats_lines.append(f"{length} букв: {main_count} (main) + {additional_count} (additional) = {main_count + additional_count}")

    stats_text = "\n".join(stats_lines)

    # Упаковываем списки в файл
    data = "=== Main Words ===\n" + "\n".join(main_words) + "\n\n=== Additional Words ===\n" + "\n".join(additional_words)
    bio = BytesIO(data.encode("utf-8"))
    bio.name = "wordlist.txt"

    # Отправляем документ с общей и детальной статистикой
    await update.message.reply_document(
        document=bio,
        filename="wordlist.txt",
        caption=(
            f"📚 В словаре всего {total} слов:\n"
            f"• {total_main} в основном списке\n"
            f"• {total_additional} в дополнительном списке\n\n"
            f"🔢 Распределение по длине:\n{stats_text}"
        )
    )


async def dump_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    path = USER_FILE  # это Path("user_activity.json")
    if not path.exists():
        return await update.message.reply_text("Файл user_activity.json не найден.")

    # прочитаем текст, и если короткий — отправим как сообщение
    content = path.read_text("utf-8")
    if len(content) < 3000:
        # отправляем в кодовом блоке
        return await update.message.reply_text(
            f"<pre>{content}</pre>", parse_mode="HTML"
        )

    # иначе — отправляем как документ
    with path.open("rb") as f:
        await update.message.reply_document(
            document=InputFile(f, filename=path.name),
            caption="📁 user_activity.json"
        )


async def suggestions_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # только админ
    if update.effective_user.id != ADMIN_ID:
        return
    sugg = load_suggestions()
    black = sugg.get("black", [])
    white = sugg.get("white", [])
    add = sugg.get("add", [])
    text = (
        "Предложения для черного списка:\n"
        + (", ".join(f'"{w}"' for w in black) if black else "— пусто")
        + "\n\nПредложения для белого списка:\n"
        + (", ".join(f'"{w}"' for w in white) if white else "— пусто")
        + "\n\nПредложения для дополнительного списка:\n"
        + (", ".join(f'"{w}"' for w in add) if add else "— пусто")
    )
    await update.message.reply_text(text)


async def suggestions_move_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Только админ
    if update.effective_user.id != ADMIN_ID:
        return

    # Блокируем во время игры
    store = load_store()
    u = store["users"].get(str(update.effective_user.id), {})
    if "current_game" in u or context.user_data.get("game_active"):
        await update.message.reply_text("Эту команду можно использовать только вне игры.")
        return ConversationHandler.END

    # Если все ок — запускаем диалог перемещения
    await update.message.reply_text(
        "Введи слова для перемещения в add список (формат):\n"
        "слово1, слово2, слово3\n\n"
        "Слова будут перемещены из черного или белого списка в add список.\n"
        "Или /cancel для отмены."
    )
    return REMOVE_INPUT


async def suggestions_move_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # только админ
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    
    context.user_data["in_remove"] = True
    text = update.message.text.strip()
    sugg = load_suggestions()
    moved = {"black": [], "white": []}

    # извлекаем слова через запятую
    words = [w.strip().lower() for w in text.split(",") if w.strip()]
    for w in words:
        # Проверяем наличие слова в черном списке
        if w in sugg["black"]:
            sugg["black"].remove(w)
            sugg["add"].add(w)
            moved["black"].append(w)
        # Проверяем наличие слова в белом списке
        elif w in sugg["white"]:
            sugg["white"].remove(w)
            sugg["add"].add(w)
            moved["white"].append(w)

    save_suggestions(sugg)
    
    # формируем ответ
    parts = []
    if moved["black"]:
        parts.append(f'Из черного списка перемещено в add: {", ".join(moved["black"])}')
    if moved["white"]:
        parts.append(f'Из белого списка перемещено в add: {", ".join(moved["white"])}')
    if not parts:
        parts = ["Ничего не перемещено."]
        
    await update.message.reply_text("\n".join(parts))
    context.user_data.pop("in_remove", None)
    context.user_data["just_done"] = True
    return ConversationHandler.END


async def suggestions_remove_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Только админ
    if update.effective_user.id != ADMIN_ID:
        return

    # Блокируем во время игры
    store = load_store()
    u = store["users"].get(str(update.effective_user.id), {})
    if "current_game" in u or context.user_data.get("game_active"):
        await update.message.reply_text("Эту команду можно использовать только вне игры.")
        return ConversationHandler.END

    # Если все ок — запускаем диалог удаления
    await update.message.reply_text(
        "Введи, что удалить (формат):\n"
        "black: слово1, слово2\n"
        "white: слово3, слово4\n"
        "add: слово5, слово6\n\n"
        "Или /cancel для отмены."
    )
    return REMOVE_INPUT


async def suggestions_remove_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # только админ
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    
    context.user_data["in_remove"] = True
    text = update.message.text.strip()
    sugg = load_suggestions()
    removed = {"black": [], "white": [], "add": []}

    # парсим построчно
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, vals = line.split(":", 1)
        key = key.strip().lower()
        if key not in ("black", "white", "add"):
            continue
        # извлекаем слова через запятую
        words = [w.strip().lower() for w in vals.split(",") if w.strip()]
        for w in words:
            if w in sugg[key]:
                sugg[key].remove(w)
                removed[key].append(w)

    save_suggestions(sugg)
    
    # Удаляем слова из профилей пользователей
    store = load_store()
    removed_count = 0
    
    # Собираем все удаленные слова из всех списков
    all_removed_words = set(removed["black"]) | set(removed["white"]) | set(removed["add"])
    
    # Проходим по всем пользователям и удаляем слова из их списков
    for user_id, user_data in store["users"].items():
        if "suggested_words" in user_data:
            before = len(user_data["suggested_words"])
            user_data["suggested_words"] = [w for w in user_data["suggested_words"] 
                                         if w not in all_removed_words]
            removed_count += before - len(user_data["suggested_words"])
    
    # Сохраняем изменения, если что-то было удалено
    if removed_count > 0:
        save_store(store)
    
    # формируем ответ
    parts = []
    if removed["black"]:
        parts.append(f'Из черного удалено: {", ".join(removed["black"])}')
    if removed["white"]:
        parts.append(f'Из белого удалено: {", ".join(removed["white"])}')
    if removed["add"]:
        parts.append(f'Из add удалено: {", ".join(removed["add"])}')
    if removed_count > 0:
        parts.append(f'Из профилей пользователей удалено {removed_count} слов.')
    if not parts:
        parts = ["Ничего не удалено."]
        
    await update.message.reply_text("\n".join(parts))
    context.user_data.pop("in_remove", None)
    context.user_data["just_done"] = True
    return ConversationHandler.END


async def suggestions_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    # 1. Загружаем предложения
    sugg = load_suggestions()  # {'black': set(), 'white': set(), 'add': set()}

    # 2. Читаем текущий base_words.json
    with BASE_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
        main_words = set(data.get("main", []))
        additional_words = set(data.get("additional", []))

    # 3. Убираем «чёрные» и добавляем «белые» и «add»
    main_words -= sugg["black"]
    main_words |= sugg["white"]
    additional_words |= sugg["add"]

    # 4. Фильтруем по критериям (только буквы, длина 4–11) и сортируем
    filtered_main = [w for w in main_words if w.isalpha() and 4 <= len(w) <= 11]
    filtered_main.sort()
    filtered_additional = [w for w in additional_words if w.isalpha() and 4 <= len(w) <= 11]
    filtered_additional.sort()

    # 5. Сохраняем обратно в base_words.json
    with BASE_FILE.open("w", encoding="utf-8") as f:
        json.dump({"main": filtered_main, "additional": filtered_additional}, f, ensure_ascii=False, indent=2)

    logger.info(f"-> Wrote {len(filtered_main)} main words and {len(filtered_additional)} additional words to {BASE_FILE.resolve()}")

    # 6. Обновляем глобальный список в памяти
    global WORDLIST
    WORDLIST = filtered_main

    # 7. Удаляем одобренные слова из списка предложенных у пользователей
    store = load_store()
    removed_count = 0
    
    # Собираем все одобренные слова (белый список и add список)
    approved_words = sugg["white"] | sugg["add"]
    blacklisted_words = sugg["black"]
    
    # Проходим по всем пользователям и удаляем одобренные слова из их списков
    for user_id, user_data in store["users"].items():
        if "suggested_words" in user_data:
            before = len(user_data["suggested_words"])
            user_data["suggested_words"] = [
                w for w in user_data["suggested_words"] 
                if w not in approved_words and w not in blacklisted_words
            ]
            removed_count += before - len(user_data["suggested_words"])
    
    # Сохраняем изменения, если что-то было удалено
    if removed_count > 0:
        save_store(store)

    # 8. Очищаем suggestions.json
    save_suggestions({"black": set(), "white": set(), "add": set()})

    # 9. Ответ админу
    await update.message.reply_text(
        f"Словарь пересобран: +{len(sugg['white'])}, +{len(sugg['add'])}, -{len(sugg['black'])}.\n"
        f"Удалено {removed_count} слов (одобренные и черный список) из профилей пользователей.\n"
        "Предложения очищены."
    )


async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # только админ
    context.user_data["in_broadcast"] = True
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("Введите текст рассылки для всех пользователей:")
    return BROADCAST


async def broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    store = load_store()      # берем тех, кого мы когда-то записали
    failed = []
    skipped = 0
    total_sent = 0
    
    for uid, user_data in store["users"].items():
        # Пропускаем забаненных пользователей
        if user_data.get("banned", False):
            skipped += 1
            continue
            
        try:
            await context.bot.send_message(chat_id=int(uid), text=text)
            total_sent += 1
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения пользователю {uid}: {e}")
            failed.append(uid)
    
    msg = f"✅ Рассылка успешно отправлена!\n"
    msg += f"• Отправлено: {total_sent} пользователям\n"
    msg += f"• Пропущено (забанено): {skipped}"
    
    if failed:
        msg += f"\n\n❌ Не удалось доставить сообщения пользователям: {', '.join(failed)}"
    
    await update.message.reply_text(msg)
    context.user_data.pop("in_broadcast", None)
    context.user_data["just_done"] = True
    return ConversationHandler.END


async def broadcast_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Рассылка отменена.")
    context.user_data.pop("in_broadcast", None)
    return ConversationHandler.END


async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Блокирует пользователя по ID"""
    # Проверяем, что команду вызвал администратор
    if update.effective_user.id != ADMIN_ID:
        return
    
    # Проверяем, передан ли ID пользователя
    if not context.args:
        await update.message.reply_text("❌ Укажите ID пользователя: /ban <user_id>")
        return
    
    user_id = context.args[0].strip()
    
    # Проверяем корректность ID
    if not user_id.isdigit():
        await update.message.reply_text("❌ Неверный формат ID. ID должен состоять только из цифр.")
        return
    
    store = load_store()
    users = store["users"]
    
    # Если пользователя нет в базе, добавляем его
    if user_id not in users:
        users[user_id] = {
            "first_name": f"Заблокированный пользователь ({user_id})",
            "suggested_words": [],
            "stats": {"games_played": 0, "wins": 0, "losses": 0, "win_rate": 0.0},
            "banned": True,
            "notification": False  # Отключаем уведомления при бане
        }
        await update.message.reply_text(f"✅ Пользователь с ID {user_id} успешно заблокирован.")
    else:
        # Пользователь уже есть в базе, обновляем статус бана
        if users[user_id].get("banned", False):
            await update.message.reply_text(f"ℹ️ Пользователь с ID {user_id} уже заблокирован.")
        else:
            users[user_id]["banned"] = True
            users[user_id]["notification"] = False  # Отключаем уведомления при бане
            # Сбрасываем состояние guessing
            if "current_game" in users[user_id]:
                del users[user_id]["current_game"]
            await update.message.reply_text(f"✅ Пользователь {users[user_id].get('first_name', user_id)} (ID: {user_id}) успешно заблокирован.")
            try:
                await context.bot.send_message(
                    chat_id=int(user_id),
                    text="❌ Вы были заблокированы в этом боте.\n\n"
                         "Если вы считаете, что это произошло по ошибке, пожалуйста, свяжитесь с администратором."
                )
                # Сбрасываем состояние пользователя после бана
                context.user_data.clear()
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление о блокировке пользователю {user_id}: {e}")
    
    save_store(store)

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Разблокирует пользователя по ID"""
    # Проверяем, что команду вызвал администратор
    if update.effective_user.id != ADMIN_ID:
        return
    
    # Проверяем, передан ли ID пользователя
    if not context.args:
        await update.message.reply_text("❌ Укажите ID пользователя: /unban <user_id>")
        return
    
    user_id = context.args[0].strip()
    
    # Проверяем корректность ID
    if not user_id.isdigit():
        await update.message.reply_text("❌ Неверный формат ID. ID должен состоять только из цифр.")
        return
    
    store = load_store()
    users = store["users"]
    
    if user_id not in users:
        await update.message.reply_text(f"ℹ️ Пользователь с ID {user_id} не найден в базе.")
    else:
        if not users[user_id].get("banned", False):
            await update.message.reply_text(f"ℹ️ Пользователь с ID {user_id} не заблокирован.")
        else:
            users[user_id]["banned"] = False
            # Удаляем флаг уведомлений, чтобы использовать настройки по умолчанию
            if "notification" in users[user_id]:
                del users[user_id]["notification"]
            # Удаляем текущую игру, если она есть
            if "current_game" in users[user_id]:
                del users[user_id]["current_game"]
            # Устанавливаем флаг, что пользователь был разбанен
            users[user_id]["was_banned"] = True
            save_store(store)
            save_store(store)
            await update.message.reply_text(f"✅ Пользователь {users[user_id].get('first_name', user_id)} (ID: {user_id}) успешно разблокирован.")
            try:
                await context.bot.send_message(
                    chat_id=int(user_id),
                    text="✅ Вы были разблокированы в этом боте.\n\n"
                         "Теперь вы можете снова использовать все функции бота."
                )
                # Устанавливаем флаг, что пользователь был разбанен
                context.user_data["was_banned"] = True
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление о разблокировке пользователю {user_id}: {e}")


def main():
    
    token = os.getenv("BOT_TOKEN")
    if not token:
        logger.error("BOT_TOKEN не установлен")
        return

    app = (
        ApplicationBuilder()
        .token(token)
        .post_init(set_commands)
        .build()
    )
	
    # отправляем один раз при загрузке
    app.job_queue.run_once(send_activity_periodic, when=0)
    app.job_queue.run_once(send_unfinished_games, when=1)


    feedback_conv = ConversationHandler(
    entry_points=[CommandHandler("feedback", feedback_start)],
    states={
        FEEDBACK_CHOOSE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, feedback_choose),
            MessageHandler(filters.ALL, block_during_feedback),
        ],
        FEEDBACK_WORD: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, feedback_word),
            MessageHandler(filters.ALL, block_during_feedback),
        ],
    },
    fallbacks=[CommandHandler("cancel", feedback_cancel)],
    allow_reentry=True
    )
    app.add_handler(feedback_conv)
    
    
    conv = ConversationHandler(
        entry_points=[
            CommandHandler("play", ask_length),
            CommandHandler("start", start),
        ],
        states={
            ASK_LENGTH: [
                CommandHandler("feedback", feedback_not_allowed_ask),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_length),
                CommandHandler("start", ignore_ask),
                CommandHandler("play", ignore_ask),
                CommandHandler("hint", hint_not_allowed),
                CommandHandler("reset", reset),
                CommandHandler("notification", only_outside_game),
                CommandHandler("my_stats", only_outside_game),
                CommandHandler("global_stats", only_outside_game),
            ],
            GUESSING: [
                CommandHandler("feedback", feedback_not_allowed_guess),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_guess),
                CommandHandler("start", ignore_guess),
		        CommandHandler("play", ignore_guess),
                CommandHandler("hint", hint),
                CommandHandler("reset", reset),
                CommandHandler("notification", only_outside_game),
                CommandHandler("my_stats", only_outside_game),
                CommandHandler("global_stats", only_outside_game),
            ],
        },
        fallbacks=[
            CommandHandler("reset", reset),
       ],
    )
    app.add_handler(conv)

    # 1) просмотр и подтверждение предложений
    app.add_handler(CommandHandler("suggestions_view", suggestions_view))
    app.add_handler(CommandHandler("suggestions_approve", suggestions_approve))

    # 2) удаление через ConversationHandler
    remove_conv = ConversationHandler(
        entry_points=[CommandHandler("suggestions_remove", suggestions_remove_start)],
        states={
            REMOVE_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, suggestions_remove_process),
            ],
        },
        fallbacks=[CommandHandler("cancel", feedback_cancel)],
        allow_reentry=True,
    )
    app.add_handler(remove_conv)

    # 3) перемещение через ConversationHandler
    move_conv = ConversationHandler(
        entry_points=[CommandHandler("suggestions_move", suggestions_move_start)],
        states={
            REMOVE_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, suggestions_move_process),
            ],
        },
        fallbacks=[CommandHandler("cancel", feedback_cancel)],
        allow_reentry=True,
    )
    app.add_handler(move_conv)

    broadcast_conv = ConversationHandler(
    entry_points=[CommandHandler("broadcast", broadcast_start)],
    states={
        BROADCAST: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_send),
        ],
    },
    fallbacks=[CommandHandler("broadcast_cancel", broadcast_cancel)],
    allow_reentry=True,
    )
    app.add_handler(broadcast_conv)

    app.add_handler(
    MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_text),
    group=99
    )

    # Глобальные
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("hint", hint_not_allowed))
    app.add_handler(CommandHandler("reset", reset_global))
    app.add_handler(CommandHandler("notification", notification_toggle))
    app.add_handler(CommandHandler("my_stats", my_stats))
    app.add_handler(CommandHandler("global_stats", global_stats))
    app.add_handler(CommandHandler("dict_file", dict_file))
    app.add_handler(CommandHandler("dump_activity", dump_activity))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))
    
    # Обработчик для кнопки предложения слова в белый список
    app.add_handler(CallbackQueryHandler(suggest_white_callback, pattern=r'^suggest_white:'))

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
