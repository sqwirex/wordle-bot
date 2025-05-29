import os
from pathlib import Path

# ROOT PATH (src)
ROOT = Path(__file__).parent.parent

# Folder with assets
ASSETS_DIR = ROOT / "assets"
DATA_DIR   = ASSETS_DIR / "data"
FONTS_DIR  = ASSETS_DIR / "fonts"

# Path to JSON file
BASE_FILE         = DATA_DIR / "base_words.json"
USER_FILE= DATA_DIR / "user_activity.json"
SUGGESTIONS_FILE  = DATA_DIR / "suggestions.json"

# Path to Font
FONT_FILE         = FONTS_DIR / "DejaVuSans-Bold.ttf"

# Bot Token and Admin ID
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID  = int(os.getenv("ADMIN_ID", "0"))