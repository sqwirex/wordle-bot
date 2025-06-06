import logging
from dotenv import load_dotenv

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters
)

from src.main.config import (BOT_TOKEN)

from src.main.constants import (
    ASK_LENGTH, GUESSING,
    FEEDBACK_CHOOSE, FEEDBACK_WORD,
    REMOVE_INPUT, BROADCAST,
)

from src.commands.unknown     import unknown_text
from src.commands.start import start
from src.commands.play import ask_length, receive_length, ignore_ask
from src.commands.guess import handle_guess, ignore_guess, suggest_white_callback
from src.commands.hint import hint, hint_not_allowed
from src.commands.reset import reset, reset_global
from src.commands.notification import notification_toggle, send_unfinished_games
from src.commands.stats import my_stats, only_outside_game, global_stats

from src.commands.feedback    import (feedback_not_allowed_ask,
                                      feedback_not_allowed_guess,
                                      feedback_start,
                                      feedback_choose,
                                      feedback_word,
                                      block_during_feedback,
                                      feedback_cancel
)

from src.commands.admin       import (ban_user, 
                                      unban_user, 
                                      dump_activity, 
                                      set_commands,
                                      dict_file,
                                      send_activity_periodic
)

from src.commands.suggestions import (suggestions_view,
                                      suggestions_approve,
                                      suggestions_remove_start,
                                      suggestions_remove_process,
                                      suggestions_move_start,
                                      suggestions_move_process,
)

from src.commands.broadcast   import (broadcast_start,
                                      broadcast_send,
                                      broadcast_cancel,
)

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def main():
    
    token = BOT_TOKEN
    if not token:
        logger.error("BOT_TOKEN не установлен")
        return

    app = (
        ApplicationBuilder()
        .token(token)
        .post_init(set_commands)
        .build()
    )
	
    # send once on start
    app.job_queue.run_once(send_activity_periodic, when=0)
    app.job_queue.run_once(send_unfinished_games, when=1)


    feedback_conv = ConversationHandler(
    entry_points=[CommandHandler("feedback", feedback_start)],
    states={
        FEEDBACK_CHOOSE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, feedback_choose),
            MessageHandler(filters.ALL, block_during_feedback),
        ],
        FEEDBACK_WORD: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, feedback_word),
            MessageHandler(filters.ALL, block_during_feedback),
        ],
    },
    fallbacks=[CommandHandler("cancel", feedback_cancel)],
    allow_reentry=True
    )
    app.add_handler(feedback_conv)
    
    
    conv = ConversationHandler(
        entry_points=[
            CommandHandler("play", ask_length),
            CommandHandler("start", start),
        ],
        states={
            ASK_LENGTH: [
                CommandHandler("feedback", feedback_not_allowed_ask),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_length),
                CommandHandler("start", ignore_ask),
                CommandHandler("play", ignore_ask),
                CommandHandler("hint", hint_not_allowed),
                CommandHandler("reset", reset),
                CommandHandler("notification", only_outside_game),
                CommandHandler("my_stats", only_outside_game),
                CommandHandler("global_stats", only_outside_game),
            ],
            GUESSING: [
                CommandHandler("feedback", feedback_not_allowed_guess),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_guess),
                CommandHandler("start", ignore_guess),
		        CommandHandler("play", ignore_guess),
                CommandHandler("hint", hint),
                CommandHandler("reset", reset),
                CommandHandler("notification", only_outside_game),
                CommandHandler("my_stats", only_outside_game),
                CommandHandler("global_stats", only_outside_game),
            ],
        },
        fallbacks=[
            CommandHandler("reset", reset),
       ],
    )
    app.add_handler(conv)

    
    app.add_handler(CommandHandler("suggestions_view", suggestions_view))
    app.add_handler(CommandHandler("suggestions_approve", suggestions_approve))

    remove_conv = ConversationHandler(
        entry_points=[CommandHandler("suggestions_remove", suggestions_remove_start)],
        states={
            REMOVE_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, suggestions_remove_process),
            ],
        },
        fallbacks=[CommandHandler("cancel", feedback_cancel)],
        allow_reentry=True,
    )
    app.add_handler(remove_conv)


    move_conv = ConversationHandler(
        entry_points=[CommandHandler("suggestions_move", suggestions_move_start)],
        states={
            REMOVE_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, suggestions_move_process),
            ],
        },
        fallbacks=[CommandHandler("cancel", feedback_cancel)],
        allow_reentry=True,
    )
    app.add_handler(move_conv)


    broadcast_conv = ConversationHandler(
        entry_points=[CommandHandler("broadcast", broadcast_start)],
        states={
            BROADCAST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_send),
            ],
        },
        fallbacks=[CommandHandler("broadcast_cancel", broadcast_cancel)],
        allow_reentry=True,
        )
    app.add_handler(broadcast_conv)

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_text),
        group=99
        )
    
    # global commands
    global_commands = [
        ("hint", hint_not_allowed),
        ("reset", reset_global),
        ("notification", notification_toggle),
        ("my_stats", my_stats),
        ("global_stats", global_stats),
        ("dict_file", dict_file),
        ("dump_activity", dump_activity),
        ("ban", ban_user),
        ("unban", unban_user)
    ]
    
    for command, handler in global_commands:
        app.add_handler(CommandHandler(command, handler))
    
    app.add_handler(CallbackQueryHandler(suggest_white_callback, pattern=r'^suggest_white:'))

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()