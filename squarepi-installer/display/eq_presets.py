#!/usr/bin/env python3
# The 13 EQ presets (name + 15 ALSA band values, -15..15, 0=flat). This is the
# same data write_eq_preset() bakes into myMPD Lua scripts in install.sh:514 --
# kept here as the single source of truth candidate flagged in
# [[project-local-display]]. If a preset changes, update both places until
# install.sh is refactored to read this file instead of duplicating it.
import json
import subprocess

CARD = "LouderRaspberry"
BANDS = ["00020 Hz", "00032 Hz", "00050 Hz", "00080 Hz", "00125 Hz",
         "00200 Hz", "00315 Hz", "00500 Hz", "00800 Hz", "01250 Hz",
         "02000 Hz", "03150 Hz", "05000 Hz", "08000 Hz", "16000 Hz"]

PRESETS = [
    ("EQ Flat",       [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
    ("EQ Bass Boost", [7, 6, 5, 4, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
    ("EQ Treble",     [0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 3, 4, 5, 6, 6]),
    ("EQ Vocal",      [-3, -3, -2, -1, 0, 2, 3, 3, 2, 1, 0, -1, -2, -2, -2]),
    ("EQ Night Mode", [-5, -5, -4, -2, 0, 0, 0, -1, -1, -1, -1, -2, -3, -4, -4]),
    ("EQ Late Night", [6, 5, 3, 1, 0, -1, -1, -1, 0, 0, 1, 2, 3, 4, 5]),
    ("EQ Rock",       [5, 4, 3, 2, 1, -1, -2, -2, -1, 1, 2, 3, 4, 5, 5]),
    ("EQ Pop",        [2, 2, 1, 0, -1, -1, 0, 1, 2, 3, 3, 2, 2, 1, 1]),
    ("EQ Jazz",       [3, 3, 2, 1, 0, 1, 2, 2, 1, 0, -1, -1, -2, -2, -3]),
    ("EQ Classical",  [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 4, 4]),
    ("EQ Club",       [8, 7, 6, 4, 2, -1, -2, -2, -1, 1, 2, 3, 4, 5, 6]),
    ("EQ Hip-Hop",    [7, 7, 6, 5, 3, 1, 0, 0, 1, 2, 2, 2, 3, 3, 2]),
    ("EQ Acoustic",   [-2, -2, 0, 1, 2, 2, 1, 0, 1, 2, 3, 3, 2, 1, 0]),
]


# Presets saved from the web UI. eq-server.py owns this file
# (its CUSTOM_PRESETS_FILE); the display only ever reads it, so the two cannot
# fight over it and a display crash can't cost you a preset. Same shape the web UI
# writes: {"name": [15 ints]} on the same -15..15 scale used above.
CUSTOM_PRESETS_FILE = "/etc/squarepi-custom-presets.json"


def load_custom_presets(path=CUSTOM_PRESETS_FILE):
    """[(name, values)] saved from the web UI, sorted by name. Returns [] for a
    missing, unreadable or malformed file -- a hand-edited or half-written JSON must
    cost you the custom list, never the built-in presets underneath it.

    Entries are validated rather than trusted: the file is writable by anything
    running as root, and a short list handed to apply_eq_preset() would silently set
    only the bands it covered, leaving the rest at whatever the last preset left."""
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    out = []
    for name, values in data.items():
        if not isinstance(name, str) or not isinstance(values, list):
            continue
        if len(values) != len(BANDS):
            continue
        try:
            clamped = [max(-15, min(15, int(v))) for v in values]
        except (TypeError, ValueError):
            continue
        out.append((name.strip()[:24] or "Unnamed", clamped))
    return sorted(out, key=lambda item: item[0].lower())


def apply_eq_preset(band_values):
    """Applies preset directly via amixer -- bypasses myMPD entirely, matching
    the project's existing direct-hardware-control style."""
    for band, value in zip(BANDS, band_values):
        subprocess.run(["amixer", "-c", CARD, "sset", band, "--", str(value)],
                        stderr=subprocess.DEVNULL)
    subprocess.run(["alsactl", "store"], stderr=subprocess.DEVNULL)
