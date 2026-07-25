#!/usr/bin/env python3
# Dedicated full-screen VU meter page -- visual styles to compare on actual
# hardware before picking one (see [[project-local-display]] idea list). Each
# render_* function takes 0-100 level(s) and returns a 160x128 RGB PIL Image.
# Fed by any object with .read() -> (left, right), e.g. vu_meter.VuMeter or a
# fake/dummy source -- see demo_vu_styles.py.
#
# The band-style meters (render_spectrum_16 etc.) take a list of 0-100 band
# levels instead of an L/R pair. NOTE: the real fifo tap in vu_meter.py only
# yields overall L/R amplitude -- real per-band data would need an FFT over
# fifo samples (numpy dependency + CPU cost on a Zero 2W). For now band styles
# are driven by fake/derived levels; treat a real spectrum as a separate
# decision if one of these styles wins.
import math
import random

from PIL import Image, ImageDraw

from screens import BAR_BG, BG, DIM, FG, _font

WIDTH, HEIGHT = 160, 128


def _level_color(frac):
    """frac: 0-1 position within the meter range. Zones: green (quiet) ->
    yellow (getting hot) -> red (max), classic LED-meter colors."""
    if frac < 0.7:
        return (34, 197, 60)
    if frac < 0.9:
        return (250, 210, 35)
    return (235, 55, 45)


def _title(draw):
    draw.text((WIDTH // 2, 12), "VU METER", font=_font(11), fill=DIM, anchor="mm")


def render_ladder_full(left, right):
    """Style A -- two vertical segmented LED-ladder columns, full screen (the
    same technique as the Now Playing flanking bars, just bigger/centered)."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    segments, seg_h, gap = 14, 6, 2
    bottom_y = HEIGHT - 6
    col_w, gap_between = 22, 14
    x0 = (WIDTH - (col_w * 2 + gap_between)) // 2
    for ch, level in enumerate((left, right)):
        x = x0 + ch * (col_w + gap_between)
        lit = round(max(0, min(100, level)) / 100 * segments)
        for i in range(segments):
            y = bottom_y - i * (seg_h + gap) - seg_h
            color = _level_color(i / segments) if i < lit else BAR_BG
            draw.rectangle((x, y, x + col_w, y + seg_h), fill=color)
    _title(draw)
    return img


def render_horizontal_bars(left, right):
    """Style B -- two horizontal bars stacked, higher segment resolution than
    the vertical columns fit in the same footprint."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    bar_x0, bar_x1 = 14, WIDTH - 14
    bar_w = bar_x1 - bar_x0
    segments = 24
    seg_w = bar_w / segments
    for idx, (label, level) in enumerate((("L", left), ("R", right))):
        y = 40 + idx * 34
        draw.text((bar_x0 - 8, y + 6), label, font=_font(11), fill=DIM, anchor="rm")
        draw.rectangle((bar_x0, y, bar_x1, y + 14), fill=BAR_BG)
        lit = round(max(0, min(100, level)) / 100 * segments)
        for i in range(lit):
            x = bar_x0 + i * seg_w
            draw.rectangle((x + 1, y + 1, x + seg_w - 1, y + 13), fill=_level_color(i / segments))
    _title(draw)
    return img


def render_gradient_bars(left, right):
    """Style C -- continuous smooth green->amber->red fill instead of discrete
    segments. Cleaner/more modern look than the LED-ladder."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    top_y, bottom_y = 24, HEIGHT - 6
    col_w, gap = 26, 18
    x0 = (WIDTH - (col_w * 2 + gap)) // 2
    height = bottom_y - top_y
    for ch, level in enumerate((left, right)):
        x = x0 + ch * (col_w + gap)
        draw.rectangle((x, top_y, x + col_w, bottom_y), fill=BAR_BG)
        fill_h = int(height * max(0, min(100, level)) / 100)
        for row in range(fill_h):
            y = bottom_y - row
            draw.line((x, y, x + col_w, y), fill=_level_color(row / height))
    _title(draw)
    return img


def render_needle(mono_level):
    """Style D -- simplified analog needle gauge (mono/average level, 0-100).
    Production note: pre-render/cache the needle per angle bucket (as
    PeppyMeter does) instead of recomputing trig every frame -- fine here
    since this is just for visual comparison, not the final render loop."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    cx, cy, radius = WIDTH // 2, HEIGHT // 2 + 16, 55
    start_angle, end_angle = 135, 405  # 270-degree sweep, gap at top

    draw.arc((cx - radius, cy - radius, cx + radius, cy + radius), start_angle, end_angle, fill=DIM, width=2)
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        angle = math.radians(start_angle + frac * (end_angle - start_angle))
        x1, y1 = cx + (radius - 8) * math.cos(angle), cy + (radius - 8) * math.sin(angle)
        x2, y2 = cx + radius * math.cos(angle), cy + radius * math.sin(angle)
        draw.line((x1, y1, x2, y2), fill=_level_color(frac), width=2)

    level = max(0, min(100, mono_level))
    needle_angle = math.radians(start_angle + (level / 100) * (end_angle - start_angle))
    nx, ny = cx + (radius - 10) * math.cos(needle_angle), cy + (radius - 10) * math.sin(needle_angle)
    draw.line((cx, cy, nx, ny), fill=_level_color(level / 100), width=2)
    draw.ellipse((cx - 4, cy - 4, cx + 4, cy + 4), fill=FG)
    _title(draw)
    return img


def render_radial(left, right):
    """Style E -- two concentric semicircle arc gauges instead of straight bars."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    cx, cy = WIDTH // 2, HEIGHT // 2 + 20
    start_angle, sweep = 180, 180
    for level, radius, width in ((left, 58, 10), (right, 44, 10)):
        draw.arc((cx - radius, cy - radius, cx + radius, cy + radius),
                  start_angle, start_angle + sweep, fill=BAR_BG, width=width)
        level = max(0, min(100, level))
        end = start_angle + sweep * (level / 100)
        if end > start_angle:
            draw.arc((cx - radius, cy - radius, cx + radius, cy + radius),
                      start_angle, end, fill=_level_color(level / 100), width=width)
    _title(draw)
    return img


# Peak-hold state persists across frames per style: value jumps up with the
# signal, then decays PEAK_DECAY per frame. Module-level since renderers are
# plain functions; call reset_peaks() when leaving the VU page.
PEAK_DECAY = 1.5
_peaks = {}


def reset_peaks():
    _peaks.clear()
    _beat.update(avg=0.0, radius=0.0)
    _particles.clear()
    _stars.clear()
    _ripples.clear()
    _fx_beat["avg"] = 0.0
    _power["level"] = 0.0


def _peak_track(key, index, value):
    peaks = _peaks.setdefault(key, {})
    held = max(peaks.get(index, 0.0) - PEAK_DECAY, value)
    peaks[index] = held
    return held


def render_spectrum_16(bands):
    """Style F -- 16-band spectrum analyzer with peak-hold dots. bands: list of
    16 levels 0-100, low frequency on the left. See module docstring: real
    per-band data needs an FFT; fake/derived levels are fine for comparing looks."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    n = 16
    margin, gap = 6, 2
    bar_w = (WIDTH - 2 * margin - (n - 1) * gap) / n
    top_y, bottom_y = 24, HEIGHT - 8
    height = bottom_y - top_y
    for i in range(n):
        level = max(0, min(100, bands[i] if i < len(bands) else 0))
        x = margin + i * (bar_w + gap)
        fill_h = int(height * level / 100)
        draw.rectangle((x, top_y, x + bar_w, bottom_y), fill=BAR_BG)
        if fill_h > 0:
            draw.rectangle((x, bottom_y - fill_h, x + bar_w, bottom_y),
                           fill=_level_color(level / 100))
        peak = _peak_track("spectrum16", i, level)
        peak_y = bottom_y - int(height * peak / 100)
        draw.rectangle((x, peak_y - 1, x + bar_w, peak_y), fill=FG)
    _title(draw)
    return img


def render_ladder_peak_hold(left, right):
    """Style G -- style A's LED-ladder columns plus a slowly-falling peak-hold
    marker above each column (the classic 'peak catcher')."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    segments, seg_h, gap = 14, 6, 2
    bottom_y = HEIGHT - 6
    col_w, gap_between = 22, 14
    x0 = (WIDTH - (col_w * 2 + gap_between)) // 2
    span = segments * (seg_h + gap)
    for ch, level in enumerate((left, right)):
        x = x0 + ch * (col_w + gap_between)
        level = max(0, min(100, level))
        lit = round(level / 100 * segments)
        for i in range(segments):
            y = bottom_y - i * (seg_h + gap) - seg_h
            color = _level_color(i / segments) if i < lit else BAR_BG
            draw.rectangle((x, y, x + col_w, y + seg_h), fill=color)
        peak = _peak_track("ladder", ch, level)
        peak_y = bottom_y - int(span * peak / 100)
        draw.rectangle((x, peak_y - 2, x + col_w, peak_y), fill=FG)
    _title(draw)
    return img


def render_mirror_bars(left, right):
    """Style H -- horizontal bars growing outward from a shared center line,
    left channel to the left, right channel to the right."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    cx = WIDTH // 2
    half = cx - 12
    segments = 12
    seg_w = half / segments
    for idx, y in ((0, 44), (1, 78)):
        level = max(0, min(100, (left, right)[idx]))
        lit = round(level / 100 * segments)
        for i in range(segments):
            color = _level_color(i / segments) if i < lit else BAR_BG
            if idx == 0:
                x1 = cx - 3 - i * seg_w
                draw.rectangle((x1 - seg_w + 2, y, x1, y + 18), fill=color)
            else:
                x0 = cx + 3 + i * seg_w
                draw.rectangle((x0, y, x0 + seg_w - 2, y + 18), fill=color)
    draw.rectangle((cx - 1, 38, cx + 1, 102), fill=DIM)
    draw.text((cx - 8, 112), "L", font=_font(10), fill=DIM, anchor="mm")
    draw.text((cx + 8, 112), "R", font=_font(10), fill=DIM, anchor="mm")
    _title(draw)
    return img


def render_goniometer(pairs):
    """Style J -- stereo goniometer / Lissajous scope: plots L against R sample
    pairs as an XY dot cloud, rotated 45 degrees as on studio gear (mono
    collapses to a vertical line, wide stereo blooms outward, out-of-phase
    content leans horizontal). pairs: list of (l, r) tuples, each -1.0..1.0 --
    the real fifo tap yields exactly this; the demo fakes it."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    cx, cy = WIDTH // 2, HEIGHT // 2 + 6
    scale = 48
    draw.line((cx, cy - scale, cx, cy + scale), fill=BAR_BG)
    draw.line((cx - scale, cy, cx + scale, cy), fill=BAR_BG)
    n = len(pairs)
    for i, (l, r) in enumerate(pairs):
        # classic M/S rotation: mid on the vertical axis, side on the horizontal
        x = cx + (l - r) * 0.7071 * scale
        y = cy - (l + r) * 0.7071 * scale
        # hue by amplitude (green quiet -> red hot), brightness by age for the
        # phosphor-trail effect (older samples dimmer, newest full)
        amp = min(1.0, math.sqrt((l * l + r * r) / 2) * 1.4)
        base = _level_color(amp)
        age = 0.35 + 0.65 * i / max(1, n - 1)
        draw.point((x, y), fill=tuple(int(c * age) for c in base))
    draw.text((cx, cy + scale + 8), "L+R", font=_font(9), fill=DIM, anchor="mm")
    _title(draw)
    return img


def render_oscilloscope(samples):
    """Style K -- scrolling waveform scope: draws the actual signal, so quiet
    passages genuinely flatten and drums genuinely spike. samples: list of
    mono values -1.0..1.0, oldest first (a ring buffer of recent fifo reads)."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    mid_y, amp = HEIGHT // 2 + 6, 46
    draw.line((0, mid_y, WIDTH, mid_y), fill=BAR_BG)
    if len(samples) >= 2:
        step = (len(samples) - 1) / (WIDTH - 1)
        prev = None
        for x in range(WIDTH):
            s = max(-1.0, min(1.0, samples[int(x * step)]))
            point = (x, mid_y - s * amp)
            if prev is not None:
                # segment hue follows its own amplitude: green quiet -> red peaks
                draw.line((prev, point), fill=_level_color(abs(s)), width=1)
            prev = point
    _title(draw)
    return img


# Beat-ring state: rolling average level + current ring radius, module-level
# for the same reason as _peaks. reset_peaks() clears this too.
_beat = {"avg": 0.0, "radius": 0.0}


def render_beat_ring(level, label=""):
    """Style L -- beat-pulse ring: a centered circle that kicks outward when
    the level spikes above its rolling average, then relaxes back. level:
    0-100 mono. label: optional text in the middle (e.g. track title) --
    doubles as an idle/screensaver mode."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    cx, cy = WIDTH // 2, HEIGHT // 2 + 6
    level = max(0, min(100, level))
    _beat["avg"] = _beat["avg"] * 0.92 + level * 0.08
    kicked = level > _beat["avg"] * 1.25 and level > 15
    target = 44 if kicked else 20 + level * 0.15
    rate = 0.6 if kicked else 0.15  # fast attack, slow release
    _beat["radius"] += (target - _beat["radius"]) * rate
    radius = int(_beat["radius"])
    frac = min(1.0, radius / 44)
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius),
                 outline=_level_color(frac), width=3)
    inner = max(4, radius - 12)
    draw.ellipse((cx - inner, cy - inner, cx + inner, cy + inner),
                 outline=BAR_BG, width=1)
    if label:
        draw.text((cx, cy), label, font=_font(10), fill=DIM, anchor="mm")
    _title(draw)
    return img


def render_wave_ring(samples):
    """Style M -- circular waveform: the signal wrapped around a ring, radius
    modulated by each sample. Loud music makes the ring spiky and alive; near
    silence it relaxes to a clean circle. samples: mono values -1.0..1.0."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    cx, cy = WIDTH // 2, HEIGHT // 2 + 6
    base_r, mod = 34, 15
    n = len(samples)
    if n >= 3:
        clamped = [max(-1.0, min(1.0, s)) for s in samples]
        points = []
        for i, s in enumerate(clamped):
            angle = 2 * math.pi * i / n
            r = base_r + s * mod
            points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
        points.append(points[0])
        clamped.append(clamped[0])
        for i in range(n):
            # segment hue follows its own amplitude: green quiet -> red peaks
            draw.line((points[i], points[i + 1]), fill=_level_color(abs(clamped[i])), width=1)
    draw.ellipse((cx - 2, cy - 2, cx + 2, cy + 2), fill=DIM)
    _title(draw)
    return img


def render_dual_scope(pairs):
    """Style N -- two-channel oscilloscope: L and R waveforms as separate
    stacked traces, like a real 2-channel scope. pairs: list of (l, r)
    tuples -1.0..1.0, oldest first."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    traces = ((44, "L"), (94, "R"))
    for ch, (mid_y, label) in enumerate(traces):
        draw.line((0, mid_y, WIDTH, mid_y), fill=BAR_BG)
        draw.text((4, mid_y - 14), label, font=_font(9), fill=DIM)
        if len(pairs) >= 2:
            step = (len(pairs) - 1) / (WIDTH - 1)
            prev = None
            for x in range(WIDTH):
                s = max(-1.0, min(1.0, pairs[int(x * step)][ch]))
                point = (x, mid_y - s * 22)
                if prev is not None:
                    draw.line((prev, point), fill=_level_color(abs(s)), width=1)
                prev = point
    _title(draw)
    return img


def render_wave_fill(samples):
    """Style O -- mirrored filled waveform (SoundCloud-style): a symmetric
    envelope around the centerline, one vertical bar per column, colored by
    its own amplitude. samples: mono values -1.0..1.0."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    mid_y, amp = HEIGHT // 2 + 6, 44
    if len(samples) >= 2:
        step = (len(samples) - 1) / (WIDTH - 1)
        for x in range(0, WIDTH, 2):
            a = abs(max(-1.0, min(1.0, samples[int(x * step)])))
            h = max(1, int(a * amp))
            draw.line((x, mid_y - h, x, mid_y + h), fill=_level_color(a))
    _title(draw)
    return img


# Animated-effect state (particles / stars / ripples) lives at module level
# like _peaks; reset_peaks() clears all of it when leaving the VU page.
_particles = []
_stars = []
_ripples = []
_fx_beat = {"avg": 0.0}


def _beat_detect(level):
    _fx_beat["avg"] = _fx_beat["avg"] * 0.9 + level * 0.1
    return level > _fx_beat["avg"] * 1.3 and level > 15


def render_particles(level):
    """Style P -- particle bursts: a spray of dots explodes from the center on
    each detected beat, drifts outward and fades. level: 0-100 mono."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    cx, cy = WIDTH // 2, HEIGHT // 2 + 6
    level = max(0, min(100, level))
    if _beat_detect(level):
        # burst hue = how hard the beat hit: green soft -> red slam
        color = _level_color(level / 100)
        for _ in range(16):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(2.0, 6.0)
            _particles.append({
                "x": float(cx), "y": float(cy),
                "vx": speed * math.cos(angle), "vy": speed * math.sin(angle),
                "life": 1.0, "color": color,
            })
    for p in _particles:
        p["x"] += p["vx"]
        p["y"] += p["vy"]
        p["vy"] += 0.15  # slight gravity so bursts arc downward
        p["life"] -= 0.06
        if p["life"] > 0:
            fade = 0.3 + 0.7 * p["life"]
            draw.ellipse((p["x"] - 1, p["y"] - 1, p["x"] + 1, p["y"] + 1),
                         fill=tuple(int(c * fade) for c in p["color"]))
    _particles[:] = [p for p in _particles
                     if p["life"] > 0 and -5 < p["x"] < WIDTH + 5 and p["y"] < HEIGHT + 5]
    draw.ellipse((cx - 2, cy - 2, cx + 2, cy + 2), fill=DIM)
    _title(draw)
    return img


def render_starfield(level):
    """Style Q -- warp-speed starfield: stars stream outward from the center,
    speed tied to loudness. Music gets loud, you go to warp. level: 0-100."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    cx, cy = WIDTH // 2, HEIGHT // 2 + 6
    if not _stars:
        for _ in range(40):
            _stars.append({"angle": random.uniform(0, 2 * math.pi),
                           "dist": random.uniform(2, 70)})
    level = max(0, min(100, level))
    speed = 0.5 + level / 100 * 4.5
    tint = _level_color(level / 100)  # whole field shifts green -> red as it gets loud
    for star in _stars:
        star["dist"] += speed * (0.3 + star["dist"] / 70)
        if star["dist"] > 90:
            star["angle"] = random.uniform(0, 2 * math.pi)
            star["dist"] = random.uniform(2, 8)
        x = cx + star["dist"] * math.cos(star["angle"])
        y = cy + star["dist"] * math.sin(star["angle"])
        fade = 0.3 + 0.7 * min(1.0, star["dist"] / 70)
        size = 1 if star["dist"] > 30 else 0
        draw.ellipse((x - size, y - size, x + size, y + size),
                     fill=tuple(int(c * fade) for c in tint))
    _title(draw)
    return img


def render_ripples(level):
    """Style R -- beat ripples: each detected beat drops a ring in the center
    that expands outward and fades, like rain on water. Multiple ripples can
    be in flight at once. level: 0-100 mono."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    cx, cy = WIDTH // 2, HEIGHT // 2 + 6
    level = max(0, min(100, level))
    if _beat_detect(level):
        # ring hue = how hard the beat hit: green soft -> red slam
        _ripples.append({"radius": 6.0, "life": 1.0, "color": _level_color(level / 100)})
    for rip in _ripples:
        rip["radius"] += 3.5
        rip["life"] -= 0.045
        if rip["life"] > 0:
            fade = 0.25 + 0.75 * rip["life"]
            r = rip["radius"]
            draw.ellipse((cx - r, cy - r, cx + r, cy + r),
                         outline=tuple(int(c * fade) for c in rip["color"]), width=2)
    _ripples[:] = [r for r in _ripples if r["life"] > 0 and r["radius"] < 110]
    draw.ellipse((cx - 2, cy - 2, cx + 2, cy + 2), fill=DIM)
    _title(draw)
    return img


# Power-meter needle state -- smoothed so the needle has analog inertia
# instead of teleporting between frames. Cleared by reset_peaks().
_power = {"level": 0.0}


def render_power_meter(mono_level):
    """Style S -- vintage amplifier power-meter face: a fan of radiating tick
    marks (green -> yellow -> red zones), dB labels along the inner arc, watt
    labels along the top, and a red needle swinging from a pivot below the
    screen. Modeled on classic hi-fi dB/W panel meters. mono_level: 0-100."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    cx, cy = WIDTH // 2, 195           # pivot well below the panel edge
    r_in, r_out = 96, 150              # tick fan span
    a_min, a_max = 118.0, 62.0         # degrees, left -> right sweep

    def polar(radius, deg):
        rad = math.radians(deg)
        return cx + radius * math.cos(rad), cy - radius * math.sin(rad)

    n_ticks = 22
    for i in range(n_ticks):
        frac = i / (n_ticks - 1)
        deg = a_min + (a_max - a_min) * frac
        major = i % 3 == 0
        color = _level_color(frac)
        x1, y1 = polar(r_in if major else r_in + 14, deg)
        x2, y2 = polar(r_out if major else r_out - 8, deg)
        draw.line((x1, y1, x2, y2), fill=color, width=2 if major else 1)

    db_labels = ("-40", "-20", "-10", "0", "+3")
    for i, text in enumerate(db_labels):
        frac = i / (len(db_labels) - 1)
        x, y = polar(r_in - 12, a_min + (a_max - a_min) * frac)
        color = _level_color(frac) if frac > 0.75 else DIM
        draw.text((x, y), text, font=_font(8), fill=color, anchor="mm")

    watt_labels = ("0.02", "0.6", "5", "40", "160")
    for i, text in enumerate(watt_labels):
        frac = i / (len(watt_labels) - 1)
        x, y = polar(r_out + 8, a_min + (a_max - a_min) * frac)
        draw.text((min(max(x, 12), WIDTH - 14), max(y, 7)), text,
                  font=_font(8), fill=DIM, anchor="mm")

    draw.text((6, 4), "dB/W", font=_font(9), fill=DIM)
    draw.text((WIDTH - 8, HEIGHT - 12), "8Ω", font=_font(9), fill=DIM, anchor="ra")

    # fast attack, slower release -- like a real meter movement
    level = max(0, min(100, mono_level))
    rate = 0.55 if level > _power["level"] else 0.25
    _power["level"] += (level - _power["level"]) * rate
    deg = a_min + (a_max - a_min) * _power["level"] / 100
    nx, ny = polar(r_out - 4, deg)
    draw.line((cx, cy, nx, ny), fill=(226, 75, 74), width=2)

    return img


def render_vfd_dots(left, right):
    """Style I -- dot-matrix / VFD-fluorescent look: rounded dots in a grid
    instead of solid bars, dim 'ghost' dots for the unlit portion."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    cols, dot, pitch = 20, 4, 7
    x0 = (WIDTH - cols * pitch) // 2
    ghost = (26, 40, 34)
    for idx, y in ((0, 48), (1, 76)):
        level = max(0, min(100, (left, right)[idx]))
        lit = round(level / 100 * cols)
        draw.text((x0 - 8, y + dot // 2), ("L", "R")[idx], font=_font(10), fill=DIM, anchor="rm")
        for i in range(cols):
            x = x0 + i * pitch
            color = _level_color(i / cols) if i < lit else ghost
            draw.ellipse((x, y, x + dot, y + dot), fill=color)
    _title(draw)
    return img
