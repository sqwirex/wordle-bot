import logging
from telegram import Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
)

from src.storage.store import load_store
from src.main.config import ADMIN_ID
from src.main.constants import BROADCAST

logger = logging.getLogger(__name__)

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


