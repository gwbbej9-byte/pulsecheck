# language: Python, file: scripts/render_ui.py, target: Windows 11
"""Draw a 920x520 dark TUI still matching pulsecheck's live table."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "screenshots" / "ui.png"
W, H = 920, 520

BG = (12, 12, 12)
TITLE_BG = (32, 32, 32)
TAB_BG = (51, 51, 51)
TAB_ACTIVE = (43, 43, 43)
RULE = (58, 58, 58)
WHITE = (204, 204, 204)
BRIGHT = (242, 242, 242)
DIM = (118, 118, 118)
CYAN = (61, 174, 233)
GREEN = (22, 198, 12)
RED = (231, 72, 86)
YELLOW = (249, 241, 165)
KIND = (180, 180, 180)
CAPTION = (204, 204, 204)
CLOSE_BG = (196, 43, 28)

ROWS = [
    ("api-gateway", "HTTP", "UP", "18.4", "—", "+42"),
    ("billing", "HTTP", "DOWN", "8.1", "status 500", "-3"),
    ("postgres", "TCP", "UP", "2.7", "—", "+128"),
    ("redis", "TCP", "DOWN", "4.1", "connection refused", "-11"),
    ("metrics", "HTTP", "UP", "22.0", "—", "+40"),
    ("replica", "TCP", "STALE", "41.2", "last ok 8.4s ago", "+1"),
]

STATUS_COLOR = {"UP": GREEN, "DOWN": RED, "STALE": YELLOW}

COLS = [
    ("NAME", 28),
    ("KIND", 188),
    ("STATUS", 268),
    ("LATENCY_MS", 372),
    ("LAST_ERROR", 522),
    ("STREAK", 820),
]


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = []
    if bold:
        names.extend(
            [
                "CascadiaMono-Bold.ttf",
                "cascadiamono.ttf",
                "consolab.ttf",
                "lucon.ttf",
            ]
        )
    names.extend(
        [
            "CascadiaMono.ttf",
            "Cascadia.ttf",
            "cascadia.ttf",
            "consola.ttf",
            "Consola.ttf",
            "lucon.ttf",
        ]
    )
    roots = [Path(r"C:\Windows\Fonts"), Path("/usr/share/fonts"), Path("/usr/share/fonts/truetype")]
    for root in roots:
        if not root.exists():
            continue
        for name in names:
            candidate = root / name
            if candidate.is_file():
                return ImageFont.truetype(str(candidate), size)
        for match in root.rglob("CascadiaMono*.ttf"):
            return ImageFont.truetype(str(match), size)
        for match in root.rglob("DejaVuSansMono.ttf"):
            return ImageFont.truetype(str(match), size)
    return ImageFont.load_default()


def text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return int(box[2] - box[0])


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    font_ui = load_font(14)
    font_tab = load_font(13)
    font = load_font(16)
    font_bold = load_font(16, bold=True)
    font_sm = load_font(14)

    d.rectangle((0, 0, W, 36), fill=TITLE_BG)
    d.rounded_rectangle((10, 5, 168, 34), radius=6, fill=TAB_ACTIVE)
    d.polygon([(10, 36), (10, 20), (0, 36)], fill=TAB_ACTIVE)
    d.text((32, 11), "pulsecheck", font=font_tab, fill=CAPTION)

    # caption buttons
    d.line((W - 128, 18, W - 116, 18), fill=WHITE, width=1)
    d.rectangle((W - 86, 12, W - 74, 24), outline=WHITE, width=1)
    d.rectangle((W - 48, 0, W, 36), fill=CLOSE_BG)
    d.line((W - 32, 12, W - 18, 26), fill=BRIGHT, width=2)
    d.line((W - 18, 12, W - 32, 26), fill=BRIGHT, width=2)

    y = 56
    d.text((28, y), "C:\\pulsecheck>", font=font, fill=GREEN)
    prompt_w = text_width(d, "C:\\pulsecheck>", font)
    d.text((28 + prompt_w + 10, y), "pulsecheck demo", font=font, fill=BRIGHT)

    y = 96
    d.text((28, y), "pulsecheck", font=font_bold, fill=BRIGHT)
    d.text((28 + text_width(d, "pulsecheck", font_bold) + 12, y), "·  14:29:03  ·  3 up  ·  2 down  ·  1 stale", font=font, fill=DIM)

    y = 136
    for label, x in COLS:
        d.text((x, y), label, font=font_sm, fill=CYAN)
    d.line((24, 162, W - 24, 162), fill=RULE, width=1)

    y = 176
    row_h = 36
    for name, kind, status, latency, error, streak in ROWS:
        d.text((COLS[0][1], y), name, font=font_bold, fill=BRIGHT)
        d.text((COLS[1][1], y), kind, font=font, fill=KIND)
        d.text((COLS[2][1], y), status, font=font_bold, fill=STATUS_COLOR[status])
        lat_font = font
        lat_x = COLS[3][1] + 88 - text_width(d, latency, lat_font)
        d.text((lat_x, y), latency, font=lat_font, fill=WHITE)
        err_color = DIM if error == "—" else WHITE
        d.text((COLS[4][1], y), error, font=font, fill=err_color)
        streak_color = GREEN if streak.startswith("+") else RED
        if status == "STALE":
            streak_color = YELLOW
        sx = COLS[5][1] + 56 - text_width(d, streak, font)
        d.text((sx, y), streak, font=font, fill=streak_color)
        y += row_h

    d.line((24, y + 4, W - 24, y + 4), fill=RULE, width=1)
    d.text((28, y + 18), "q quit   r refresh", font=font_sm, fill=DIM)
    d.text((28, y + 42), "6 targets  ·  mock 127.0.0.1:18765  ·  /ok 200  /fail 500", font=font_ui, fill=(80, 80, 80))

    img.save(OUT, "PNG")
    print(f"wrote {OUT} ({W}x{H})")


if __name__ == "__main__":
    main()
