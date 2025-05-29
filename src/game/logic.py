import json
from typing import Dict, List
from src.main.config import BASE_FILE
from src.main.constants import GREEN, YELLOW, WHITE
from src.languages.russian import replace_yo


def normalize(text: str) -> str:
    return text.strip().lower()


# Read word list from base_words.json
with BASE_FILE.open("r", encoding="utf-8") as f:
    base_words = json.load(f)
    main_words = base_words.get("main", [])
    additional_words = base_words.get("additional", [])

# Filter by criteria: letters only, length 4-11 characters
# and normalize words
filtered_main = [normalize(replace_yo(w)) for w in main_words if w.isalpha() and 4 <= len(w) <= 11]
filtered_additional = [normalize(replace_yo(w)) for w in additional_words if w.isalpha() and 4 <= len(w) <= 11]

# Remove duplicates that could appear after normalization
filtered_main = list(dict.fromkeys(filtered_main))
filtered_additional = list(dict.fromkeys(filtered_additional))

# sort
WORDLIST = sorted(filtered_main)
with BASE_FILE.open("w", encoding="utf-8") as f:
    json.dump({"main": WORDLIST, "additional": sorted(filtered_additional)}, f, ensure_ascii=False, indent=2)


def compute_letter_status(secret: str, guesses: List[str]) -> Dict[str, str]:
    """
    For each letter returns:
      - "green"  if it was 🟩
      - "yellow" if it was 🟨 (and wasn't 🟩)
      - "red"    if it was ⬜ (and wasn't 🟩 or 🟨)
    """
    status: dict[str,str] = {}
    for guess in guesses:
        fb = [] 
        s_chars = list(secret)
        # first green ones
        for i,ch in enumerate(guess):
            if secret[i] == ch:
                fb.append("🟩")
                s_chars[i] = None
            else:
                fb.append(None)
        # then yellow/white
        for i,ch in enumerate(guess):
            if fb[i] is None:
                if ch in s_chars:
                    fb[i] = "🟨"
                    s_chars[s_chars.index(ch)] = None
                else:
                    fb[i] = "⬜"
        # upload global status
        for ch,sym in zip(guess, fb):
            prev = status.get(ch)
            if sym == "🟩":
                status[ch] = "green"
            elif sym == "🟨" and prev != "green":
                status[ch] = "yellow"
            elif sym == "⬜" and prev not in ("green","yellow"):
                status[ch] = "red"
    return status


def make_feedback(secret: str, guess: str) -> str:
    fb = [None] * len(guess)
    secret_chars = list(secret)
    # 1) gteen
    for i, ch in enumerate(guess):
        if secret[i] == ch:
            fb[i] = GREEN
            secret_chars[i] = None
    # 2) yellow/white
    for i, ch in enumerate(guess):
        if fb[i] is None:
            if ch in secret_chars:
                fb[i] = YELLOW
                secret_chars[secret_chars.index(ch)] = None
            else:
                fb[i] = WHITE
    return "".join(fb)
