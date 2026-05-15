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
                                   MSG_SUGGESTION_ADDED, replace_yo
) 

@check_ban_status
async def handle_guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    store   = load_store()
    user    = store["users"].setdefault(user_id, {
        "first_name": update.effective_user.first_name,
        "stats": {"games_played": 0, "wins": 0, "losses": 0}
    })

    # Update last visit time
    user["last_seen_msk"] = datetime.now(ZoneInfo("Europe/Moscow")).isoformat()

    cg     = user["current_game"]
    guess = normalize(replace_yo(update.message.text))
    secret = cg["secret"]
    length = len(secret)

    # Normalize word for checking
    normalized_guess = normalize(replace_yo(guess))
    
    # Check for spaces before length validation
    if " " in guess:
        await update.message.reply_text(SPACE_ATTENTION)
        return GUESSING
    
    # Length validation
    if len(guess) != length:
        await update.message.reply_text(
            MSG_LENGTH_VALIDATE.format(length=length)
        )
        return GUESSING
    
    # Check if user has suggested this word before
    user_id = str(update.effective_user.id)
    user = store["users"].get(user_id, {})
    suggested_words = user.get("suggested_words", [])
    
    if normalized_guess in suggested_words and normalized_guess not in WORDLIST:
        await update.message.reply_text(SUGGESTION_SUGGESTED_NOW)
        return GUESSING
    
    # Check word in main and additional lists
    with BASE_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
        main_words = set(data.get("main", []))
        additional_words = set(data.get("additional", []))
        all_words = main_words | additional_words
    
    if normalized_guess not in all_words:
        # Suggest adding word to whitelist
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

    # Save the move
    cg["guesses"].append(guess)
    cg["attempts"] += 1
    save_store(store)

    # Render board with 6 rows + mini-keyboard at the bottom
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

    # —— Victory ——
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

    # —— Defeat ——
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

    # Game continues
    return GUESSING


@check_ban_status
async def ignore_guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(START_AND_PLAY_NOT_WORK)
    return GUESSING


@check_ban_status
async def suggest_white_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Handler for clicking the button to suggest a word to the whitelist
    query = update.callback_query
    await query.answer()
    
    # Extract word from callback_data and normalize it
    word = normalize(replace_yo(query.data.split(':', 1)[1]))
    user_id = str(update.effective_user.id)
    
    # Load current suggestions and main dictionary
    current_suggestions = load_suggestions()
    with BASE_FILE.open("r", encoding="utf-8") as f:
        base_words = set(json.load(f))
    
    # Load user data
    store = load_store()
    user = store["users"].get(user_id, {})
    
    # Add word to whitelist suggestions if it's not there yet
    if word not in current_suggestions["white"] and word not in base_words:
        current_suggestions["white"].add(word)
        save_suggestions(current_suggestions)
        # Update global variable
        global suggestions
        suggestions = current_suggestions
    
    # Add word to user's suggested words list if it's not there yet
    if "suggested_words" not in user:
        user["suggested_words"] = []
    
    if word not in user["suggested_words"]:
        user["suggested_words"].append(word)
        save_store(store)
    
    # Update message, removing the button
    await query.edit_message_text(
        MSG_SUGGESTION_ADDED.format(word=word)
    )
    
    return GUESSING