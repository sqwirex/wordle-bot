from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
)

from src.storage.store import load_store, save_store, load_suggestions, save_suggestions, clear_notification_flag
from src.decorators.checkban import check_ban_status
from src.game.logic import WORDLIST, normalize
from src.main.config import SUGGESTIONS_FILE
from src.main.constants import FEEDBACK_CHOOSE, FEEDBACK_WORD, GUESSING, ASK_LENGTH
from src.languages.russian import (FB_ONLY_OUTSIDE_GAME, BLACK_LIST_BUTTON, WHITE_LIST_BUTTON,
                                   CANCEL_BUTTON, ASK_LIST_QUESTION, MSG_CANCELED, MSG_CLICK_BUTTON,
                                   MSG_TYPE_TEST, SPACE_ATTENTION, MSG_FILE_SO_BIG, MSG_ADD_BLACK_LIST,
                                   MSG_DENIED_BLACK_LIST, MSG_ADD_WHITE_LIST, MSG_DENIED_WHITE_LIST_ALREADY_HAVE, 
                                   MSG_DENIED_WHITE_LIST_LENGHT, MSG_NOT_USE_COMMANDS_WHILE_FB, replace_yo

)


@check_ban_status
async def feedback_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    store = load_store()
    u = store["users"].get(str(update.effective_user.id), {})
    clear_notification_flag(str(update.effective_user.id))
    if "current_game" in u or context.user_data.get("game_active"):
        await update.message.reply_text(
            FB_ONLY_OUTSIDE_GAME,
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END

    # offer to choose a list
    keyboard = [
        [BLACK_LIST_BUTTON, WHITE_LIST_BUTTON],
        [CANCEL_BUTTON]
    ]
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text(ASK_LIST_QUESTION, reply_markup=markup)

    # remember current state
    context.user_data["feedback_state"] = FEEDBACK_CHOOSE
    context.user_data["in_feedback"] = True
    return FEEDBACK_CHOOSE


@check_ban_status
async def feedback_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == CANCEL_BUTTON:
        await update.message.reply_text(MSG_CANCELED, reply_markup=ReplyKeyboardRemove())
        context.user_data.pop("in_feedback", None)
        context.user_data["just_done"] = True
        return ConversationHandler.END

    if text not in (BLACK_LIST_BUTTON, WHITE_LIST_BUTTON):
        await update.message.reply_text(MSG_CLICK_BUTTON)
        return FEEDBACK_CHOOSE

    # where to put it
    context.user_data["fb_target"] = "black" if text == BLACK_LIST_BUTTON else "white"
    # remove keyboard and ask for word
    await update.message.reply_text(
        MSG_TYPE_TEST, reply_markup=ReplyKeyboardRemove()
    )

    context.user_data["feedback_state"] = FEEDBACK_WORD
    return FEEDBACK_WORD


@check_ban_status
async def feedback_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    word = normalize(replace_yo(update.message.text))
    target = context.user_data["fb_target"]

    if SUGGESTIONS_FILE.exists() and SUGGESTIONS_FILE.stat().st_size >= 1_000_000:
        await update.message.reply_text(MSG_FILE_SO_BIG)
        context.user_data.pop("in_feedback", None)
        context.user_data["just_done"] = True
        return ConversationHandler.END

    if " " in word:
        await update.message.reply_text(SPACE_ATTENTION)
        return FEEDBACK_WORD

    suggestions = load_suggestions()

    # Black list: add only if word is in dictionary
    if target == "black":
        if word in WORDLIST:
            suggestions["black"].add(word)
            save_suggestions(suggestions)
            
            # Add word to user profile
            store = load_store()
            user_id = str(update.effective_user.id)
            if user_id not in store["users"]:
                store["users"][user_id] = {}
            if "suggested_words" not in store["users"][user_id]:
                store["users"][user_id]["suggested_words"] = []
            if word not in store["users"][user_id]["suggested_words"]:
                store["users"][user_id]["suggested_words"].append(word)
                save_store(store)
                
            resp = MSG_ADD_BLACK_LIST
        else:
            resp = MSG_DENIED_BLACK_LIST

    # White list: add only if word is not in dictionary and length is 4-11
    else:
        if 4 <= len(word) <= 11 and word not in WORDLIST:
            suggestions["white"].add(word)
            save_suggestions(suggestions)
            
            # Add word to user profile
            store = load_store()
            user_id = str(update.effective_user.id)
            if user_id not in store["users"]:
                store["users"][user_id] = {}
            if "suggested_words" not in store["users"][user_id]:
                store["users"][user_id]["suggested_words"] = []
            if word not in store["users"][user_id]["suggested_words"]:
                store["users"][user_id]["suggested_words"].append(word)
                save_store(store)
                
            resp = MSG_ADD_WHITE_LIST
        else:
            if word in WORDLIST:
                resp = MSG_DENIED_WHITE_LIST_ALREADY_HAVE
            elif not (4 <= len(word) <= 11):
                resp = MSG_DENIED_WHITE_LIST_LENGHT

    await update.message.reply_text(resp)
    context.user_data.pop("in_feedback", None)
    context.user_data["just_done"] = True
    return ConversationHandler.END


@check_ban_status
async def feedback_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    await update.message.reply_text(MSG_CANCELED, reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


@check_ban_status
async def block_during_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # block any other input
    await update.message.reply_text(MSG_NOT_USE_COMMANDS_WHILE_FB)
    # return to current state
    return context.user_data.get("feedback_state", FEEDBACK_CHOOSE)


@check_ban_status
async def feedback_not_allowed_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(FB_ONLY_OUTSIDE_GAME)
    return ASK_LENGTH


@check_ban_status
async def feedback_not_allowed_guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(FB_ONLY_OUTSIDE_GAME)
    return GUESSING