import json
from datetime import datetime
from zoneinfo import ZoneInfo
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import ContextTypes, ConversationHandler

from src.storage.store import load_store, save_store, load_suggestions, save_suggestions
from src.decorators.checkban import check_ban_status
from src.game.logic import WORDLIST, normalize
from src.game.render import render_full_board_with_keyboard
from src.main.config import BASE_FILE
from src.main.constants import GUESSING
from src.languages.russian import (SPACE_ATTENTION, MSG_LENGTH_VALIDATE, 
                                   SUGGESTION_SUGGESTED_NOW, SUGGESTED_ADD_WORD, 
                                   MSG_NOT_FOUND, MSG_ATTEMPT, pluralize_attempt,
                                   MSG_WIN, MSG_GAME_OVER, START_AND_PLAY_NOT_WORK,
                                   MSG_SUGGESTION_ADDED
) 

@check_ban_status
async def handle_guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    store   = load_store()
    user    = store["users"].setdefault(user_id, {
        "first_name": update.effective_user.first_name,
        "stats": {"games_played": 0, "wins": 0, "losses": 0}
    })

    # Обновляем время последнего визита
    user["last_seen_msk"] = datetime.now(ZoneInfo("Europe/Moscow")).isoformat()

    cg     = user["current_game"]
    guess = normalize(update.message.text)
    secret = cg["secret"]
    length = len(secret)

    # Нормализуем слово для проверки (приводим к нижний регистр и заменяем ё на е)
    normalized_guess = normalize(guess)
    
    # Проверяем на пробелы до проверки длины
    if " " in guess:
        await update.message.reply_text(SPACE_ATTENTION)
        return GUESSING
    
    # Валидация длины
    if len(guess) != length:
        await update.message.reply_text(
            MSG_LENGTH_VALIDATE.format(length=length)
        )
        return GUESSING
    
    # Проверяем, не предлагал ли пользователь это слово ранее
    user_id = str(update.effective_user.id)
    user = store["users"].get(user_id, {})
    suggested_words = user.get("suggested_words", [])
    
    if normalized_guess in suggested_words and normalized_guess not in WORDLIST:
        await update.message.reply_text(SUGGESTION_SUGGESTED_NOW)
        return GUESSING
    
    # Проверяем слово в основном и дополнительном списках
    with BASE_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
        main_words = set(data.get("main", []))
        additional_words = set(data.get("additional", []))
        all_words = main_words | additional_words
    
    if normalized_guess not in all_words:
        # Предлагаем добавить слово в белый список
        keyboard = [
            [
                InlineKeyboardButton(
                    SUGGESTED_ADD_WORD,
                    callback_data=f"suggest_white:{guess}"
                )
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            MSG_NOT_FOUND.format(guess=normalized_guess),
            reply_markup=reply_markup
        )
        return GUESSING

    if " " in guess:
        await update.message.reply_text(SPACE_ATTENTION)
        return GUESSING

    # Сохраняем ход
    cg["guesses"].append(guess)
    cg["attempts"] += 1
    save_store(store)

    # Рендерим доску из 6 строк + мини-клавиатуру снизу.
    # Клавиатура будет крупнее для слов ≥8 букв, чуть меньше для 7 и еще меньше для 4–5.
    img_buf = render_full_board_with_keyboard(
        guesses=cg["guesses"],
        secret=secret,
        total_rows=6,
        max_width_px=1080
    )
    await update.message.reply_photo(
        photo=InputFile(img_buf, filename="wordle_board.png"),
        caption=MSG_ATTEMPT.format(attempt=cg['attempts'])
    )

    # —— Победа ——
    if guess == secret:
        stats = user["stats"]
        stats["games_played"] += 1
        stats["wins"] += 1
        stats["win_rate"] = stats["wins"] / stats["games_played"]

        g = store["global"]
        g["total_games"] += 1
        g["total_wins"] += 1
        g["win_rate"] = g["total_wins"] / g["total_games"]

        top_uid, top_data = max(
            store["users"].items(),
            key=lambda kv: kv[1]["stats"]["wins"]
        )
        store["global"]["top_player"] = {
            "user_id":  top_uid,
            "username": top_data.get("username") or top_data.get("first_name", ""),
            "wins":     top_data["stats"]["wins"]
        }

        attempts = cg['attempts']
        attempt_word = pluralize_attempt(attempts)

        await update.message.reply_text(
            MSG_WIN.format(attempts=attempts, attempt_word=attempt_word)
        )

        del user["current_game"]
        context.user_data.pop("game_active", None)
        context.user_data["just_done"] = True
        save_store(store)
        return ConversationHandler.END

    # —— Поражение ——
    if cg["attempts"] >= 6:
        stats = user["stats"]
        stats["games_played"] += 1
        stats["losses"] += 1
        stats["win_rate"] = stats["wins"] / stats["games_played"]

        g = store["global"]
        g["total_games"] += 1
        g["total_losses"] += 1
        g["win_rate"] = g["total_wins"] / g["total_games"]

        await update.message.reply_text(
            MSG_GAME_OVER.format(secret=secret)
        )

        del user["current_game"]
        context.user_data.pop("game_active", None)
        context.user_data["just_done"] = True
        save_store(store)
        return ConversationHandler.END

    # Игра продолжается
    return GUESSING


@check_ban_status
async def ignore_guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(START_AND_PLAY_NOT_WORK)
    return GUESSING


@check_ban_status
async def suggest_white_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатия на кнопку предложения слова в белый список"""
    query = update.callback_query
    await query.answer()
    
    # Извлекаем слово из callback_data и нормализуем его
    word = normalize(query.data.split(':', 1)[1])
    user_id = str(update.effective_user.id)
    
    # Загружаем текущие предложения и основной словарь
    current_suggestions = load_suggestions()
    with BASE_FILE.open("r", encoding="utf-8") as f:
        base_words = set(json.load(f))
    
    # Загружаем данные пользователя
    store = load_store()
    user = store["users"].get(user_id, {})
    
    # Добавляем слово в предложения для белого списка, если его там еще нет
    if word not in current_suggestions["white"] and word not in base_words:
        current_suggestions["white"].add(word)
        save_suggestions(current_suggestions)
        # Обновляем глобальную переменную
        global suggestions
        suggestions = current_suggestions
    
    # Добавляем слово в список предложенных пользователем, если его там еще нет
    if "suggested_words" not in user:
        user["suggested_words"] = []
    
    if word not in user["suggested_words"]:
        user["suggested_words"].append(word)
        save_store(store)
    
    # Обновляем сообщение, убирая кнопку
    await query.edit_message_text(
        MSG_SUGGESTION_ADDED.format(word=word)
    )
    
    return GUESSING