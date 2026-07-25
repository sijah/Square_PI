#!/usr/bin/env python3
# MPD/BT status polling and transport/volume control for the display service.
# MPD parts mirror eq-server.py's _mpd_now_playing() (eq-server.py:273) but widen
# state to include "pause" and add elapsed/duration -- eq-server.py's version only
# needed play/title/artist for the web now-playing strip. BT volume mirrors
# get_bt_volume()/set_bt_volume() (eq-server.py:229). TODO: once this is proven on
# hardware, factor eq-server.py to import from here instead of duplicating.
import socket
import subprocess

CARD = "LouderRaspberry"
BT_VOL_CONTROL = "BT Volume"
MPD_HOST = ("127.0.0.1", 6600)


def _run(args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=2).stdout
    except Exception:
        return ""


def mpc(*args):
    subprocess.run(["mpc", *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


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


def _safe_float(value):
    try:
        return float(value or 0)
    except ValueError:
        return 0.0


def get_mpd_now_playing():
    data = _mpd_status()
    state = data.get("state")
    if state not in ("play", "pause"):
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
        "title": title,
        "artist": artist,
        "source": "MPD",
        "elapsed": _safe_float(data.get("elapsed")),
        "duration": _safe_float(data.get("duration")),
    }


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
                "title": title,
                "artist": artist,
                "source": "Bluetooth",
                "elapsed": None,
                "duration": None,
            }
        return None
    except Exception:
        return None


def get_now_playing():
    """Always returns a dict; never raises. elapsed/duration are None for BT
    (AVRCP position isn't reliably available -- see [[project-bt-avrcp]])."""
    return get_mpd_now_playing() or _bt_now_playing() or {
        "playing": False, "title": "", "artist": "", "source": None,
        "elapsed": None, "duration": None,
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
    pct = max(0, min(100, int(pct)))
    val = round(pct * 99 / 100)
    subprocess.run(["amixer", "-c", CARD, "cset", "name=" + BT_VOL_CONTROL, str(val)],
                    stderr=subprocess.DEVNULL)
