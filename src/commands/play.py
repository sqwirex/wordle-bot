import random
from telegram import Update
from telegram.ext import ContextTypes

from storage import load_store, save_store, clear_notification_flag, update_user_activity
from ..constants import ASK_LENGTH, GUESSING
from game import WORDLIST
from commands import check_ban_status

# ...existing code...
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
async def ignore_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Команды /start и /play не работают во время игры — сначала /reset.")
    return ASK_LENGTH