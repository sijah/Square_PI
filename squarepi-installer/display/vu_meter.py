#!/usr/bin/env python3
# Real-time L/R level reader for the Now Playing VU meter. MPD-only by design
# (see [[project-local-display]] -- Bluetooth doesn't need metering).
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
# Technique mirrors PeppyMeter (github.com/project-owner/PeppyMeter
# datasource.py): drain the pipe to the single freshest sample rather than a
# windowed RMS, then damp successive samples with a log-ratio step so the meter
# has analog-needle-like inertia instead of jittering every poll.
#
# Deviation from PeppyMeter: samples are 16-bit *signed* PCM (format above),
# so bytes are decoded as signed and abs()'d for amplitude. PeppyMeter's own
# code reads the same bytes as unsigned, which on signed PCM produces huge
# spurious swings on negative half-cycles -- not carried over here.
import math
import os
import struct

PIPE_PATH = "/tmp/mpd.fifo"


class VuMeter:
    def __init__(self, pipe_path=PIPE_PATH):
        self.pipe_path = pipe_path
        self.pipe = None
        self.prev_left = 0.0
        self.prev_right = 0.0
        self._open()

    def _open(self):
        try:
            self.pipe = os.open(self.pipe_path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            self.pipe = None

    def _drain_latest(self):
        if self.pipe is None:
            self._open()
            if self.pipe is None:
                return None
        latest = None
        while True:
            try:
                chunk = os.read(self.pipe, 4)
            except BlockingIOError:
                break
            except OSError:
                self.pipe = None
                return None
            if not chunk:
                break
            if len(chunk) == 4:
                latest = chunk
        return latest

    @staticmethod
    def _damp(previous, new):
        """Log-ratio damping between successive samples -- see module docstring."""
        if previous <= 0:
            return new
        if new <= 0:
            return 0.0
        db = 20 * math.log10(new / previous)
        db = max(-20.0, min(3.0, db))
        return (db + 20.0) * (100.0 / 23.0)

    def read(self):
        """Returns (left, right) each 0-100. (0, 0) if no data (pipe not open,
        MPD not playing, or nothing written recently)."""
        chunk = self._drain_latest()
        if not chunk:
            return 0.0, 0.0
        left_sample, right_sample = struct.unpack_from("<hh", chunk, 0)
        left_raw = abs(left_sample) / 32768 * 100
        right_raw = abs(right_sample) / 32768 * 100
        left = self._damp(self.prev_left, left_raw)
        right = self._damp(self.prev_right, right_raw)
        self.prev_left, self.prev_right = left, right
        return left, right

    def close(self):
        if self.pipe is not None:
            try:
                os.close(self.pipe)
            except OSError:
                pass
            self.pipe = None
