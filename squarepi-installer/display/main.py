#!/usr/bin/env python3
# Main display service loop. Single KY-040 (rotate + short press + long press)
# drives all 4 primary screens -- interaction model locked in
# [[project-local-display]]:
#   rotate       = screen's primary continuous action
#   short press  = screen's primary discrete action
#   long press   = cycle to next screen
import time
from threading import Event

from gpiozero import Button, RotaryEncoder

import audio_control as audio
from eq_presets import PRESETS, apply_eq_preset
from screens import render_bt_volume, render_eq_preset, render_mpd_volume, render_now_playing
from st7735_driver import init_display
from vu_meter import VuMeter

SCREEN_NOW_PLAYING, SCREEN_MPD_VOLUME, SCREEN_BT_VOLUME, SCREEN_EQ_PRESET = range(4)
SCREEN_ORDER = (SCREEN_NOW_PLAYING, SCREEN_MPD_VOLUME, SCREEN_BT_VOLUME, SCREEN_EQ_PRESET)

ENCODER_CLK = 17
ENCODER_DT = 27
ENCODER_SW = 22

VOLUME_STEP = 4
HOLD_TIME = 0.6
TICK_SECONDS = 1.0


class DisplayApp:
    def __init__(self):
        self.disp = init_display()
        self.vu = VuMeter()
        self.dirty = Event()
        self.screen_pos = 0
        self.eq_selected = 0
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
        self.dirty.set()

    def _on_release(self):
        if self._was_held:
            self._was_held = False
            return
        screen = self._current_screen()
        if screen == SCREEN_NOW_PLAYING:
            audio.mpd_toggle_play_pause()
        elif screen == SCREEN_EQ_PRESET:
            _, band_values = PRESETS[self.eq_selected]
            apply_eq_preset(band_values)
        self.dirty.set()

    def _on_rotate(self):
        steps = self.encoder.steps
        self.encoder.steps = 0
        if steps == 0:
            return
        screen = self._current_screen()
        if screen == SCREEN_NOW_PLAYING:
            audio.mpd_next() if steps > 0 else audio.mpd_prev()
        elif screen == SCREEN_MPD_VOLUME:
            audio.mpd_volume_set(audio.mpd_volume_get() + steps * VOLUME_STEP)
        elif screen == SCREEN_BT_VOLUME:
            audio.bt_volume_set(audio.bt_volume_get() + steps * VOLUME_STEP)
        elif screen == SCREEN_EQ_PRESET:
            self.eq_selected = max(0, min(len(PRESETS) - 1, self.eq_selected + steps))
        self.dirty.set()

    def render(self):
        screen = self._current_screen()
        if screen == SCREEN_NOW_PLAYING:
            now_playing = audio.get_now_playing()
            is_mpd_playing = now_playing.get("source") == "MPD" and now_playing.get("playing")
            vu_levels = self.vu.read() if is_mpd_playing else None
            img = render_now_playing(now_playing, vu_levels)
        elif screen == SCREEN_MPD_VOLUME:
            img = render_mpd_volume(audio.mpd_volume_get())
        elif screen == SCREEN_BT_VOLUME:
            img = render_bt_volume(audio.bt_volume_get())
        else:
            names = [name for name, _ in PRESETS]
            img = render_eq_preset(names, self.eq_selected)
        self.disp.image(img)

    def run(self):
        try:
            while True:
                self.render()
                self.dirty.wait(timeout=TICK_SECONDS)
                self.dirty.clear()
        finally:
            self.vu.close()


if __name__ == "__main__":
    DisplayApp().run()
