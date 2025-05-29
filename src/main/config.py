import os
from pathlib import Path

# Корневой каталог проекта (где лежит bot.py и прочие модули)
ROOT = Path(__file__).parent.parent

# Папка с статическими ассетами
ASSETS_DIR = ROOT / "assets"
DATA_DIR   = ASSETS_DIR / "data"
FONTS_DIR  = ASSETS_DIR / "fonts"

# Пути к JSON-файлам
BASE_FILE         = DATA_DIR / "base_words.json"
USER_FILE= DATA_DIR / "user_activity.json"
SUGGESTIONS_FILE  = DATA_DIR / "suggestions.json"

# Путь к шрифту для отрисовки доски
FONT_FILE         = FONTS_DIR / "DejaVuSans-Bold.ttf"

# Токен и админ-ID из окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID  = int(os.getenv("ADMIN_ID", "0"))