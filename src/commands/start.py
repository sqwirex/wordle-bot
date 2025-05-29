from telegram import Update
from telegram.ext import ContextTypes

from src.storage.store import load_store, update_user_activity, clear_notification_flag
from src.decorators.checkban import check_ban_status
from src.main.constants import GUESSING
from src.languages.russian import START_MESSENGE, GAME_CONTINUE

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
            GAME_CONTINUE.format(
                letters=len(cg['secret']),
                attempt=cg['attempts']
            )
        )
        return GUESSING

    
    await update.message.reply_text(START_MESSENGE)