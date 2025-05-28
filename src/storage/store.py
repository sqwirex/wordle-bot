import json
from datetime import datetime
from zoneinfo import ZoneInfo
from ..config import SUGGESTIONS_FILE, USER_FILE

def load_suggestions() -> dict[str, set[str]]:
    """Возвращает {'black': set(...), 'white': set(...), 'add': set(...)} без дубликатов."""
    if not SUGGESTIONS_FILE.exists():
        return {"black": set(), "white": set(), "add": set()}
    raw = SUGGESTIONS_FILE.read_text("utf-8").strip()
    if not raw:
        return {"black": set(), "white": set(), "add": set()}
    try:
        data = json.loads(raw)
        return {
            "black": set(data.get("black", [])),
            "white": set(data.get("white", [])),
            "add": set(data.get("add", [])),
        }
    except json.JSONDecodeError:
        return {"black": set(), "white": set(), "add": set()}



def save_suggestions(sugg: dict[str, set[str]]):
    """
    Сохраняет suggestions, конвертируя множества в отсортированные списки.
    """
    out = {
        "black": sorted(sugg["black"]),
        "white": sorted(sugg["white"]),
        "add": sorted(sugg["add"]),
    }
    with SUGGESTIONS_FILE.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


# загружаем один раз при старте
suggestions = load_suggestions()

def load_store() -> dict:
    """
    Загружает user_activity.json.
    Если файла нет или он пуст/битый — возвращает чистый шаблон:
    {
      "users": {},
      "global": { "total_games":0, "total_wins":0, "total_losses":0, "win_rate":0.0 }
    }
    """
    template = {
        "users": {},
        "global": {
            "total_games": 0,
            "total_wins": 0,
            "total_losses": 0,
            "win_rate": 0.0
        }
    }
    if not USER_FILE.exists():
        return template

    raw = USER_FILE.read_text("utf-8").strip()
    if not raw:
        return template

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return template

    # Убедимся, что структура корректна
    if not isinstance(data, dict):
        return template

    # Проверим разделы
    if not isinstance(data.get("users"), dict):
        data["users"] = {}
    if not isinstance(data.get("global"), dict):
        data["global"] = template["global"].copy()

    # Подставим недостающие ключи в global
    for key, val in template["global"].items():
        data["global"].setdefault(key, val)

    return data

def save_store(store: dict) -> None:
    """
    Сохраняет переданный store в USER_FILE в JSON-формате с отступами.
    Ожидаем, что store имеет формат:
    {
      "users": { ... },
      "global": { ... }
    }
    """
    USER_FILE.write_text(
        json.dumps(store, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

def update_user_activity(user) -> None:
    """
    Создает или обновляет запись user в store['users'], добавляя:
    - first_name, last_name, username
    - is_bot, is_premium, language_code
    - last_seen_msk (по московскому времени)
    - stats (если еще нет): games_played, wins, losses, win rate
    - banned: флаг бана пользователя (если не установлен, то False)
    """
    store = load_store()
    uid = str(user.id)
    users = store["users"]

    # Если пользователь впервые — создаем базовую запись
    if uid not in users:
        users[uid] = {
            "first_name": user.first_name,
            "suggested_words": [],  # Список слов, предложенных пользователем
            "stats": {
                "games_played": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0
            },
            "banned": False  # По умолчанию пользователь не забанен
        }

    u = users[uid]
    # Обновляем поля профиля
    u["first_name"]    = user.first_name
    u["last_name"]     = user.last_name
    u["username"]      = user.username
    u["is_bot"]        = user.is_bot
    u["is_premium"]    = getattr(user, "is_premium", False)
    u["language_code"] = user.language_code
    u["last_seen_msk"] = datetime.now(ZoneInfo("Europe/Moscow")).isoformat()

    save_store(store)


def clear_notification_flag(user_id: str):
    store = load_store()
    u = store["users"].get(user_id)
    if u and u.get("notified"):
        u["notified"] = False
        save_store(store)


async def is_banned(user_id: str) -> bool:
    """Проверяет, забанен ли пользователь"""
    store = load_store()
    user_data = store["users"].get(str(user_id), {})
    return user_data.get("banned", False)