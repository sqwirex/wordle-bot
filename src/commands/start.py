from telegram import Update
from telegram.ext import ContextTypes

from storage.store import load_store, update_user_activity, clear_notification_flag
from decorators.checkban import check_ban_status
from main.constants import GUESSING

@check_ban_status
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_user_activity(update.effective_user)
    store = load_store()
    u = store["users"].get(str(update.effective_user.id), {})
    clear_notification_flag(str(update.effective_user.id))
    if "current_game" in u:
        cg = u["current_game"]
        # заполняем context.user_data из cg:
        context.user_data.update({
            "secret": cg["secret"],
            "length": len(cg["secret"]),
            "attempts": cg["attempts"],
            "guesses": cg["guesses"],
        })
        await update.message.reply_text(
            f"Продолжаем игру: {len(cg['secret'])}-буквенное слово, ты на попытке {cg['attempts']}. Вводи догадку:"
        )
        return GUESSING

    
    await update.message.reply_text(
        "Привет! Я Wordle Bot — угадай слово за 6 попыток.\n"
        "https://github.com/sqwirex/wordle-bot - ссылка на репозиторий с кодом бота\n\n"
        "/play — начать или продолжить игру\n"
        "/hint — дает слово в подсказку, если вы затрудняетесь ответить " \
        "(случайное слово в котором совпадают некоторые буквы с загаданным)\n"
        "/reset — сбросить текущую игру\n"
        "/notification — включить/отключить уведомления при пробуждении бота\n"
        "/my_stats — посмотреть свою статистику\n"
        "/global_stats — посмотреть глобальную статистику за все время\n"
        "/feedback — если ты встретил слово, которое не должно быть в словаре или не существует, введи его в Черный список, " \
        "если же наоборот, ты вбил слово, а бот его не признает, но ты уверен что оно существует, отправляй его в Белый список. " \
        "Администратор бота рассмотрит твое предложение и добавит в ближайшем обновлении, если оно действительно подходит!\n\n"
        "Только не забывай: я еще учусь и не знаю некоторых слов!\n"
        "Не расстраивайся, если я ругаюсь на твое слово — мне есть чему учиться :)\n\n"
        "Кстати, иногда я могу «выключаться», потому что живу в контейнере!\n"
        "Если я не отвечаю — попробуй позже и нажми /play или /start, чтобы продолжить прервавшуюся игру.\n\n"
    )