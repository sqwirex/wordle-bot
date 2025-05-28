import json
from typing import Dict, List
from ..config import BASE_FILE
from ..constants import GREEN, YELLOW, WHITE


def normalize(text: str) -> str:
    # переводим все в нижний регистр и убираем «е»
    return text.strip().lower().replace("ё", "е")


# Читаем список слов из base_words.json
with BASE_FILE.open("r", encoding="utf-8") as f:
    base_words = json.load(f)
    main_words = base_words.get("main", [])
    additional_words = base_words.get("additional", [])

# Фильтруем по критериям: только буквы, длина 4–11 символов
# и нормализуем слова (нижний регистр, замена ё на е)
filtered_main = [normalize(w) for w in main_words if w.isalpha() and 4 <= len(w) <= 11]
filtered_additional = [normalize(w) for w in additional_words if w.isalpha() and 4 <= len(w) <= 11]

# Удаляем дубликаты, которые могли появиться после нормализации
filtered_main = list(dict.fromkeys(filtered_main))
filtered_additional = list(dict.fromkeys(filtered_additional))

# Сортируем списки
WORDLIST = sorted(filtered_main)
with BASE_FILE.open("w", encoding="utf-8") as f:
    json.dump({"main": WORDLIST, "additional": sorted(filtered_additional)}, f, ensure_ascii=False, indent=2)


def compute_letter_status(secret: str, guesses: List[str]) -> Dict[str, str]:
    """
    Для каждой буквы возвращает:
      - "green"  если была 🟩
      - "yellow" если была 🟨 (и не была 🟩)
      - "red"    если была ⬜ (и не была ни 🟩, ни 🟨)
    """
    status: dict[str,str] = {}
    for guess in guesses:
        fb = [] 
        s_chars = list(secret)
        # сначала зеленые
        for i,ch in enumerate(guess):
            if secret[i] == ch:
                fb.append("🟩")
                s_chars[i] = None
            else:
                fb.append(None)
        # затем желтые/красные
        for i,ch in enumerate(guess):
            if fb[i] is None:
                if ch in s_chars:
                    fb[i] = "🟨"
                    s_chars[s_chars.index(ch)] = None
                else:
                    fb[i] = "⬜"
        # обновляем глобальный статус
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
    # 1) зеленые
    for i, ch in enumerate(guess):
        if secret[i] == ch:
            fb[i] = GREEN
            secret_chars[i] = None
    # 2) желтые/красные
    for i, ch in enumerate(guess):
        if fb[i] is None:
            if ch in secret_chars:
                fb[i] = YELLOW
                secret_chars[secret_chars.index(ch)] = None
            else:
                fb[i] = WHITE
    return "".join(fb)
