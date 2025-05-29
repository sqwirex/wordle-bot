from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from src.storage.store import load_store, update_user_activity, clear_notification_flag
from src.decorators.checkban import check_ban_status
from src.languages.russian import ONLY_OUTSIDE_GAME, MSG_STATS, MSG_GLOBAL_STATS, MSG_TOP_PLAYER

@check_ban_status
async def my_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_user_activity(update.effective_user)
    store = load_store()
    uid = str(update.effective_user.id)
    user = store["users"].get(uid)
    if not user or "current_game" in user:
        await update.message.reply_text(ONLY_OUTSIDE_GAME)
        return
    s = user.get("stats", {})
    await update.message.reply_text(
    MSG_STATS.format(
        games_played=s.get('games_played', 0),
        wins=s.get('wins', 0),
        losses=s.get('losses', 0),
        win_rate=s.get('win_rate', 0.0) * 100
    ),
    parse_mode="Markdown"
)


@check_ban_status
async def global_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_user_activity(update.effective_user)
    store = load_store()
    g = store["global"]
    # если во время партии — запрет
    uid = str(update.effective_user.id)
    user = store["users"].get(uid)
    if user and "current_game" in user:
        await update.message.reply_text(ONLY_OUTSIDE_GAME)
        return
    
    tp = g.get("top_player", {})
    if tp:
        top_line = MSG_TOP_PLAYER.format(
            username=tp['username'],
            wins=tp['wins']
        )
    else:
        top_line = ""

    await update.message.reply_text(
        MSG_GLOBAL_STATS.format(
            total_games=g.get('total_games', 0),
            total_wins=g.get('total_wins', 0),
            total_losses=g.get('total_losses', 0),
            win_rate=g.get('win_rate', 0.0) * 100,
            top_line=top_line
        ),
        parse_mode="Markdown"
    )


@check_ban_status
async def only_outside_game(update, context):
    clear_notification_flag(str(update.effective_user.id))
    await update.message.reply_text(ONLY_OUTSIDE_GAME)
    # вернем то состояние, в котором сейчас юзер:
    return context.user_data.get("state", ConversationHandler.END)