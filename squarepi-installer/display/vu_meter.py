#!/usr/bin/env python3
# Real-time L/R level reader for the Now Playing VU meter and for every
# vu_styles.py screen. MPD-only by design (see [[project-local-display]] --
# Bluetooth doesn't need metering).
#
# Requires a second, additive audio_output in /etc/mpd.conf -- does not touch the
# existing alsa output / squarepi_mix dmix chain:
#
#     audio_output {
#         type    "fifo"
#         name    "vu_meter"
#         path    "/tmp/mpd.fifo"
#         format  "44100:16:2"
#     }
#
# HOW IT MEASURES LEVEL
#
# Every poll drains the whole fifo (MPD writes 44100 frames/sec regardless of
# how often we look) and keeps the freshest BUFFER_LEN frames. read() reports
# the peak of that window, put through attack/release ballistics.
#
# Two deliberate departures from PeppyMeter (github.com/project-owner/
# PeppyMeter, datasource.py), whose drain-the-pipe approach this started from:
#
#   1. Samples are 16-bit *signed* PCM (format above), so bytes are decoded as
#      signed and abs()'d for amplitude. PeppyMeter's own code reads the same
#      bytes as unsigned, which on signed PCM produces huge spurious swings on
#      negative half-cycles.
#   2. Level comes from the peak over a short window, not from the single
#      freshest sample. One instantaneous sample says very little about
#      loudness: a full-scale sine crosses zero twice per cycle, so reading it
#      at one arbitrary instant lands anywhere between 0 and 100. BUFFER_LEN
#      frames is ~4.5 ms at 44.1 kHz -- at least one full cycle down to ~220 Hz.
#
# Damping is a plain asymmetric one-pole filter over that peak; see
# _ballistic() for what it replaced and why.
#
# WHAT EACH ACCESSOR IS FOR
#
# read() feeds the small Now Playing meter and the 13 level-based vu_styles.py
# screens. read_waveform()/read_pairs() expose the rolling sample buffer itself,
# needed by the screens that draw an actual trace (oscilloscope, goniometer,
# dual scope, wave ring/fill). All accessors share one drain pass, so a single
# pipe fd serves both consumption styles without contention.
import math
import os
import random
import struct
import time
from collections import deque

PIPE_PATH = "/tmp/mpd.fifo"

# Covers the largest window any vu_styles.py renderer asks for (read_pairs'
# default of 200). ~4.5 ms of audio at 44.1 kHz.
BUFFER_LEN = 200
TAIL_BYTES = BUFFER_LEN * 4  # 4 bytes per frame: 2 channels x 16-bit
CHUNK_BYTES = 4096           # multiple of 4, so every read lands on a frame

# Needle ballistics, expressed as time constants in seconds rather than
# per-poll fractions: main.py polls at 1 Hz on most screens but ~6.7 Hz on the
# VU Style screen, and a fixed per-poll coefficient would make the meter behave
# differently on each. Converted to a coefficient from real elapsed time.
ATTACK_TC = 0.15   # rise: ~63% of the gap closed in 150 ms
RELEASE_TC = 0.55  # fall: slower, so the needle drops back rather than snapping

# How long the fifo may go quiet before the rolling buffers count as silence
# instead of as the last thing that played.
STALE_AFTER = 0.5


class VuMeter:
    def __init__(self, pipe_path=PIPE_PATH):
        self.pipe_path = pipe_path
        self.pipe = None
        self.level_left = 0.0
        self.level_right = 0.0
        self._mono_buf = deque(maxlen=BUFFER_LEN)
        self._pair_buf = deque(maxlen=BUFFER_LEN)
        self._carry = b""         # trailing partial frame, carried between drains
        self._last_data_t = None  # monotonic time of the last frame actually read
        self._last_read_t = None  # monotonic time of the last read() call
        self._frames_since_read = 0
        self._open()

    def _open(self):
        try:
            self.pipe = os.open(self.pipe_path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            self.pipe = None

    def _drain_all(self):
        """Empty the fifo, decode the freshest BUFFER_LEN frames into the
        rolling buffers, and return how many frames were appended.

        Reads in CHUNK_BYTES blocks and bulk-unpacks only the tail, rather than
        one 4-byte os.read plus one struct call per frame: at 44.1 kHz the
        per-frame form costs ~44k syscalls and ~44k struct calls every second,
        which is measurable CPU on a Zero 2W. Nothing needs the frames that get
        skipped -- no renderer asks for more than BUFFER_LEN samples, and
        read()'s peak window is that same buffer.

        Safe for any accessor to call, including twice in one tick: the frame
        count accrues in self._frames_since_read until read() consumes it, so a
        second drain that finds nothing cannot hide the first one's data.
        """
        if self.pipe is None:
            self._open()
            if self.pipe is None:
                return 0
        buf = self._carry
        self._carry = b""
        while True:
            try:
                chunk = os.read(self.pipe, CHUNK_BYTES)
            except BlockingIOError:
                break  # nothing more queued right now
            except OSError:
                self.pipe = None
                return 0
            if not chunk:
                break  # EOF -- no writer on the fifo
            buf += chunk
            # Cap the working buffer. A long backlog (the display parked on
            # another screen for a while) would otherwise grow it unbounded.
            if len(buf) > TAIL_BYTES * 2:
                drop = len(buf) - TAIL_BYTES
                drop -= drop % 4  # never split a frame
                buf = buf[drop:]
        frames = len(buf) // 4
        self._carry = buf[frames * 4:]
        if frames == 0:
            return 0
        if frames > BUFFER_LEN:  # only the freshest window can still matter
            buf = buf[(frames - BUFFER_LEN) * 4:frames * 4]
            frames = BUFFER_LEN
        else:
            buf = buf[:frames * 4]
        samples = struct.unpack("<%dh" % (frames * 2), buf)
        for i in range(0, frames * 2, 2):
            lf = samples[i] / 32768.0
            rf = samples[i + 1] / 32768.0
            self._pair_buf.append((lf, rf))
            self._mono_buf.append((lf + rf) / 2.0)
        self._last_data_t = time.monotonic()
        self._frames_since_read += frames
        return frames

    def _buffers_live(self):
        """False once the fifo has been quiet for STALE_AFTER seconds -- MPD
        paused, stopped, or never started. Without this the rolling buffers
        would keep serving the last window of audio indefinitely, so a scope
        trace would freeze mid-waveform instead of flattening out.

        Only the trace accessors use this: a trace can only be shown or not, so
        a short hold keeps it from flickering between polls. read() has real
        ballistics and instead falls back the moment no new frames arrive, so
        the needle glides down on pause rather than freezing for STALE_AFTER
        and then dropping."""
        if self._last_data_t is None:
            return False
        return (time.monotonic() - self._last_data_t) < STALE_AFTER

    @staticmethod
    def _ballistic(previous, target, dt):
        """One attack/release step from `previous` toward `target`, both 0-100.

        This replaced a log-ratio damping step that fed 20*log10(new/previous)
        into the displayed value. Because that output depended only on the
        *ratio* between successive samples, it reported rate-of-change rather
        than level: a steady loud signal pegged near full scale, a steady quiet
        one strobed between ~0 and ~87, and since it stored its own damped
        output as "previous", each frame compared an amplitude against a
        damping result. What follows is an ordinary one-pole filter over the
        real amplitude, rising faster than it falls -- which is what an analog
        VU needle does.
        """
        if dt is None:
            return target  # first reading: adopt the level outright
        tc = ATTACK_TC if target > previous else RELEASE_TC
        coeff = 1.0 - math.exp(-max(0.0, dt) / tc)
        return previous + (target - previous) * coeff

    def read(self):
        """Returns (left, right), each 0-100: peak over the freshest window,
        smoothed by the ballistics above. Releases toward 0 when nothing is
        playing rather than holding the last level."""
        self._drain_all()
        fresh, self._frames_since_read = self._frames_since_read, 0
        now = time.monotonic()
        dt = None if self._last_read_t is None else now - self._last_read_t
        self._last_read_t = now

        if fresh and self._pair_buf:
            window = list(self._pair_buf)
            target_left = max(abs(l) for l, _ in window) * 100.0
            target_right = max(abs(r) for _, r in window) * 100.0
        else:
            target_left = target_right = 0.0

        self.level_left = self._ballistic(self.level_left, target_left, dt)
        self.level_right = self._ballistic(self.level_right, target_right, dt)
        return self.level_left, self.level_right

    def read_waveform(self, n=160):
        """Last n mono samples (-1.0..1.0), oldest first. [] if nothing is
        playing."""
        self._drain_all()
        if not self._buffers_live():
            return []
        return list(self._mono_buf)[-n:]

    def read_pairs(self, n=200):
        """Last n (left, right) sample pairs (-1.0..1.0), oldest first. [] if
        nothing is playing."""
        self._drain_all()
        if not self._buffers_live():
            return []
        return list(self._pair_buf)[-n:]

    def read_pseudo_spectrum(self, n=16):
        """Derived, NOT a real per-band decomposition -- true per-band data
        needs an FFT (deferred, see vu_styles.render_spectrum_16 docstring;
        no numpy dependency on a Zero 2W). Shapes the real recent RMS level
        with a fixed bass-heavy falloff plus small jitter, so the spectrum
        style still tracks actual playback (silent when nothing plays) rather
        than being pure random noise."""
        self._drain_all()
        if not self._buffers_live() or not self._mono_buf:
            return [0.0] * n
        recent = list(self._mono_buf)
        # RMS across the whole window, scaled so a full-scale sine reads ~100.
        rms = math.sqrt(sum(s * s for s in recent) / len(recent))
        level = min(100.0, rms * 100.0 * math.sqrt(2.0))
        return [max(0.0, min(100.0, level * (1.0 - (i / n) * 0.6) + random.uniform(-6, 6)))
                for i in range(n)]

    def close(self):
        if self.pipe is not None:
            try:
                os.close(self.pipe)
            except OSError:
                pass
            self.pipe = None
