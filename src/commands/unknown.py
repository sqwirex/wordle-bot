from telegram import Update
from telegram.ext import ContextTypes

from decorators.checkban import check_ban_status
from storage.store import clear_notification_flag

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