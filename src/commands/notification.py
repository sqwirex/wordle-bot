from telegram import Update
from telegram.ext import ContextTypes

from src.storage.store import load_store, save_store, clear_notification_flag
from src.decorators.checkban import check_ban_status
from src.languages.russian import MSG_WAKE_UP, MSG_NOTIFICATIONS_STATE, STATE_OFF, STATE_ON

async def send_unfinished_games(context: ContextTypes.DEFAULT_TYPE):
    """
    Sends a reminder to users who have notifications enabled for unfinished games,
    but only if the user hasn't responded since the last reminder.
    After sending, sets a flag to prevent further notifications until the user plays or sends a message.
    """
    store = load_store()

    for uid, udata in store["users"].items():
        # notifications are disabled
        if not udata.get("notify_on_wakeup", True):
            continue
        # user has no unfinished game
        if "current_game" not in udata:
            continue
        # if already sent and user hasn't responded — skip
        if udata.get("notified", False):
            continue

        # Send reminder
        cg = udata["current_game"]
        length = len(cg["secret"])
        attempts = cg["attempts"]
        text = MSG_WAKE_UP.format(length=length, attempts=attempts)
        try:
            await context.bot.send_message(chat_id=int(uid), text=text)
        except Exception as e:
            logger.warning(f"Не смогли напомнить {uid}: {e}")
            continue

        # Remember sending time
        udata["notified"] = True
        save_store(store)


@check_ban_status
async def notification_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    store = load_store()
    user = store["users"].setdefault(uid, {"stats": {...}})
    clear_notification_flag(str(update.effective_user.id))
    # Toggle
    current = user.get("notify_on_wakeup", True)
    user["notify_on_wakeup"] = not current
    save_store(store)
    state = STATE_ON if not current else STATE_OFF
    await update.message.reply_text(
        MSG_NOTIFICATIONS_STATE.format(state=state)
    )