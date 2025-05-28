import os
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
# Импортируем константы и команды
from .constants import (
    ASK_LENGTH, GUESSING,
    FEEDBACK_CHOOSE, FEEDBACK_WORD,
    REMOVE_INPUT, BROADCAST
)
from .commands.start import start
from .commands.play import ask_length, receive_length, ignore_ask
from .commands.guess import handle_guess, ignore_guess, suggest_white_callback
from .commands.hint import hint, hint_not_allowed
from .commands.reset import reset, reset_global
from .commands.stats import my_stats, only_outside_game, global_stats
from .commands.feedback    import (feedback_not_allowed_ask,
                                      feedback_not_allowed_guess,
                                      feedback_start,
                                      feedback_choose,
                                      feedback_word,
                                      block_during_feedback,
                                      feedback_cancel)
from .commands.suggestions import (suggestions_view,
                                      suggestions_approve,
                                      suggestions_remove_start,
                                      suggestions_remove_process,
                                      suggestions_move_start,
                                      suggestions_move_process,
                                      )
from .commands.broadcast   import (broadcast_start,
                                      broadcast_send,
                                      broadcast_cancel,
                                      )
from .commands.admin       import (ban_user, 
                                      unban_user, 
                                      dump_activity, 
                                      set_commands,
                                      dict_file,
                                      send_activity_periodic
                                      )
from .commands.notification import notification_toggle, send_unfinished_games
from .commands.unknown     import unknown_text
# Загрузка .env
load_dotenv()

# Логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def main():
    
    token = os.getenv("BOT_TOKEN")
    if not token:
        logger.error("BOT_TOKEN не установлен")
        return

    app = (
        ApplicationBuilder()
        .token(token)
        .post_init(set_commands)
        .build()
    )
	
    # отправляем один раз при загрузке
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

    
    # 1) просмотр и подтверждение предложений
    app.add_handler(CommandHandler("suggestions_view", suggestions_view))
    app.add_handler(CommandHandler("suggestions_approve", suggestions_approve))

    # 2) удаление через ConversationHandler
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


    # 3) перемещение через ConversationHandler
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
    

    # Глобальные
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("hint", hint_not_allowed))
    app.add_handler(CommandHandler("reset", reset_global))
    app.add_handler(CommandHandler("notification", notification_toggle))
    app.add_handler(CommandHandler("my_stats", my_stats))
    app.add_handler(CommandHandler("global_stats", global_stats))
    app.add_handler(CommandHandler("dict_file", dict_file))
    app.add_handler(CommandHandler("dump_activity", dump_activity))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))
    
    # Обработчик для кнопки предложения слова в белый список
    app.add_handler(CallbackQueryHandler(suggest_white_callback, pattern=r'^suggest_white:'))

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()