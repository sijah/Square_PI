#!/usr/bin/env python3
# Auto-cycling visual demo -- no rotary encoder, no MPD, no HAT required.
# Advances through every screen automatically every SCREEN_SECONDS so the ST7735
# rendering can be checked with the KY-040 not yet wired up. Same dummy data as
# demo_cycle_screens.py, just timer-driven instead of knob-driven.
#
# Updated for the 2.0.0 redesign: the two volume screens are gone (volume is an
# overlay now), and the demo walks the new screen set instead.
import math
import random
import time

import vu_styles
from eq_presets import PRESETS
from screens import (WIDTH, bold, marquee_offset, overlay_style_name,
                     overlay_volume, render_eq_applied, render_eq_presets,
                     render_list, render_music, render_network,
                     render_now_playing, render_queue, render_system,
                     render_vu_needles)
from st7735_driver import init_display

(SCREEN_HOME, SCREEN_OVERLAY, SCREEN_MENU, SCREEN_PLAY, SCREEN_QUEUE, SCREEN_EQ,
 SCREEN_EQ_APPLIED, SCREEN_VU, SCREEN_SETTINGS, SCREEN_NETWORK, SCREEN_SYSTEM,
 SCREEN_VU_STYLE) = range(12)
SCREEN_ORDER = tuple(range(12))
SCREEN_NAMES = ("Home", "Volume overlay", "Main Menu", "Play / Music", "Queue",
                "EQ Presets", "EQ Applied", "VU Meter", "Settings", "Network",
                "System Info", "VU Style")

DEMO_FLAGS = {"wifi": True, "bt": True}
# Stand-in for the Play screen's entry list: the two actions, then playlists.
DEMO_MUSIC_ACTIONS = ("Resume Queue", "Shuffle All Music")
DEMO_MUSIC_HINT = "37 TRACKS QUEUED"  # shown while Resume Queue is selected
DEMO_MUSIC_ENTRIES = (*DEMO_MUSIC_ACTIONS, "Bass Test", "chill evening",
                      "Late Night Deep House", "Workout")
DEMO_MENU = ("Now Playing", "Play / Music", "Playback Queue", "Equalizer",
             "VU Meter", "Settings", "System Info")
DEMO_SETTINGS = ("Network", "Display Timeout", "Power")
DEMO_QUEUE = (("Time", "Pink Floyd", 413), ("Money", "Pink Floyd", 382),
              ("Us and Them", "Pink Floyd", 469),
              ("Any Colour You Like", "Pink Floyd", 204))
DEMO_NETWORK = {"connected": True, "ssid": "SquarePi_Net", "ip": "192.168.1.105",
                "signal": "-48 dBm", "host": "squarepi.local"}
DEMO_SYSTEM = {"firmware": "2.0.0", "board": "Pi Zero 2 W", "cpu_temp": "42 °C",
               "uptime": "3d 14h", "memory_pct": 38, "storage_pct": 29}

# Mirrors main.py's VU_STYLES table -- cycles all 19 vu_styles.py renderers
# while parked on the VU Style screen, fed by FakeVuMeter below.
VU_STYLES = (
    ("LED Ladder", lambda vu: vu_styles.render_ladder_full(*vu.read())),
    ("Horizontal Bars", lambda vu: vu_styles.render_horizontal_bars(*vu.read())),
    ("Gradient Fill", lambda vu: vu_styles.render_gradient_bars(*vu.read())),
    ("Analog Needle", lambda vu: vu_styles.render_needle(sum(vu.read()) / 2)),
    ("Radial Arcs", lambda vu: vu_styles.render_radial(*vu.read())),
    ("16-Band Spectrum", lambda vu: vu_styles.render_spectrum_16(vu.read_pseudo_spectrum())),
    ("Ladder + Peak Hold", lambda vu: vu_styles.render_ladder_peak_hold(*vu.read())),
    ("Mirror Bars", lambda vu: vu_styles.render_mirror_bars(*vu.read())),
    ("VFD Dots", lambda vu: vu_styles.render_vfd_dots(*vu.read())),
    ("Goniometer", lambda vu: vu_styles.render_goniometer(vu.read_pairs())),
    ("Oscilloscope", lambda vu: vu_styles.render_oscilloscope(vu.read_waveform())),
    ("Beat Pulse Ring", lambda vu: vu_styles.render_beat_ring(sum(vu.read()) / 2)),
    ("Circular Waveform", lambda vu: vu_styles.render_wave_ring(vu.read_waveform(120))),
    ("Dual Scope", lambda vu: vu_styles.render_dual_scope(vu.read_pairs(160))),
    ("Wave Fill", lambda vu: vu_styles.render_wave_fill(vu.read_waveform())),
    ("Particle Bursts", lambda vu: vu_styles.render_particles(sum(vu.read()) / 2)),
    ("Starfield", lambda vu: vu_styles.render_starfield(sum(vu.read()) / 2)),
    ("Beat Ripples", lambda vu: vu_styles.render_ripples(sum(vu.read()) / 2)),
    ("Power Meter", lambda vu: vu_styles.render_power_meter(sum(vu.read()) / 2)),
)

SCREEN_SECONDS = 10
# Redraw rate while a screen is showing. Matches main.py's marquee tick rather than
# the old 0.2s: at 26 px/s a 0.2s frame steps the title 5px, which judders. The VU
# animation gets smoother out of the same change.
FRAME_SECONDS = 0.08
VU_STYLE_SECONDS = 6  # each VU style gets its own shorter sub-cycle while on that screen


class FakeVuMeter:
    """Smoothed random walk + fake waveform generator standing in for
    vu_meter.VuMeter -- implements the same read()/read_waveform()/
    read_pairs()/read_pseudo_spectrum() interface so every VU_STYLES entry
    has something to draw, purely visual."""

    def __init__(self):
        self.left = 40.0
        self.right = 35.0
        self.phase = 0.0
        self.amp = 0.6
        self.width = 0.5

    def read(self):
        self.left = max(0, min(100, self.left + random.uniform(-12, 12)))
        self.right = max(0, min(100, self.right + random.uniform(-12, 12)))
        return self.left, self.right

    def _step_state(self):
        self.amp = max(0.1, min(1.0, self.amp + random.uniform(-0.08, 0.08)))
        self.width = max(0.0, min(1.0, self.width + random.uniform(-0.06, 0.06)))

    def read_waveform(self, n=160):
        self._step_state()
        out = []
        for i in range(n):
            t = self.phase + i * 0.19
            s = math.sin(t) * 0.7 + math.sin(t * 2.7) * 0.3
            out.append(s * self.amp + random.uniform(-0.05, 0.05))
        self.phase += n * 0.19
        return out

    def read_pairs(self, n=200):
        self._step_state()
        out = []
        for i in range(n):
            t = self.phase + i * 0.13
            mid = (math.sin(t) * 0.7 + math.sin(t * 3.1) * 0.3) * self.amp
            side = math.sin(t * 1.9 + 1.0) * self.amp * self.width * 0.6
            out.append((mid + side, mid - side))
        self.phase += n * 0.13
        return out

    def read_pseudo_spectrum(self, n=16):
        level = (self.left + self.right) / 2
        return [max(0.0, min(100.0, level * (1.0 - (i / n) * 0.6) + random.uniform(-6, 6)))
                for i in range(n)]


class DemoState:
    def __init__(self):
        # Long on purpose: a title that fits would never show the marquee.
        self.title = "Bohemian Rhapsody (Remastered 2011 Deluxe Edition)"
        self.artist = "Queen"
        self.duration = 180.0
        self.elapsed = 42.0
        self.mpd_volume = 62
        self.bt_volume = 48
        self.eq_selected = 0
        self.vu = FakeVuMeter()
        self._last_tick = time.monotonic()

    def tick(self):
        now = time.monotonic()
        dt = now - self._last_tick
        self._last_tick = now
        self.elapsed = (self.elapsed + dt) % self.duration

    def now_playing_dict(self):
        return {
            "playing": True,
            "stopped": False,
            "title": self.title,
            "artist": self.artist,
            "album": "A Night at the Opera",
            "source": "MPD",
            "elapsed": self.elapsed,
            "duration": self.duration,
            "fmt": ["FLAC", "16bit", "44.1k"],
        }


def render(disp, state, screen, vu_style_pos):
    # No encoder here, so selections walk off the clock to show them scroll.
    step = int(state.elapsed)
    np = state.now_playing_dict()
    home = render_now_playing(
        np, np["fmt"], DEMO_FLAGS,
        scroll=marquee_offset(state.elapsed, np["title"], bold(15), WIDTH - 12))

    if screen == SCREEN_HOME:
        img = home
    elif screen == SCREEN_OVERLAY:
        # Walks all three rows so every focus state gets shown, including TRACK.
        target = ("MPD", "BT", "TRACK")[(step // 3) % 3]
        img = overlay_volume(home, state.mpd_volume, state.bt_volume, target,
                             track_index=14, track_total=550)
    elif screen == SCREEN_MENU:
        img = render_list("MAIN MENU", list(DEMO_MENU), step % len(DEMO_MENU),
                          footer="PRESS OPEN · LONG BACK", **DEMO_FLAGS)
    elif screen == SCREEN_PLAY:
        selected = step % len(DEMO_MUSIC_ENTRIES)
        img = render_music(list(DEMO_MUSIC_ENTRIES), selected, len(DEMO_MUSIC_ACTIONS),
                           DEMO_MUSIC_HINT if selected == 0 else None, **DEMO_FLAGS)
    elif screen == SCREEN_QUEUE:
        img = render_queue(list(DEMO_QUEUE), step % len(DEMO_QUEUE), **DEMO_FLAGS)
    elif screen == SCREEN_EQ:
        names = [name.replace("EQ ", "") for name, _ in PRESETS]
        img = render_eq_presets(names, step % len(names), applied=0, **DEMO_FLAGS)
    elif screen == SCREEN_EQ_APPLIED:
        name, bands = PRESETS[step % len(PRESETS)]
        img = render_eq_applied(name.replace("EQ ", ""), bands)
    elif screen == SCREEN_VU:
        left, right = state.vu.read()
        img = render_vu_needles(left, right, volume=state.mpd_volume,
                                peak_db=-2.1, **DEMO_FLAGS)
    elif screen == SCREEN_SETTINGS:
        img = render_list("SETTINGS", list(DEMO_SETTINGS), step % len(DEMO_SETTINGS),
                          values=[None, "30 s", None],
                          footer="PRESS OPEN · LONG BACK", **DEMO_FLAGS)
    elif screen == SCREEN_NETWORK:
        img = render_network(DEMO_NETWORK, **DEMO_FLAGS)
    elif screen == SCREEN_SYSTEM:
        img = render_system(DEMO_SYSTEM, **DEMO_FLAGS)
    else:
        name, render_fn = VU_STYLES[vu_style_pos]
        img = render_fn(state.vu)
        img = overlay_style_name(img, name, vu_style_pos, len(VU_STYLES))
    disp.image(img)


def main():
    disp = init_display()
    state = DemoState()
    screen_pos = 0
    vu_style_pos = 0
    screen_deadline = time.monotonic() + SCREEN_SECONDS
    vu_style_deadline = time.monotonic() + VU_STYLE_SECONDS

    print(f"Auto-cycling every {SCREEN_SECONDS}s (no encoder needed). Ctrl+C to exit.")
    print("Showing:", SCREEN_NAMES[screen_pos])

    while True:
        state.tick()
        render(disp, state, SCREEN_ORDER[screen_pos], vu_style_pos)

        if time.monotonic() >= screen_deadline:
            screen_pos = (screen_pos + 1) % len(SCREEN_ORDER)
            screen_deadline = time.monotonic() + SCREEN_SECONDS
            if SCREEN_ORDER[screen_pos] == SCREEN_VU_STYLE:
                vu_style_pos = 0
                vu_styles.reset_peaks()
                vu_style_deadline = time.monotonic() + VU_STYLE_SECONDS
            print("Showing:", SCREEN_NAMES[screen_pos])

        if SCREEN_ORDER[screen_pos] == SCREEN_VU_STYLE and time.monotonic() >= vu_style_deadline:
            vu_style_pos = (vu_style_pos + 1) % len(VU_STYLES)
            vu_styles.reset_peaks()
            vu_style_deadline = time.monotonic() + VU_STYLE_SECONDS
            print("  VU style:", VU_STYLES[vu_style_pos][0])

        time.sleep(FRAME_SECONDS)


if __name__ == "__main__":
    main()
