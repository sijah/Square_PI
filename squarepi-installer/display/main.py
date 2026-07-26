#!/usr/bin/env python3
# Main display service loop. One KY-040 (rotate + short press + long press) drives
# every screen. Interaction model, revised for 2.0.0 (see [[project-local-display]]):
#
#   rotate      = the screen's continuous action; on screens that don't have one
#                 (Home, VU) it raises the volume overlay and adjusts volume
#   short press = the screen's discrete action; while the overlay is up it
#                 switches which path the volume targets
#   long press  = Menu from Home, Back everywhere else
#
# The old model cycled screens on long press, which spent the only spare gesture
# and made hierarchy impossible. Navigation now lives in nav.py, and all screen
# drawing in screens.py, so the only thing here is state and wiring.
import time
from threading import Event

from gpiozero import Button, RotaryEncoder
from PIL import Image

import audio_control as audio
import nav
import script_fonts
import sysinfo
import vu_styles
from eq_presets import PRESETS, apply_eq_preset, load_custom_presets
from screens import (WIDTH, bold, marquee_offset, marquee_period,
                     overlay_style_name, overlay_volume, render_confirm,
                     render_eq_applied, render_eq_presets, render_list,
                     render_music, render_network, render_now_playing,
                     render_queue, render_system, render_vu_needles)
from st7735_driver import init_display
from vu_meter import VuMeter

# All 19 vu_styles.py renderers, each fed from the real VuMeter -- level-based
# styles use the damped (left, right) amplitude (.read()); waveform-based styles
# (goniometer, oscilloscope, wave ring/fill, dual scope) need the raw rolling
# sample buffer instead (.read_pairs()/.read_waveform()); the spectrum style uses
# the derived (non-FFT) pseudo-spectrum -- see vu_meter.py.
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

ENCODER_CLK = 17
ENCODER_DT = 27
ENCODER_SW = 22

HOLD_TIME = 0.6
TICK_SECONDS = 1.0
FAST_TICK_SECONDS = 0.15   # VU pages animate rather than just refreshing once a second
MARQUEE_TICK_SECONDS = 0.08  # title scroll; only used while a title actually overruns
# Geometry the marquee has to agree with render_now_playing() on. Both the offset
# maths here and the drawing there measure against the same font and width, so a
# change to the title style needs changing in one place only.
MARQUEE_FONT_SIZE = 15
MARQUEE_MAX_W = WIDTH - 12
OVERLAY_SECONDS = 2.0      # how long the volume HUD lingers after the last detent
STYLE_NAME_SECONDS = 2.0   # style name stamp, so rotating 19 styles isn't blind
MUSIC_CACHE_SECONDS = 15   # don't re-query playlists on every repaint
QUEUE_CACHE_SECONDS = 5
BT_CACHE_SECONDS = 4       # BlueZ connection state, for the status-strip icon
# Now Playing metadata. Each read is an MPD socket round trip (connect, status,
# currentsong, parse), and _frame() needs one per frame. At the old 1 Hz that was
# free; with the marquee running at 12 Hz it became 12 MPD queries a second, which on
# a Zero 2W sharing four cores with FLAC decoding is enough to make the EQ web UI
# crawl. A scrolling title needs a new pixel offset, not new metadata. 0.5 s keeps
# the position readout honest -- it is displayed to the second.
NOW_PLAYING_CACHE_SECONDS = 0.5
EQ_CACHE_SECONDS = 10      # custom presets file; also re-read on entering the screen

# Menu rows, paired with the screen each one opens.
MENU_ITEMS = (
    ("Now Playing", nav.HOME),
    ("Play / Music", nav.PLAY),
    ("Playback Queue", nav.QUEUE),
    ("Equalizer", nav.EQ),
    ("VU Meter", nav.VU),
    ("Settings", nav.SETTINGS),
    ("System Info", nav.SYSTEM),
)
SETTINGS_ITEMS = (
    ("Network", nav.NETWORK),
    ("Display Timeout", None),   # cycles its value in place
    ("Power", nav.POWER),
)
POWER_ITEMS = (
    ("Restart", nav.CONFIRM_RESTART),
    ("Shut down", nav.CONFIRM_SHUTDOWN),
)
# In-RAM only, like the volume target: no config file, no SD writes, and a power
# cycle returns to a known state. Off by default -- a panel that goes black on its
# own is alarming if you didn't ask for it.
TIMEOUT_CHOICES = ((0, "Off"), (30, "30 s"), (120, "2 min"), (300, "5 min"))

SHUFFLE_ALL_LABEL = "Shuffle All Music"
# Music entry kinds. Resume sorts ahead of Shuffle because it's the
# non-destructive one -- if there's already a queue, "play that" is the likelier
# intent than "throw it away".
MUSIC_RESUME, MUSIC_SHUFFLE, MUSIC_PLAYLIST = "resume", "shuffle", "playlist"


class DisplayApp:
    def __init__(self):
        self.disp = init_display()
        self.vu = VuMeter()
        self.dirty = Event()
        self.nav = nav.Nav(now=time.monotonic())

        # Per-screen cursor positions, so returning to a list lands where you left.
        self.cursor = {n: 0 for n in (nav.MENU, nav.PLAY, nav.QUEUE, nav.EQ,
                                      nav.SETTINGS, nav.POWER, nav.VU_STYLE)}
        self.applied_eq = None
        self.last_applied_name = ""

        self._bt_cache = False
        self._bt_cache_t = 0.0
        self._np_cache = None
        self._np_cache_t = 0.0
        self._eq_cache = None
        self._eq_cache_t = 0.0

        self._music_cache = None
        self._music_cache_t = 0.0
        self._queue_cache = None
        self._queue_cache_t = 0.0

        # Volume overlay: detents accumulate here and are flushed by the render
        # loop, never applied from the callback. Each apply is a subprocess and a
        # brisk spin is 20+ detents a second.
        # Title marquee: the loop restarts whenever the title changes, so a new
        # track always begins from its first character rather than mid-slide.
        self._marquee_text = None
        self._marquee_t0 = 0.0
        self._marquee_active = False

        self._pending_detents = 0
        self._overlay_until = 0.0
        self._style_name_until = 0.0
        self._vol_error_until = 0.0

        self.timeout_choice = 0
        self._last_input = time.monotonic()
        self._blanked = False
        self._was_held = False

        self.encoder = RotaryEncoder(ENCODER_CLK, ENCODER_DT, max_steps=0)
        self.button = Button(ENCODER_SW, pull_up=True, bounce_time=0.05,
                             hold_time=HOLD_TIME)
        self.encoder.when_rotated = self._on_rotate
        self.button.when_held = self._on_hold
        self.button.when_released = self._on_release

    # ------------------------------------------------------------- helpers
    def _overlay_visible(self, now=None):
        return (now or time.monotonic()) < self._overlay_until

    def _note_input(self, now):
        self._last_input = now
        self.nav.touch(now)
        # Any input invalidates the metadata cache, so a press that changes what's
        # playing shows up on the next frame instead of when the TTL happens to lapse.
        self._np_cache = None
        if self._blanked:
            # First input after blanking only wakes the panel; it must not also
            # act, or a knock on the desk changes your volume.
            self._blanked = False
            self.dirty.set()
            return False
        return True

    def _music_entries(self, force=False):
        """(kind, label, hint) rows: available actions first, then saved playlists.
        Returns [] when MPD is unreachable, which the renderer surfaces rather
        than offering actions that couldn't work."""
        now = time.monotonic()
        if force or self._music_cache is None or (now - self._music_cache_t) > MUSIC_CACHE_SECONDS:
            playlists = audio.mpd_playlists()
            if playlists is None:
                self._music_cache = []
            else:
                entries = []
                queued, state = audio.mpd_queue_state()
                if queued and state != "play":
                    # Whatever a previous session or myMPD left queued is still
                    # there -- offer it before anything that would wipe it. The
                    # count goes in the hint, not the label: "Resume Queue (37)"
                    # is wider than the row and would elide.
                    entries.append((MUSIC_RESUME, "Resume Queue",
                                    f"{queued} TRACKS QUEUED"))
                entries.append((MUSIC_SHUFFLE, SHUFFLE_ALL_LABEL, None))
                entries.extend((MUSIC_PLAYLIST, name, None) for name in playlists)
                self._music_cache = entries
            self._music_cache_t = now
            self.cursor[nav.PLAY] = max(
                0, min(self.cursor[nav.PLAY], len(self._music_cache) - 1))
        return self._music_cache

    def _queue_tracks(self, force=False):
        now = time.monotonic()
        if force or self._queue_cache is None or (now - self._queue_cache_t) > QUEUE_CACHE_SECONDS:
            self._queue_cache = audio.mpd_queue_tracks() or []
            self._queue_cache_t = now
        return self._queue_cache

    def _rows_for(self, screen):
        """Row count of whatever list is on screen, for cursor clamping."""
        if screen == nav.MENU:
            return len(MENU_ITEMS)
        if screen == nav.SETTINGS:
            return len(SETTINGS_ITEMS)
        if screen == nav.POWER:
            return len(POWER_ITEMS)
        if screen == nav.EQ:
            return len(self._eq_presets())
        if screen == nav.VU_STYLE:
            return len(VU_STYLES)
        if screen == nav.PLAY:
            return len(self._music_entries())
        if screen == nav.QUEUE:
            return len(self._queue_tracks())
        return 0

    # ------------------------------------------------------------ callbacks
    def _on_hold(self):
        now = time.monotonic()
        self._was_held = True
        if not self._note_input(now):
            return
        if self._overlay_visible(now):
            # Dismiss the HUD and let the long press act on the screen underneath;
            # the overlay is a HUD, not a screen, so it never eats Back.
            self._overlay_until = 0.0
        screen = self.nav.long_press(now)
        self._on_enter(screen)
        self.dirty.set()

    def _on_release(self):
        if self._was_held:
            self._was_held = False
            return
        now = time.monotonic()
        if not self._note_input(now):
            return

        if self._overlay_visible(now):
            # Press switches which path the knob drives. This is the one gesture
            # the overlay does capture -- rotate is adjusting and long press is
            # Back, so press is all that's left.
            _, _, bt_available = audio.volume_levels()
            _, track_total = audio.track_position()
            audio.toggle_volume_target(bt_available, track_available=track_total > 0)
            self._overlay_until = now + OVERLAY_SECONDS
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
        if not self._note_input(now):
            return

        screen = self.nav.screen
        if self.nav.rotate_adjusts_volume():
            self._pending_detents += steps
            self._overlay_until = now + OVERLAY_SECONDS
        elif screen in self.cursor:
            rows = self._rows_for(screen)
            if rows:
                new = max(0, min(rows - 1, self.cursor[screen] + steps))
                if screen == nav.VU_STYLE and new != self.cursor[screen]:
                    vu_styles.reset_peaks()  # don't carry animation state across styles
                    self._style_name_until = now + STYLE_NAME_SECONDS
                self.cursor[screen] = new
        self.dirty.set()

    # ------------------------------------------------------- screen actions
    def _on_enter(self, screen):
        """Refresh anything that goes stale while you were elsewhere."""
        now = time.monotonic()
        if screen == nav.PLAY:
            self._music_entries(force=True)
        elif screen == nav.QUEUE:
            self._queue_tracks(force=True)
            current = audio.mpd_current_position()
            if current is not None:
                self.cursor[nav.QUEUE] = current
        elif screen == nav.EQ:
            # Re-read the custom presets file, so a preset you just saved in the
            # browser is on the list by the time you walk over to the knob.
            self._eq_presets(force=True)
            self.cursor[nav.EQ] = min(self.cursor[nav.EQ],
                                      max(0, len(self._eq_cache) - 1))
        elif screen == nav.VU_STYLE:
            vu_styles.reset_peaks()
            self._style_name_until = now + STYLE_NAME_SECONDS

    def _activate(self, screen, now):
        """Short press on a screen with the overlay down."""
        if screen == nav.HOME:
            audio.mpd_toggle_play_pause()

        elif screen == nav.MENU:
            _, target = MENU_ITEMS[self.cursor[nav.MENU]]
            if target == nav.HOME:
                self.nav.go_home(now)
            else:
                self.nav.push(target, now)
                self._on_enter(target)

        elif screen == nav.PLAY:
            entries = self._music_entries()
            if entries:
                kind, label, _ = entries[self.cursor[nav.PLAY]]
                if kind == MUSIC_RESUME:
                    audio.mpd_resume()
                elif kind == MUSIC_SHUFFLE:
                    audio.mpd_shuffle_all()
                else:
                    audio.mpd_play_playlist(label)
                self._music_cache = None   # the queue just changed
                self._queue_cache = None
                # Home is the confirmation that the press worked, and where you
                # want to be once music is running.
                self.nav.go_home(now)

        elif screen == nav.QUEUE:
            if self._queue_tracks():
                audio.mpd_play_position(self.cursor[nav.QUEUE])
                self.nav.go_home(now)

        elif screen == nav.EQ:
            index = self.cursor[nav.EQ]
            name, band_values = self._eq_presets()[index]
            apply_eq_preset(band_values)
            self.applied_eq = index
            self.last_applied_name = name
            # push, so the 2s confirmation falls back to the preset list rather
            # than to Home -- picking a second preset shouldn't mean navigating
            # in from scratch. It can't stack up: you can only press this from EQ,
            # and once you're on EQ_APPLIED the next press pops.
            self.nav.push(nav.EQ_APPLIED, now)

        elif screen == nav.EQ_APPLIED:
            self.nav.pop(now)

        elif screen == nav.VU:
            # Press opens the style browser. That's how the 19 full-screen meters
            # stay reachable without spending another Main Menu row on them;
            # play/pause lives on Home.
            self.nav.push(nav.VU_STYLE, now)
            self._on_enter(nav.VU_STYLE)

        elif screen == nav.VU_STYLE:
            self.nav.pop(now)

        elif screen == nav.SETTINGS:
            _, target = SETTINGS_ITEMS[self.cursor[nav.SETTINGS]]
            if target is None:
                self.timeout_choice = (self.timeout_choice + 1) % len(TIMEOUT_CHOICES)
            else:
                self.nav.push(target, now)
                self._on_enter(target)

        elif screen == nav.POWER:
            _, target = POWER_ITEMS[self.cursor[nav.POWER]]
            self.nav.push(target, now)

        elif screen in (nav.CONFIRM_RESTART, nav.CONFIRM_SHUTDOWN):
            self._power_action(screen)

        elif screen == nav.NETWORK:
            sysinfo._cache.clear()   # press refreshes

    def _power_action(self, screen):
        """Mute before halting, matching the existing /api/power behaviour -- an
        amp cut mid-signal thumps. Uses the existing MPD mixer only; nothing here
        touches the audio path ([[feedback-audio-path-frozen]])."""
        import subprocess
        try:
            audio.mpd_volume_set(0)
        except Exception:
            pass
        self.disp.image(render_confirm(
            "POWER", "Restarting…" if screen == nav.CONFIRM_RESTART else "Goodbye"))
        command = "reboot" if screen == nav.CONFIRM_RESTART else "poweroff"
        subprocess.run(["systemctl", command], stderr=subprocess.DEVNULL)

    # ---------------------------------------------------------------- render
    def _flush_volume(self):
        """Apply accumulated detents as one call. Runs on the render loop, not the
        encoder callback, which is what keeps a fast spin from queueing 20
        subprocesses behind the knob."""
        if self._pending_detents:
            detents, self._pending_detents = self._pending_detents, 0
            if audio.volume_nudge(detents) is None and audio.volume_target() == audio.TARGET_BT:
                # A write that ALSA refused. Say so on the panel: silently showing
                # the level we wanted is how the display ends up lying about the
                # hardware. Only meaningful for BT, whose control can be locked by
                # bluealsa-aplay; an absent control is reported separately.
                self._vol_error_until = time.monotonic() + 3.0

    def _eq_presets(self, force=False):
        """The 13 built-ins followed by whatever you saved in the web UI.

        Built-ins first and customs appended, so the index of a built-in never moves
        when you add or delete a custom -- self.applied_eq is an index, and a list
        that reorders itself would leave the applied marker pointing at the wrong
        row. Re-read on entering the screen (see _on_enter), which is what makes a
        preset saved in the browser appear without restarting the service."""
        now = time.monotonic()
        if (force or self._eq_cache is None
                or now - self._eq_cache_t > EQ_CACHE_SECONDS):
            self._eq_cache = list(PRESETS) + load_custom_presets()
            self._eq_cache_t = now
        return self._eq_cache

    def _now_playing(self, force=False):
        """Current track, cached so the marquee's frame rate doesn't multiply into MPD
        queries. Any user input forces a re-read, so pressing play/pause still updates
        the panel immediately rather than up to half a second later."""
        now = time.monotonic()
        if (force or self._np_cache is None
                or now - self._np_cache_t > NOW_PLAYING_CACHE_SECONDS):
            self._np_cache = audio.get_now_playing()
            self._np_cache_t = now
        return self._np_cache

    def _bt_connected(self):
        """Is a phone paired and connected, cached for a few seconds.

        Asks BlueZ directly rather than inferring it from what is playing. The old
        test -- source == "Bluetooth" -- left the status icon dark whenever a phone
        was connected but idle, or connected and playing on a handset that reports no
        AVRCP metadata, which is precisely the case bt_connected() was written for
        ([[project-bt-avrcp]]). Cached because this is a D-Bus round trip and the
        render loop runs at up to 12 Hz while a title is scrolling."""
        now = time.monotonic()
        if now - self._bt_cache_t > BT_CACHE_SECONDS:
            try:
                self._bt_cache = audio.bt_connected()
            except Exception:
                # Status icon, not a control path: an unreachable BlueZ shows no icon
                # rather than taking the panel down.
                self._bt_cache = False
            self._bt_cache_t = now
        return self._bt_cache

    def _marquee_scroll(self, now_playing):
        """Offset for the Now Playing title, and the flag that decides whether the
        loop needs to tick fast. A title that fits sets _marquee_active False, so
        the common case costs exactly what it did before the marquee existed: one
        repaint a second."""
        title = now_playing.get("title") or "Nothing playing"
        font = bold(MARQUEE_FONT_SIZE)
        now = time.monotonic()
        if title != self._marquee_text:
            self._marquee_text = title
            self._marquee_t0 = now
        self._marquee_active = marquee_period(title, font, MARQUEE_MAX_W) > 0
        if not self._marquee_active:
            return 0
        return marquee_offset(now - self._marquee_t0, title, font, MARQUEE_MAX_W)

    def _frame(self):
        screen = self.nav.screen
        now_playing = self._now_playing()
        flags = sysinfo.status_flags(bt_connected=self._bt_connected())

        if screen == nav.HOME:
            img = render_now_playing(now_playing, now_playing.get("fmt"), flags,
                                     scroll=self._marquee_scroll(now_playing))
        elif screen == nav.MENU:
            img = render_list("MAIN MENU", [label for label, _ in MENU_ITEMS],
                              self.cursor[nav.MENU], footer="PRESS OPEN · LONG BACK",
                              **flags)
        elif screen == nav.PLAY:
            entries = self._music_entries()
            labels = [label for _, label, _ in entries]
            actions = sum(1 for kind, _, _ in entries if kind != MUSIC_PLAYLIST)
            hint = entries[self.cursor[nav.PLAY]][2] if entries else None
            if hint is None and entries and len(labels) == actions:
                hint = "SAVE PLAYLISTS IN MYMPD"
            img = render_music(labels, self.cursor[nav.PLAY], actions, hint, **flags)
        elif screen == nav.QUEUE:
            img = render_queue(self._queue_tracks(), self.cursor[nav.QUEUE], **flags)
        elif screen == nav.EQ:
            entries = self._eq_presets()
            names = [name.replace("EQ ", "") for name, _ in entries]
            img = render_eq_presets(names, self.cursor[nav.EQ], self.applied_eq,
                                    custom_from=len(PRESETS) if len(entries) > len(PRESETS)
                                    else None, **flags)
        elif screen == nav.EQ_APPLIED:
            _, band_values = self._eq_presets()[self.cursor[nav.EQ]]
            img = render_eq_applied(self.last_applied_name.replace("EQ ", ""), band_values)
        elif screen == nav.VU:
            left, right = self.vu.read()
            img = render_vu_needles(left, right, volume=audio.mpd_volume_get(), **flags)
        elif screen == nav.VU_STYLE:
            _, render_fn = VU_STYLES[self.cursor[nav.VU_STYLE]]
            img = render_fn(self.vu)
            if time.monotonic() < self._style_name_until:
                name, _ = VU_STYLES[self.cursor[nav.VU_STYLE]]
                img = overlay_style_name(img, name, self.cursor[nav.VU_STYLE],
                                         len(VU_STYLES))
        elif screen == nav.SETTINGS:
            values = [None, TIMEOUT_CHOICES[self.timeout_choice][1], None]
            img = render_list("SETTINGS", [label for label, _ in SETTINGS_ITEMS],
                              self.cursor[nav.SETTINGS], values=values,
                              footer="PRESS OPEN · LONG BACK", **flags)
        elif screen == nav.POWER:
            img = render_list("POWER", [label for label, _ in POWER_ITEMS],
                              self.cursor[nav.POWER], footer="LONG PRESS · BACK",
                              **flags)
        elif screen == nav.NETWORK:
            img = render_network(sysinfo.network_info(), **flags)
        elif screen == nav.SYSTEM:
            img = render_system(sysinfo.system_info(), **flags)
        elif screen == nav.CONFIRM_RESTART:
            img = render_confirm("RESTART", "Restart?", **flags)
        elif screen == nav.CONFIRM_SHUTDOWN:
            img = render_confirm("SHUT DOWN", "Shut down?", **flags)
        else:
            img = render_now_playing(now_playing, now_playing.get("fmt"), flags)

        if self._overlay_visible():
            mpd_pct, bt_pct, bt_available = audio.volume_levels()
            track_index, track_total = audio.track_position()
            target = audio.volume_target()
            # The hint line describes the FOCUSED row. It used to announce
            # "BT NOT AVAILABLE" whenever BT was absent regardless of focus, so every
            # ordinary MPD volume turn on a unit that had never played Bluetooth came
            # with a warning about a row the user wasn't touching. The greyed row and
            # its "--" already say that; the hint only speaks for the active row.
            if target == audio.TARGET_TRACK and now_playing.get("source") == "Bluetooth":
                # Skip is MPD-only: `next` sent to MPD while a phone is playing over
                # Bluetooth does nothing audible. Say so rather than accept the
                # rotation and swallow it. AVRCP skip is a separate piece of work.
                hint = "SKIP IS MPD ONLY"
            elif target == audio.TARGET_BT and not bt_available:
                # Reachable when BT disappears while its row is focused; the row
                # cannot be selected in the first place while unavailable.
                hint = "BT NOT AVAILABLE"
            elif target == audio.TARGET_BT and time.monotonic() < self._vol_error_until:
                hint = "BT VOLUME LOCKED"
            else:
                hint = None
            img = overlay_volume(img, mpd_pct, bt_pct, target, bt_available, hint,
                                 track_index=track_index, track_total=track_total)
        return img

    def render(self):
        if self._blanked:
            return
        self.disp.image(self._frame())

    def _next_tick(self, now):
        """Sleep only until something will actually change: an animation frame, the
        overlay hiding, an auto-return firing, or the panel blanking."""
        screen = self.nav.screen
        animating = screen in (nav.VU, nav.VU_STYLE) or self._overlay_visible(now)
        if animating:
            candidates = [FAST_TICK_SECONDS]
        elif screen == nav.HOME and self._marquee_active:
            # Home only ticks fast while a title is genuinely too long for the
            # panel. _marquee_active is set by the previous frame's measurement,
            # which is a frame behind the truth and doesn't matter: the first frame
            # of a long title is the hold phase, where the offset is 0 anyway.
            candidates = [MARQUEE_TICK_SECONDS]
        else:
            candidates = [TICK_SECONDS]
        if self._overlay_visible(now):
            candidates.append(self._overlay_until - now)
        expiry = self.nav.seconds_until_expiry(now)
        if expiry is not None:
            candidates.append(expiry)
        limit = TIMEOUT_CHOICES[self.timeout_choice][0]
        if limit and not self._blanked:
            candidates.append(limit - (now - self._last_input))
        return max(0.05, min(candidates))

    def _maybe_blank(self, now):
        """Blank the panel once the display timeout has passed with no input.

        Blank rather than dim: backlight dimming needs the panel's LED pin on a
        GPIO, and on this wiring it may be tied to 3V3 ([[project-local-display]])."""
        limit = TIMEOUT_CHOICES[self.timeout_choice][0]
        if not limit or self._blanked or (now - self._last_input) <= limit:
            return
        self._blanked = True
        # render() returns early while blanked, so this flag would stay stuck at its
        # last value and spin the loop at marquee rate against a black panel.
        self._marquee_active = False
        self.disp.image(Image.new("RGB", (160, 128), (0, 0, 0)))

    def _step(self, now):
        """One iteration of the render loop, factored out of run() so it can be
        driven a frame at a time by the headless tests."""
        self._flush_volume()
        if not self._overlay_visible(now):
            # The TRACK row is not sticky, unlike the volume target. If it were, the
            # knob's resting action on Home would silently become "skip tracks" and
            # reaching for volume would lose your place in the queue.
            audio.release_track_target()
        if self.nav.expire(now):
            self._on_enter(self.nav.screen)
        self._maybe_blank(now)
        self.render()

    def run(self):
        try:
            while True:
                self._step(time.monotonic())
                self.dirty.wait(timeout=self._next_tick(time.monotonic()))
                self.dirty.clear()
        finally:
            self.vu.close()


def log_text_support():
    """One line to the journal about what the panel can actually render.

    Worth the noise because both failure modes are silent and look like each other
    from the outside: a missing script font draws .notdef boxes, and a Pillow built
    without libraqm draws the right glyphs in the wrong order -- which for Malayalam
    or Tamil is wrong in a way that still looks like text. Nobody debugging "the
    titles are square boxes" should have to guess which one they have."""
    installed = [tag for tag, _lo, _hi in script_fonts._BLOCKS
                 if script_fonts.font_path(tag)]
    missing = [tag for tag, _lo, _hi in script_fonts._BLOCKS
               if not script_fonts.font_path(tag)]
    print("display: script fonts:", ", ".join(installed) or "none",
          "| missing:", ", ".join(missing) or "none",
          "| complex shaping:", "yes" if script_fonts.shaping_available() else "NO",
          flush=True)
    if missing and script_fonts.shaping_available():
        print("display: install fonts-lohit-deva / -mlym / -taml for those scripts",
              flush=True)
    if not script_fonts.shaping_available():
        print("display: Pillow lacks libraqm -- Indic text will render in the wrong "
              "order even with fonts installed", flush=True)


if __name__ == "__main__":
    log_text_support()
    DisplayApp().run()
