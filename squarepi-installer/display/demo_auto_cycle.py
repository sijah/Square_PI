#!/usr/bin/env python3
# Auto-cycling visual demo -- no rotary encoder required at all. Advances
# through the 4 screens automatically every SCREEN_SECONDS, so you can see the
# ST7735 rendering with the KY-040 not yet wired up. Same dummy data as
# demo_cycle_screens.py, just timer-driven instead of knob-driven.
import random
import time

from eq_presets import PRESETS
from screens import render_bt_volume, render_eq_preset, render_mpd_volume, render_now_playing
from st7735_driver import init_display

SCREEN_NOW_PLAYING, SCREEN_MPD_VOLUME, SCREEN_BT_VOLUME, SCREEN_EQ_PRESET = range(4)
SCREEN_ORDER = (SCREEN_NOW_PLAYING, SCREEN_MPD_VOLUME, SCREEN_BT_VOLUME, SCREEN_EQ_PRESET)
SCREEN_NAMES = ("Now Playing", "MPD Volume", "BT Volume", "EQ Preset")

SCREEN_SECONDS = 10
FRAME_SECONDS = 0.2  # redraw rate while a screen is showing (keeps the VU animation moving)


class FakeVuMeter:
    """Smoothed random walk standing in for vu_meter.VuMeter -- purely visual."""

    def __init__(self):
        self.left = 40.0
        self.right = 35.0

    def read(self):
        self.left = max(0, min(100, self.left + random.uniform(-12, 12)))
        self.right = max(0, min(100, self.right + random.uniform(-12, 12)))
        return self.left, self.right


class DemoState:
    def __init__(self):
        self.title = "Bohemian Rhapsody"
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
            "title": self.title,
            "artist": self.artist,
            "source": "MPD",
            "elapsed": self.elapsed,
            "duration": self.duration,
        }


def render(disp, state, screen):
    if screen == SCREEN_NOW_PLAYING:
        img = render_now_playing(state.now_playing_dict(), state.vu.read())
    elif screen == SCREEN_MPD_VOLUME:
        img = render_mpd_volume(state.mpd_volume)
    elif screen == SCREEN_BT_VOLUME:
        img = render_bt_volume(state.bt_volume)
    else:
        names = [name for name, _ in PRESETS]
        img = render_eq_preset(names, state.eq_selected)
    disp.image(img)


def main():
    disp = init_display()
    state = DemoState()
    screen_pos = 0
    screen_deadline = time.monotonic() + SCREEN_SECONDS

    print(f"Auto-cycling every {SCREEN_SECONDS}s (no encoder needed). Ctrl+C to exit.")
    print("Showing:", SCREEN_NAMES[screen_pos])

    while True:
        state.tick()
        render(disp, state, SCREEN_ORDER[screen_pos])

        if time.monotonic() >= screen_deadline:
            screen_pos = (screen_pos + 1) % len(SCREEN_ORDER)
            screen_deadline = time.monotonic() + SCREEN_SECONDS
            print("Showing:", SCREEN_NAMES[screen_pos])

        time.sleep(FRAME_SECONDS)


if __name__ == "__main__":
    main()
