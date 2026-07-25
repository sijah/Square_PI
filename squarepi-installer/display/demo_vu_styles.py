#!/usr/bin/env python3
# Dedicated full-screen VU meter page -- cycles through all visual styles
# automatically every STYLE_SECONDS so you can compare them on the actual
# panel before picking one. No rotary encoder needed. Uses fake
# smoothed-random-walk levels (no MPD/HAT required).
import random
import time

import math

from st7735_driver import init_display
from vu_styles import (
    render_beat_ring,
    render_dual_scope,
    render_goniometer,
    render_gradient_bars,
    render_horizontal_bars,
    render_ladder_full,
    render_ladder_peak_hold,
    render_mirror_bars,
    render_needle,
    render_oscilloscope,
    render_particles,
    render_power_meter,
    render_radial,
    render_ripples,
    render_spectrum_16,
    render_starfield,
    render_vfd_dots,
    render_wave_fill,
    render_wave_ring,
    reset_peaks,
)

STYLE_SECONDS = 10
FRAME_SECONDS = 0.15  # fast redraw so the meter motion looks smooth


class FakeVuMeter:
    """Smoothed random walk -- stands in for vu_meter.VuMeter so the meter
    visibly moves without any real audio pipeline."""

    def __init__(self):
        self.left = 40.0
        self.right = 35.0

    def read(self):
        self.left = max(0, min(100, self.left + random.uniform(-12, 12)))
        self.right = max(0, min(100, self.right + random.uniform(-12, 12)))
        return self.left, self.right


class FakeSpectrum:
    """16 fake band levels shaped like real music: more energy in the low
    bands, each band randomly walking with a pull back toward its baseline."""

    def __init__(self, n=16):
        self.n = n
        self.base = [70 - i * 3 for i in range(n)]
        self.levels = list(self.base)

    def read(self):
        for i in range(self.n):
            drift = random.uniform(-14, 14) + (self.base[i] - self.levels[i]) * 0.2
            self.levels[i] = max(0, min(100, self.levels[i] + drift))
        return self.levels


class FakeScope:
    """Fake waveform for the oscilloscope and goniometer: a couple of summed
    sines with wandering amplitude and stereo width, so the scope shows a
    music-ish wave and the goniometer blooms/collapses as 'width' changes."""

    def __init__(self):
        self.phase = 0.0
        self.amp = 0.6
        self.width = 0.5  # 0 = mono (gonio collapses to a line), 1 = wide

    def _step_state(self):
        self.amp = max(0.1, min(1.0, self.amp + random.uniform(-0.08, 0.08)))
        self.width = max(0.0, min(1.0, self.width + random.uniform(-0.06, 0.06)))

    def read_mono(self, n=160):
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


STYLES = (
    ("A: LED ladder (full screen)", lambda vu, sp, sc: render_ladder_full(*vu.read())),
    ("B: Horizontal bars", lambda vu, sp, sc: render_horizontal_bars(*vu.read())),
    ("C: Gradient fill", lambda vu, sp, sc: render_gradient_bars(*vu.read())),
    ("D: Analog needle (mono)", lambda vu, sp, sc: render_needle(sum(vu.read()) / 2)),
    ("E: Radial arcs", lambda vu, sp, sc: render_radial(*vu.read())),
    ("F: 16-band spectrum", lambda vu, sp, sc: render_spectrum_16(sp.read())),
    ("G: LED ladder + peak hold", lambda vu, sp, sc: render_ladder_peak_hold(*vu.read())),
    ("H: Mirrored center-out bars", lambda vu, sp, sc: render_mirror_bars(*vu.read())),
    ("I: VFD dot-matrix", lambda vu, sp, sc: render_vfd_dots(*vu.read())),
    ("J: Goniometer (stereo scope)", lambda vu, sp, sc: render_goniometer(sc.read_pairs())),
    ("K: Oscilloscope", lambda vu, sp, sc: render_oscilloscope(sc.read_mono())),
    ("L: Beat-pulse ring", lambda vu, sp, sc: render_beat_ring(sum(vu.read()) / 2, "SquarePi")),
    ("M: Circular waveform ring", lambda vu, sp, sc: render_wave_ring(sc.read_mono(120))),
    ("N: Dual-trace scope (L/R)", lambda vu, sp, sc: render_dual_scope(sc.read_pairs(160))),
    ("O: Mirrored waveform fill", lambda vu, sp, sc: render_wave_fill(sc.read_mono())),
    ("P: Particle bursts", lambda vu, sp, sc: render_particles(sum(vu.read()) / 2)),
    ("Q: Starfield warp", lambda vu, sp, sc: render_starfield(sum(vu.read()) / 2)),
    ("R: Beat ripples", lambda vu, sp, sc: render_ripples(sum(vu.read()) / 2)),
    ("S: Power meter (vintage)", lambda vu, sp, sc: render_power_meter(sum(vu.read()) / 2)),
)


def main():
    disp = init_display()
    vu = FakeVuMeter()
    spectrum = FakeSpectrum()
    scope = FakeScope()
    style_pos = 0
    style_deadline = time.monotonic() + STYLE_SECONDS

    print(f"Cycling {len(STYLES)} VU meter styles every {STYLE_SECONDS}s. Ctrl+C to exit.")
    print("Showing:", STYLES[style_pos][0])

    while True:
        name, render = STYLES[style_pos]
        disp.image(render(vu, spectrum, scope))

        if time.monotonic() >= style_deadline:
            style_pos = (style_pos + 1) % len(STYLES)
            style_deadline = time.monotonic() + STYLE_SECONDS
            reset_peaks()
            print("Showing:", STYLES[style_pos][0])

        time.sleep(FRAME_SECONDS)


if __name__ == "__main__":
    main()
