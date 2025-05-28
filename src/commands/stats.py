from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from ..storage.store import load_store, update_user_activity, clear_notification_flag
from ..commands.middlewares import check_ban_status

@check_ban_status
async def my_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает личную статистику — только вне игры."""
    update_user_activity(update.effective_user)
    store = load_store()
    uid = str(update.effective_user.id)
    user = store["users"].get(uid)
    if not user or "current_game" in user:
        await update.message.reply_text("Эту команду можно использовать только вне игры.")
        return
    s = user.get("stats", {})
    await update.message.reply_text(
        "```"
        f"🧑 Ваши результаты:\n\n"
        f"🎲 Всего игр: {s.get('games_played',0)}\n"
        f"🏆 Побед: {s.get('wins',0)}\n"
        f"💔 Поражений: {s.get('losses',0)}\n"
        f"📊 Процент: {s.get('win_rate',0.0)*100:.2f}%"
        "```",
        parse_mode="Markdown"
    )


@check_ban_status
async def global_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_user_activity(update.effective_user)
    """Показывает глобальную статистику — только вне игры."""
    store = load_store()
    g = store["global"]
    # если во время партии — запрет
    uid = str(update.effective_user.id)
    user = store["users"].get(uid)
    if user and "current_game" in user:
        await update.message.reply_text("Эту команду можно использовать только вне игры.")
        return
    
    tp = g.get("top_player", {})
    if tp:
        top_line = f"Сильнейший: @{tp['username']} ({tp['wins']} побед)\n\n"
    else:
        top_line = ""
    
    await update.message.reply_text(
        "```"
        f"🌐 Глобальная статистика:\n\n"
        f"🎲 Всего игр: {g['total_games']}\n"
        f"🏆 Побед: {g['total_wins']}\n"
        f"💔 Поражений: {g['total_losses']}\n"
        f"📊 Процент: {g['win_rate']*100:.2f}%\n\n"
        f"{top_line}"
        "```",
        parse_mode="Markdown"
    )


@check_ban_status
async def only_outside_game(update, context):
    clear_notification_flag(str(update.effective_user.id))
    await update.message.reply_text("Эту команду можно использовать только вне игры.")
    # вернем то состояние, в котором сейчас юзер:
    return context.user_data.get("state", ConversationHandler.END)