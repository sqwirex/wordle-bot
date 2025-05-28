from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from ..storage.store import load_store, save_store, clear_notification_flag, update_user_activity
from .middlewares import check_ban_status

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