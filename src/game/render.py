from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

from src.game.logic import make_feedback, compute_letter_status
from src.main.constants import GREEN, YELLOW, WHITE
from src.languages.russian import KB_LAYOUT, SPECIAL_RUSSIAN_LETTERS
from src.main.config import FONT_FILE


def render_full_board_with_keyboard(
    guesses: list[str],
    secret: str,
    total_rows: int = 6,
    max_width_px: int = 1080
) -> BytesIO:
    # --- антиалиасинг: рендерим в 3x размере, потом уменьшаем ---
    scale = 3
    padding   = 6 * scale
    board_def = 80 * scale
    cols      = len(secret)
    total_pad = (cols + 1) * padding

    # размер квадратика доски
    board_sq = min(board_def, (max_width_px * scale - total_pad) // cols)
    board_sq = max(20 * scale, board_sq)

    board_w = cols * board_sq + total_pad
    board_h = total_rows * board_sq + (total_rows + 1) * padding

    # выбираем масштаб клавиш по длине слова
    if cols >= 8:
        factor = 0.6
    elif cols == 7:
        factor = 0.5
    elif cols == 6:
        factor = 0.4
    elif cols == 5:
        factor = 0.3
    elif cols == 4:
        factor = 0.25

    kb_sq   = max(12 * scale, int(board_sq * factor))
    kb_rows = len(KB_LAYOUT)
    img_h   = board_h + kb_rows * kb_sq + (kb_rows + 1) * padding

    img        = Image.new("RGB", (board_w, img_h), (24, 24, 32))  # почти чёрный фон
    draw       = ImageDraw.Draw(img)
    font_board = ImageFont.truetype(FONT_FILE, int(board_sq * 0.6))
    font_kb    = ImageFont.truetype(FONT_FILE, int(kb_sq * 0.6))

    # --- игровая доска (6 строк) ---
    for r in range(total_rows):
        y0 = padding + r * (board_sq + padding)
        if r < len(guesses):
            guess = guesses[r]
            fb    = make_feedback(secret, guess)
        else:
            guess = None
            fb    = [None] * cols

        for c in range(cols):
            x0 = padding + c * (board_sq + padding)
            x1 = x0 + board_sq
            y1 = y0 + board_sq

            color = fb[c]
            if color == GREEN:
                bg = (121,184,81)  # #79b851
            elif color == YELLOW:
                bg = (243,194,55)  # #f3c237
            elif color == WHITE:
                bg = (72,73,84)  # #484954
            else:
                bg = (211,214,218)  # #d3d6da (неактивная)

            draw.rectangle([x0,y0,x1,y1], fill=bg, outline=(40,40,50), width=2)

            if guess:
                ch = guess[c].upper()
                tc = (255,255,255)  # белые буквы всегда
                bbox = draw.textbbox((0,0), ch, font=font_board)
                w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
                # Смещение по y для всех, кроме Щ, Ц, Д, Й
                if ch.lower() in SPECIAL_RUSSIAN_LETTERS:
                    y_offset = -board_sq * 0.05  # специальные буквы чуть выше (5%)
                else:
                    y_offset = -board_sq * 0.10  # остальные буквы выше (10%)
                draw.text(
                    (x0 + (board_sq-w)/2, y0 + (board_sq-h)/2 + y_offset),
                    ch, font=font_board, fill=tc
                )

    # --- мини-клавиатура ---
    letter_status = compute_letter_status(secret, guesses)
    for ri, row in enumerate(KB_LAYOUT):
        y0      = board_h + padding + ri * (kb_sq + padding)
        row_len = len(row)
        row_pad = (row_len + 1) * padding
        row_w   = row_len * kb_sq + row_pad
        x_off   = (board_w - row_w) // 2

        for i, ch in enumerate(row):
            x0 = x_off + padding + i * (kb_sq + padding)
            x1 = x0 + kb_sq
            y1 = y0 + kb_sq

            st = letter_status.get(ch)
            if st == "green":
                bg = (121,184,81)  # #79b851
            elif st == "yellow":
                bg = (243,194,55)  # #f3c237
            elif st == "red":
                bg = (72,73,84)  # #484954
            else:
                bg = (129,130,155)  # #81829b — обычные буквы на клавиатуре

            draw.rectangle([x0,y0,x1,y1], fill=bg, outline=(40,40,50), width=1)
            tc = (255,255,255)  # белые буквы всегда
            letter = ch.upper()
            bbox   = draw.textbbox((0,0), letter, font=font_kb)
            w, h   = bbox[2]-bbox[0], bbox[3]-bbox[1]
            # Смещение по y для всех, кроме Щ, Ц, Д, Й
            if ch in SPECIAL_RUSSIAN_LETTERS:
                y_offset = -kb_sq * 0.05  # специальные буквы чуть выше (5%)
            else:
                y_offset = -kb_sq * 0.10  # остальные буквы выше (10%)
            draw.text(
                (x0 + (kb_sq-w)/2, y0 + (kb_sq-h)/2 + y_offset),
                letter, font=font_kb, fill=tc
            )

    # уменьшение до нормального размера с антиалиасингом
    final_img = img.resize((board_w // scale, img_h // scale), Image.LANCZOS)
    final_buf = BytesIO()
    final_img.save(final_buf, format="PNG")
    final_buf.seek(0)
    return final_buf