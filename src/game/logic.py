import json
from typing import Dict, List, Tuple
from src.main.config import BASE_FILE
from src.main.constants import GREEN, YELLOW, WHITE
from src.languages.russian import replace_yo


def normalize(text: str) -> str:
    return text.strip().lower()


def load_wordlist() -> Tuple[List[str], List[str]]:
    """Load and filter word lists from base_words.json."""
    with BASE_FILE.open("r", encoding="utf-8") as f:
        base_words = json.load(f)
        main_words = base_words.get("main", [])
        additional_words = base_words.get("additional", [])

    # Filter and normalize words
    filtered_main = [normalize(replace_yo(w)) for w in main_words if w.isalpha() and 4 <= len(w) <= 11]
    filtered_additional = [normalize(replace_yo(w)) for w in additional_words if w.isalpha() and 4 <= len(w) <= 11]

    # Remove duplicates
    filtered_main = list(dict.fromkeys(filtered_main))
    filtered_additional = list(dict.fromkeys(filtered_additional))

    # Sort and save
    main_sorted = sorted(filtered_main)
    additional_sorted = sorted(filtered_additional)
    with BASE_FILE.open("w", encoding="utf-8") as f:
        json.dump({"main": main_sorted, "additional": additional_sorted}, f, ensure_ascii=False, indent=2)

    return main_sorted, additional_sorted


# Initialize wordlist
WORDLIST, _ = load_wordlist()


def analyze_guess(secret: str, guess: str) -> Tuple[str, Dict[str, str]]:
    """
    Analyze a guess against the secret word.
    Returns a tuple of (feedback string, letter status dictionary).
    """
    fb = [None] * len(guess)
    secret_chars = list(secret)
    status: Dict[str, str] = {}

    # First pass: check for exact matches (green)
    for i, ch in enumerate(guess):
        if secret[i] == ch:
            fb[i] = GREEN
            secret_chars[i] = None
            status[ch] = "green"

    # Second pass: check for partial matches (yellow) and misses (white)
    for i, ch in enumerate(guess):
        if fb[i] is None:
            if ch in secret_chars:
                fb[i] = YELLOW
                secret_chars[secret_chars.index(ch)] = None
                if ch not in status:
                    status[ch] = "yellow"
            else:
                fb[i] = WHITE
                if ch not in status:
                    status[ch] = "red"

    return "".join(fb), status


def make_feedback(secret: str, guess: str) -> str:
    """Get feedback string for a guess."""
    return analyze_guess(secret, guess)[0]


def compute_letter_status(secret: str, guesses: List[str]) -> Dict[str, str]:
    """Compute the status of each letter based on all guesses."""
    status: Dict[str, str] = {}
    for guess in guesses:
        _, guess_status = analyze_guess(secret, guess)
        # Update status only if new status is better
        for letter, new_status in guess_status.items():
            if letter not in status or (
                new_status == "green" or
                (new_status == "yellow" and status[letter] != "green") or
                (new_status == "red" and status[letter] not in ("green", "yellow"))
            ):
                status[letter] = new_status
    return status
