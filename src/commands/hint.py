import random
from collections import Counter
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from src.storage.store import load_store, save_store, clear_notification_flag
from src.decorators.checkban import check_ban_status
from src.game.logic import WORDLIST
from src.main.constants import GUESSING, ASK_LENGTH
from src.languages.russian import ONLY_IN_GAME, HINT_USED, HINT_NOT_FIND, MSG_HINT

@check_ban_status
async def hint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    store = load_store()
    user_entry = store["users"].setdefault(user_id, {
        "stats": {"games_played": 0, "wins": 0, "losses": 0}
    })

    if "current_game" not in user_entry:
        await update.message.reply_text(ONLY_IN_GAME)
        return ConversationHandler.END

    cg = user_entry["current_game"]

    # If hint is already used — don't give another one
    if cg.get("hint_used", False):
        await update.message.reply_text(HINT_USED)
        return GUESSING

    secret = cg["secret"]
    length = len(secret)

    # How many letters to hint
    hint_counts = {4:1, 5:2, 6:2, 7:3, 8:3, 9:4, 10:4, 11:5}
    num_letters = hint_counts.get(length, 1)

    secret_counter = Counter(secret)

    # Select candidates
    candidates = []
    for w in WORDLIST:
        if len(w) != length or w == secret:
            continue
        w_counter = Counter(w)
        common = sum(min(secret_counter[ch], w_counter[ch]) for ch in w_counter)
        if common == num_letters:
            candidates.append(w)

    if not candidates:
        await update.message.reply_text(HINT_NOT_FIND)
        return GUESSING

    hint_word = random.choice(candidates)

    # Mark in JSON that hint was used
    cg["hint_used"] = True
    save_store(store)

    await update.message.reply_text(
        MSG_HINT.format(hint_word=hint_word)
    )
    return GUESSING


@check_ban_status
async def hint_not_allowed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Message shown when /hint is called outside of a game.
    clear_notification_flag(str(update.effective_user.id))
    await update.message.reply_text(ONLY_IN_GAME)
    # if we're currently choosing length — stay in ASK_LENGTH, otherwise in GUESSING
    return context.user_data.get("state", ASK_LENGTH)