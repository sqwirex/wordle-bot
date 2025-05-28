from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
)

from storage import load_store, save_store, load_suggestions, save_suggestions, clear_notification_flag
from commands import check_ban_status
from game import WORDLIST, normalize
from ..config import SUGGESTIONS_FILE
from ..constants import FEEDBACK_CHOOSE, FEEDBACK_WORD, GUESSING, ASK_LENGTH


@check_ban_status
async def feedback_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # запретим во время игры
    store = load_store()
    u = store["users"].get(str(update.effective_user.id), {})
    clear_notification_flag(str(update.effective_user.id))
    if "current_game" in u or context.user_data.get("game_active"):
        await update.message.reply_text(
            "Нельзя отправлять фидбек пока идет игра или после перезапуска.\n"
            "Сначала продолжи играть /play, а потом либо закончи игру, либо сбрось /reset",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END

    # предлагаем выбрать список
    keyboard = [
        ["Черный список", "Белый список"],
        ["Отмена"]
    ]
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Куда добавить слово?", reply_markup=markup)

    # запомним текущее состояние
    context.user_data["feedback_state"] = FEEDBACK_CHOOSE
    context.user_data["in_feedback"] = True
    return FEEDBACK_CHOOSE


@check_ban_status
async def feedback_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "Отмена":
        await update.message.reply_text("Отменено.", reply_markup=ReplyKeyboardRemove())
        context.user_data.pop("in_feedback", None)
        context.user_data["just_done"] = True
        return ConversationHandler.END

    if text not in ("Черный список", "Белый список"):
        await update.message.reply_text("Пожалуйста, нажимайте одну из кнопок.")
        return FEEDBACK_CHOOSE

    # куда кладем
    context.user_data["fb_target"] = "black" if text == "Черный список" else "white"
    # убираем клавиатуру и спрашиваем слово
    await update.message.reply_text(
        "Введите слово для предложения:", reply_markup=ReplyKeyboardRemove()
    )

    context.user_data["feedback_state"] = FEEDBACK_WORD
    return FEEDBACK_WORD


@check_ban_status
async def feedback_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    word = normalize(update.message.text)
    target = context.user_data["fb_target"]

    if SUGGESTIONS_FILE.exists() and SUGGESTIONS_FILE.stat().st_size >= 1_000_000:
        await update.message.reply_text(
            "Прости, сейчас нельзя добавить новое слово — файл предложений уже слишком большой."
        )
        context.user_data.pop("in_feedback", None)
        context.user_data["just_done"] = True
        return ConversationHandler.END

    if " " in word:
        await update.message.reply_text("Пожалуйста, введите слово без пробелов.")
        return FEEDBACK_WORD

    suggestions = load_suggestions()

    # Черный список: добавляем, только если слово есть в словаре
    if target == "black":
        if word in WORDLIST:
            suggestions["black"].add(word)
            save_suggestions(suggestions)
            
            # Добавляем слово в профиль пользователя
            store = load_store()
            user_id = str(update.effective_user.id)
            if user_id not in store["users"]:
                store["users"][user_id] = {}
            if "suggested_words" not in store["users"][user_id]:
                store["users"][user_id]["suggested_words"] = []
            if word not in store["users"][user_id]["suggested_words"]:
                store["users"][user_id]["suggested_words"].append(word)
                save_store(store)
                
            resp = "Спасибо, добавил в предложения для чёрного списка."
        else:
            resp = "Нельзя: слово должно быть в основном словаре."

    # Белый список: добавляем, только если слова нет в словаре и длина 4–11
    else:
        if 4 <= len(word) <= 11 and word not in WORDLIST:
            suggestions["white"].add(word)
            save_suggestions(suggestions)
            
            # Добавляем слово в профиль пользователя
            store = load_store()
            user_id = str(update.effective_user.id)
            if user_id not in store["users"]:
                store["users"][user_id] = {}
            if "suggested_words" not in store["users"][user_id]:
                store["users"][user_id]["suggested_words"] = []
            if word not in store["users"][user_id]["suggested_words"]:
                store["users"][user_id]["suggested_words"].append(word)
                save_store(store)
                
            resp = "Спасибо, добавил в предложения для белого списка."
        else:
            if word in WORDLIST:
                resp = "Нельзя: такое слово уже есть в основном словаре."
            elif not (4 <= len(word) <= 11):
                resp = "Нельзя: длина слова должна быть от 4 до 11 символов."
            else:
                resp = "Нельзя: слово должно быть вне основного словаря и из 4–11 букв."

    await update.message.reply_text(resp)
    context.user_data.pop("in_feedback", None)
    context.user_data["just_done"] = True
    return ConversationHandler.END


@check_ban_status
async def feedback_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    await update.message.reply_text("Отменено.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


@check_ban_status
async def block_during_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # любой посторонний ввод заглушаем
    await update.message.reply_text(
        "Сейчас идет ввод для фидбека, нельзя использовать команды."
    )
    # возвращаемся в текущее состояние
    return context.user_data.get("feedback_state", FEEDBACK_CHOOSE)


@check_ban_status
async def feedback_not_allowed_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Нельзя отправлять фидбек пока вы выбираете длину слова. "
        "Сначала укажите длину (4–11)."
    )
    return ASK_LENGTH


@check_ban_status
async def feedback_not_allowed_guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Нельзя отправлять фидбек во время игры. "
        "Сначала закончите игру или /reset."
    )
    return GUESSING