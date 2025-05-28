from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
import logging

from storage import load_store, save_store

logger = logging.getLogger(__name__)

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