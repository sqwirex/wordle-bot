import json
import logging
from telegram import Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
)

from ..storage.store import load_store, save_store, load_suggestions, save_suggestions
from main.config import ADMIN_ID, BASE_FILE
from main.constants import REMOVE_INPUT
from game.logic import WORDLIST

logger = logging.getLogger(__name__)

async def suggestions_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # только админ
    if update.effective_user.id != ADMIN_ID:
        return
    sugg = load_suggestions()
    black = sugg.get("black", [])
    white = sugg.get("white", [])
    add = sugg.get("add", [])
    text = (
        "Предложения для черного списка:\n"
        + (", ".join(f'"{w}"' for w in black) if black else "— пусто")
        + "\n\nПредложения для белого списка:\n"
        + (", ".join(f'"{w}"' for w in white) if white else "— пусто")
        + "\n\nПредложения для дополнительного списка:\n"
        + (", ".join(f'"{w}"' for w in add) if add else "— пусто")
    )
    await update.message.reply_text(text)


async def suggestions_move_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Только админ
    if update.effective_user.id != ADMIN_ID:
        return

    # Блокируем во время игры
    store = load_store()
    u = store["users"].get(str(update.effective_user.id), {})
    if "current_game" in u or context.user_data.get("game_active"):
        await update.message.reply_text("Эту команду можно использовать только вне игры.")
        return ConversationHandler.END

    # Если все ок — запускаем диалог перемещения
    await update.message.reply_text(
        "Введи слова для перемещения в add список (формат):\n"
        "слово1, слово2, слово3\n\n"
        "Слова будут перемещены из черного или белого списка в add список.\n"
        "Или /cancel для отмены."
    )
    return REMOVE_INPUT


async def suggestions_move_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # только админ
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    
    context.user_data["in_remove"] = True
    text = update.message.text.strip()
    sugg = load_suggestions()
    moved = {"black": [], "white": []}

    # извлекаем слова через запятую
    words = [w.strip().lower() for w in text.split(",") if w.strip()]
    for w in words:
        # Проверяем наличие слова в черном списке
        if w in sugg["black"]:
            sugg["black"].remove(w)
            sugg["add"].add(w)
            moved["black"].append(w)
        # Проверяем наличие слова в белом списке
        elif w in sugg["white"]:
            sugg["white"].remove(w)
            sugg["add"].add(w)
            moved["white"].append(w)

    save_suggestions(sugg)
    
    # формируем ответ
    parts = []
    if moved["black"]:
        parts.append(f'Из черного списка перемещено в add: {", ".join(moved["black"])}')
    if moved["white"]:
        parts.append(f'Из белого списка перемещено в add: {", ".join(moved["white"])}')
    if not parts:
        parts = ["Ничего не перемещено."]
        
    await update.message.reply_text("\n".join(parts))
    context.user_data.pop("in_remove", None)
    context.user_data["just_done"] = True
    return ConversationHandler.END


async def suggestions_remove_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Только админ
    if update.effective_user.id != ADMIN_ID:
        return

    # Блокируем во время игры
    store = load_store()
    u = store["users"].get(str(update.effective_user.id), {})
    if "current_game" in u or context.user_data.get("game_active"):
        await update.message.reply_text("Эту команду можно использовать только вне игры.")
        return ConversationHandler.END

    # Если все ок — запускаем диалог удаления
    await update.message.reply_text(
        "Введи, что удалить (формат):\n"
        "black: слово1, слово2\n"
        "white: слово3, слово4\n"
        "add: слово5, слово6\n\n"
        "Или /cancel для отмены."
    )
    return REMOVE_INPUT


async def suggestions_remove_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # только админ
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    
    context.user_data["in_remove"] = True
    text = update.message.text.strip()
    sugg = load_suggestions()
    removed = {"black": [], "white": [], "add": []}

    # парсим построчно
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, vals = line.split(":", 1)
        key = key.strip().lower()
        if key not in ("black", "white", "add"):
            continue
        # извлекаем слова через запятую
        words = [w.strip().lower() for w in vals.split(",") if w.strip()]
        for w in words:
            if w in sugg[key]:
                sugg[key].remove(w)
                removed[key].append(w)

    save_suggestions(sugg)
    
    # Удаляем слова из профилей пользователей
    store = load_store()
    removed_count = 0
    
    # Собираем все удаленные слова из всех списков
    all_removed_words = set(removed["black"]) | set(removed["white"]) | set(removed["add"])
    
    # Проходим по всем пользователям и удаляем слова из их списков
    for user_id, user_data in store["users"].items():
        if "suggested_words" in user_data:
            before = len(user_data["suggested_words"])
            user_data["suggested_words"] = [w for w in user_data["suggested_words"] 
                                         if w not in all_removed_words]
            removed_count += before - len(user_data["suggested_words"])
    
    # Сохраняем изменения, если что-то было удалено
    if removed_count > 0:
        save_store(store)
    
    # формируем ответ
    parts = []
    if removed["black"]:
        parts.append(f'Из черного удалено: {", ".join(removed["black"])}')
    if removed["white"]:
        parts.append(f'Из белого удалено: {", ".join(removed["white"])}')
    if removed["add"]:
        parts.append(f'Из add удалено: {", ".join(removed["add"])}')
    if removed_count > 0:
        parts.append(f'Из профилей пользователей удалено {removed_count} слов.')
    if not parts:
        parts = ["Ничего не удалено."]
        
    await update.message.reply_text("\n".join(parts))
    context.user_data.pop("in_remove", None)
    context.user_data["just_done"] = True
    return ConversationHandler.END


async def suggestions_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    # 1. Загружаем предложения
    sugg = load_suggestions()  # {'black': set(), 'white': set(), 'add': set()}

    # 2. Читаем текущий base_words.json
    with BASE_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
        main_words = set(data.get("main", []))
        additional_words = set(data.get("additional", []))

    # 3. Убираем «чёрные» и добавляем «белые» и «add»
    main_words -= sugg["black"]
    main_words |= sugg["white"]
    additional_words |= sugg["add"]

    # 4. Фильтруем по критериям (только буквы, длина 4–11) и сортируем
    filtered_main = [w for w in main_words if w.isalpha() and 4 <= len(w) <= 11]
    filtered_main.sort()
    filtered_additional = [w for w in additional_words if w.isalpha() and 4 <= len(w) <= 11]
    filtered_additional.sort()

    # 5. Сохраняем обратно в base_words.json
    with BASE_FILE.open("w", encoding="utf-8") as f:
        json.dump({"main": filtered_main, "additional": filtered_additional}, f, ensure_ascii=False, indent=2)

    logger.info(f"-> Wrote {len(filtered_main)} main words and {len(filtered_additional)} additional words to {BASE_FILE.resolve()}")

    # 6. Обновляем глобальный список в памяти
    global WORDLIST
    WORDLIST = filtered_main

    # 7. Удаляем одобренные слова из списка предложенных у пользователей
    store = load_store()
    removed_count = 0
    
    # Собираем все одобренные слова (белый список и add список)
    approved_words = sugg["white"] | sugg["add"]
    blacklisted_words = sugg["black"]
    
    # Проходим по всем пользователям и удаляем одобренные слова из их списков
    for user_id, user_data in store["users"].items():
        if "suggested_words" in user_data:
            before = len(user_data["suggested_words"])
            user_data["suggested_words"] = [
                w for w in user_data["suggested_words"] 
                if w not in approved_words and w not in blacklisted_words
            ]
            removed_count += before - len(user_data["suggested_words"])
    
    # Сохраняем изменения, если что-то было удалено
    if removed_count > 0:
        save_store(store)

    # 8. Очищаем suggestions.json
    save_suggestions({"black": set(), "white": set(), "add": set()})

    # 9. Ответ админу
    await update.message.reply_text(
        f"Словарь пересобран: +{len(sugg['white'])}, +{len(sugg['add'])}, -{len(sugg['black'])}.\n"
        f"Удалено {removed_count} слов (одобренные и черный список) из профилей пользователей.\n"
        "Предложения очищены."
    )