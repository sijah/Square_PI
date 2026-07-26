#!/usr/bin/env python3
# Encoder-driven demo: drives the REAL nav.py state machine with fake data. No
# MPD, no Bluetooth, no SquarePi HAT and no amixer required -- just the ST7735 and
# KY-040 wired up.
#
# This is the honest way to check the 2.0.0 interaction model on hardware before
# the services are involved: navigation, the auto-return timeouts and the volume
# overlay are the same code main.py runs. Only the data and the volume writes are
# faked, and the power confirmations are deliberately inert.
#
#   rotate      = scroll on lists; on Home/VU it raises the volume overlay
#   short press = open/apply; switches volume target while the overlay is up
#   long press  = Menu from Home, Back everywhere else
import math
import random
import time
from threading import Event

from gpiozero import Button, RotaryEncoder
from PIL import Image

import nav
import vu_styles
from eq_presets import PRESETS
from screens import (WIDTH, bold, marquee_offset, marquee_period,
                     overlay_style_name, overlay_volume, render_confirm,
                     render_eq_applied, render_eq_presets, render_list,
                     render_music, render_network, render_now_playing,
                     render_queue, render_system, render_vu_needles)
from st7735_driver import init_display

ENCODER_CLK = 17
ENCODER_DT = 27
ENCODER_SW = 22
HOLD_TIME = 0.6
TICK_SECONDS = 1.0
FAST_TICK_SECONDS = 0.15
OVERLAY_SECONDS = 2.0
STYLE_NAME_SECONDS = 2.0

FLAGS = {"wifi": True, "bt": True}
MENU_ITEMS = (("Now Playing", nav.HOME), ("Play / Music", nav.PLAY),
              ("Playback Queue", nav.QUEUE), ("Equalizer", nav.EQ),
              ("VU Meter", nav.VU), ("Settings", nav.SETTINGS),
              ("System Info", nav.SYSTEM))
SETTINGS_ITEMS = (("Network", nav.NETWORK), ("Display Timeout", None),
                  ("Power", nav.POWER))
POWER_ITEMS = (("Restart", nav.CONFIRM_RESTART), ("Shut down", nav.CONFIRM_SHUTDOWN))
TIMEOUT_CHOICES = ((0, "Off"), (30, "30 s"), (120, "2 min"), (300, "5 min"))

# Stand-ins for audio_control's real queries, so the lists have something to scroll.
MUSIC_ACTIONS = ("Resume Queue", "Shuffle All Music")
MUSIC_HINT = "37 TRACKS QUEUED"
MUSIC_ENTRIES = (*MUSIC_ACTIONS, "Bass Test", "chill evening",
                 "Late Night Deep House", "Workout")
QUEUE_TRACKS = (("Time", "Pink Floyd", 413), ("Money", "Pink Floyd", 382),
                ("Us and Them", "Pink Floyd", 469),
                ("Any Colour You Like", "Pink Floyd", 204),
                ("Brain Damage", "Pink Floyd", 226))
# The overlay's TRACK row shows a position against the whole queue, not against the
# five rows the Queue screen demo happens to list. 550 is the real drive measured in
# [[usb-queue-persistence]], so the row is exercised at a realistic width.
DEMO_QUEUE_LEN = 550
NETWORK = {"connected": True, "ssid": "SquarePi_Net", "ip": "192.168.1.105",
           "signal": "-48 dBm", "host": "squarepi.local"}
SYSTEM = {"firmware": "2.0.0 (demo)", "board": "Pi Zero 2 W", "cpu_temp": "42 °C",
          "uptime": "3d 14h", "memory_pct": 38, "storage_pct": 29}

# Mirrors main.py's VU_STYLES table -- same 19 vu_styles.py renderers, fed by
# FakeVuMeter below instead of the real fifo-backed VuMeter.
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


class FakeVuMeter:
    """Smoothed random walk + fake waveform generator standing in for
    vu_meter.VuMeter -- same read()/read_waveform()/read_pairs()/
    read_pseudo_spectrum() interface, so every VU_STYLES entry has something to
    draw. Purely visual: no fifo, no real PCM."""

    def __init__(self):
        self.left, self.right = 40.0, 35.0
        self.phase, self.amp, self.width = 0.0, 0.6, 0.5

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


class DemoApp:
    """Mirrors main.py's DisplayApp with fake data and no real writes."""

    def __init__(self):
        self.disp = init_display()
        self.vu = FakeVuMeter()
        self.dirty = Event()
        self.nav = nav.Nav(now=time.monotonic())
        self.cursor = {n: 0 for n in (nav.MENU, nav.PLAY, nav.QUEUE, nav.EQ,
                                      nav.SETTINGS, nav.POWER, nav.VU_STYLE)}
        self.mpd_volume, self.bt_volume = 62, 48
        self.volume_target = "MPD"
        self.track_index = 14
        self.applied_eq = None
        self.last_applied_name = ""
        self.timeout_choice = 0
        self.elapsed = 42.0
        self._last_frame = time.monotonic()
        self._t0 = self._last_frame
        self._marquee_active = False
        self._pending_detents = 0
        self._overlay_until = 0.0
        self._style_name_until = 0.0
        self._was_held = False

        self.encoder = RotaryEncoder(ENCODER_CLK, ENCODER_DT, max_steps=0)
        self.button = Button(ENCODER_SW, pull_up=True, bounce_time=0.05,
                             hold_time=HOLD_TIME)
        self.encoder.when_rotated = self._on_rotate
        self.button.when_held = self._on_hold
        self.button.when_released = self._on_release

    def _overlay_visible(self, now=None):
        return (now or time.monotonic()) < self._overlay_until

    def _rows_for(self, screen):
        return {nav.MENU: len(MENU_ITEMS), nav.SETTINGS: len(SETTINGS_ITEMS),
                nav.POWER: len(POWER_ITEMS), nav.EQ: len(PRESETS),
                nav.VU_STYLE: len(VU_STYLES), nav.PLAY: len(MUSIC_ENTRIES),
                nav.QUEUE: len(QUEUE_TRACKS)}.get(screen, 0)

    # ------------------------------------------------------------ callbacks
    def _on_hold(self):
        now = time.monotonic()
        self._was_held = True
        self._overlay_until = 0.0
        screen = self.nav.long_press(now)
        if screen == nav.VU_STYLE:
            self._style_name_until = now + STYLE_NAME_SECONDS
        print("  ->", screen)
        self.dirty.set()

    def _on_release(self):
        if self._was_held:
            self._was_held = False
            return
        now = time.monotonic()
        if self._overlay_visible(now):
            order = ("MPD", "BT", "TRACK")
            self.volume_target = order[(order.index(self.volume_target) + 1) % 3]
            self._overlay_until = now + OVERLAY_SECONDS
            print("  overlay row:", self.volume_target)
            self.dirty.set()
            return
        self._activate(self.nav.screen, now)
        self.dirty.set()

    def _on_rotate(self):
        steps = self.encoder.steps
        self.encoder.steps = 0
        if steps == 0:
            return
        now = time.monotonic()
        self.nav.touch(now)
        screen = self.nav.screen
        if self.nav.rotate_adjusts_volume():
            self._pending_detents += steps
            self._overlay_until = now + OVERLAY_SECONDS
        elif screen in self.cursor:
            rows = self._rows_for(screen)
            if rows:
                new = max(0, min(rows - 1, self.cursor[screen] + steps))
                if screen == nav.VU_STYLE and new != self.cursor[screen]:
                    vu_styles.reset_peaks()
                    self._style_name_until = now + STYLE_NAME_SECONDS
                self.cursor[screen] = new
        self.dirty.set()

    def _activate(self, screen, now):
        if screen == nav.HOME:
            print("  play/pause (fake)")
        elif screen == nav.MENU:
            _, target = MENU_ITEMS[self.cursor[nav.MENU]]
            if target == nav.HOME:
                self.nav.go_home(now)
            else:
                self.nav.push(target, now)
            print("  ->", self.nav.screen)
        elif screen == nav.PLAY:
            print("  would play:", MUSIC_ENTRIES[self.cursor[nav.PLAY]])
            self.nav.go_home(now)
        elif screen == nav.QUEUE:
            print("  would play queue position", self.cursor[nav.QUEUE])
            self.nav.go_home(now)
        elif screen == nav.EQ:
            index = self.cursor[nav.EQ]
            self.applied_eq = index
            self.last_applied_name = PRESETS[index][0]
            print("  would apply:", self.last_applied_name)
            self.nav.push(nav.EQ_APPLIED, now)
        elif screen == nav.EQ_APPLIED:
            self.nav.pop(now)
        elif screen == nav.VU:
            self.nav.push(nav.VU_STYLE, now)
            self._style_name_until = now + STYLE_NAME_SECONDS
        elif screen == nav.VU_STYLE:
            self.nav.pop(now)
        elif screen == nav.SETTINGS:
            _, target = SETTINGS_ITEMS[self.cursor[nav.SETTINGS]]
            if target is None:
                self.timeout_choice = (self.timeout_choice + 1) % len(TIMEOUT_CHOICES)
                print("  display timeout:", TIMEOUT_CHOICES[self.timeout_choice][1])
            else:
                self.nav.push(target, now)
        elif screen == nav.POWER:
            self.nav.push(POWER_ITEMS[self.cursor[nav.POWER]][1], now)
        elif screen in (nav.CONFIRM_RESTART, nav.CONFIRM_SHUTDOWN):
            # Deliberately inert: a visual demo must never halt the Pi.
            print("  CONFIRMED (demo: no action taken)")
            self.nav.go_home(now)

    # --------------------------------------------------------------- render
    def _now_playing(self):
        # Deliberately long enough to overrun 148px: a demo title that fits would
        # never exercise the marquee, which is the thing most worth watching on real
        # hardware (SPI bandwidth and PIL cost, not geometry).
        return {"playing": True, "stopped": False,
                "title": "Bohemian Rhapsody (Remastered 2011 Deluxe Edition)",
                "artist": "Queen", "album": "A Night at the Opera", "source": "MPD",
                "elapsed": self.elapsed, "duration": 355.0,
                "fmt": ["FLAC", "16bit", "44.1k"]}

    def _marquee_scroll(self, title):
        """Same shape as main.py's, minus the track-change reset: the demo's title
        never changes."""
        self._marquee_active = marquee_period(title, bold(15), WIDTH - 12) > 0
        if not self._marquee_active:
            return 0
        return marquee_offset(time.monotonic() - self._t0, title, bold(15), WIDTH - 12)

    def _frame(self):
        screen = self.nav.screen
        if screen == nav.HOME:
            np = self._now_playing()
            img = render_now_playing(np, np["fmt"], FLAGS,
                                     scroll=self._marquee_scroll(np["title"]))
        elif screen == nav.MENU:
            img = render_list("MAIN MENU", [label for label, _ in MENU_ITEMS],
                              self.cursor[nav.MENU],
                              footer="PRESS OPEN · LONG BACK", **FLAGS)
        elif screen == nav.PLAY:
            selected = self.cursor[nav.PLAY]
            img = render_music(list(MUSIC_ENTRIES), selected, len(MUSIC_ACTIONS),
                               MUSIC_HINT if selected == 0 else None, **FLAGS)
        elif screen == nav.QUEUE:
            img = render_queue(list(QUEUE_TRACKS), self.cursor[nav.QUEUE], **FLAGS)
        elif screen == nav.EQ:
            names = [name.replace("EQ ", "") for name, _ in PRESETS]
            img = render_eq_presets(names, self.cursor[nav.EQ], self.applied_eq, **FLAGS)
        elif screen == nav.EQ_APPLIED:
            _, bands = PRESETS[self.cursor[nav.EQ]]
            img = render_eq_applied(self.last_applied_name.replace("EQ ", ""), bands)
        elif screen == nav.VU:
            left, right = self.vu.read()
            img = render_vu_needles(left, right, volume=self.mpd_volume,
                                    peak_db=-2.1, **FLAGS)
        elif screen == nav.VU_STYLE:
            name, render_fn = VU_STYLES[self.cursor[nav.VU_STYLE]]
            img = render_fn(self.vu)
            if time.monotonic() < self._style_name_until:
                img = overlay_style_name(img, name, self.cursor[nav.VU_STYLE],
                                         len(VU_STYLES))
        elif screen == nav.SETTINGS:
            img = render_list("SETTINGS", [label for label, _ in SETTINGS_ITEMS],
                              self.cursor[nav.SETTINGS],
                              values=[None, TIMEOUT_CHOICES[self.timeout_choice][1], None],
                              footer="PRESS OPEN · LONG BACK", **FLAGS)
        elif screen == nav.POWER:
            img = render_list("POWER", [label for label, _ in POWER_ITEMS],
                              self.cursor[nav.POWER], footer="LONG PRESS · BACK", **FLAGS)
        elif screen == nav.NETWORK:
            img = render_network(NETWORK, **FLAGS)
        elif screen == nav.SYSTEM:
            img = render_system(SYSTEM, **FLAGS)
        elif screen == nav.CONFIRM_RESTART:
            img = render_confirm("RESTART", "Restart?", **FLAGS)
        elif screen == nav.CONFIRM_SHUTDOWN:
            img = render_confirm("SHUT DOWN", "Shut down?", **FLAGS)
        else:
            img = Image.new("RGB", (160, 128), (0, 0, 0))

        if self._overlay_visible():
            img = overlay_volume(img, self.mpd_volume, self.bt_volume,
                                 self.volume_target,
                                 track_index=self.track_index,
                                 track_total=DEMO_QUEUE_LEN)
        return img

    def _flush_volume(self):
        """Same coalescing shape as main.py, so the knob feel being tested here is
        the knob feel that ships."""
        if self._pending_detents:
            detents, self._pending_detents = self._pending_detents, 0
            if self.volume_target == "TRACK":
                # Moves the position instead of a level, the same way the real one
                # walks the queue. Nothing is played here.
                self.track_index = max(1, min(DEMO_QUEUE_LEN,
                                              self.track_index + detents))
                print("  would skip to", self.track_index)
            elif self.volume_target == "MPD":
                self.mpd_volume = max(0, min(100, self.mpd_volume + detents * 4))
            else:
                self.bt_volume = max(0, min(100, self.bt_volume + detents * 4))

    def run(self):
        print("Demo: rotate / press / long press. Ctrl+C to exit.")
        print("  ->", self.nav.screen)
        while True:
            now = time.monotonic()
            self.elapsed = (self.elapsed + (now - self._last_frame)) % 355.0
            self._last_frame = now
            self._flush_volume()
            if self.nav.expire(now):
                print("  timeout ->", self.nav.screen)
            self.disp.image(self._frame())

            animating = (self.nav.screen in (nav.VU, nav.VU_STYLE)
                         or self._overlay_visible(now)
                         or (self.nav.screen == nav.HOME and self._marquee_active))
            self.dirty.wait(timeout=FAST_TICK_SECONDS if animating else TICK_SECONDS)
            self.dirty.clear()


if __name__ == "__main__":
    DemoApp().run()
