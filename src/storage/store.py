import json
from datetime import datetime
from zoneinfo import ZoneInfo
from src.main.config import SUGGESTIONS_FILE, USER_FILE

# Return {'black': set(...), 'white': set(...), 'add': set(...)} without dublicate.
def load_suggestions() -> dict[str, set[str]]:
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


# Save suggestions, converted set to array.
def save_suggestions(sugg: dict[str, set[str]]):
    out = {
        "black": sorted(sugg["black"]),
        "white": sorted(sugg["white"]),
        "add": sorted(sugg["add"]),
    }
    with SUGGESTIONS_FILE.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


# load once on start
suggestions = load_suggestions()

# load user_activity.json
def load_store() -> dict:
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

    # check structure
    if not isinstance(data, dict):
        return template
    if not isinstance(data.get("users"), dict):
        data["users"] = {}
    if not isinstance(data.get("global"), dict):
        data["global"] = template["global"].copy()

    # add key to global
    for key, val in template["global"].items():
        data["global"].setdefault(key, val)

    return data

# save user_activity.json
def save_store(store: dict) -> None:
    USER_FILE.write_text(
        json.dumps(store, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

# Create or upload user in store['users']:
def update_user_activity(user) -> None:
    
    store = load_store()
    uid = str(user.id)
    users = store["users"]

    # if new user:
    if uid not in users:
        users[uid] = {
            "first_name": user.first_name,
            "suggested_words": [], 
            "stats": {
                "games_played": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0
            },
            "banned": False
        }

    u = users[uid]
    # upload
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

# check ban flag
async def is_banned(user_id: str) -> bool:
    store = load_store()
    user_data = store["users"].get(str(user_id), {})
    return user_data.get("banned", False)