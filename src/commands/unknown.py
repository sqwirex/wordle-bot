from telegram import Update
from telegram.ext import ContextTypes

from src.decorators.checkban import check_ban_status
from src.storage.store import clear_notification_flag
from src.languages.russian import MSG_UNKNOWN

@check_ban_status
async def unknown_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_notification_flag(str(update.effective_user.id))
    if context.user_data.get("game_active") or context.user_data.get("in_feedback") or context.user_data.get("in_remove"):
        return
    if context.user_data.pop("just_done", False):
        return
    await update.message.reply_text(MSG_UNKNOWN)