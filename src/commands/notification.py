import logging
from telegram import Update
from telegram.ext import ContextTypes

from src.storage.store import load_store, save_store, clear_notification_flag
from src.decorators.checkban import check_ban_status
from src.languages.russian import MSG_WAKE_UP, MSG_NOTIFICATIONS_STATE, STATE_OFF, STATE_ON

logger = logging.getLogger(__name__)

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
        text = MSG_WAKE_UP.format(length=length, attempts=attempts)
        try:
            await context.bot.send_message(chat_id=int(uid), text=text)
        except Exception as e:
            logger.warning(f"Не смогли напомнить {uid}: {e}")
            continue

        # Запоминаем время отправки
        udata["notified"] = True
        save_store(store)


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
    state = STATE_ON if not current else STATE_OFF
    await update.message.reply_text(
        MSG_NOTIFICATIONS_STATE.format(state=state)
    )