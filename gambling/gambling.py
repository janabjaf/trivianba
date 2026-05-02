"""gambling.py – Casino mini-games cog for Red-DiscordBot."""
from __future__ import annotations

import asyncio
import functools
import io
import math
import random
from typing import Dict, List, Optional, Tuple

import discord
from redbot.core import commands
from PIL import Image, ImageDraw, ImageFont

# ──────────────────────────────────────────────────────────────────────────────
# Roulette constants
# ──────────────────────────────────────────────────────────────────────────────
WHEEL_ORDER: List[int] = [
    0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36,
    11, 30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9,
    22, 18, 29, 7, 28, 12, 35, 3, 26,
]
RED_SLOTS = frozenset({
    1, 3, 5, 7, 9, 12, 14, 16, 18, 19,
    21, 23, 25, 27, 30, 32, 34, 36,
})

# ──────────────────────────────────────────────────────────────────────────────
# Slot machine constants
# ──────────────────────────────────────────────────────────────────────────────
SYMBOLS: List[Tuple[str, Tuple[int, int, int]]] = [
    ("7",    (220,  30,  30)),
    ("BAR",  (200, 155,   0)),
    ("CHR",  (200,  20,  80)),   # Cherry
    ("BELL", (220, 200,   0)),
    ("STAR", (255, 200,  10)),
    ("LEM",  (190, 190,  30)),   # Lemon
    ("GEM",  ( 20, 180, 230)),   # Diamond
    ("WILD", (140,  20, 200)),
]

# ──────────────────────────────────────────────────────────────────────────────
# Card / deck helpers
# ──────────────────────────────────────────────────────────────────────────────
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
SUITS = ["♠", "♥", "♦", "♣"]
CARD_VALUES = {
    "A": 11, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6,
    "7": 7, "8": 8, "9": 9, "10": 10, "J": 10, "Q": 10, "K": 10,
}
RED_SUITS = {"♥", "♦"}

RANK_ORDER = {"A": 14, "K": 13, "Q": 12, "J": 11,
              "10": 10, "9": 9, "8": 8, "7": 7, "6": 6,
              "5": 5, "4": 4, "3": 3, "2": 2}


def _new_deck() -> List[Tuple[str, str]]:
    deck = [(r, s) for r in RANKS for s in SUITS]
    random.shuffle(deck)
    return deck


def _hand_value(hand: List[Tuple[str, str]]) -> int:
    total = sum(CARD_VALUES[r] for r, _ in hand)
    aces = sum(1 for r, _ in hand if r == "A")
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def _card_str(card: Tuple[str, str]) -> str:
    r, s = card
    return f"{r}{s}"


def _hand_str(hand: List[Tuple[str, str]]) -> str:
    return "  ".join(_card_str(c) for c in hand)


# ──────────────────────────────────────────────────────────────────────────────
# PIL helpers
# ──────────────────────────────────────────────────────────────────────────────
def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _centered_text(
    draw: ImageDraw.ImageDraw,
    x: float, y: float,
    text: str,
    font: ImageFont.ImageFont,
    fill: Tuple[int, int, int],
) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text((x - tw / 2, y - th / 2), text, font=font, fill=fill)


def _rounded_rect(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[int, int, int, int],
    radius: int,
    fill: Tuple[int, int, int],
    outline: Optional[Tuple[int, int, int]] = None,
    width: int = 2,
) -> None:
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle(xy, radius=radius, fill=fill,
                           outline=outline, width=width)


def _star_polygon(
    cx: float, cy: float, r_outer: float, r_inner: float, n: int = 5
) -> List[Tuple[float, float]]:
    pts: List[Tuple[float, float]] = []
    for i in range(n * 2):
        ang = math.radians(-90 + i * 180 / n)
        r = r_outer if i % 2 == 0 else r_inner
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return pts


# ──────────────────────────────────────────────────────────────────────────────
# Roulette GIF generator
# ──────────────────────────────────────────────────────────────────────────────
def _slot_color(n: int) -> Tuple[int, int, int]:
    if n == 0:
        return (0, 140, 55)
    return (185, 25, 25) if n in RED_SLOTS else (22, 22, 22)


def _roulette_frame(
    wheel_angle: float,
    ball_angle: Optional[float],
    ball_r: float,
    size: int,
) -> Image.Image:
    cx = cy = size // 2
    R = size // 2 - 16
    r_inner = int(R * 0.36)
    r_track = int(R * 0.87)

    img = Image.new("RGB", (size, size), (18, 55, 28))
    draw = ImageDraw.Draw(img)

    # Multi-layer outer rim (gives depth / 3-D feel)
    for d in range(18, 0, -2):
        frac = d / 18.0
        c = int(90 * frac)
        draw.ellipse(
            [cx - R - d, cy - R - d, cx + R + d, cy + R + d],
            fill=(c, int(c * 0.65), 0),
        )

    # Segments
    N = len(WHEEL_ORDER)
    aps = 360.0 / N
    for j, num in enumerate(WHEEL_ORDER):
        start = wheel_angle + j * aps - 90.0 - aps / 2
        draw.pieslice(
            [cx - R, cy - R, cx + R, cy + R],
            start=start, end=start + aps,
            fill=_slot_color(num),
            outline=(200, 162, 0), width=1,
        )

    # Ball track ring
    draw.ellipse(
        [cx - r_track, cy - r_track, cx + r_track, cy + r_track],
        outline=(210, 175, 20), width=2,
    )

    # Inner platform (mahogany)
    draw.ellipse(
        [cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner],
        fill=(52, 30, 12), outline=(200, 162, 0), width=3,
    )

    # Spokes
    for k in range(8):
        ang = math.radians(wheel_angle + k * 45)
        x1 = cx + int(r_inner * math.cos(ang))
        y1 = cy + int(r_inner * math.sin(ang))
        x2 = cx + int(R * 0.50 * math.cos(ang))
        y2 = cy + int(R * 0.50 * math.sin(ang))
        draw.line([(x1, y1), (x2, y2)], fill=(200, 162, 0), width=1)

    # Centre hub
    draw.ellipse(
        [cx - 20, cy - 20, cx + 20, cy + 20],
        fill=(200, 162, 0), outline=(140, 110, 0), width=2,
    )

    # Ball
    if ball_angle is not None:
        bx = cx + int(ball_r * math.cos(math.radians(ball_angle)))
        by = cy + int(ball_r * math.sin(math.radians(ball_angle)))
        br = 9
        draw.ellipse(
            [bx - br, by - br, bx + br, by + br],
            fill=(245, 245, 245), outline=(170, 170, 170), width=1,
        )
        # Specular highlight
        draw.ellipse(
            [bx - br + 2, by - br + 2, bx, by],
            fill=(255, 255, 255),
        )

    return img


def _make_roulette_gif(winning_number: int) -> bytes:
    N = len(WHEEL_ORDER)
    win_idx = WHEEL_ORDER.index(winning_number)
    SIZE = 480
    R_TRACK = SIZE // 2 - 16 - 24   # ball orbit radius

    # How many degrees we must rotate so winning slot ends at 12-o'clock
    # In the wheel's local frame, slot j starts at j*(360/N) from 12-o'clock.
    slot_center_local = win_idx * (360.0 / N)
    # We want wheel_angle (the offset we add to all angles) to satisfy:
    # wheel_angle + slot_center_local = 0 (mod 360)  => wheel_angle = -slot_center_local
    final_wheel_angle = (-slot_center_local) % 360

    TOTAL = 90
    FULL_SPINS = 7

    # total degrees the wheel rotates (forward = clockwise visually)
    total_travel = FULL_SPINS * 360.0 + final_wheel_angle

    # Ball orbits counter-clockwise (negative direction)
    BALL_SPINS = 10
    ball_travel_total = BALL_SPINS * 360.0

    frames: List[Image.Image] = []
    durations: List[int] = []

    for i in range(TOTAL):
        t = i / (TOTAL - 1)
        ease = 1.0 - (1.0 - t) ** 3      # cubic ease-out

        # Wheel rotates clockwise, expressed as negative offset in our draw fn
        wheel_angle = -(ease * total_travel) % 360

        # Ball orbits counter-clockwise at decreasing speed
        ball_ease = 1.0 - (1.0 - t) ** 2  # ease-out for ball
        ball_travel = ball_ease * ball_travel_total
        ball_ang_raw = 270.0 + ball_travel   # start at top, go counter-cw
        ball_angle = ball_ang_raw % 360

        # Ball spirals inward in the last 25% of frames
        if t < 0.75:
            br = float(R_TRACK)
        else:
            inward_t = (t - 0.75) / 0.25
            r_landing = int((SIZE // 2 - 16) * 0.68)
            br = R_TRACK + (r_landing - R_TRACK) * (inward_t ** 2)

        img = _roulette_frame(wheel_angle, ball_angle, br, SIZE)
        frames.append(img.quantize(colors=96, method=Image.Quantize.FASTOCTREE))

        # Frame timing: fast at start, slow at end (mimics deceleration)
        raw_ms = 25 + int(120 * (t ** 2.5))
        durations.append(raw_ms)

    buf = io.BytesIO()
    frames[0].save(
        buf, format="GIF", save_all=True, append_images=frames[1:],
        loop=0, duration=durations, optimize=False,
    )
    return buf.getvalue()


# ──────────────────────────────────────────────────────────────────────────────
# Slot machine GIF generator
# ──────────────────────────────────────────────────────────────────────────────
_SYM_W, _SYM_H = 110, 90

def _draw_symbol(sym_idx: int) -> Image.Image:
    """Draw a single slot symbol as a PIL image."""
    label, color = SYMBOLS[sym_idx]
    img = Image.new("RGB", (_SYM_W, _SYM_H), (30, 30, 30))
    draw = ImageDraw.Draw(img)
    cx, cy = _SYM_W // 2, _SYM_H // 2

    _rounded_rect(draw, (4, 4, _SYM_W - 4, _SYM_H - 4),
                  radius=10, fill=(50, 50, 55), outline=color, width=3)

    if label == "STAR":
        pts = _star_polygon(cx, cy, 30, 13)
        draw.polygon([(int(x), int(y)) for x, y in pts], fill=color)
    elif label == "GEM":
        # Rotated square (diamond shape)
        draw.polygon(
            [(cx, cy - 30), (cx + 22, cy), (cx, cy + 30), (cx - 22, cy)],
            fill=color,
        )
    elif label == "CHR":
        # Two circles + stem = cherry
        draw.ellipse([cx - 26, cy - 5, cx - 2, cy + 25], fill=color)
        draw.ellipse([cx + 2, cy - 5, cx + 26, cy + 25], fill=color)
        draw.line([(cx - 14, cy - 5), (cx, cy - 25)], fill=(0, 155, 50), width=3)
        draw.line([(cx + 14, cy - 5), (cx, cy - 25)], fill=(0, 155, 50), width=3)
    elif label == "BELL":
        # Trapezoid body + clapper
        draw.polygon(
            [(cx - 25, cy + 15), (cx + 25, cy + 15),
             (cx + 18, cy - 22), (cx - 18, cy - 22)],
            fill=color,
        )
        draw.ellipse([cx - 7, cy + 15, cx + 7, cy + 28], fill=color)
        draw.ellipse([cx - 16, cy - 28, cx + 16, cy - 20], fill=color)
    elif label == "LEM":
        draw.ellipse([cx - 28, cy - 22, cx + 28, cy + 22], fill=color)
        # Little nub at top
        draw.ellipse([cx - 6, cy - 30, cx + 6, cy - 20], fill=color)
    elif label == "BAR":
        _rounded_rect(draw, (cx - 32, cy - 14, cx + 32, cy + 14),
                      radius=5, fill=color)
        draw.line([(cx - 28, cy - 4), (cx + 28, cy - 4)], fill=(255, 240, 160), width=2)
        draw.line([(cx - 28, cy + 4), (cx + 28, cy + 4)], fill=(255, 240, 160), width=2)
    elif label == "WILD":
        draw.ellipse([cx - 30, cy - 30, cx + 30, cy + 30], fill=color)
        f = _font(24)
        _centered_text(draw, cx, cy, "W", f, (255, 255, 255))
    else:  # "7"
        f = _font(54)
        _centered_text(draw, cx, cy, "7", f, color)

    return img


def _make_slots_gif(r0: int, r1: int, r2: int) -> bytes:
    """Animate a 3-reel slot machine stopping at symbols r0, r1, r2."""
    REEL_COUNT = 3
    VISIBLE = 3          # symbols visible per reel at once
    STRIP_LEN = 24       # total strip length per reel (wraps)
    TOTAL_FRAMES = 50
    # Frame indices at which each reel stops scrolling
    STOP_FRAMES = [22, 32, 42]

    MARGIN = 12
    W = REEL_COUNT * _SYM_W + (REEL_COUNT + 1) * MARGIN
    H = VISIBLE * _SYM_H + (VISIBLE + 1) * MARGIN + 50  # +50 for header

    # Pre-render all 8 symbols
    sym_imgs = [_draw_symbol(i) for i in range(len(SYMBOLS))]

    # Build strips: each reel strip ends with the winning symbol at bottom
    strips: List[List[int]] = []
    for win in (r0, r1, r2):
        strip = [random.randint(0, len(SYMBOLS) - 1) for _ in range(STRIP_LEN - 1)]
        strip.append(win)
        strips.append(strip)

    # Scroll offsets (in pixels) for each reel
    # offset means "how many pixels from the top of the strip we've scrolled"
    offsets = [0.0, 0.0, 0.0]
    final_offsets = [
        (STRIP_LEN - VISIBLE) * _SYM_H for _ in range(REEL_COUNT)
    ]
    speeds = [(_SYM_H * 3.5)] * REEL_COUNT  # px per frame initial

    frames: List[Image.Image] = []

    for fi in range(TOTAL_FRAMES):
        bg = Image.new("RGB", (W, H), (20, 20, 25))
        draw = ImageDraw.Draw(bg)

        # Header bar
        _rounded_rect(draw, (0, 0, W, 46), radius=0,
                      fill=(35, 35, 40), outline=(200, 162, 0), width=2)
        f_hdr = _font(22)
        _centered_text(draw, W / 2, 23, "🎰  SLOTS  🎰", f_hdr, (200, 162, 0))

        for ri in range(REEL_COUNT):
            if fi >= STOP_FRAMES[ri]:
                # Snap to final position
                offsets[ri] = float(final_offsets[ri])
            else:
                # Ease-in-out: fast start, decelerating toward stop frame
                remaining = STOP_FRAMES[ri] - fi
                offsets[ri] += max(4.0, _SYM_H * 2.5 * (remaining / STOP_FRAMES[ri]))
                offsets[ri] = min(offsets[ri], float(final_offsets[ri]))

            strip = strips[ri]
            rx = MARGIN + ri * (_SYM_W + MARGIN)
            ry = 50  # below header

            # Clipping mask for the reel window
            reel_x0 = rx - 2
            reel_y0 = ry
            reel_x1 = rx + _SYM_W + 2
            reel_y1 = ry + VISIBLE * _SYM_H + (VISIBLE + 1) * MARGIN

            # Reel background
            _rounded_rect(draw, (reel_x0, reel_y0, reel_x1, reel_y1),
                          radius=6, fill=(12, 12, 16), outline=(200, 162, 0), width=2)

            # Draw visible symbols
            px_offset = int(offsets[ri]) % (_SYM_H + MARGIN)
            start_idx = int(offsets[ri]) // (_SYM_H + MARGIN)

            for row in range(VISIBLE + 1):
                idx = (start_idx + row) % len(strip)
                sym_img = sym_imgs[strip[idx]]
                sy = ry + MARGIN + row * (_SYM_H + MARGIN) - px_offset
                if reel_y0 <= sy + _SYM_H and sy <= reel_y1:
                    # Paste into reel area (clip to window)
                    paste_y = max(sy, reel_y0)
                    crop_y0 = paste_y - sy
                    crop_y1 = min(sy + _SYM_H, reel_y1) - sy
                    if crop_y1 > crop_y0:
                        crop = sym_img.crop((0, crop_y0, _SYM_W, crop_y1))
                        bg.paste(crop, (rx, paste_y))

            # Win line indicator (middle row)
            mid_y = ry + MARGIN + _SYM_H + MARGIN // 2
            draw.line([(reel_x0, mid_y), (reel_x1, mid_y)],
                      fill=(255, 230, 0), width=1)

        frames.append(bg.quantize(colors=120, method=Image.Quantize.FASTOCTREE))

    buf = io.BytesIO()
    frames[0].save(
        buf, format="GIF", save_all=True, append_images=frames[1:],
        loop=0, duration=60, optimize=False,
    )
    return buf.getvalue()


# ──────────────────────────────────────────────────────────────────────────────
# Dice GIF generator
# ──────────────────────────────────────────────────────────────────────────────
_PIP_POSITIONS: Dict[int, List[Tuple[float, float]]] = {
    1: [(0.5, 0.5)],
    2: [(0.25, 0.25), (0.75, 0.75)],
    3: [(0.25, 0.25), (0.5, 0.5), (0.75, 0.75)],
    4: [(0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75)],
    5: [(0.25, 0.25), (0.75, 0.25), (0.5, 0.5), (0.25, 0.75), (0.75, 0.75)],
    6: [(0.25, 0.2), (0.75, 0.2), (0.25, 0.5), (0.75, 0.5),
        (0.25, 0.8), (0.75, 0.8)],
}


def _draw_die_face(
    value: int,
    size: int = 180,
    label: Optional[str] = None,
) -> Image.Image:
    """Draw a d6 pip face, or a labelled face if ``label`` is given."""
    img = Image.new("RGB", (size, size), (45, 45, 55))
    draw = ImageDraw.Draw(img)
    pad = 10
    _rounded_rect(draw, (pad, pad, size - pad, size - pad),
                  radius=24, fill=(240, 235, 225), outline=(200, 195, 185), width=3)

    if label is not None:
        # Non-d6: just write the number in the centre
        f = _font(max(18, size // 4))
        _centered_text(draw, size / 2, size / 2, label, f, (30, 30, 30))
    else:
        pip_r = max(7, size // 20)
        pip_col = (30, 30, 30) if value != 1 else (210, 30, 30)
        for fx, fy in _PIP_POSITIONS[value]:
            px = int(pad + fx * (size - 2 * pad))
            py = int(pad + fy * (size - 2 * pad))
            draw.ellipse(
                [px - pip_r, py - pip_r, px + pip_r, py + pip_r],
                fill=pip_col,
            )
    return img


def _make_dice_gif(result: int, sides: int = 6) -> bytes:
    SIZE = 200
    TOTAL = 28
    is_d6 = sides == 6
    frames: List[Image.Image] = []
    durations: List[int] = []

    # Build frame sequence: random rolling faces then freeze on result
    rolling_vals = [random.randint(1, 6) for _ in range(TOTAL - 5)]
    sequence_vals = rolling_vals + [min(result, 6)] * 5  # pip display (1-6)

    for i, disp_val in enumerate(sequence_vals):
        t = i / (TOTAL - 1)
        is_rolling = i < TOTAL - 5

        if is_d6:
            img = _draw_die_face(disp_val, SIZE)
        else:
            # Rolling: show random d6 pip faces; final 5 frames: result as text
            if is_rolling:
                img = _draw_die_face(disp_val, SIZE)
            else:
                img = _draw_die_face(result, SIZE, label=str(result))

        if is_rolling:
            draw = ImageDraw.Draw(img)
            for _ in range(3):
                lx = random.randint(10, SIZE - 10)
                draw.line(
                    [(lx, 10), (lx + 5, SIZE - 10)],
                    fill=(150, 145, 140), width=1,
                )

        frames.append(img.quantize(colors=64, method=Image.Quantize.FASTOCTREE))
        durations.append(int(30 + 200 * (t ** 2)))

    buf = io.BytesIO()
    frames[0].save(
        buf, format="GIF", save_all=True, append_images=frames[1:],
        loop=0, duration=durations, optimize=False,
    )
    return buf.getvalue()


# ──────────────────────────────────────────────────────────────────────────────
# Coin flip GIF generator
# ──────────────────────────────────────────────────────────────────────────────
def _coin_frame(phase: float, heads: bool, size: int = 220) -> Image.Image:
    """
    phase: 0.0 → 1.0 (one full spin)
    Coin shows heads if cos(phase * 2π) > 0, tails otherwise.
    Width squishes to simulate perspective rotation.
    """
    img = Image.new("RGB", (size, size), (28, 28, 35))
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2
    r = size // 2 - 18
    angle = phase * math.pi * 2
    cos_a = abs(math.cos(angle))
    # Which face?
    showing_heads = math.cos(angle) > 0  # positive half = heads side

    face_color = (210, 175, 0) if showing_heads else (170, 170, 185)
    edge_color = (150, 120, 0) if showing_heads else (120, 120, 140)
    x_radius = max(4, int(r * cos_a))

    # Edge depth
    draw.ellipse(
        [cx - x_radius - 4, cy - r - 4, cx + x_radius + 4, cy + r + 4],
        fill=edge_color,
    )
    # Main face
    draw.ellipse(
        [cx - x_radius, cy - r, cx + x_radius, cy + r],
        fill=face_color,
    )

    # Label
    if cos_a > 0.15:
        label = "HEADS" if showing_heads else "TAILS"
        f = _font(max(10, int(22 * cos_a)))
        _centered_text(draw, cx, cy, label, f, (255, 255, 220) if showing_heads else (50, 50, 60))
        # Ring detail
        inner_x = max(2, int((x_radius - 8) * cos_a / max(cos_a, 0.01)))
        if inner_x > 4:
            draw.ellipse(
                [cx - inner_x, cy - r + 8, cx + inner_x, cy + r - 8],
                outline=(255, 220, 80) if showing_heads else (200, 200, 210),
                width=2,
            )

    return img


def _make_coin_gif(heads: bool) -> bytes:
    TOTAL = 32
    FULL_SPINS = 4
    SIZE = 220
    frames: List[Image.Image] = []
    durations: List[int] = []

    for i in range(TOTAL):
        t = i / (TOTAL - 1)
        ease = 1.0 - (1.0 - t) ** 3

        # End phase must show the correct face: heads → phase ends at 0 (cos=1)
        # tails → phase ends at 0.5 (cos=-1)
        end_phase = 0.0 if heads else 0.5
        phase = ease * (FULL_SPINS + end_phase)

        img = _coin_frame(phase, heads, SIZE)
        frames.append(img.quantize(colors=80, method=Image.Quantize.FASTOCTREE))
        durations.append(int(20 + 120 * (t ** 2)))

    buf = io.BytesIO()
    frames[0].save(
        buf, format="GIF", save_all=True, append_images=frames[1:],
        loop=0, duration=durations, optimize=False,
    )
    return buf.getvalue()


# ──────────────────────────────────────────────────────────────────────────────
# Cog
# ──────────────────────────────────────────────────────────────────────────────
class Gambling(commands.Cog):
    """Casino-style gambling games with animated visuals.  No currency required."""

    def __init__(self, bot) -> None:
        self.bot = bot
        # user_id -> {deck, player, dealer, over}
        self._bj_sessions: Dict[int, Dict] = {}
        # user_id -> {card, deck}
        self._hl_sessions: Dict[int, Dict] = {}

    # ── Error handler ─────────────────────────────────────────────────────────
    async def cog_command_error(
        self, ctx: commands.Context, error: commands.CommandError
    ) -> None:
        if isinstance(error, commands.BadArgument):
            await ctx.send(str(error))
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send_help(ctx.command)
        else:
            raise error

    # ── Roulette ──────────────────────────────────────────────────────────────
    @commands.command(name="roulette")
    @commands.cooldown(1, 8, commands.BucketType.user)
    async def cmd_roulette(self, ctx: commands.Context) -> None:
        """Spin the European roulette wheel.

        The ball is dropped, the wheel spins, and whatever slot it lands on
        is your result.  No bets — just pure spin.
        """
        winning = random.choice(WHEEL_ORDER)
        async with ctx.typing():
            loop = asyncio.get_running_loop()
            gif_bytes = await loop.run_in_executor(
                None, functools.partial(_make_roulette_gif, winning)
            )

        color_name = (
            "🟢 Green" if winning == 0
            else "🔴 Red" if winning in RED_SLOTS
            else "⚫ Black"
        )
        parity = "Even" if winning != 0 and winning % 2 == 0 else "Odd" if winning != 0 else "—"
        dozen = (
            "1st dozen (1-12)" if 1 <= winning <= 12
            else "2nd dozen (13-24)" if 13 <= winning <= 24
            else "3rd dozen (25-36)" if 25 <= winning <= 36
            else "—"
        )
        half = (
            "Low (1-18)" if 1 <= winning <= 18
            else "High (19-36)" if 19 <= winning <= 36
            else "—"
        )

        embed = discord.Embed(
            title="🎡 Roulette",
            color=discord.Color.green() if winning == 0
            else discord.Color.red() if winning in RED_SLOTS
            else discord.Color.dark_gray(),
        )
        embed.add_field(name="Result", value=f"**{winning}**", inline=True)
        embed.add_field(name="Colour", value=color_name, inline=True)
        embed.add_field(name="Parity", value=parity, inline=True)
        embed.add_field(name="Dozen", value=dozen, inline=True)
        embed.add_field(name="Half", value=half, inline=True)
        embed.set_image(url="attachment://roulette.gif")

        file = discord.File(io.BytesIO(gif_bytes), filename="roulette.gif")
        await ctx.send(embed=embed, file=file)

    # ── Slots ─────────────────────────────────────────────────────────────────
    @commands.command(name="slots")
    @commands.cooldown(1, 6, commands.BucketType.user)
    async def cmd_slots(self, ctx: commands.Context) -> None:
        """Pull the slot machine lever.

        Three reels spin and stop one by one.
        Three of a kind → jackpot.  Two of a kind → nice.  Else → rough luck.
        """
        r0, r1, r2 = (
            random.randint(0, len(SYMBOLS) - 1),
            random.randint(0, len(SYMBOLS) - 1),
            random.randint(0, len(SYMBOLS) - 1),
        )
        # Slight weighting: jackpot ~5 % of the time
        if random.random() < 0.05:
            r1 = r2 = r0

        async with ctx.typing():
            loop = asyncio.get_running_loop()
            gif_bytes = await loop.run_in_executor(
                None, functools.partial(_make_slots_gif, r0, r1, r2)
            )

        names = [SYMBOLS[r0][0], SYMBOLS[r1][0], SYMBOLS[r2][0]]
        if r0 == r1 == r2:
            outcome = f"🎉 **JACKPOT!** Three `{names[0]}` in a row!"
            col = discord.Color.gold()
        elif r0 == r1 or r1 == r2 or r0 == r2:
            outcome = f"✨ **Two of a kind!**  `{'  '.join(names)}`"
            col = discord.Color.blurple()
        else:
            outcome = f"❌ **No match.**  `{'  '.join(names)}`"
            col = discord.Color.dark_gray()

        embed = discord.Embed(title="🎰 Slots", description=outcome, color=col)
        embed.set_image(url="attachment://slots.gif")
        file = discord.File(io.BytesIO(gif_bytes), filename="slots.gif")
        await ctx.send(embed=embed, file=file)

    # ── Dice ──────────────────────────────────────────────────────────────────
    @commands.command(name="dice", aliases=["roll"])
    @commands.cooldown(1, 4, commands.BucketType.user)
    async def cmd_dice(self, ctx: commands.Context, sides: int = 6) -> None:
        """Roll a die.

        `[p]dice` — standard d6
        `[p]dice 20` — d20
        `[p]dice 100` — d100
        """
        if sides < 2:
            return await ctx.send("A die needs at least 2 sides.")
        if sides > 1000:
            return await ctx.send("Let's keep it under 1000 sides.")
        result = random.randint(1, sides)

        async with ctx.typing():
            loop = asyncio.get_running_loop()
            gif_bytes = await loop.run_in_executor(
                None, functools.partial(_make_dice_gif, min(result, 6), sides)
            )

        embed = discord.Embed(
            title=f"🎲 d{sides}",
            description=f"Rolled a **{result}**!",
            color=discord.Color.blurple(),
        )
        embed.set_image(url="attachment://dice.gif")
        file = discord.File(io.BytesIO(gif_bytes), filename="dice.gif")
        await ctx.send(embed=embed, file=file)

    # ── Coin flip ─────────────────────────────────────────────────────────────
    @commands.command(name="coinflip", aliases=["flip", "coin"])
    @commands.cooldown(1, 4, commands.BucketType.user)
    async def cmd_coinflip(self, ctx: commands.Context) -> None:
        """Flip a coin — heads or tails."""
        heads = random.random() < 0.5
        async with ctx.typing():
            loop = asyncio.get_running_loop()
            gif_bytes = await loop.run_in_executor(
                None, functools.partial(_make_coin_gif, heads)
            )

        label = "**HEADS** 🪙" if heads else "**TAILS** 🟫"
        embed = discord.Embed(
            title="🪙 Coin Flip",
            description=f"It landed on {label}!",
            color=discord.Color.gold() if heads else discord.Color.greyple(),
        )
        embed.set_image(url="attachment://coin.gif")
        file = discord.File(io.BytesIO(gif_bytes), filename="coin.gif")
        await ctx.send(embed=embed, file=file)

    # ── Blackjack ─────────────────────────────────────────────────────────────
    @commands.command(name="blackjack", aliases=["bj", "21"])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def cmd_blackjack(self, ctx: commands.Context) -> None:
        """Start a game of Blackjack against the dealer.

        After dealing, use `[p]hit` to draw another card or `[p]stand` to hold.
        Closest to 21 without going over wins.  Dealer stands on 17.
        """
        uid = ctx.author.id
        deck = _new_deck()
        player = [deck.pop(), deck.pop()]
        dealer = [deck.pop(), deck.pop()]
        self._bj_sessions[uid] = {
            "deck": deck,
            "player": player,
            "dealer": dealer,
            "over": False,
        }

        pval = _hand_value(player)
        embed = self._bj_embed(ctx, player, dealer, show_dealer_hole=False)

        if pval == 21:
            embed = self._bj_embed(ctx, player, dealer, show_dealer_hole=True)
            dval = _hand_value(dealer)
            if dval == 21:
                result = "🤝 Both have Blackjack — **Push!**"
            else:
                result = "🃏 **Blackjack! You win!**"
            embed.add_field(name="Result", value=result, inline=False)
            self._bj_sessions.pop(uid, None)
        else:
            embed.add_field(
                name="Your turn",
                value=f"Use `{ctx.clean_prefix}hit` to draw or `{ctx.clean_prefix}stand` to hold.",
                inline=False,
            )

        await ctx.send(embed=embed)

    @commands.command(name="hit")
    async def cmd_hit(self, ctx: commands.Context) -> None:
        """Draw another card in your active Blackjack game."""
        uid = ctx.author.id
        sess = self._bj_sessions.get(uid)
        if not sess:
            return await ctx.send(
                f"No active game. Start one with `{ctx.clean_prefix}blackjack`."
            )
        if sess["over"]:
            return await ctx.send("That game is already finished.")

        sess["player"].append(sess["deck"].pop())
        pval = _hand_value(sess["player"])
        embed = self._bj_embed(ctx, sess["player"], sess["dealer"], show_dealer_hole=False)

        if pval > 21:
            embed = self._bj_embed(ctx, sess["player"], sess["dealer"], show_dealer_hole=True)
            embed.add_field(name="Result", value="💥 **Bust! You went over 21.**", inline=False)
            sess["over"] = True
            self._bj_sessions.pop(uid, None)
        elif pval == 21:
            await ctx.send(embed=embed)
            await self._dealer_play(ctx, sess)
            return
        else:
            embed.add_field(
                name="Your turn",
                value=f"`{ctx.clean_prefix}hit` for another card · `{ctx.clean_prefix}stand` to hold",
                inline=False,
            )

        await ctx.send(embed=embed)

    @commands.command(name="stand")
    async def cmd_stand(self, ctx: commands.Context) -> None:
        """Hold your hand and let the dealer play."""
        uid = ctx.author.id
        sess = self._bj_sessions.get(uid)
        if not sess:
            return await ctx.send(
                f"No active game. Start one with `{ctx.clean_prefix}blackjack`."
            )
        if sess["over"]:
            return await ctx.send("That game is already finished.")
        await self._dealer_play(ctx, sess)

    async def _dealer_play(self, ctx: commands.Context, sess: Dict) -> None:
        uid = ctx.author.id
        dealer, deck, player = sess["dealer"], sess["deck"], sess["player"]
        while _hand_value(dealer) < 17:
            dealer.append(deck.pop())
        pval = _hand_value(player)
        dval = _hand_value(dealer)
        if dval > 21:
            result = "🎉 **Dealer bust — you win!**"
        elif pval > dval:
            result = f"🏆 **You win!** ({pval} vs {dval})"
        elif pval < dval:
            result = f"💀 **Dealer wins.** ({dval} vs {pval})"
        else:
            result = f"🤝 **Push!** Both have {pval}."
        embed = self._bj_embed(ctx, player, dealer, show_dealer_hole=True)
        embed.add_field(name="Result", value=result, inline=False)
        self._bj_sessions.pop(uid, None)
        await ctx.send(embed=embed)

    def _bj_embed(
        self,
        ctx: commands.Context,
        player: List,
        dealer: List,
        show_dealer_hole: bool,
    ) -> discord.Embed:
        pval = _hand_value(player)
        embed = discord.Embed(title="🃏 Blackjack", color=discord.Color.dark_green())
        if show_dealer_hole:
            dval = _hand_value(dealer)
            embed.add_field(
                name=f"Dealer — {dval}",
                value=_hand_str(dealer),
                inline=False,
            )
        else:
            embed.add_field(
                name="Dealer",
                value=f"{_card_str(dealer[0])}  ??",
                inline=False,
            )
        embed.add_field(
            name=f"You — {pval}",
            value=_hand_str(player),
            inline=False,
        )
        return embed

    # ── Crash ─────────────────────────────────────────────────────────────────
    @commands.command(name="crash")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def cmd_crash(self, ctx: commands.Context) -> None:
        """Watch the multiplier climb — until it crashes.

        The multiplier rises each second.  It crashes at a random point.
        See how high it gets before it blows up.
        """
        # Crash point: exponential distribution so most crash early, but
        # occasionally it flies high.
        crash_at = round(max(1.01, random.expovariate(0.6) + 1.0), 2)
        step = 0.10
        current = 1.00

        embed = discord.Embed(
            title="💥 Crash",
            description="🚀 Multiplier is climbing...",
            color=discord.Color.green(),
        )
        msg = await ctx.send(embed=embed)

        while current < crash_at:
            await asyncio.sleep(0.8)
            current = round(current + step, 2)
            step = round(step * 1.07, 3)  # acceleration
            pct = current / crash_at
            bar_filled = int(pct * 12)
            bar = "▓" * bar_filled + "░" * (12 - bar_filled)
            color = (
                discord.Color.green() if pct < 0.6
                else discord.Color.orange() if pct < 0.85
                else discord.Color.red()
            )
            embed = discord.Embed(
                title="💥 Crash",
                description=f"**{current:.2f}×**  `[{bar}]`",
                color=color,
            )
            try:
                await msg.edit(embed=embed)
            except discord.HTTPException:
                break

        embed = discord.Embed(
            title="💥 Crash",
            description=f"**💣 CRASHED at {crash_at:.2f}×**",
            color=discord.Color.dark_red(),
        )
        try:
            await msg.edit(embed=embed)
        except discord.HTTPException:
            await ctx.send(embed=embed)

    # ── High-Low ──────────────────────────────────────────────────────────────
    @commands.command(name="highlow", aliases=["hilo", "hl"])
    @commands.cooldown(1, 4, commands.BucketType.user)
    async def cmd_highlow(
        self, ctx: commands.Context, guess: Optional[str] = None
    ) -> None:
        """Guess whether the next card is higher or lower.

        `[p]highlow` — start a new game (shows your first card)
        `[p]highlow higher` — guess the next card is higher
        `[p]highlow lower` — guess the next card is lower
        Aces are always high (14).  Ties count as a win for you.
        """
        uid = ctx.author.id

        if guess is None:
            # Start or reset
            deck = _new_deck()
            card = deck.pop()
            self._hl_sessions[uid] = {"card": card, "deck": deck, "streak": 0}
            embed = discord.Embed(
                title="🃏 High-Low",
                description=(
                    f"Your card: **{_card_str(card)}**\n\n"
                    f"Will the next card be **higher** or **lower**?\n"
                    f"`{ctx.clean_prefix}highlow higher` · `{ctx.clean_prefix}highlow lower`"
                ),
                color=discord.Color.blurple(),
            )
            embed.set_footer(text="Aces = 14.  Ties count in your favour.")
            return await ctx.send(embed=embed)

        guess = guess.lower()
        if guess not in ("higher", "lower", "h", "l", "high", "low"):
            return await ctx.send(
                f"Say `{ctx.clean_prefix}highlow higher` or `{ctx.clean_prefix}highlow lower`."
            )
        guess_higher = guess in ("higher", "h", "high")

        sess = self._hl_sessions.get(uid)
        if not sess:
            return await ctx.send(
                f"Start a game first with `{ctx.clean_prefix}highlow`."
            )

        old_card = sess["card"]
        if not sess["deck"]:
            sess["deck"] = _new_deck()
        new_card = sess["deck"].pop()

        old_val = RANK_ORDER[old_card[0]]
        new_val = RANK_ORDER[new_card[0]]

        actually_higher = new_val >= old_val   # ties = win for player

        won = (guess_higher and actually_higher) or (not guess_higher and not actually_higher)

        if won:
            sess["streak"] += 1
            sess["card"] = new_card
            direction = "higher" if new_val > old_val else "same (tie — still a win!)"
            embed = discord.Embed(
                title="🃏 High-Low",
                description=(
                    f"**{_card_str(old_card)}** → **{_card_str(new_card)}** — {direction}\n"
                    f"✅ **Correct!** Streak: **{sess['streak']}**\n\n"
                    f"Go again?\n"
                    f"`{ctx.clean_prefix}highlow higher` · `{ctx.clean_prefix}highlow lower`"
                ),
                color=discord.Color.green(),
            )
        else:
            streak = sess["streak"]
            direction = "lower" if new_val < old_val else "higher"
            embed = discord.Embed(
                title="🃏 High-Low",
                description=(
                    f"**{_card_str(old_card)}** → **{_card_str(new_card)}** — was {direction}\n"
                    f"❌ **Wrong!** You ended with a streak of **{streak}**.\n\n"
                    f"Start fresh: `{ctx.clean_prefix}highlow`"
                ),
                color=discord.Color.red(),
            )
            self._hl_sessions.pop(uid, None)

        await ctx.send(embed=embed)
