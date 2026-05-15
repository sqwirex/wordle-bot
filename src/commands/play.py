import random
from telegram import Update
from telegram.ext import ContextTypes

from src.storage.store import load_store, save_store, clear_notification_flag, update_user_activity
from src.main.constants import ASK_LENGTH, GUESSING
from src.game.logic import WORDLIST
from src.decorators.checkban import check_ban_status
from src.languages.russian import (GAME_CONTINUE, LETTERS_QUESTION, 
                                   NOT_FIND_WORDS, NEED_FIX_LETTERS, 
                                   START_AND_PLAY_NOT_WORK, MSG_GAME_START
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
        context.user_data.update({
            "secret": cg["secret"],
            "length": len(cg["secret"]),
            "attempts": cg["attempts"],
            "guesses": cg["guesses"],
        })
        await update.message.reply_text(
            GAME_CONTINUE.format(
                letters=len(cg['secret']),
                attempt=cg['attempts']
            )
        )
        return GUESSING
    
    await update.message.reply_text(LETTERS_QUESTION)
    return ASK_LENGTH


@check_ban_status
async def receive_length(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_user_activity(update.effective_user)
    text = update.message.text.strip()
    if not text.isdigit() or not 4 <= int(text) <= 11:
        await update.message.reply_text(NEED_FIX_LETTERS)
        return ASK_LENGTH

    length = int(text)
    candidates = [w for w in WORDLIST if len(w) == length]
    if not candidates:
        await update.message.reply_text(NOT_FIND_WORDS)
        return ASK_LENGTH

    secret = random.choice(candidates)
    
    store = load_store()
    u = store["users"].setdefault(str(update.effective_user.id), {"stats": {"games_played":0,"wins":0,"losses":0}})
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
        MSG_GAME_START.format(length=length)
    )
    
    return GUESSING


@check_ban_status
async def ignore_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(START_AND_PLAY_NOT_WORK)
    return ASK_LENGTH