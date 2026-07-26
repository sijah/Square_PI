#!/usr/bin/env python3
# Screen renderers for the local display (see [[project-local-display]]).
# Each function returns a 160x128 RGB PIL Image ready for disp.image().
#
# Redesigned for 2.0.0 against a premium-streamer reference: one accent colour,
# a persistent status strip, hairline rules instead of filled panels, and
# tabular numerals for anything numeric. Deliberately NOT in this version --
# album art and manual band editing (both deferred by the user).
#
# Every renderer is a pure function of its arguments: no I/O, no clock reads, no
# module state. Scroll/selection/animation state lives in main.py so these stay
# testable headless on a dev box with no GPIO. The marquee follows that rule too:
# marquee_offset() converts an elapsed time to a pixel offset without keeping any
# state of its own, and the caller passes the result in as `scroll`.
import os
import unicodedata

from PIL import Image, ImageDraw, ImageFont

import script_fonts

WIDTH, HEIGHT = 160, 128

_FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
# Three cuts, three jobs. Before 2.0.0 only the bold face was bundled, so every
# glyph on the panel was bold -- which is most of why it read as a hobby project
# rather than a product. Mono is here for numerals: it's the only bundled face
# with uniform digit widths, so a counting value doesn't jitter sideways.
_F_REG = os.path.join(_FONT_DIR, "DejaVuSans.ttf")
_F_BOLD = os.path.join(_FONT_DIR, "DejaVuSans-Bold.ttf")
_F_MONO = os.path.join(_FONT_DIR, "DejaVuSansMono-Bold.ttf")
_font_cache = {}


def _font(path, size):
    key = (path, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(path, size)
    return _font_cache[key]


def reg(size):
    return _font(_F_REG, size)


def bold(size):
    return _font(_F_BOLD, size)


def mono(size):
    return _font(_F_MONO, size)


# One accent, not three. Source is communicated by a word, never by hue --
# colour-coding MPD green / BT blue / EQ purple is what made the old screens read
# as a debug tool.
BG = (6, 10, 11)
PANEL = (16, 24, 26)
FG = (238, 244, 245)
DIM = (128, 142, 145)
DIMMER = (68, 80, 82)
RULE = (30, 42, 44)
ACCENT = (45, 212, 191)
ACCENT_DEEP = (16, 94, 88)
METER = (200, 205, 210)
WARN = (250, 204, 21)
HOT = (239, 68, 68)


def _canvas():
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    return img, ImageDraw.Draw(img)


def _elide(draw, font, text, max_width):
    if _measure(text, font) <= max_width:
        return text
    while text and _measure(text + "…", font) > max_width:
        text = _trim_one(text)
    return (text + "…") if text else ""


# --------------------------------------------------- user metadata (any script)
# Track titles arrive from MPD tags in whatever script they were tagged in. Pillow
# has no font fallback, so drawing Malayalam with DejaVu produces .notdef boxes
# silently; these three helpers pick a font per script run instead. Chrome never
# goes through them -- it is ASCII by construction and uses the bundled faces
# directly. See script_fonts.py for why one font could not cover all three scripts.

def _run_font(tag, font):
    """The face to draw a run with: a script font at the same size and weight as the
    caller's Latin font, or that Latin font when the run is Latin (or when no script
    font is installed, in which case boxes are the honest outcome)."""
    if tag is None:
        return font
    # Named want_bold, not bold: `bold` is this module's font accessor and shadowing
    # it inside a helper that picks fonts is asking for trouble later.
    want_bold = "Bold" in getattr(font, "path", "")
    return script_fonts.font_for(tag, font.size, bold=want_bold) or font


_measure_cache = {}


def _measure(text, font):
    """Width of `text` if drawn by _draw_text. Must agree with it exactly, or
    elision and the marquee will disagree with what lands on the panel.

    Memoised: the marquee measures the current title two or three times per frame
    (period, then offset, then the draw) at up to 12 frames a second, and for a
    mixed-script string each measurement walks the runs. The same handful of strings
    recur every frame, so the hit rate is effectively 100%."""
    key = (text, getattr(font, "path", ""), font.size)
    hit = _measure_cache.get(key)
    if hit is not None:
        return hit
    if not script_fonts.has_complex(text):
        width = font.getlength(text)
    else:
        width = sum(_run_font(tag, font).getlength(run)
                    for tag, run in script_fonts.runs(text))
    if len(_measure_cache) > 256:
        # Bounded, and cheap to rebuild: elision walks a string one character at a
        # time, so a long queue of long titles would otherwise grow this without end.
        _measure_cache.clear()
    _measure_cache[key] = width
    return width


def _draw_text(draw, xy, text, font, fill, anchor=None):
    """Drop-in for draw.text() that switches font per script run.

    Runs are drawn left to right at accumulated advances. Only the fast path
    (all-Latin, which is every string on a Latin-tagged library) touches draw.text
    directly, so nothing about existing behaviour changes."""
    x, y = xy
    if not script_fonts.has_complex(text):
        draw.text((x, y), text, font=font, fill=fill, anchor=anchor)
        return
    if anchor == "ra":
        x -= _measure(text, font)
        anchor = None
    for tag, run in script_fonts.runs(text):
        rf = _run_font(tag, font)
        draw.text((x, y), run, font=rf, fill=fill, anchor=anchor)
        x += rf.getlength(run)


def _trim_one(text):
    """Drop one character from the end without splitting a grapheme cluster.

    Cutting between a consonant and its vowel sign leaves a mark orphaned onto
    whatever follows, so combining marks come off together with their base."""
    text = text[:-1]
    # Both mark categories have to be tested. Non-spacing marks (Mn) mostly carry a
    # non-zero combining class, but many Indic vowel signs are *spacing* marks (Mc)
    # with class 0 -- checking combining() alone would leave those stranded, which is
    # exactly the case this function exists for. A trailing virama is Mn and comes
    # off the same way: a half-form whose consonant is gone is not a character.
    while text and (unicodedata.combining(text[-1])
                    or unicodedata.category(text[-1]) in ("Mn", "Mc")):
        text = text[:-1]
    return text


def _caps(draw, x, y, text, font, fill, tracking=1.0):
    """All-caps micro-label with letterspacing, drawn glyph by glyph because PIL
    has no tracking. y is the vertical centre. Returns the advance width."""
    cx = x
    for ch in text:
        draw.text((cx, y), ch, font=font, fill=fill, anchor="lm")
        cx += draw.textlength(ch, font=font) + tracking
    return cx - x - tracking


def _caps_width(draw, text, font, tracking=1.0):
    if not text:
        return 0
    return sum(draw.textlength(c, font=font) for c in text) + tracking * (len(text) - 1)


def _caps_centred(draw, y, text, font, fill, tracking=1.0):
    w = _caps_width(draw, text, font, tracking)
    _caps(draw, (WIDTH - w) / 2, y, text, font, fill, tracking)


# ------------------------------------------------------------------- marquee
# Tuning. Speed is a trade against the tick rate: the step per frame is
# PX_PER_S * tick, and anything past ~2.5 px reads as juddering rather than sliding
# at this font size. 26 px/s against main.py's 0.08 s tick lands on 2.1 px.
#
# It also trades against loop time. A pathological 490px title (a remaster with a
# parenthetical) takes text_w/PX_PER_S to pass by, so at 20 px/s the loop ran 27 s
# and a glance at the panel showed a mid-word fragment with no context. 26 px/s
# brings the worst case to ~21 s and typical overflow to well under 10 s.
MARQUEE_PX_PER_S = 26.0
MARQUEE_GAP = 26        # blank run between the tail and the wrapped-around head
MARQUEE_HOLD_S = 1.8    # pause at the start of every loop, so the head is readable
MARQUEE_FADE = 10       # edge fade width; hides the hard clip mid-glyph
# 24, not the 21 that fitted DejaVu. Measured at bold(15): Latin ink occupies rows
# 3..16, but Malayalam reaches row 0 and Devanagari row 20 -- above-base vowel signs
# and below-base conjuncts use the room Latin leaves empty, so both sat flush against
# a 21px tile and a taller cluster would have been clipped. The tile still ends at
# y=42 while the artist line's ink starts at 43, so nothing below is disturbed.
_MARQUEE_TILE_H = 24
_mask_cache = {}


def _marquee_mask(w, h, both_edges):
    """Cached alpha ramp used to fade the marquee's edges into the background.

    A hard clip cuts glyphs mid-stroke, which is the single thing that most makes a
    scrolling label look homemade. Built once per geometry and applied with a C-level
    composite, so the per-frame cost is one blend of a 148x21 image -- doing the same
    ramp with per-pixel Python would be far more expensive than the scroll itself."""
    key = (w, h, both_edges)
    if key not in _mask_cache:
        mask = Image.new("L", (w, h), 255)
        md = ImageDraw.Draw(mask)
        for i in range(MARQUEE_FADE):
            level = int(255 * (i + 1) / (MARQUEE_FADE + 1))
            md.line((w - 1 - i, 0, w - 1 - i, h), fill=level)
            if both_edges:
                md.line((i, 0, i, h), fill=level)
        _mask_cache[key] = mask
    return _mask_cache[key]


def _text_w(text, font):
    # Measured without a canvas: ImageDraw.textlength needs a draw object, but
    # font.getlength is the same metric and callers here have no image yet.
    # Routed through _measure so a Malayalam title's scroll distance is its real
    # width and not DejaVu's idea of it -- the two differ, and the marquee would
    # either stop short of the end or scroll past it into blank space.
    return _measure(text, font)


def marquee_period(text, font, max_w):
    """Seconds for one full loop, or 0 if the text fits and won't scroll."""
    over = _text_w(text, font) - max_w
    if over <= 0:
        return 0.0
    return MARQUEE_HOLD_S + (_text_w(text, font) + MARQUEE_GAP) / MARQUEE_PX_PER_S


def marquee_offset(elapsed, text, font, max_w):
    """Pixel offset for a marquee that has been showing `text` for `elapsed`
    seconds. Returns 0 when the text fits, which is how callers decide whether to
    animate at all -- a title that fits must cost nothing.

    Each loop holds at offset 0 before travelling text_w + GAP, which lands exactly
    back on 0, so the wrap is seamless and the start of the title is always legible
    for a moment."""
    period = marquee_period(text, font, max_w)
    if not period:
        return 0
    phase = float(elapsed) % period
    if phase < MARQUEE_HOLD_S:
        return 0
    return int((phase - MARQUEE_HOLD_S) * MARQUEE_PX_PER_S)


def _marquee(img, x, y, text, font, fill, max_w, offset, height=_MARQUEE_TILE_H):
    """Draw `text` scrolled left by `offset`, clipped to max_w, wrapping around.

    Rendered into a scratch tile and pasted because PIL has no clip region: drawing
    at a negative x on the real canvas would spill over the status strip and the
    artist line. The tile is ~150x21 px, so the per-frame allocation is trivial
    next to the 40 KB SPI write it feeds."""
    if _text_w(text, font) <= max_w:
        # Text that fits is drawn straight, whatever offset arrived -- the offset is
        # advisory. Honouring a stale one would slide a short title sideways for a
        # frame after a track change.
        _draw_text(ImageDraw.Draw(img), (x, y), text, font, fill)
        return
    w = int(max_w)
    tile = Image.new("RGB", (w, height), BG)
    td = ImageDraw.Draw(tile)
    period = _text_w(text, font) + MARQUEE_GAP
    off = offset % period
    _draw_text(td, (-off, 0), text, font, fill)
    # The wrapped copy. Only visible in the last GAP px of the loop, but drawing it
    # unconditionally is cheaper than working out whether it is needed.
    _draw_text(td, (period - off, 0), text, font, fill)
    # Fade the leading edge only once the text has started moving: during the hold
    # phase the first character sits at x=0 and dimming it would be a defect.
    tile = Image.composite(tile, Image.new("RGB", (w, height), BG),
                           _marquee_mask(w, height, both_edges=off > 0))
    img.paste(tile, (int(x), int(y)))


def _hairline(draw, x0, x1, y, fill=RULE):
    draw.line((x0, y, x1, y), fill=fill)


def _fmt_time(seconds):
    seconds = int(seconds or 0)
    return f"{seconds // 60}:{seconds % 60:02d}"


# ------------------------------------------------------------------- chrome

def _icon_bt(draw, x, y, colour):
    draw.line((x + 3, y, x + 3, y + 9), fill=colour)
    draw.line((x + 3, y, x + 6, y + 3), fill=colour)
    draw.line((x + 6, y + 3, x, y + 6), fill=colour)
    draw.line((x + 3, y + 9, x + 6, y + 6), fill=colour)
    draw.line((x + 6, y + 6, x, y + 3), fill=colour)


def _icon_wifi(draw, x, y, colour, bars=3):
    for i in range(bars):
        r = 2 + i * 3
        draw.arc((x + 4 - r, y + 8 - r, x + 4 + r, y + 8 + r), 210, 330, fill=colour)
    draw.point((x + 4, y + 8), fill=colour)


def _statusbar(draw, title, right=None, bt=False, wifi=False):
    """Persistent 13px strip. Costs one row and makes every screen read as part
    of one instrument. The Wi-Fi arcs reach 8px left of their origin, so the two
    icons need 14px of separation -- at 12 they overlap into one blob."""
    _caps(draw, 5, 7, title, bold(9), ACCENT, tracking=1.2)
    x = WIDTH - 13
    if wifi:
        _icon_wifi(draw, x, 1, ACCENT)
        x -= 14
    if bt:
        _icon_bt(draw, x + 2, 1, ACCENT)
    if right:
        draw.text((x - 4, 3), right, font=mono(9), fill=DIM, anchor="ra")
    _hairline(draw, 0, WIDTH, 13)


def _footer(draw, text):
    _hairline(draw, 0, WIDTH, HEIGHT - 13)
    _caps(draw, 5, HEIGHT - 6, text, reg(8), DIMMER, tracking=0.6)


def _badge(draw, x, y, text, colour, font=None):
    font = font or reg(8)
    w = draw.textlength(text, font=font)
    draw.rounded_rectangle((x, y, x + w + 7, y + 12), radius=2, outline=colour)
    draw.text((x + 4, y + 2), text, font=font, fill=colour)
    return x + w + 7


def _tick_scale(draw, x0, x1, y, frac, height=7, step=4, major=5, lit=ACCENT):
    """Fine-tick position scale. 1px ticks with every `major`th at full height;
    the elapsed portion is lit and the rest stays as unlit engraving. Cheaper to
    push over SPI than the filled bar it replaces."""
    count = int((x1 - x0) // step) + 1
    cut = x0 + (x1 - x0) * max(0.0, min(1.0, frac))
    for i in range(count):
        x = x0 + i * step
        tall = (i % major == 0)
        h = height if tall else height - 3
        colour = lit if x <= cut else (DIMMER if tall else RULE)
        draw.line((x, y + (height - h), x, y + height), fill=colour)


def _skip_glyphs(draw, cx, y, colour, spread=26):
    """The prev/next pair, at `spread` px either side of cx.

    Shared by Now Playing's transport row and the overlay's TRACK row so there is
    one skip glyph in the product rather than two that nearly match. Home has drawn
    these since 2.0.0 as pure status; the overlay row is what finally makes them
    mean something."""
    inner = spread - 7
    draw.polygon([(cx - spread, y), (cx - inner, y - 4), (cx - inner, y + 4)], fill=colour)
    draw.line((cx - spread - 1, y - 4, cx - spread - 1, y + 4), fill=colour)
    draw.polygon([(cx + inner, y - 4), (cx + spread, y), (cx + inner, y + 4)], fill=colour)
    draw.line((cx + spread + 1, y - 4, cx + spread + 1, y + 4), fill=colour)


def _transport(draw, cx, y, playing):
    _skip_glyphs(draw, cx, y, DIM)
    if playing:
        draw.rectangle((cx - 3, y - 5, cx - 1, y + 5), fill=ACCENT)
        draw.rectangle((cx + 2, y - 5, cx + 4, y + 5), fill=ACCENT)
    else:
        draw.polygon([(cx - 3, y - 5), (cx + 5, y), (cx - 3, y + 5)], fill=ACCENT)


# ------------------------------------------------------------- 1. NOW PLAYING

def render_now_playing(now_playing, fmt=None, net=None, scroll=0):
    """now_playing: dict from audio_control.get_now_playing().
    fmt: list of short format badges (e.g. ["FLAC", "16bit", "44.1k"]) or None.
    net: dict with 'wifi'/'bt' booleans for the status strip, or None.
    scroll: title marquee offset in px, from marquee_offset(). 0 = no scrolling.

    No album art and no VU columns here -- art was deferred, and metering has its
    own full-screen page now, so this screen is metadata plus position only."""
    img, d = _canvas()
    net = net or {}
    source = now_playing.get("source")
    # "Bluetooth" spelled out overruns the strip once the two icons are there, and
    # the strip is letterspaced caps, which makes it wider still.
    label = {"MPD": "MPD", "Bluetooth": "BT"}.get(source, "SQUAREPI")
    _statusbar(d, label, bt=net.get("bt", False), wifi=net.get("wifi", False))

    title = now_playing.get("title") or "Nothing playing"
    artist = now_playing.get("artist") or ""
    album = now_playing.get("album") or ""
    max_w = WIDTH - 12

    # The title scrolls; artist and album stay elided. Two lines sliding at once
    # reads as a ticker, and the title is the field that actually overruns -- an
    # artist name long enough to clip is rare, and its tail is rarely the useful
    # part ("Featuring…"), where a truncated song title often is.
    _marquee(img, 6, 18, title, bold(15), FG if source else DIM, max_w, scroll)
    if artist:
        _draw_text(d, (6, 40), _elide(d, reg(11), artist, max_w), reg(11), DIM)
    if album:
        _draw_text(d, (6, 55), _elide(d, reg(10), album, max_w), reg(10), DIMMER)

    if fmt:
        x = 6
        for i, text in enumerate(fmt):
            # First badge is the codec and gets the accent; the rest are detail.
            x = _badge(d, x, 70, text, ACCENT if i == 0 else DIMMER) + 4

    if not source:
        # Cold boot with an empty queue. Say how to fix it -- this screen used to
        # be a dead end, which is what the Play screen was added to solve.
        _footer(d, "LONG PRESS · MENU")
        return img

    if now_playing.get("stopped"):
        # A queue is loaded but stopped. Saying "STOPPED" and what to do about it
        # beats the old "Nothing playing", which was actively misleading.
        _transport(d, WIDTH // 2, 92, playing=False)
        _caps(d, 6, 110, "STOPPED", reg(9), DIM, tracking=1.2)
        d.text((WIDTH - 6, 105), "press to play", font=reg(9), fill=DIMMER, anchor="ra")
        return img

    _transport(d, WIDTH // 2, 92, playing=now_playing.get("playing", False))
    duration = now_playing.get("duration") or 0
    elapsed = now_playing.get("elapsed") or 0
    if duration:
        _tick_scale(d, 6, WIDTH - 7, 102, elapsed / duration)
        d.text((6, 114), _fmt_time(elapsed), font=mono(10), fill=FG)
        # Remaining, not duration: it's the number people actually read.
        d.text((WIDTH - 6, 114), "-" + _fmt_time(duration - elapsed),
               font=mono(10), fill=DIM, anchor="ra")
    elif now_playing.get("playing"):
        # Bluetooth: AVRCP position isn't reliable, so show liveness not position
        # (see [[project-bt-avrcp]]).
        d.ellipse((6, 112, 13, 119), fill=ACCENT)
        _caps(d, 19, 116, "PLAYING", reg(8), DIMMER, tracking=1)
    return img


# ------------------------------------------------------- 2. LISTS (menu etc.)

def render_list(title, rows, selected, values=None, footer=None, chevrons=True,
                visible=4, row_h=22, top=18, bt=False, wifi=False):
    """The one list component behind Main Menu and Settings. The selected row is a
    filled panel with a 2px accent edge -- not a full-width pill, which read as a
    chunky mobile list. Cheap to redraw as a single region."""
    img, d = _canvas()
    _statusbar(d, title, bt=bt, wifi=wifi)
    if not rows:
        d.text((WIDTH // 2, 64), "Nothing here", font=reg(12), fill=DIM, anchor="mm")
        return img

    selected = max(0, min(selected, len(rows) - 1))
    first = max(0, min(selected - 1, max(0, len(rows) - visible)))
    for i in range(visible):
        idx = first + i
        if idx >= len(rows):
            break
        y = top + i * row_h
        is_sel = (idx == selected)
        if is_sel:
            d.rectangle((3, y, WIDTH - 4, y + row_h - 3), fill=PANEL)
            d.rectangle((3, y, 5, y + row_h - 3), fill=ACCENT)
        font = bold(11) if is_sel else reg(11)
        _draw_text(d, (13, y + 4), _elide(d, font, rows[idx], 104), font,
               fill=FG if is_sel else DIM)
        if values and values[idx] is not None:
            d.text((WIDTH - 16, y + 5), str(values[idx]), font=mono(9),
                   fill=ACCENT if is_sel else DIMMER, anchor="ra")
        elif chevrons:
            cy = y + row_h // 2 - 1
            colour = ACCENT if is_sel else DIMMER
            d.line((WIDTH - 12, cy - 3, WIDTH - 9, cy), fill=colour)
            d.line((WIDTH - 9, cy, WIDTH - 12, cy + 3), fill=colour)

    if len(rows) > visible:
        # Position pips down the right edge: on a 4-of-N list you otherwise have
        # no idea how long the list is.
        span = HEIGHT - 40
        for idx in range(len(rows)):
            y = 20 + idx * span // max(1, len(rows) - 1)
            d.point((WIDTH - 2, y), fill=ACCENT if idx == selected else DIMMER)
    if footer:
        _footer(d, footer)
    return img


# ----------------------------------------------------------------- 3. PLAY

def render_music(entries, selected, action_count=1, hint=None, bt=False, wifi=False):
    """Flat "pick something and play it" list: the first action_count entries are
    actions (Resume Queue / Shuffle All) and the rest are saved playlists.

    Still deliberately flat. Long press is Back now rather than screen-cycling, so
    a drilldown tree is finally *possible* -- but a 200-album list is unusable on
    an encoder, which is why albums were rejected on their own merits
    (see [[project-local-display]])."""
    img, d = _canvas()
    _statusbar(d, "PLAY", right=f"{selected + 1}/{len(entries)}" if entries else None,
               bt=bt, wifi=wifi)
    if not entries:
        d.text((WIDTH // 2, 60), "MPD unreachable", font=reg(12), fill=DIM, anchor="mm")
        _footer(d, "LONG PRESS · BACK")
        return img

    selected = max(0, min(selected, len(entries) - 1))
    first = max(0, min(selected - 1, max(0, len(entries) - 3)))
    for i in range(3):
        idx = first + i
        if idx >= len(entries):
            break
        y = 20 + i * 25
        is_sel = (idx == selected)
        if is_sel:
            d.rectangle((3, y, WIDTH - 4, y + 22), fill=PANEL)
            d.rectangle((3, y, 5, y + 22), fill=ACCENT)
            _draw_text(d, (13, y + 4), _elide(d, bold(12), entries[idx], 132),
                   font=bold(12), fill=FG)
        else:
            # Actions stay accent-tinted even unselected, so they read as actions
            # rather than as more playlist names.
            colour = ACCENT_DEEP if idx < action_count else DIM
            _draw_text(d, (13, y + 5), _elide(d, reg(11), entries[idx], 132),
                   font=reg(11), fill=colour)
    _footer(d, hint or "PRESS PLAY · LONG BACK")
    return img


# ---------------------------------------------------------------- 4. QUEUE

def render_queue(tracks, selected, bt=False, wifi=False):
    """tracks: list of (title, artist, duration_seconds). Two-line rows, because
    a title alone doesn't disambiguate a 550-track shuffle."""
    img, d = _canvas()
    _statusbar(d, "QUEUE", right=f"{selected + 1}/{len(tracks)}" if tracks else None,
               bt=bt, wifi=wifi)
    if not tracks:
        d.text((WIDTH // 2, 60), "Queue is empty", font=reg(12), fill=DIM, anchor="mm")
        _footer(d, "ADD FROM PLAY SCREEN")
        return img

    selected = max(0, min(selected, len(tracks) - 1))
    first = max(0, min(selected - 1, max(0, len(tracks) - 4)))
    for i in range(4):
        idx = first + i
        if idx >= len(tracks):
            break
        title, artist, dur = tracks[idx]
        y = 16 + i * 25
        is_sel = (idx == selected)
        if is_sel:
            d.rectangle((3, y, WIDTH - 4, y + 22), fill=PANEL)
            d.rectangle((3, y, 5, y + 22), fill=ACCENT)
            d.polygon([(11, y + 6), (16, y + 10), (11, y + 14)], fill=ACCENT)
        else:
            d.text((9, y + 5), str(idx + 1), font=mono(9), fill=DIMMER)
        font = bold(10) if is_sel else reg(10)
        _draw_text(d, (21, y + 2), _elide(d, font, title, 82), font,
               fill=FG if is_sel else DIM)
        _draw_text(d, (21, y + 13), _elide(d, reg(8), artist or "", 82), reg(8), DIMMER)
        d.text((WIDTH - 6, y + 7), _fmt_time(dur), font=mono(9),
               fill=ACCENT if is_sel else DIMMER, anchor="ra")
    return img


# ------------------------------------------------------------- 5. EQ PRESETS

def render_eq_presets(names, selected, applied=None, bt=False, wifi=False,
                      custom_from=None):
    """Presets only -- no band editing, by decision: the panel applies presets and
    the web UI builds them. `applied` marks the one currently in effect, if known.

    custom_from: index at which presets saved in the web UI begin, or None. They get
    a small mark rather than a heading row: on a four-row window a heading could be
    the only thing visible after a scroll, and the mark travels with its row."""
    img, d = _canvas()
    _statusbar(d, "EQ PRESET", right=f"{selected + 1}/{len(names)}" if names else None,
               bt=bt, wifi=wifi)
    if not names:
        d.text((WIDTH // 2, 60), "No presets", font=reg(12), fill=DIM, anchor="mm")
        return img

    selected = max(0, min(selected, len(names) - 1))
    first = max(0, min(selected - 1, max(0, len(names) - 4)))
    for i in range(4):
        idx = first + i
        if idx >= len(names):
            break
        y = 18 + i * 22
        is_sel = (idx == selected)
        if is_sel:
            d.rectangle((3, y, WIDTH - 4, y + 19), fill=PANEL)
            d.rectangle((3, y, 5, y + 19), fill=ACCENT)
        font = bold(11) if is_sel else reg(11)
        is_custom = custom_from is not None and idx >= custom_from
        if is_custom and not is_sel:
            # Two-pixel tick in the left margin: enough to separate yours from the
            # built-ins without spending a column of text width on a label. Hidden on
            # the selected row, where it sits 1px from the selection bar and the two
            # read as one muddy double-rule. The indent stays either way, so names
            # don't shift as the cursor passes.
            d.rectangle((8, y + 6, 9, y + 13), fill=ACCENT_DEEP)
        # Customs start 5px further right to clear the tick; built-ins are unmoved.
        _draw_text(d, (18 if is_custom else 13, y + 3),
                   _elide(d, font, names[idx], 113 if is_custom else 118), font,
                   fill=FG if is_sel else DIM)
        if applied is not None and idx == applied:
            d.text((WIDTH - 8, y + 4), "•", font=bold(12),
                   fill=ACCENT if is_sel else ACCENT_DEEP, anchor="ra")
    _footer(d, "PRESS APPLY · LONG BACK")
    return img


def render_eq_applied(name, band_values):
    """Confirmation after a press: what got applied and its actual curve. This is
    the screen that replaces the band editor."""
    img, d = _canvas()
    _statusbar(d, "EQ PRESET")
    d.text((WIDTH // 2, 26), _elide(d, bold(13), name, WIDTH - 16), font=bold(13),
           fill=FG, anchor="mm")
    _caps_centred(d, 42, "APPLIED", reg(8), ACCENT, tracking=1.4)

    x0, bw, gap, base = 5, 7, 3, 92
    for i, gain in enumerate(band_values[:15]):
        x = x0 + i * (bw + gap)
        rungs = max(1, abs(int(gain)) * 2)
        for k in range(rungs):
            y = base - 4 - k * 5 if gain >= 0 else base + 2 + k * 5
            d.rectangle((x, y, x + bw, y + 3), fill=ACCENT_DEEP)
    d.line((x0, base, WIDTH - 5, base), fill=RULE)
    _footer(d, "15 BANDS · EDIT IN WEB UI")
    return img


# -------------------------------------------------------------- 6. VU METER

_VU_A0, _VU_A1 = 214, 326  # Pillow degrees: clockwise from 3 o'clock, so this arcs over the top


def _polar(cx, cy, r, frac):
    import math
    angle = math.radians(_VU_A0 + (_VU_A1 - _VU_A0) * frac)
    return cx + math.cos(angle) * r, cy + math.sin(angle) * r


def _needle(d, cx, cy, r, value, label):
    box = (cx - r, cy - r, cx + r, cy + r)
    d.arc(box, _VU_A0, _VU_A1, fill=DIM)
    d.arc(box, _VU_A0 + (_VU_A1 - _VU_A0) * 0.70, _VU_A1 - 12, fill=WARN)
    d.arc(box, _VU_A1 - 12, _VU_A1, fill=HOT)
    for frac in (0.0, 0.25, 0.5, 0.70, 0.86, 1.0):
        x0, y0 = _polar(cx, cy, r - 4, frac)
        x1, y1 = _polar(cx, cy, r, frac)
        d.line((x0, y0, x1, y1), fill=DIM)
    # Scale labels placed polar just outside the arc. At a fixed y they landed on
    # top of the arc itself.
    for frac, text in ((0.0, "-20"), (0.5, "-6"), (1.0, "+3")):
        lx, ly = _polar(cx, cy, r + 8, frac)
        d.text((lx, ly), text, font=reg(7), fill=HOT if text == "+3" else DIMMER,
               anchor="mm")
    nx, ny = _polar(cx, cy, r - 6, max(0.0, min(1.0, value)))
    d.line((cx, cy, nx, ny), fill=ACCENT, width=2)
    d.ellipse((cx - 3, cy - 3, cx + 3, cy + 3), fill=FG)
    d.text((cx, cy + 10), label, font=bold(10), fill=DIM, anchor="mm")


def render_vu_needles(left, right, volume=None, peak_db=None, bt=False, wifi=False):
    """Twin analog swing. left/right are 0-100. The dedicated full-screen styles
    in vu_styles.py are still reachable; this is the default metering page."""
    img, d = _canvas()
    _statusbar(d, "VU METER", bt=bt, wifi=wifi)
    _needle(d, 41, 78, 31, max(0.0, min(100.0, left)) / 100.0, "L")
    _needle(d, 119, 78, 31, max(0.0, min(100.0, right)) / 100.0, "R")

    _hairline(d, 5, WIDTH - 5, 98)
    if volume is not None:
        d.text((5, 105), "VOL", font=reg(9), fill=DIM)
        for i in range(14):
            x = 32 + i * 5
            lit = i < round(volume / 100 * 14)
            d.rectangle((x, 105, x + 3, 115), fill=ACCENT if lit else RULE)
    if peak_db is not None:
        d.text((WIDTH - 5, 104), f"{peak_db:.1f} dB", font=mono(9), fill=DIM, anchor="ra")
    return img


def overlay_style_name(img, name, index, total):
    """Stamps the style name over a full-screen VU style for a couple of seconds
    after switching. Fixes the known gap where rotating 19 styles was blind, but
    without permanently covering the meter it is naming."""
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, WIDTH, 16), fill=PANEL)
    d.text((5, 2), _elide(d, bold(11), name, 110), font=bold(11), fill=FG)
    d.text((WIDTH - 5, 3), f"{index + 1}/{total}", font=mono(9), fill=ACCENT, anchor="ra")
    return img


# --------------------------------------------------------- 7. INFO SCREENS

def render_network(info, bt=False, wifi=False):
    """info: dict with connected/ssid/ip/signal/host. Full-width label/value rows;
    a second large Wi-Fi glyph would just duplicate the status strip."""
    img, d = _canvas()
    _statusbar(d, "NETWORK", bt=bt, wifi=wifi)
    connected = info.get("connected")
    _caps(d, 6, 24, "CONNECTED" if connected else "OFFLINE", bold(9),
          ACCENT if connected else HOT, tracking=1.2)
    _icon_wifi(d, WIDTH - 22, 18, ACCENT if connected else DIMMER, bars=4)
    _hairline(d, 5, WIDTH - 5, 32)

    rows = (("SSID", info.get("ssid")), ("IP", info.get("ip")),
            ("SIGNAL", info.get("signal")), ("HOST", info.get("host")))
    for i, (key, value) in enumerate(rows):
        y = 38 + i * 22
        _caps(d, 6, y + 5, key, reg(8), DIMMER, tracking=0.8)
        _draw_text(d, (WIDTH - 6, y), _elide(d, reg(10), str(value or "--"), 100),
               font=reg(10), fill=FG, anchor="ra")
    return img


def render_system(info, bt=False, wifi=False):
    """info: dict with firmware/board/cpu_temp/uptime/memory_pct/storage_pct."""
    img, d = _canvas()
    _statusbar(d, "SYSTEM", bt=bt, wifi=wifi)
    rows = (("Firmware", info.get("firmware")), ("Board", info.get("board")),
            ("CPU Temp", info.get("cpu_temp")), ("Uptime", info.get("uptime")))
    for i, (key, value) in enumerate(rows):
        y = 18 + i * 15
        d.text((6, y), key, font=reg(10), fill=DIM)
        d.text((WIDTH - 6, y), str(value or "--"), font=mono(10), fill=FG, anchor="ra")

    for i, (key, pct) in enumerate((("Memory", info.get("memory_pct")),
                                    ("Storage", info.get("storage_pct")))):
        y = 82 + i * 18
        d.text((6, y), key, font=reg(9), fill=DIM)
        d.rectangle((58, y + 2, 130, y + 8), fill=RULE)
        if pct is not None:
            d.rectangle((58, y + 2, 58 + int(72 * max(0, min(100, pct)) / 100), y + 8),
                        fill=ACCENT)
            d.text((WIDTH - 6, y), f"{int(pct)}%", font=mono(9), fill=DIM, anchor="ra")
    return img


def render_confirm(title, message, bt=False, wifi=False):
    """Power actions: nothing this destructive fires without a confirm step."""
    img, d = _canvas()
    _statusbar(d, title, bt=bt, wifi=wifi)
    d.text((WIDTH // 2, 46), message, font=bold(14), fill=FG, anchor="mm")
    _caps_centred(d, 68, "PRESS TO CONFIRM", reg(9), ACCENT, tracking=1.2)
    _caps_centred(d, 84, "LONG PRESS TO CANCEL", reg(8), DIMMER, tracking=0.8)
    return img


# ------------------------------------------------------- 8. VOLUME OVERLAY

# 21, not the 23 the two-row overlay used: three rows at 23 put the strip's top edge
# at y=48, which cut the Now Playing artist line clean in half. At 21 the strip
# starts at 54, just clear of it. Row *contents* are unaffected -- the box is
# y-2..y+16 either way, so this only closes up the gap between rows.
_OVL_ROW_H = 21
_OVL_HINT_H = 11


def _overlay_top(rows):
    """One source of truth for the HUD's height, so adding a row can't leave the
    panel and the rows disagreeing about where the strip starts."""
    return HEIGHT - _OVL_HINT_H - rows * _OVL_ROW_H


def _volume_row(d, y, label, pct, focused, available=True):
    if focused:
        d.rectangle((0, y - 2, WIDTH, y + _OVL_ROW_H - 5), fill=PANEL)
        d.rectangle((0, y - 2, 2, y + _OVL_ROW_H - 5), fill=ACCENT)
    label_colour = ACCENT if focused else (DIM if available else DIMMER)
    _caps(d, 7, y + 8, label, bold(9) if focused else reg(9), label_colour, tracking=1.2)

    bx0, bx1, by = 38, WIDTH - 38, y + 6
    d.rectangle((bx0, by, bx1, by + 5), fill=RULE)
    if available:
        fill_w = int((bx1 - bx0) * max(0, min(100, pct)) / 100)
        if fill_w:
            d.rectangle((bx0, by, bx0 + fill_w, by + 5),
                        fill=ACCENT if focused else ACCENT_DEEP)
    d.text((WIDTH - 6, y + 1), str(int(pct)) if available else "--",
           font=mono(13) if focused else mono(11), fill=FG if focused else DIM,
           anchor="ra")


def _track_row(d, y, focused, index=None, total=0):
    """Third overlay row: rotate skips instead of moving a level. No bar, because
    there is no level -- position stands in for one."""
    available = total > 0
    if focused:
        d.rectangle((0, y - 2, WIDTH, y + _OVL_ROW_H - 5), fill=PANEL)
        d.rectangle((0, y - 2, 2, y + _OVL_ROW_H - 5), fill=ACCENT)
    label_colour = ACCENT if focused else (DIM if available else DIMMER)
    _caps(d, 7, y + 8, "TRACK", bold(9) if focused else reg(9), label_colour,
          tracking=1.2)

    # The same glyphs Home already shows, in the position the volume rows put their
    # bar: rotation acts on the focused row, and here what it moves is tracks.
    arrow = ACCENT if focused else (DIMMER if available else RULE)
    _skip_glyphs(d, 70, y + 8, arrow, spread=13)

    if not available:
        text = "--"
    elif index is None:
        # A queue exists but nothing is current (stopped after a load). Skipping
        # still works, so don't grey the row out -- just don't invent a position.
        text = f"-/{total}"
    else:
        text = f"{index}/{total}"
    d.text((WIDTH - 6, y + 2), text, font=mono(11) if focused else mono(10),
           fill=FG if focused else DIM, anchor="ra")


def overlay_volume(base, mpd_pct, bt_pct, target, bt_available=True, hint=None,
                   track_index=None, track_total=0):
    """Volume + skip HUD composited over whatever screen is showing.

    Deliberately has no source detection: the user picks the target and it sticks
    until power cycle (defaulting to MPD on boot). Bluetooth playback cannot be
    detected reliably -- AVRCP is absent on some phones, and BT Volume is a lazily
    created softvol control that only exists once BT has played -- so a routing
    overlay would send the knob to the wrong path. Both levels are on screen, so
    "which am I moving" is answered by layout rather than by trust.

    The third row skips tracks. It is the same mechanism as the other two -- rotate
    acts on whatever is focused -- and unlike them it does NOT stick past the
    overlay closing, or the knob's resting action on Home would quietly become
    "skip" instead of "volume".

    Press switches rows while this is up, which means play/pause is unavailable
    for those ~2 seconds. Rotate is adjusting and long press opens the Menu, so
    press is the only gesture left.
    """
    # One Image.blend over 160x128: C-speed, no per-pixel Python, cheap enough to
    # run on every detent.
    img = Image.blend(base, Image.new("RGB", base.size, BG), 0.58)
    d = ImageDraw.Draw(img)
    top = _overlay_top(3)
    d.rectangle((0, top, WIDTH, HEIGHT), fill=(10, 15, 16))
    d.line((0, top, WIDTH, top), fill=ACCENT)

    _volume_row(d, top + 5, "MPD", mpd_pct, target == "MPD")
    _volume_row(d, top + 5 + _OVL_ROW_H, "BT", bt_pct, target == "BT",
                available=bt_available)
    _track_row(d, top + 5 + 2 * _OVL_ROW_H, target == "TRACK",
               index=track_index, total=track_total)
    _caps_centred(d, HEIGHT - 5, hint or "PRESS ▸ SWITCH", reg(7), DIMMER,
                  tracking=0.8)
    return img
