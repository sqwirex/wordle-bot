import os
import json
import logging
from io import BytesIO
from collections import Counter
from telegram import Update, BotCommand, BotCommandScopeChat, InputFile
from telegram.ext import ContextTypes

from src.storage.store import load_store, save_store
from src.main.config import ADMIN_ID, BASE_FILE, USER_FILE

logger = logging.getLogger(__name__)

async def set_commands(app):
    
    await app.bot.set_my_commands(
        [
            BotCommand("start", "Показать приветствие"),
            BotCommand("play", "Начать новую игру"),
            BotCommand("hint", "Подсказка"),
            BotCommand("reset", "Сбросить игру"),
            BotCommand("notification", "Включить/Отключить уведомления"),
            BotCommand("my_stats", "Ваша статистика"),
            BotCommand("global_stats", "Глобальная статистика"),
            BotCommand("feedback", "Жалоба на слово"),
            BotCommand("dict_file", "Посмотреть словарь"),
            BotCommand("dump_activity", "Скачать user_activity.json"),
            BotCommand("suggestions_view", "Посмотреть фидбек юзеров"),
            BotCommand("suggestions_move", "Переместить слово из белого списка в add список"),
            BotCommand("suggestions_remove", "Удалить что-то из фидбека"),
            BotCommand("suggestions_approve", "Внести изменения в словарь"),
            BotCommand("broadcast", "Отправить сообщение всем юзерам"),
            BotCommand("broadcast_cancel", "Отменить отправку"),
            BotCommand("ban", "Заблокировать пользователя"),
            BotCommand("unban", "Разблокировать пользователя"),
        ],
        scope=BotCommandScopeChat(chat_id=ADMIN_ID)
    )

# Sends user_activity.json to admin on startup
async def send_activity_periodic(context: ContextTypes.DEFAULT_TYPE):
    ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
    activity_path = USER_FILE
    if not activity_path.exists():
        return

    with activity_path.open("rb") as f:
        await context.bot.send_document(
            chat_id=ADMIN_ID,
            document=InputFile(f, filename="user_activity.json"),
            caption="📁 user_activity.json"
        )


async def dict_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    # Read fresh dictionary from base_words.json
    with BASE_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
        main_words = data.get("main", [])
        additional_words = data.get("additional", [])

    total_main = len(main_words)
    total_additional = len(additional_words)
    total = total_main + total_additional

    # Count words of each length (4-11)
    main_length_counts = Counter(len(w) for w in main_words)
    additional_length_counts = Counter(len(w) for w in additional_words)

    stats_lines = []
    for length in range(4, 12):
        main_count = main_length_counts.get(length, 0)
        additional_count = additional_length_counts.get(length, 0)
        stats_lines.append(f"{length} букв: {main_count} (main) + {additional_count} (additional) = {main_count + additional_count}")

    stats_text = "\n".join(stats_lines)

    # Pack lists into file
    data = "=== Main Words ===\n" + "\n".join(main_words) + "\n\n=== Additional Words ===\n" + "\n".join(additional_words)
    bio = BytesIO(data.encode("utf-8"))
    bio.name = "wordlist.txt"

    # Send document with general and detailed statistics
    await update.message.reply_document(
        document=bio,
        filename="wordlist.txt",
        caption=(
            f"📚 В словаре всего {total} слов:\n"
            f"• {total_main} в основном списке\n"
            f"• {total_additional} в дополнительном списке\n\n"
            f"🔢 Распределение по длине:\n{stats_text}"
        )
    )


async def dump_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    path = USER_FILE
    if not path.exists():
        return await update.message.reply_text("Файл user_activity.json не найден.")

    with path.open("rb") as f:
        await update.message.reply_document(
            document=InputFile(f, filename=path.name),
            caption="📁 user_activity.json"
        )


async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Ban user by ID
    if update.effective_user.id != ADMIN_ID:
        return
    
    # Check if user ID is provided
    if not context.args:
        await update.message.reply_text("❌ Укажите ID пользователя: /ban <user_id>")
        return
    
    user_id = context.args[0].strip()
    
    # Check ID format
    if not user_id.isdigit():
        await update.message.reply_text("❌ Неверный формат ID. ID должен состоять только из цифр.")
        return
    
    store = load_store()
    users = store["users"]
    
    # If user is not in database, add them
    if user_id not in users:
        users[user_id] = {
            "first_name": f"Заблокированный пользователь ({user_id})",
            "suggested_words": [],
            "stats": {"games_played": 0, "wins": 0, "losses": 0, "win_rate": 0.0},
            "banned": True,
            "notification": False  # Disable notifications on ban
        }
        await update.message.reply_text(f"✅ Пользователь с ID {user_id} успешно заблокирован.")
    else:
        # If user exists in database, update ban status
        if users[user_id].get("banned", False):
            await update.message.reply_text(f"ℹ️ Пользователь с ID {user_id} уже заблокирован.")
        else:
            users[user_id]["banned"] = True
            users[user_id]["notification"] = False  # Disable notifications on ban
            # Reset guessing state
            if "current_game" in users[user_id]:
                del users[user_id]["current_game"]
            await update.message.reply_text(f"✅ Пользователь {users[user_id].get('first_name', user_id)} (ID: {user_id}) успешно заблокирован.")
            try:
                await context.bot.send_message(
                    chat_id=int(user_id),
                    text="❌ Вы были заблокированы в этом боте.\n\n"
                         "Если вы считаете, что это произошло по ошибке, пожалуйста, свяжитесь с администратором."
                )
                # Reset user state after ban
                context.user_data.clear()
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление о блокировке пользователю {user_id}: {e}")
    
    save_store(store)


async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Unban user by ID
    if update.effective_user.id != ADMIN_ID:
        return
    
    # Check if user ID is provided
    if not context.args:
        await update.message.reply_text("❌ Укажите ID пользователя: /unban <user_id>")
        return
    
    user_id = context.args[0].strip()
    
    # Check ID format
    if not user_id.isdigit():
        await update.message.reply_text("❌ Неверный формат ID. ID должен состоять только из цифр.")
        return
    
    store = load_store()
    users = store["users"]
    
    if user_id not in users:
        await update.message.reply_text(f"ℹ️ Пользователь с ID {user_id} не найден в базе.")
    else:
        if not users[user_id].get("banned", False):
            await update.message.reply_text(f"ℹ️ Пользователь с ID {user_id} не заблокирован.")
        else:
            users[user_id]["banned"] = False
            # Remove notification flag to use default settings
            if "notification" in users[user_id]:
                del users[user_id]["notification"]
            # Remove current game if exists
            if "current_game" in users[user_id]:
                del users[user_id]["current_game"]
            # Set flag that user was unbanned
            users[user_id]["was_banned"] = True
            save_store(store)
            save_store(store)
            await update.message.reply_text(f"✅ Пользователь {users[user_id].get('first_name', user_id)} (ID: {user_id}) успешно разблокирован.")
            try:
                await context.bot.send_message(
                    chat_id=int(user_id),
                    text="✅ Вы были разблокированы в этом боте.\n\n"
                         "Теперь вы можете снова использовать все функции бота."
                )
                # Set flag that user was unbanned
                context.user_data["was_banned"] = True
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление о разблокировке пользователю {user_id}: {e}")