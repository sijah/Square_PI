#!/usr/bin/env python3
# Screen renderers for the 4 primary display screens (see [[project-local-display]]).
# Each function returns a 160x128 RGB PIL Image ready for disp.image().
import os

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 160, 128

_FONT_PATH = os.path.join(os.path.dirname(__file__), "fonts", "DejaVuSans-Bold.ttf")
_font_cache = {}


def _font(size):
    if size not in _font_cache:
        _font_cache[size] = ImageFont.truetype(_FONT_PATH, size)
    return _font_cache[size]


BG = (0, 0, 0)
FG = (255, 255, 255)
DIM = (130, 130, 130)
DIMMER = (70, 70, 70)
MPD_ACCENT = (29, 158, 117)
BT_ACCENT = (55, 138, 221)
EQ_ACCENT = (60, 52, 137)
EQ_ACCENT_TEXT = (238, 237, 254)
BAR_BG = (42, 42, 42)

METER_SEGMENTS = 8
METER_SEG_H = 12
METER_SEG_GAP = 3
METER_BOTTOM_Y = 118
METER_GREEN_TOP_INDEX = 4   # segments 0-4 green
METER_AMBER_TOP_INDEX = 6   # segments 5-6 amber, 7 red


def _seg_color(index):
    if index <= METER_GREEN_TOP_INDEX:
        return (34, 197, 60)
    if index <= METER_AMBER_TOP_INDEX:
        return (250, 210, 35)
    return (235, 55, 45)


def _draw_meter_column(draw, x, lit_count):
    for i in range(METER_SEGMENTS):
        y = METER_BOTTOM_Y - i * (METER_SEG_H + METER_SEG_GAP) - METER_SEG_H
        color = _seg_color(i) if i < lit_count else BAR_BG
        draw.rectangle((x, y, x + 16, y + METER_SEG_H), fill=color)


def _elide(draw, font, text, max_width):
    if draw.textlength(text, font=font) <= max_width:
        return text
    while text and draw.textlength(text + "...", font=font) > max_width:
        text = text[:-1]
    return (text + "...") if text else ""


def _fmt_time(seconds):
    seconds = int(seconds or 0)
    return f"{seconds // 60}:{seconds % 60:02d}"


def render_now_playing(now_playing, vu_levels=None):
    """now_playing: dict from audio_control.get_now_playing().
    vu_levels: (left, right) each 0-100, or None to omit the meter entirely
    (used for non-MPD sources / not playing -- see [[project-local-display]])."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)

    source = now_playing.get("source")
    playing = now_playing.get("playing")
    title = now_playing.get("title") or "Nothing playing"
    artist = now_playing.get("artist") or ""

    show_meter = vu_levels is not None and source == "MPD" and playing
    text_left = 56 if show_meter else 10

    if show_meter:
        left, right = vu_levels
        lit_left = round(max(0, min(100, left)) / 100 * METER_SEGMENTS)
        lit_right = round(max(0, min(100, right)) / 100 * METER_SEGMENTS)
        _draw_meter_column(draw, 10, lit_left)
        _draw_meter_column(draw, 30, lit_right)

    if source:
        badge_color = MPD_ACCENT if source == "MPD" else BT_ACCENT
        label = "MPD" if source == "MPD" else "BT"
        draw.rounded_rectangle((text_left, 6, text_left + 40, 24), radius=9, fill=badge_color)
        draw.text((text_left + 20, 15), label, font=_font(11), fill=BG, anchor="mm")

    title_font = _font(15)
    artist_font = _font(12)
    max_w = WIDTH - text_left - 6
    draw.text((text_left, 40), _elide(draw, title_font, title, max_w), font=title_font, fill=FG)
    if artist:
        draw.text((text_left, 62), _elide(draw, artist_font, artist, max_w), font=artist_font, fill=DIM)

    if source == "MPD" and now_playing.get("duration"):
        elapsed = now_playing.get("elapsed") or 0
        duration = now_playing.get("duration") or 1
        frac = max(0.0, min(1.0, elapsed / duration))
        bar_x0, bar_x1, bar_y = text_left, WIDTH - 6, 98
        draw.rectangle((bar_x0, bar_y, bar_x1, bar_y + 4), fill=BAR_BG)
        draw.rectangle((bar_x0, bar_y, bar_x0 + int((bar_x1 - bar_x0) * frac), bar_y + 4), fill=MPD_ACCENT)
        draw.text((bar_x0, bar_y + 8), _fmt_time(elapsed), font=_font(10), fill=DIM)
        draw.text((bar_x1, bar_y + 8), _fmt_time(duration), font=_font(10), fill=DIM, anchor="ra")
    elif source == "Bluetooth" and playing:
        draw.ellipse((text_left, 96, text_left + 8, 104), fill=BT_ACCENT)

    return img


def render_volume(label, pct, accent):
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    draw.text((WIDTH // 2, 26), label, font=_font(13), fill=accent, anchor="mm")
    draw.text((WIDTH // 2, 60), f"{pct}%", font=_font(30), fill=FG, anchor="mm")
    bar_x0, bar_x1, bar_y = 20, WIDTH - 20, 92
    draw.rectangle((bar_x0, bar_y, bar_x1, bar_y + 8), fill=BAR_BG)
    fill_w = int((bar_x1 - bar_x0) * max(0, min(100, pct)) / 100)
    draw.rectangle((bar_x0, bar_y, bar_x0 + fill_w, bar_y + 8), fill=accent)
    return img


def render_mpd_volume(pct):
    return render_volume("MPD VOLUME", pct, MPD_ACCENT)


def render_bt_volume(pct):
    return render_volume("BT VOLUME", pct, BT_ACCENT)


def render_eq_preset(preset_names, selected_index):
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    row_h = 30
    center_y = HEIGHT // 2
    for offset in (-1, 0, 1):
        idx = selected_index + offset
        if idx < 0 or idx >= len(preset_names):
            continue
        y = center_y + offset * row_h
        if offset == 0:
            draw.rounded_rectangle((6, y - 15, WIDTH - 6, y + 15), radius=4, fill=EQ_ACCENT)
            draw.text((WIDTH // 2, y), preset_names[idx], font=_font(14), fill=EQ_ACCENT_TEXT, anchor="mm")
        else:
            color = DIM if abs(offset) == 1 else DIMMER
            draw.text((WIDTH // 2, y), preset_names[idx], font=_font(12), fill=color, anchor="mm")
    return img
