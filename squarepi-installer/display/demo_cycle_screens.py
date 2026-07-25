#!/usr/bin/env python3
# Pure-visual demo: cycles the 4 screens with dummy data. No MPD, no Bluetooth,
# no SquarePi HAT/amixer required -- just the ST7735 + KY-040 wired up. Same
# interaction model as main.py (rotate / short press / long press), but all
# state is fake so you can confirm rendering + encoder cycling look right
# before the real hardware/services are in place.
import random
import time
from threading import Event

from gpiozero import Button, RotaryEncoder

from eq_presets import PRESETS
from screens import render_bt_volume, render_eq_preset, render_mpd_volume, render_now_playing
from st7735_driver import init_display

SCREEN_NOW_PLAYING, SCREEN_MPD_VOLUME, SCREEN_BT_VOLUME, SCREEN_EQ_PRESET = range(4)
SCREEN_ORDER = (SCREEN_NOW_PLAYING, SCREEN_MPD_VOLUME, SCREEN_BT_VOLUME, SCREEN_EQ_PRESET)
SCREEN_NAMES = ("Now Playing", "MPD Volume", "BT Volume", "EQ Preset")

ENCODER_CLK = 17
ENCODER_DT = 27
ENCODER_SW = 22
HOLD_TIME = 0.6
VOLUME_STEP = 4
TICK_SECONDS = 0.2  # faster than main.py's 1s so the fake VU meter looks alive


class FakeVuMeter:
    """Smoothed random walk standing in for vu_meter.VuMeter -- makes the
    meter columns visibly move without any real audio pipeline."""

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
        self.playing = True
        self.mpd_volume = 62
        self.bt_volume = 48
        self.eq_selected = 0
        self.vu = FakeVuMeter()
        self._last_tick = time.monotonic()

    def tick(self):
        now = time.monotonic()
        dt = now - self._last_tick
        self._last_tick = now
        if self.playing:
            self.elapsed = (self.elapsed + dt) % self.duration

    def now_playing_dict(self):
        return {
            "playing": self.playing,
            "title": self.title,
            "artist": self.artist,
            "source": "MPD",
            "elapsed": self.elapsed,
            "duration": self.duration,
        }


class DemoApp:
    def __init__(self):
        self.disp = init_display()
        self.state = DemoState()
        self.dirty = Event()
        self.screen_pos = 0
        self._was_held = False

        self.encoder = RotaryEncoder(ENCODER_CLK, ENCODER_DT, max_steps=0)
        self.button = Button(ENCODER_SW, pull_up=True, bounce_time=0.05, hold_time=HOLD_TIME)
        self.encoder.when_rotated = self._on_rotate
        self.button.when_held = self._on_hold
        self.button.when_released = self._on_release

    def _current_screen(self):
        return SCREEN_ORDER[self.screen_pos]

    def _on_hold(self):
        self._was_held = True
        self.screen_pos = (self.screen_pos + 1) % len(SCREEN_ORDER)
        print("Switched to:", SCREEN_NAMES[self.screen_pos])
        self.dirty.set()

    def _on_release(self):
        if self._was_held:
            self._was_held = False
            return
        screen = self._current_screen()
        if screen == SCREEN_NOW_PLAYING:
            self.state.playing = not self.state.playing
            print("Play/pause toggled:", self.state.playing)
        elif screen == SCREEN_EQ_PRESET:
            print("Applied preset (dummy):", PRESETS[self.state.eq_selected][0])
        self.dirty.set()

    def _on_rotate(self):
        steps = self.encoder.steps
        self.encoder.steps = 0
        if steps == 0:
            return
        screen = self._current_screen()
        if screen == SCREEN_NOW_PLAYING:
            print("Skip", "next" if steps > 0 else "prev", "(dummy)")
        elif screen == SCREEN_MPD_VOLUME:
            self.state.mpd_volume = max(0, min(100, self.state.mpd_volume + steps * VOLUME_STEP))
        elif screen == SCREEN_BT_VOLUME:
            self.state.bt_volume = max(0, min(100, self.state.bt_volume + steps * VOLUME_STEP))
        elif screen == SCREEN_EQ_PRESET:
            self.state.eq_selected = max(0, min(len(PRESETS) - 1, self.state.eq_selected + steps))
        self.dirty.set()

    def render(self):
        screen = self._current_screen()
        if screen == SCREEN_NOW_PLAYING:
            vu_levels = self.state.vu.read() if self.state.playing else None
            img = render_now_playing(self.state.now_playing_dict(), vu_levels)
        elif screen == SCREEN_MPD_VOLUME:
            img = render_mpd_volume(self.state.mpd_volume)
        elif screen == SCREEN_BT_VOLUME:
            img = render_bt_volume(self.state.bt_volume)
        else:
            names = [name for name, _ in PRESETS]
            img = render_eq_preset(names, self.state.eq_selected)
        self.disp.image(img)

    def run(self):
        print("Long-press: next screen | short-press: play/pause or apply preset | rotate: adjust")
        while True:
            self.state.tick()
            self.render()
            self.dirty.wait(timeout=TICK_SECONDS)
            self.dirty.clear()


if __name__ == "__main__":
    DemoApp().run()
