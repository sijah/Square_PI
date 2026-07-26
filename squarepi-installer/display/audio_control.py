#!/usr/bin/env python3
# MPD/BT status polling and transport/volume control for the display service.
# MPD parts mirror eq-server.py's _mpd_now_playing() (eq-server.py:273) but widen
# state to include "pause" and add elapsed/duration -- eq-server.py's version only
# needed play/title/artist for the web now-playing strip. BT volume mirrors
# get_bt_volume()/set_bt_volume() (eq-server.py:229). TODO: once this is proven on
# hardware, factor eq-server.py to import from here instead of duplicating.
import socket
import subprocess
import time

CARD = "LouderRaspberry"
BT_VOL_CONTROL = "BT Volume"
MPD_HOST = ("127.0.0.1", 6600)


def _run(args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=2).stdout
    except Exception:
        return ""


def mpc(*args, timeout=10):
    # Called from the encoder callback thread, so a wedged MPD must not block
    # forever: every invocation is bounded and failures are swallowed. 10s is
    # generous enough for "add the whole library" on a slow SD card.
    try:
        subprocess.run(["mpc", *args], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=timeout)
    except Exception:
        pass


def _mpd_status():
    try:
        s = socket.create_connection(MPD_HOST, timeout=0.4)
        s.settimeout(0.4)
        f = s.makefile("rw", encoding="utf-8", newline="\n")
        f.readline()  # greeting line
        f.write("command_list_begin\nstatus\ncurrentsong\ncommand_list_end\n")
        f.flush()
        data = {}
        for line in f:
            if line.startswith("OK") or line.startswith("ACK"):
                break
            if ": " in line:
                k, v = line.split(": ", 1)
                data.setdefault(k.strip(), v.strip())
        try:
            s.close()
        except Exception:
            pass
        return data
    except Exception:
        return {}


def _mpd_lines(command):
    """Run one MPD command and return its raw response lines, or None if MPD
    couldn't be reached at all. Callers need that distinction: an empty list is a
    legitimate answer ("no playlists saved"), None is a broken daemon.

    Separate from _mpd_status() because that one collapses duplicate keys via
    setdefault, which is exactly wrong for list responses like listplaylists."""
    try:
        s = socket.create_connection(MPD_HOST, timeout=0.4)
        s.settimeout(1.5)
        f = s.makefile("rw", encoding="utf-8", newline="\n")
        f.readline()  # greeting line
        f.write(command + "\n")
        f.flush()
        out = []
        for line in f:
            if line.startswith("OK") or line.startswith("ACK"):
                break
            out.append(line.rstrip("\n"))
        try:
            s.close()
        except Exception:
            pass
        return out
    except Exception:
        return None


def _safe_float(value):
    try:
        return float(value or 0)
    except ValueError:
        return 0.0


def get_mpd_now_playing():
    data = _mpd_status()
    state = data.get("state")
    # "stop" is included deliberately: a queue left sitting there by myMPD still
    # has a current song, and reporting that as "nothing playing" hid the one
    # thing the user wanted -- press to start it. A genuinely empty queue has no
    # current song, so it still falls through to None below.
    if state not in ("play", "pause", "stop"):
        return None
    title = data.get("Title") or ""
    artist = data.get("Artist") or ""
    if not title:
        file_ = data.get("file") or ""
        title = data.get("Name") or (file_.rsplit("/", 1)[-1] if file_ else "")
    if not title:
        return None
    return {
        "playing": state == "play",
        "stopped": state == "stop",
        "title": title,
        "artist": artist,
        "album": data.get("Album") or "",
        "source": "MPD",
        "elapsed": _safe_float(data.get("elapsed")),
        "duration": _safe_float(data.get("duration")),
        "fmt": _format_badges(data),
    }


def _format_badges(data):
    """Short badges for the Now Playing strip, e.g. ["FLAC", "16bit", "44.1k"].

    MPD's status already carries all of this -- `audio` as "44100:16:2" and the
    file extension for the codec -- we simply never read it. Returns [] rather
    than guessing when the fields are missing or unparseable (DSD reports a bit
    depth of "dsd", and lossy formats report no meaningful depth at all)."""
    badges = []
    path = data.get("file") or ""
    ext = path.rsplit(".", 1)[-1].upper() if "." in path else ""
    if ext and len(ext) <= 4 and ext.isalnum():
        badges.append(ext)
    audio = data.get("audio") or ""
    parts = audio.split(":")
    if len(parts) >= 2:
        if parts[1].isdigit():
            badges.append(f"{parts[1]}bit")
        if parts[0].isdigit():
            rate = int(parts[0]) / 1000
            badges.append(f"{rate:g}k")
    return badges


def _bt_now_playing():
    try:
        import dbus
        bus = dbus.SystemBus()
        mgr = dbus.Interface(bus.get_object("org.bluez", "/"),
                              "org.freedesktop.DBus.ObjectManager")
        for _path, ifaces in mgr.GetManagedObjects(timeout=1.0).items():
            mp = ifaces.get("org.bluez.MediaPlayer1")
            if not mp:
                continue
            track = mp.get("Track", {}) or {}
            title = str(track.get("Title", "")) if track else ""
            artist = str(track.get("Artist", "")) if track else ""
            if not title:
                continue
            status = str(mp.get("Status", "")).lower()
            return {
                "playing": status == "playing",
                "stopped": False,
                "title": title,
                "artist": artist,
                "album": str(track.get("Album", "")) if track else "",
                "source": "Bluetooth",
                "elapsed": None,
                "duration": None,
                "fmt": [],
            }
        return None
    except Exception:
        return None


def bt_connected():
    """Whether any Bluetooth audio device is currently connected.

    Separate from _bt_now_playing(): that one needs AVRCP metadata, which some
    phones never provide, so it returns None during perfectly good playback. The
    Device1 Connected property is present regardless of AVRCP support."""
    try:
        import dbus
        bus = dbus.SystemBus()
        mgr = dbus.Interface(bus.get_object("org.bluez", "/"),
                             "org.freedesktop.DBus.ObjectManager")
        for _path, ifaces in mgr.GetManagedObjects(timeout=1.0).items():
            device = ifaces.get("org.bluez.Device1")
            if device and bool(device.get("Connected", False)):
                return True
        return False
    except Exception:
        return False


def get_now_playing():
    """Always returns a dict; never raises. elapsed/duration are None for BT
    (AVRCP position isn't reliably available -- see [[project-bt-avrcp]]).

    MPD only wins when it is actually playing. It used to win whenever it had a
    current song at all, including `pause` and `stop` -- and since restore_paused
    leaves MPD paused with a track on every boot ([[usb-queue-persistence]]),
    Bluetooth playback was reported as "MPD" on the panel. A paused MPD is still
    preferred over nothing, hence the second fallback."""
    mpd = get_mpd_now_playing()
    if mpd and mpd.get("playing"):
        return mpd
    bt = _bt_now_playing()
    if bt and bt.get("playing"):
        return bt
    return mpd or bt or {
        "playing": False, "stopped": False, "title": "", "artist": "",
        "album": "", "source": None, "elapsed": None, "duration": None, "fmt": [],
    }


def mpd_volume_get():
    try:
        return int(_mpd_status().get("volume", 0))
    except (ValueError, TypeError):
        return 0


def mpd_volume_set(pct):
    mpc("volume", str(max(0, min(100, int(pct)))))


def mpd_next():
    mpc("next")


def mpd_prev():
    mpc("prev")


def mpd_toggle_play_pause():
    mpc("pause") if _mpd_status().get("state") == "play" else mpc("play")


def mpd_playlists():
    """Saved MPD playlist names, case-insensitively sorted. [] means none saved;
    None means MPD is unreachable, so the Music screen can say so instead of
    offering a Shuffle All button that would silently do nothing."""
    lines = _mpd_lines("listplaylists")
    if lines is None:
        return None
    names = [line.split(": ", 1)[1] for line in lines if line.startswith("playlist: ")]
    return sorted(names, key=str.lower)


def mpd_queue_state():
    """(queue_length, state). Lets the Music screen offer "resume what myMPD
    already queued" instead of only ever replacing the queue."""
    data = _mpd_status()
    try:
        length = int(data.get("playlistlength", 0))
    except (ValueError, TypeError):
        length = 0
    return length, data.get("state", "")


def mpd_resume():
    """Play the existing queue untouched -- no clear, no add."""
    mpc("play")


def mpd_play_playlist(name):
    """Replace the queue with one saved playlist and start it. Name is passed as
    an argv element, never through a shell, so quotes/spaces in playlist names
    are safe."""
    mpc("clear")
    mpc("load", name)
    mpc("play")


def _library_roots():
    """Top-level entries of the music directory, as add-able URIs."""
    lines = _mpd_lines("lsinfo") or []
    return [line.split(": ", 1)[1] for line in lines
            if line.startswith("directory: ") or line.startswith("file: ")]


def mpd_shuffle_all():
    """The one-press "just play something": whole library, shuffled. This is what
    makes the display usable on a cold boot with an empty queue.

    Which URI means "everything" has varied across MPD versions, so rather than
    trusting one spelling this checks whether the queue actually grew and falls
    back to adding each top-level entry. Silently adding nothing and then calling
    play would look identical to broken hardware from the front panel."""
    mpc("clear")
    for root in ("/", ""):
        mpc("add", root, timeout=30)
        if mpd_queue_state()[0]:
            break
    else:
        for entry in _library_roots():
            mpc("add", entry, timeout=30)
    mpc("shuffle")
    mpc("play")


def mpd_queue_tracks(limit=200):
    """(title, artist, seconds) for the current play queue, for the Queue screen.

    Capped: a shuffled 550-track library is a realistic queue here, and parsing
    all of it on the encoder thread to render four visible rows is waste."""
    lines = _mpd_lines("playlistinfo")
    if lines is None:
        return None
    tracks, current = [], {}
    for line in lines:
        if ": " not in line:
            continue
        key, value = line.split(": ", 1)
        if key == "file":
            if current:
                tracks.append(current)
                if len(tracks) >= limit:
                    return [_queue_entry(t) for t in tracks]
            current = {"file": value}
        else:
            current.setdefault(key, value)
    if current:
        tracks.append(current)
    return [_queue_entry(t) for t in tracks[:limit]]


def _queue_entry(track):
    title = track.get("Title") or track.get("Name") or ""
    if not title:
        title = (track.get("file") or "").rsplit("/", 1)[-1]
    return (title, track.get("Artist") or "", _safe_float(track.get("Time")))


def mpd_play_position(index):
    """Play queue position `index` (0-based, as the Queue screen numbers it)."""
    mpc("play", str(int(index) + 1))


def mpd_current_position():
    """0-based index of the current queue song, or None. Lets the Queue screen
    open with the cursor on what's playing instead of at the top."""
    try:
        return int(_mpd_status().get("song"))
    except (ValueError, TypeError):
        return None


def bt_control_exists():
    """Whether the "BT Volume" softvol control exists in ALSA right now.

    Needed because bt_volume_get() cannot report this: _run() swallows the amixer
    failure and the parse loop falls through to a confident-looking 50. The
    control is created lazily by ALSA the first time squarepi_bt_vol is opened
    (install.sh:1026), so on a fresh boot with no BT playback it is absent and the
    overlay's BT row must render inert rather than showing a fake level.

    NOTE: once created it persists for the rest of the boot, so this means "BT has
    played since boot", NOT "a phone is connected right now" -- use bt_connected()
    for that. Confirming the exact lifetime on hardware is an open item."""
    out = _run(["amixer", "-c", CARD, "controls"])
    return BT_VOL_CONTROL.lower() in out.lower()


def bt_volume_get():
    out = _run(["amixer", "-c", CARD, "cget", "name=" + BT_VOL_CONTROL])
    for line in out.splitlines():
        line = line.strip()
        if line.startswith(": values="):
            try:
                val = int(line.split("=", 1)[1].split(",")[0])
                return round(val * 100 / 99)
            except (ValueError, IndexError):
                pass
    return 50


def bt_volume_set(pct):
    """Set BT volume. Returns True only if the write actually landed.

    It used to send stderr to /dev/null and return nothing, which made a rejected
    write indistinguishable from a successful one -- the display would then show a
    level it had never set.

    Rejection is real: `BT Volume` is a softvol control created and owned by
    bluealsa-aplay, and while that process holds the element lock (amixer shows
    `l` in the access flags) other writers get EPERM. Measured on hardware as
    transient -- the lock appeared in one read and was gone moments later, and a
    root write then succeeded -- so one short retry is worth more than a silently
    lost detent. Non-root writers get EPERM regardless; the display service runs
    as root, so this matters mainly for hand-testing as the `pi` user."""
    pct = max(0, min(100, int(pct)))
    val = round(pct * 99 / 100)
    for attempt in (0, 1):
        result = subprocess.run(
            ["amixer", "-c", CARD, "cset", "name=" + BT_VOL_CONTROL, str(val)],
            capture_output=True, text=True)
        if result.returncode == 0:
            return True
        if attempt == 0:
            time.sleep(0.05)
    return False


# --------------------------------------------------------------------------
# Merged volume: one control, two paths.
#
# The target is picked by the user and sticks until power cycle, defaulting to
# MPD on boot. There is deliberately no source auto-detection: BT playback can't
# be detected reliably (AVRCP is absent on some phones, and BT Volume is a lazily
# created control), so routing by guess would send the knob to the wrong path.
#
# This is a display-layer merge only. Both paths stay exactly as they are -- no
# master softvol, no dmix changes, no new ALSA controls
# ([[feedback-audio-path-frozen]]).
TARGET_MPD = "MPD"
TARGET_BT = "BT"
# Third row of the same overlay: rotate skips tracks instead of moving a level.
# Same mechanism as the other two rows -- rotation acts on whatever is focused --
# so there is no new gesture to learn, which is why this beat a double-press (which
# would have made play/pause wait to disambiguate) and a Transport screen (four
# actions deep for something you want instantly).
TARGET_TRACK = "TRACK"
VOLUME_TARGETS = (TARGET_MPD, TARGET_BT)

# One detent moves this many percent. Separate per path because the two mixers
# have different ranges and resolutions, so equal percentages do not mean equal
# loudness change -- the numbers to make a detent *feel* the same on both are an
# open hardware item.
VOLUME_STEP = {TARGET_MPD: 4, TARGET_BT: 4}

_target = TARGET_MPD
# The volume row to fall back to when the overlay closes on the TRACK row. TRACK is
# deliberately NOT sticky: the volume target persisting until power cycle is the
# user's design and it works, but if TRACK persisted the same way then the default
# action of the knob on Home would silently become "skip tracks" -- you would reach
# for volume and lose your place in the queue instead.
_last_volume_target = TARGET_MPD


def volume_target():
    return _target


def set_volume_target(target):
    global _target, _last_volume_target
    if target in (TARGET_MPD, TARGET_BT, TARGET_TRACK):
        _target = target
        if target in VOLUME_TARGETS:
            _last_volume_target = target
    return _target


def release_track_target():
    """Called when the overlay hides. Restores the last volume row if the cursor was
    parked on TRACK, so rotating on Home always means volume again."""
    global _target
    if _target == TARGET_TRACK:
        _target = _last_volume_target
    return _target


def toggle_volume_target(bt_available=True, track_available=True):
    """Press cycles rows in the overlay: MPD -> BT -> TRACK -> MPD. Skips a row that
    would silently do nothing rather than parking the cursor on it -- BT before it
    has ever played, or TRACK with no queue to skip through.

    Note this does NOT record the fallback row: reaching TRACK means pressing past
    BT, and merely passing through a row must not make it the one the knob returns
    to. Only an actual rotation counts as using a row."""
    global _target
    order = [TARGET_MPD]
    if bt_available:
        order.append(TARGET_BT)
    if track_available:
        order.append(TARGET_TRACK)
    try:
        index = order.index(_target)
    except ValueError:
        # The focused row just became unavailable underneath us (BT vanished, or the
        # queue emptied). Start over rather than raise.
        index = -1
    _target = order[(index + 1) % len(order)]
    return _target


def volume_levels():
    """(mpd_pct, bt_pct, bt_available) for the overlay -- both rows always shown."""
    available = bt_control_exists()
    return mpd_volume_get(), (bt_volume_get() if available else 0), available


def track_position():
    """(index, total) 1-based for the TRACK row, or (None, 0) when there is nothing
    to skip through. Skipping is MPD-only: `next` sent to MPD while a phone is
    playing over Bluetooth does nothing visible, so the row has to be able to say
    it isn't usable rather than accept a rotation and swallow it."""
    total, _state = mpd_queue_state()
    if not total:
        return None, 0
    index = mpd_current_position()
    return (None if index is None else index + 1), total


def skip_tracks(detents):
    """Skip `detents` tracks (negative = previous). Returns the number of skips
    actually issued -- which is clamped to the queue length, so it can be smaller
    than `detents` -- or None if there was no queue to skip through.

    Coalesced by the caller like volume: a brisk spin is 20+ detents and each skip
    is a subprocess plus an MPD command, so applying them one per callback would
    both lag the knob and fire twenty skips."""
    if not detents:
        return None
    total, _state = mpd_queue_state()
    if not total:
        return None
    step = mpd_next if detents > 0 else mpd_prev
    issued = min(abs(detents), total)
    for _ in range(issued):
        step()
    # Signed, and the real count: a caller that logs or displays this must not be
    # told 40 skips happened on a 12-track queue.
    return issued if detents > 0 else -issued


def volume_nudge(detents):
    """Apply a rotation to the focused overlay row. Returns the new percentage for a
    volume row, the number of skips for TRACK, or None if nothing could be done --
    callers treat it as "did anything happen", not as a level.

    Callers coalesce detents before calling: each of these is a subprocess and the
    encoder can produce 20+ detents a second, so applying them one at a time from
    the callback thread makes the knob feel like treacle."""
    global _last_volume_target
    if not detents:
        return None
    if _target == TARGET_TRACK:
        return skip_tracks(detents)
    # Adjusting a volume row is what marks it as the one in use, and so the one the
    # knob falls back to when the TRACK row closes.
    _last_volume_target = _target
    step = VOLUME_STEP.get(_target, 4) * detents
    if _target == TARGET_BT:
        if not bt_control_exists():
            return None
        level = max(0, min(100, bt_volume_get() + step))
        # None, not the level: reporting a level we failed to set is how the panel
        # ends up lying about the state of the hardware.
        return level if bt_volume_set(level) else None
    level = max(0, min(100, mpd_volume_get() + step))
    mpd_volume_set(level)
    return level
