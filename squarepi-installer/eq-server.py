#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 sijah
"""
SquarePi DSP Control Server
Full DSP web interface: Gain/Balance, 15-band EQ, Mixer matrix, System faults.
Port 8081. Pure Python stdlib — no pip dependencies.
"""

import json
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

EQ_SERVER_VER = "1.5.2"

CARD = "LouderRaspberry"
BT_VOL_CONTROL = "BT Volume"
BT_VOL_FILE = "/var/lib/squarepi/bt_volume"

# ── EQ bands ──────────────────────────────────────────────────────────────────
# (display label, amixer control name)
BANDS = [
    ("20 Hz",  "00020 Hz"), ("32 Hz",  "00032 Hz"), ("50 Hz",  "00050 Hz"),
    ("80 Hz",  "00080 Hz"), ("125 Hz", "00125 Hz"), ("200 Hz", "00200 Hz"),
    ("315 Hz", "00315 Hz"), ("500 Hz", "00500 Hz"), ("800 Hz", "00800 Hz"),
    ("1.25k",  "01250 Hz"), ("2k",     "02000 Hz"), ("3.15k",  "03150 Hz"),
    ("5k",     "05000 Hz"), ("8k",     "08000 Hz"), ("16k",    "16000 Hz"),
]

# ALSA range -15 to 15; 0 = flat (0 dB), 1 unit = 1 dB
BAND_MIN = -15
BAND_MAX = 15

PRESETS = {
    "flat":       [ 0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0],
    "bass_boost": [ 7,  6,  5,  4,  3,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0],
    "vocal":      [-3, -3, -2, -1,  0,  2,  3,  3,  2,  1,  0, -1, -2, -2, -2],
    "night":      [-5, -5, -4, -2,  0,  0,  0, -1, -1, -1, -1, -2, -3, -4, -4],
    "treble":     [ 0,  0,  0,  0,  0,  0,  0,  0,  0,  2,  3,  4,  5,  6,  6],
    "rock":       [ 5,  4,  3,  2,  1, -1, -2, -2, -1,  1,  2,  3,  4,  5,  5],
    "pop":        [ 2,  2,  1,  0, -1, -1,  0,  1,  2,  3,  3,  2,  2,  1,  1],
    "jazz":       [ 3,  3,  2,  1,  0,  1,  2,  2,  1,  0, -1, -1, -2, -2, -3],
    "classical":  [ 0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  1,  2,  3,  4,  4],
    "club":       [ 8,  7,  6,  4,  2, -1, -2, -2, -1,  1,  2,  3,  4,  5,  6],
    "hiphop":     [ 7,  7,  6,  5,  3,  1,  0,  0,  1,  2,  2,  2,  3,  3,  2],
    "acoustic":   [-2, -2,  0,  1,  2,  2,  1,  0,  1,  2,  3,  3,  2,  1,  0],
    "late_night": [ 6,  5,  3,  1,  0, -1, -1, -1,  0,  0,  1,  2,  3,  4,  5],
}

# ── Fault controls ─────────────────────────────────────────────────────────────
# (response key, amixer control name, is_warning)
FAULT_CONTROLS = [
    ("oc_l",  "Fault Left Channel OC",            False),
    ("oc_r",  "Fault Right Channel OC",           False),
    ("dc_l",  "Fault Left Channel DC",            False),
    ("dc_r",  "Fault Right Channel DC",           False),
    ("uvlo",  "Fault PVDD Undervoltage",          False),
    ("ovlo",  "Fault PVDD Overvoltage",           False),
    ("clk",   "Fault Clock",                      False),
    ("otp",   "Fault OTP CRC Error",              False),
    ("ots",   "Fault Over Temperature Shutdown",  False),
    ("t112",  "Warning Over Temperature 112C",    True),
    ("t122",  "Warning Over Temperature 122C",    True),
    ("t134",  "Warning Over Temperature 134C",    True),
    ("t146",  "Warning Over Temperature 146C",    True),
]

# Mixer matrix control names
MATRIX_CONTROLS = {
    "l2l": "Mixer L2L Gain",
    "r2l": "Mixer R2L Gain",
    "l2r": "Mixer L2R Gain",
    "r2r": "Mixer R2R Gain",
}

# Channel gain ALSA range: 0-110 where 110 = 0 dB, 0 = -110 dB
CHANNEL_MAX = 110

# Custom presets — persisted to disk
CUSTOM_PRESETS_FILE = "/etc/squarepi-custom-presets.json"

def load_custom_presets():
    try:
        with open(CUSTOM_PRESETS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def save_custom_presets(data):
    try:
        with open(CUSTOM_PRESETS_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass

CUSTOM_PRESETS = load_custom_presets()


# ── amixer helpers ─────────────────────────────────────────────────────────────

def _run(args):
    try:
        return subprocess.check_output(
            args, stderr=subprocess.DEVNULL
        ).decode()
    except Exception:
        return ""


def amixer_get(control):
    """Read ALSA integer for a control. Handles both 'Mono: VALUE [%]' and 'Playback VALUE [%]' formats."""
    out = _run(["amixer", "-c", CARD, "sget", control])
    for line in out.splitlines():
        stripped = line.strip()
        # EQ bands: "Mono: 15 [100%]" or "Mono: -7 [27%]"
        if stripped.startswith("Mono:") and "[" in stripped:
            parts = stripped.split()
            try:
                return int(parts[1])
            except (ValueError, IndexError):
                pass
        # Channel/gain controls: "Playback 110 [100%]"
        if "Playback" in stripped and "[" in stripped:
            parts = stripped.split()
            for i, p in enumerate(parts):
                if p == "Playback" and i + 1 < len(parts):
                    try:
                        return int(parts[i + 1])
                    except ValueError:
                        pass
    return 0


def amixer_set(control, value):
    """Write ALSA integer for a control."""
    subprocess.run(
        ["amixer", "-c", CARD, "sset", control, "--", str(value)],
        stderr=subprocess.DEVNULL
    )


def amixer_get_int(control):
    """Read raw integer ALSA value (works for any integer control)."""
    out = _run(["amixer", "-c", CARD, "sget", control])
    for line in out.splitlines():
        if "Playback" in line:
            parts = line.split()
            for i, p in enumerate(parts):
                if p == "Playback" and i + 1 < len(parts):
                    try:
                        return int(parts[i + 1])
                    except ValueError:
                        pass
    return 0


def amixer_get_enum(control):
    """Read current enum string value."""
    out = _run(["amixer", "-c", CARD, "sget", control])
    for line in out.splitlines():
        if "Item0:" in line:
            # Item0: 'Stereo'
            s = line.split("Item0:")[-1].strip().strip("'\"")
            return s
    return ""


def amixer_set_enum(control, value):
    """Set an enum control by string value."""
    subprocess.run(
        ["amixer", "-c", CARD, "sset", control, value],
        stderr=subprocess.DEVNULL
    )


def power_off_or_reboot(action):
    """Mute the amp, then reboot or shut the Pi down.

    eq-server runs as root, so systemctl needs no sudo. The amp is muted first
    (Analog Gain to 0) so the speakers don't thump when the TAS5805M loses its
    I2S clock as the system halts. The actual halt is deferred ~1s on a
    background thread so the HTTP response reaches the browser before systemd
    tears the server down.
    """
    amixer_set("Analog Gain", 0)
    cmd = "reboot" if action == "restart" else "poweroff"

    def _halt():
        time.sleep(1)
        subprocess.run(["systemctl", cmd], stderr=subprocess.DEVNULL)

    threading.Thread(target=_halt, daemon=True).start()


def get_faults():
    """Read all fault/warning booleans. Returns dict key→int (0 or 1)."""
    result = {}
    for key, ctrl, _ in FAULT_CONTROLS:
        raw = amixer_get_int(ctrl)
        result[key] = raw
    return result


def get_balance():
    """
    Read balance from Channel L/R Gain.
    Returns int in [-20, 20]. Positive = right louder, negative = left louder.
    ALSA range: 0-110 where 110 = 0 dB.
    """
    l_raw = amixer_get_int("Channel Left Gain")
    r_raw = amixer_get_int("Channel Right Gain")
    return max(-20, min(20, r_raw - l_raw))


def set_balance(balance):
    """
    Set Channel L/R Gain from balance value [-20, 20].
    Positive = right louder (cut left), negative = left louder (cut right).
    """
    balance = max(-20, min(20, balance))
    l_raw = CHANNEL_MAX - max(0, balance)
    r_raw = CHANNEL_MAX - max(0, -balance)
    amixer_set("Channel Left Gain", l_raw)
    amixer_set("Channel Right Gain", r_raw)


def _bt_vol_load_saved():
    """Read persisted BT volume from file. Returns 50 if file missing or invalid."""
    try:
        with open(BT_VOL_FILE) as f:
            return max(0, min(100, int(f.read().strip())))
    except Exception:
        return 50


def _bt_vol_save(pct):
    try:
        os.makedirs(os.path.dirname(BT_VOL_FILE), exist_ok=True)
        with open(BT_VOL_FILE, "w") as f:
            f.write(str(pct))
    except Exception:
        pass


def get_bt_volume():
    """Read BT Volume softvol as 0-100 percentage. Falls back to saved file value."""
    out = _run(["amixer", "-c", CARD, "cget", "name=" + BT_VOL_CONTROL])
    for line in out.splitlines():
        line = line.strip()
        if line.startswith(": values="):
            try:
                val = int(line.split("=", 1)[1].split(",")[0])
                return round(val * 100 / 99)
            except (ValueError, IndexError):
                pass
    return _bt_vol_load_saved()


def set_bt_volume(pct):
    """Set BT Volume softvol (0-100 percent) and persist to file."""
    pct = max(0, min(100, int(pct)))
    val = round(pct * 99 / 100)
    subprocess.run(
        ["amixer", "-c", CARD, "cset", "name=" + BT_VOL_CONTROL, str(val)],
        stderr=subprocess.DEVNULL
    )
    _bt_vol_save(pct)


def _bt_vol_restore_thread():
    """Continuously monitor the softvol control. Each time audio starts (control
    appears after being absent), apply the saved value. Runs for the lifetime of
    the process so every BT reconnect gets the correct volume."""
    was_present = False
    while True:
        time.sleep(1)
        out = _run(["amixer", "-c", CARD, "cget", "name=" + BT_VOL_CONTROL])
        is_present = ": values=" in out
        if is_present and not was_present:
            target = _bt_vol_load_saved()
            val = round(target * 99 / 100)
            subprocess.run(
                ["amixer", "-c", CARD, "cset", "name=" + BT_VOL_CONTROL, str(val)],
                stderr=subprocess.DEVNULL
            )
        was_present = is_present


def _mpd_now_playing():
    """Query MPD over its socket for the current song. Stdlib only, fully fail-safe."""
    try:
        import socket
        s = socket.create_connection(("127.0.0.1", 6600), timeout=0.4)
        s.settimeout(0.4)
        f = s.makefile("rw", encoding="utf-8", newline="\n")
        f.readline()  # greeting line: "OK MPD <version>"
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
        if data.get("state") != "play":
            return None
        title = data.get("Title") or ""
        artist = data.get("Artist") or ""
        if not title:
            f2 = data.get("file") or ""
            title = data.get("Name") or (f2.rsplit("/", 1)[-1] if f2 else "")
        if not title:
            return None
        return {"playing": True, "title": title, "artist": artist, "source": "MPD"}
    except Exception:
        return None


def _bt_now_playing():
    """Best-effort AVRCP track metadata from BlueZ over D-Bus. None on any failure."""
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
            return {"playing": True, "title": title, "artist": artist, "source": "Bluetooth"}
        return None
    except Exception:
        return None


def get_now_playing():
    """Track for the now-playing strip. Tries MPD, then Bluetooth AVRCP.
    Always returns a dict; never raises."""
    return _mpd_now_playing() or _bt_now_playing() or {"playing": False}


def get_state():
    """Return all DSP state in one call."""
    bands = {label: amixer_get(ctrl) for label, ctrl in BANDS}
    return {
        "bands":       bands,
        "gain":        amixer_get_int("Analog Gain"),
        "balance":     get_balance(),
        "bt_volume":   get_bt_volume(),
        "eq_enabled":  amixer_get_enum("Equalizer") != "Off",
        "mixer_mode":  amixer_get_enum("Mixer Mode") or "Stereo",
        "matrix": {
            "l2l": amixer_get_int(MATRIX_CONTROLS["l2l"]),
            "r2l": amixer_get_int(MATRIX_CONTROLS["r2l"]),
            "l2r": amixer_get_int(MATRIX_CONTROLS["l2r"]),
            "r2r": amixer_get_int(MATRIX_CONTROLS["r2r"]),
        },
        "faults": get_faults(),
    }


# ── HTML page ──────────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SquarePi DSP</title>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 36 28'><rect width='36' height='28' rx='6' fill='%23080a0e'/><polyline points='4,21 4,9 12,9 12,21 20,21 20,9 28,9 28,21 33,21' fill='none' stroke='%23f59e0b' stroke-width='2.6' stroke-linejoin='miter' stroke-linecap='square'/></svg>">
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --acc:#f59e0b; --acc-dim:#78350f;
    --bg:#080a0e; --sur:#0d1117; --pan:#0f1520;
    --bdr:#1e293b; --txt:#cbd5e1; --mut:#475569; --dim:#1e293b;
    --grn:#22c55e; --red:#ef4444; --blu:#60a5fa;
    --eq-panel:#05090f; --eq-track:#1a2840; --label:#7d90a8; --tick:#4a6892;
  }
  html,body { height:100%; overflow:hidden; }
  body { background:var(--bg); color:var(--txt); font-family:'Courier New','Lucida Console',monospace; }

  /* App shell */
  .app { display:grid; grid-template-rows:50px 1fr; height:100vh; overflow:hidden; }

  /* Top bar */
  .topbar { display:flex; align-items:center; background:var(--sur); border-bottom:1px solid var(--bdr); padding:0 14px; gap:10px; }
  .topbar-brand { display:flex; align-items:center; gap:10px; width:184px; flex-shrink:0; }
  .brand-name { font-size:0.88rem; font-weight:700; letter-spacing:0.2em; color:var(--acc); }
  .brand-sub { font-size:0.58rem; color:var(--mut); letter-spacing:0.12em; margin-top:1px; }
  .topbar-center { flex:1; }
  .topbar-actions { display:flex; align-items:center; gap:6px; }
  .tb-btn { background:var(--pan); color:var(--txt); border:1px solid var(--bdr); border-radius:3px; padding:5px 11px; font-size:0.57rem; font-family:inherit; letter-spacing:0.08em; cursor:pointer; }
  .tb-btn:hover { border-color:var(--acc); color:var(--acc); }
  .preset-sel-top { background:var(--pan); color:var(--txt); border:1px solid var(--bdr); border-radius:3px; padding:5px 10px; font-size:0.57rem; font-family:inherit; letter-spacing:0.06em; cursor:pointer; outline:none; }
  .tb-icon { font-size:0.9rem; color:var(--mut); cursor:pointer; padding:4px 5px; }
  .tb-icon:hover { color:var(--txt); }
  .pwr-wrap { position:relative; }
  .pwr-btn { color:var(--red); border-color:var(--red); }
  .pwr-btn:hover { background:var(--red); color:#fff; }
  .pwr-menu { display:none; position:absolute; right:0; top:calc(100% + 4px); flex-direction:column; gap:3px; min-width:132px; padding:4px; background:var(--pan); border:1px solid var(--bdr); border-radius:4px; box-shadow:0 6px 18px rgba(0,0,0,0.5); z-index:50; }
  .pwr-menu.open { display:flex; }
  .pwr-menu button { background:transparent; color:var(--txt); border:none; text-align:left; padding:7px 10px; font-family:inherit; font-size:0.6rem; letter-spacing:0.06em; cursor:pointer; border-radius:3px; }
  .pwr-menu button:hover { background:var(--sur); }
  .pwr-menu button.danger:hover { background:var(--red); color:#fff; }

  /* 3-column shell */
  .columns { display:grid; grid-template-columns:160px 1fr; overflow:hidden; min-height:0; }

  /* Left sidebar */
  .sidebar { background:var(--sur); border-right:1px solid var(--bdr); display:flex; flex-direction:column; overflow-y:auto; }
  .nav-group { padding:8px 0; flex:1; }
  .nav-item { display:flex; align-items:center; gap:9px; padding:10px 16px; font-size:0.66rem; letter-spacing:0.08em; color:var(--mut); cursor:pointer; border-left:2px solid transparent; text-transform:uppercase; user-select:none; }
  .nav-item:hover { background:var(--pan); color:var(--txt); }
  .nav-item.active { color:var(--acc); border-left-color:var(--acc); background:var(--pan); }
  .nav-icon { font-size:0.85rem; width:14px; text-align:center; flex-shrink:0; }
  .nav-divider { height:1px; background:var(--bdr); margin:4px 0; }
  .device-info { padding:12px 16px; border-top:1px solid var(--bdr); }
  .d-lbl { font-size:0.58rem; color:var(--mut); letter-spacing:0.1em; text-transform:uppercase; margin-top:6px; }
  .d-lbl:first-child { margin-top:0; }
  .d-val { font-size:0.7rem; color:var(--txt); margin-top:1px; }
  .s-dot { display:inline-block; width:5px; height:5px; border-radius:50%; background:var(--grn); box-shadow:0 0 4px var(--grn); margin-right:5px; vertical-align:middle; }

  /* Main content */
  .content { overflow-y:auto; padding:9px 11px; background:var(--bg); }

  /* Cards */
  .card { background:var(--bg); border:1px solid var(--bdr); border-left:2px solid var(--acc-dim); border-radius:5px; margin-bottom:8px; overflow:hidden; }
  .card-hdr { display:flex; align-items:center; padding:9px 14px; background:var(--sur); gap:8px; flex-wrap:wrap; }
  .card-title { font-size:0.62rem; font-weight:700; color:var(--acc); letter-spacing:0.14em; flex-shrink:0; }
  .card-body { padding:12px 14px; background:var(--bg); }
  .eq-hdr-ctrls { display:flex; align-items:center; gap:6px; flex-wrap:wrap; flex:1; justify-content:flex-end; }
  .preset-lbl { font-size:0.6rem; color:var(--label); letter-spacing:0.08em; }
  .preset-sel { background:var(--pan); color:var(--txt); border:1px solid var(--bdr); border-radius:2px; padding:4px 8px; font-size:0.55rem; font-family:inherit; letter-spacing:0.04em; outline:none; cursor:pointer; }
  .action-btn { background:var(--pan); color:var(--mut); border:1px solid var(--bdr); border-radius:2px; padding:4px 9px; font-size:0.55rem; font-family:inherit; letter-spacing:0.07em; cursor:pointer; }
  .action-btn:hover { border-color:var(--acc-dim); color:var(--txt); }
  .action-btn.danger { color:var(--red); border-color:#3a1010; }
  .action-btn.danger:hover { border-color:var(--red); }
  .action-btn.bypass.active { background:var(--acc); color:#000; border-color:var(--acc); }

  .ctrl-row { display:flex; align-items:center; gap:10px; margin-bottom:9px; }
  .ctrl-lbl { font-size:0.6rem; color:var(--mut); width:90px; flex-shrink:0; letter-spacing:0.07em; text-transform:uppercase; }
  .ctrl-row input[type=range] { flex:1; accent-color:var(--acc); cursor:pointer; }
  .ctrl-val { font-size:0.7rem; color:var(--acc); font-weight:700; width:70px; text-align:right; flex-shrink:0; letter-spacing:0.03em; }

  .toggle-row { display:flex; align-items:center; gap:8px; margin-bottom:11px; }
  .toggle-lbl { font-size:0.6rem; color:var(--mut); letter-spacing:0.1em; text-transform:uppercase; }
  .tog { padding:4px 16px; border-radius:2px; font-size:0.6rem; font-weight:700; letter-spacing:0.1em; border:1px solid var(--bdr); background:var(--sur); color:var(--mut); cursor:pointer; font-family:inherit; }
  .tog.active { background:var(--acc); border-color:var(--acc); color:#000; }

  .presets { display:flex; gap:5px; flex-wrap:wrap; margin-bottom:10px; }
  .pre-btn { background:var(--sur); color:var(--mut); border:1px solid var(--bdr); border-radius:2px; padding:5px 10px; font-size:0.58rem; font-family:inherit; letter-spacing:0.07em; text-transform:uppercase; cursor:pointer; }
  .pre-btn:hover { border-color:var(--acc-dim); color:var(--txt); }
  .pre-btn.active { background:var(--acc); border-color:var(--acc); color:#000; font-weight:700; }

  /* ── EQ RACK ── */
  .eq-curve-wrap { background:var(--eq-panel); border:1px solid #0f1828; border-radius:3px 3px 0 0; border-bottom:none; position:relative; height:180px; overflow:hidden; }
  #eq-curve { width:100%; display:block; cursor:ns-resize; touch-action:none; }
  .curve-lbl { position:absolute; top:4px; right:7px; font-size:0.56rem; color:var(--tick); letter-spacing:0.1em; pointer-events:none; }

  .eq-rack { background:var(--eq-panel); border:1px solid #0f1828; border-radius:0 0 3px 3px; padding:4px 2px 6px 2px; display:flex; align-items:stretch; }
  .db-scale { display:flex; flex-direction:column; justify-content:space-between; padding:23px 6px 16px 0; min-width:30px; }
  .db-scale.right { padding:23px 0 16px 6px; }
  .db-tick { font-size:0.56rem; color:var(--tick); text-align:right; line-height:1; }
  .db-tick.z { color:#6090b0; font-weight:700; }
  .db-scale.right .db-tick { text-align:left; }

  .eq-grid { display:grid; grid-template-columns:repeat(15,1fr); gap:1px; flex:1; }
  .band { display:flex; flex-direction:column; align-items:center; }

  .band-db { background:var(--eq-panel); border:1px solid #0d1320; border-radius:2px; font-size:0.6rem; font-weight:700; min-height:17px; width:100%; text-align:center; padding:2px 0; letter-spacing:-0.02em; white-space:nowrap; overflow:hidden; color:var(--label); margin-bottom:2px; font-family:'Courier New',monospace; }
  .band-db.pos { color:var(--acc); }
  .band-db.neg { color:var(--blu); }

  .fader-wrap { position:relative; width:100%; height:160px; overflow:hidden; }
  .fader-track { position:absolute; width:5px; height:140px; background:var(--eq-track); border-radius:3px; top:10px; left:50%; transform:translateX(-50%); z-index:0; }
  .fader-zero { position:absolute; width:14px; height:2px; background:#3a6080; top:80px; left:50%; transform:translateX(-50%); z-index:3; border-radius:1px; }

  input.vsl {
    -webkit-appearance:none; appearance:none;
    position:absolute; left:50%; top:50%;
    margin-left:-70px; margin-top:-14px;
    transform:rotate(-90deg);
    width:140px; height:28px;
    cursor:pointer; background:transparent; outline:none; z-index:2;
  }
  input.vsl::-webkit-slider-runnable-track { height:4px; background:transparent; border-radius:2px; }
  input.vsl::-webkit-slider-thumb {
    -webkit-appearance:none; width:18px; height:18px;
    background:radial-gradient(circle at 35% 35%,#e8eef5,#a0b8cc);
    border-radius:50%; border:2px solid #506070; cursor:grab; margin-top:-7px;
    box-shadow:0 1px 4px rgba(0,0,0,0.5);
  }
  input.vsl:active::-webkit-slider-thumb { background:radial-gradient(circle at 35% 35%,#ffd060,#f59e0b); border-color:#f59e0b; cursor:grabbing; }
  input.vsl::-moz-range-track { height:4px; background:transparent; border-radius:2px; }
  input.vsl::-moz-range-thumb { width:18px; height:18px; background:#c0ccd8; border-radius:50%; border:2px solid #506070; }

  .band-freq { font-size:0.56rem; color:var(--label); text-align:center; padding-top:4px; letter-spacing:-0.01em; }

  .custom-save-row { display:flex; align-items:center; gap:8px; margin:9px 0 8px; flex-wrap:wrap; }
  .custom-save-row input { background:var(--sur); color:var(--txt); border:1px solid var(--bdr); border-radius:2px; padding:6px 11px; font-size:0.65rem; font-family:inherit; width:160px; outline:none; letter-spacing:0.04em; }
  .custom-save-row input:focus { border-color:var(--acc); }
  .custom-save-row input::placeholder { color:var(--mut); }
  .pre-btn.custom { position:relative; padding-right:24px; }
  .pre-btn.custom .del { position:absolute; right:5px; top:50%; transform:translateY(-50%); font-size:0.6rem; color:var(--mut); cursor:pointer; }
  .pre-btn.custom .del:hover { color:var(--red); }

  .mode-btns { display:flex; gap:5px; flex-wrap:wrap; margin-bottom:10px; }
  .mode-btn { background:var(--sur); color:var(--mut); border:1px solid var(--bdr); border-radius:2px; padding:6px 14px; font-size:0.6rem; font-family:inherit; letter-spacing:0.07em; text-transform:uppercase; cursor:pointer; }
  .mode-btn:hover { border-color:var(--acc-dim); }
  .mode-btn.active { background:#0f2040; border-color:#3b82f6; color:#93c5fd; }
  .matrix { display:none; margin-top:8px; }
  .matrix.open { display:block; }
  .matrix-grid { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
  .mat-lbl { font-size:0.58rem; color:var(--mut); letter-spacing:0.07em; text-transform:uppercase; margin-bottom:3px; }

  /* System stat cards */
  .sys-stat-grid { display:grid; grid-template-columns:1fr 1fr; gap:6px; margin-bottom:12px; }
  .sys-stat-card { background:var(--sur); border:1px solid var(--bdr); border-radius:4px; padding:8px 10px; }
  .sys-stat-lbl { font-size:0.6rem; color:var(--label); letter-spacing:0.1em; text-transform:uppercase; }
  .sys-stat-val { font-size:0.88rem; font-weight:700; font-family:'Courier New',monospace; margin-top:2px; color:var(--txt); }
  .sys-stat-val.ok { color:var(--grn); }
  .sys-stat-val.warn { color:var(--acc); }
  .sys-stat-val.err { color:var(--red); }
  .sys-led { width:8px; height:8px; border-radius:50%; background:var(--grn); box-shadow:0 0 6px var(--grn); flex-shrink:0; transition:all 0.3s; }
  .sys-led.warn { background:var(--acc); box-shadow:0 0 6px var(--acc); }
  .sys-led.err { background:var(--red); box-shadow:0 0 6px var(--red); animation:blink 1s infinite; }
  @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.2} }
  .faults-section-title { font-size:0.6rem; color:var(--label); letter-spacing:0.12em; text-transform:uppercase; margin:10px 0 8px; }
  .faults-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:5px; margin-bottom:13px; }
  .fault-item { display:flex; flex-direction:column; align-items:center; gap:5px; background:var(--sur); border:1px solid var(--bdr); border-radius:4px; padding:8px 4px; }
  .fdot { width:8px; height:8px; border-radius:50%; background:var(--grn); box-shadow:0 0 5px var(--grn); flex-shrink:0; transition:all 0.3s; }
  .fdot.warn { background:var(--acc); box-shadow:0 0 5px var(--acc); }
  .fdot.err { background:var(--red); box-shadow:0 0 5px var(--red); animation:blink 1s infinite; }
  .fault-name { font-size:0.58rem; color:var(--label); text-align:center; line-height:1.3; }

  .save-row { display:flex; align-items:center; gap:12px; }
  .save-btn { background:var(--sur); color:var(--txt); border:1px solid var(--bdr); border-radius:3px; padding:7px 16px; font-size:0.65rem; font-family:inherit; letter-spacing:0.07em; cursor:pointer; }
  .save-btn:hover { border-color:var(--acc); color:var(--acc); }
  .status { font-size:0.63rem; color:var(--grn); min-height:16px; letter-spacing:0.04em; }
  hr { border:none; border-top:1px solid var(--bdr); margin:10px 0; }

  .delay-row { display:flex; align-items:center; gap:6px; }
  .delay-val { font-size:0.6rem; color:var(--acc); min-width:46px; text-align:right; }
  .delay-row input[type=range] { flex:1; accent-color:var(--acc); }
  .locked-notice { font-size:0.53rem; color:#2a3a4a; background:var(--pan); border:1px solid var(--bdr); border-radius:3px; padding:8px; text-align:center; letter-spacing:0.04em; line-height:1.6; }


  /* Theme selector (top bar) */
  .theme-sel { background:var(--pan); color:var(--txt); border:1px solid var(--bdr); border-radius:3px; padding:5px 9px; font-size:0.57rem; font-family:inherit; letter-spacing:0.05em; cursor:pointer; outline:none; }
  .brand-logo polyline { stroke:var(--acc); }

  /* Now-playing strip */
  .nowplay { display:flex; align-items:center; gap:9px; background:var(--sur); border:1px solid var(--bdr); border-left:3px solid var(--grn); border-radius:6px; padding:7px 11px; margin-bottom:8px; }
  .nowplay.idle { border-left-color:var(--bdr); opacity:0.65; }
  .np-art { width:30px; height:30px; border-radius:4px; background:var(--pan); display:flex; align-items:center; justify-content:center; color:var(--acc); font-size:15px; flex-shrink:0; }
  .np-meta { flex:1; min-width:0; }
  .np-src { font-size:0.55rem; color:var(--label); letter-spacing:0.12em; text-transform:uppercase; }
  .np-track { font-size:0.72rem; color:var(--txt); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; margin-top:1px; }
  .np-vu { display:flex; align-items:flex-end; gap:2px; height:18px; flex-shrink:0; }
  .np-vu i { width:3px; background:var(--grn); border-radius:1px; height:5px; transition:height 0.25s; }

  /* A/B compare + unsaved chip */
  .ab-wrap { display:flex; align-items:center; gap:4px; }
  .ab-lbl { font-size:0.55rem; color:var(--label); letter-spacing:0.08em; }
  .ab-btn { font-size:0.6rem; font-weight:700; font-family:inherit; border:1px solid var(--bdr); background:var(--sur); color:var(--mut); border-radius:2px; padding:3px 10px; cursor:pointer; letter-spacing:0.05em; }
  .ab-btn.active { background:var(--acc); border-color:var(--acc); color:#000; }
  .unsaved-chip { display:none; align-items:center; gap:4px; font-size:0.55rem; color:var(--acc); letter-spacing:0.08em; }
  .unsaved-chip.show { display:inline-flex; }
  .unsaved-chip .udot { width:6px; height:6px; border-radius:50%; background:var(--acc); }

  /* Preset sparkline */
  .pre-btn { display:inline-flex; align-items:center; gap:6px; }
  .pre-spark { width:28px; height:12px; flex-shrink:0; }
  .pre-spark path { fill:none; stroke:var(--acc); stroke-width:1.4; }
  .pre-btn.active .pre-spark path { stroke:#000; }

  /* Responsive */
  @media (max-width:680px) { .columns { grid-template-columns:1fr; } .sidebar { display:none; } }
</style>
</head>
<body>
<div class="app">

<!-- TOP BAR -->
<div class="topbar">
  <div class="topbar-brand">
    <svg class="brand-logo" width="28" height="18" viewBox="0 0 36 22" fill="none">
      <polyline points="0,18 0,4 9,4 9,18 18,18 18,4 27,4 27,18 36,18 36,11"
                stroke-width="2.2" fill="none"
                stroke-linecap="square" stroke-linejoin="miter"/>
    </svg>
    <div>
      <div class="brand-name">SQUARE PI</div>
      <div class="brand-sub">DSP Control Interface &nbsp;&#x25AA;&nbsp; v__EQ_VER__</div>
    </div>
  </div>
  <div class="topbar-center"></div>
  <div class="topbar-actions">
    <select class="theme-sel" id="theme-sel" title="Colour theme" onchange="applyTheme(this.value, true)">
      <option value="amber">Amber</option>
      <option value="blue">Studio</option>
      <option value="green">Phosphor</option>
      <option value="mcintosh">McIntosh</option>
      <option value="graphite">Graphite</option>
      <option value="daylight">Daylight</option>
    </select>
    <button class="tb-btn" onclick="saveSettings()">SAVE</button>
    <select class="preset-sel-top" onchange="if(this.value){applyPreset(this.value);this.value=''}">
      <option value="">PRESETS &#9660;</option>
      <option value="flat">Flat</option>
      <option value="bass_boost">Bass Boost</option>
      <option value="treble">Treble</option>
      <option value="vocal">Vocal</option>
      <option value="night">Night</option>
      <option value="late_night">Late Night</option>
      <option value="rock">Rock</option>
      <option value="pop">Pop</option>
      <option value="jazz">Jazz</option>
      <option value="classical">Classical</option>
      <option value="club">Club</option>
      <option value="hiphop">Hip-Hop</option>
      <option value="acoustic">Acoustic</option>
    </select>
    <span class="tb-icon" title="Save to chip" onclick="saveSettings()">&#9211;</span>
    <div class="pwr-wrap">
      <button class="tb-btn pwr-btn" title="Power" onclick="togglePowerMenu(event)">&#9211;&nbsp;POWER</button>
      <div class="pwr-menu" id="pwr-menu">
        <button onclick="powerAction('restart')">&#8635;&nbsp;&nbsp;Restart</button>
        <button class="danger" onclick="powerAction('shutdown')">&#9211;&nbsp;&nbsp;Shut down</button>
      </div>
    </div>
  </div>
</div>

<!-- 3-COLUMN LAYOUT -->
<div class="columns">

<!-- LEFT SIDEBAR -->
<aside class="sidebar">
  <div class="nav-group">
    <div class="nav-item" data-s="gain" onclick="navTo('gain')">
      <span class="nav-icon">&#9638;</span>GAIN &amp; BAL
    </div>
    <div class="nav-item active" data-s="eq" onclick="navTo('eq')">
      <span class="nav-icon">&#8801;</span>EQUALIZER
    </div>
    <div class="nav-item" data-s="mixer" onclick="navTo('mixer')">
      <span class="nav-icon">&#9868;</span>MIXER
    </div>
    <div class="nav-divider"></div>
    <div class="nav-item" data-s="system" onclick="navTo('system')">
      <span class="nav-icon">&#9633;</span>SYSTEM
    </div>
  </div>
  <div class="device-info">
    <div class="d-lbl">Device</div>
    <div class="d-val" style="color:var(--acc)">TAS5805M</div>
    <div class="d-lbl">Mode</div>
    <div class="d-val">15-Band EQ</div>
    <div class="d-lbl">Status</div>
    <div class="d-val"><span class="s-dot"></span>Connected</div>
  </div>
</aside>

<!-- MAIN CONTENT -->
<div class="content" id="content">

<!-- NOW PLAYING -->
<div class="nowplay idle" id="nowplay">
  <div class="np-art">&#9835;</div>
  <div class="np-meta">
    <div class="np-src" id="np-src">Not playing</div>
    <div class="np-track" id="np-track">&#8212;</div>
  </div>
  <div class="np-vu" id="np-vu" style="display:none"><i></i><i></i><i></i><i></i><i></i></div>
</div>

<!-- GAIN & BALANCE -->
<div class="card" id="card-gain">
  <div class="card-hdr">
    <span class="card-title">&#x25BA; GAIN &amp; BALANCE</span>
  </div>
  <div class="card-body">
    <div class="ctrl-row">
      <span class="ctrl-lbl">Analog Gain</span>
      <input type="range" id="sl-gain" min="0" max="31" value="31" oninput="onGain(this.value)">
      <span class="ctrl-val" id="v-gain">0.0 dB</span>
    </div>
    <div class="ctrl-row">
      <span class="ctrl-lbl">Balance</span>
      <input type="range" id="sl-bal" min="-20" max="20" value="0" oninput="onBalance(this.value)">
      <span class="ctrl-val" id="v-bal">Centre</span>
    </div>
    <div class="ctrl-row">
      <span class="ctrl-lbl">BT Volume</span>
      <input type="range" id="sl-btvol" min="0" max="100" value="25" oninput="onBtVolume(this.value)">
      <span class="ctrl-val" id="v-btvol">25%</span>
    </div>
  </div>
</div>

<!-- EQ -->
<div class="card" id="card-eq">
  <div class="card-hdr">
    <span class="card-title">&#x25BA; EQUALIZER &mdash; 15 BAND</span>
    <span class="unsaved-chip" id="unsaved-chip"><span class="udot"></span>UNSAVED</span>
    <div class="eq-hdr-ctrls">
      <span class="ab-lbl">A/B</span>
      <div class="ab-wrap">
        <button class="ab-btn active" id="ab-a" onclick="abSwitch('A')">A</button>
        <button class="ab-btn" id="ab-b" onclick="abSwitch('B')">B</button>
        <button class="action-btn" onclick="abCopy()" title="Copy active slot to the other">COPY</button>
      </div>
      <button class="tog active" id="eq-on"  onclick="setEqBypass(true)">ON</button>
      <button class="tog"        id="eq-off" onclick="setEqBypass(false)">OFF</button>
      <span class="preset-lbl">PRESET</span>
      <select class="preset-sel" onchange="if(this.value){applyPreset(this.value);this.value=''}">
        <option value="">&#x2014; Select &#x2014;</option>
        <option value="flat">Flat</option>
        <option value="bass_boost">Bass Boost</option>
        <option value="treble">Treble</option>
        <option value="vocal">Vocal</option>
        <option value="night">Night</option>
        <option value="late_night">Late Night</option>
        <option value="rock">Rock</option>
        <option value="pop">Pop</option>
        <option value="jazz">Jazz</option>
        <option value="classical">Classical</option>
        <option value="club">Club</option>
        <option value="hiphop">Hip-Hop</option>
        <option value="acoustic">Acoustic</option>
      </select>
      <button class="action-btn" onclick="saveCustomPreset()">SAVE EQ</button>
      <button class="action-btn danger" onclick="applyPreset('flat')">RESET</button>
      <button class="action-btn bypass" id="bypass-btn" onclick="toggleBypass()">BYPASS</button>
    </div>
  </div>
  <div class="card-body">
    <div class="presets" id="preset-row">
      <button class="pre-btn" onclick="applyPreset('flat')">Flat</button>
      <button class="pre-btn" onclick="applyPreset('bass_boost')">Bass</button>
      <button class="pre-btn" onclick="applyPreset('treble')">Treble</button>
      <button class="pre-btn" onclick="applyPreset('vocal')">Vocal</button>
      <button class="pre-btn" onclick="applyPreset('night')">Night</button>
      <button class="pre-btn" onclick="applyPreset('late_night')">Late Night</button>
      <button class="pre-btn" onclick="applyPreset('rock')">Rock</button>
      <button class="pre-btn" onclick="applyPreset('pop')">Pop</button>
      <button class="pre-btn" onclick="applyPreset('jazz')">Jazz</button>
      <button class="pre-btn" onclick="applyPreset('classical')">Classical</button>
      <button class="pre-btn" onclick="applyPreset('club')">Club</button>
      <button class="pre-btn" onclick="applyPreset('hiphop')">Hip-Hop</button>
      <button class="pre-btn" onclick="applyPreset('acoustic')">Acoustic</button>
      <!-- custom presets injected here by JS -->
    </div>
    <div class="custom-save-row">
      <input type="text" id="custom-name" maxlength="24" placeholder="Custom preset name…">
      <button class="save-btn" onclick="saveCustomPreset()">&#9632; Save EQ</button>
    </div>
    <div class="eq-wrap">
      <div class="eq-curve-wrap">
        <canvas id="eq-curve"></canvas>
        <span class="curve-lbl">FREQ RESPONSE</span>
      </div>
      <div class="eq-rack">
        <div class="db-scale">
          <div class="db-tick">+15</div>
          <div class="db-tick">+10</div>
          <div class="db-tick">+5</div>
          <div class="db-tick z">0</div>
          <div class="db-tick">-5</div>
          <div class="db-tick">-10</div>
          <div class="db-tick">-15</div>
        </div>
        <div class="eq-grid" id="eq-grid"></div>
        <div class="db-scale right">
          <div class="db-tick">+15</div>
          <div class="db-tick">+10</div>
          <div class="db-tick">+5</div>
          <div class="db-tick z">0</div>
          <div class="db-tick">-5</div>
          <div class="db-tick">-10</div>
          <div class="db-tick">-15</div>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- MIXER -->
<div class="card" id="card-mixer">
  <div class="card-hdr">
    <span class="card-title">&#x25BA; MIXER</span>
  </div>
  <div class="card-body">
    <div style="font-size:0.48rem;color:var(--mut);letter-spacing:0.12em;text-transform:uppercase;margin-bottom:5px">&#x25BA; Output Mode</div>
    <div class="mode-btns">
      <button class="mode-btn active" id="mb-Stereo" onclick="setMode('Stereo')">Stereo</button>
      <button class="mode-btn"        id="mb-Mono"   onclick="setMode('Mono')">Mono</button>
      <button class="mode-btn"        id="mb-Left"   onclick="setMode('Left')">Left Only</button>
      <button class="mode-btn"        id="mb-Right"  onclick="setMode('Right')">Right Only</button>
      <button class="mode-btn"        id="mb-Custom" onclick="setMode('Custom')">Custom</button>
    </div>
    <div class="matrix" id="matrix">
      <div class="matrix-grid">
        <div>
          <div class="mat-lbl">L in &#x2192; L out</div>
          <div class="ctrl-row">
            <input type="range" min="-110" max="0" value="0" id="sl-l2l" oninput="onMatrix('l2l',this.value)">
            <span class="ctrl-val" id="v-l2l">0 dB</span>
          </div>
        </div>
        <div>
          <div class="mat-lbl">R in &#x2192; L out</div>
          <div class="ctrl-row">
            <input type="range" min="-110" max="0" value="-110" id="sl-r2l" oninput="onMatrix('r2l',this.value)">
            <span class="ctrl-val" id="v-r2l">&#x2212;110 dB</span>
          </div>
        </div>
        <div>
          <div class="mat-lbl">L in &#x2192; R out</div>
          <div class="ctrl-row">
            <input type="range" min="-110" max="0" value="-110" id="sl-l2r" oninput="onMatrix('l2r',this.value)">
            <span class="ctrl-val" id="v-l2r">&#x2212;110 dB</span>
          </div>
        </div>
        <div>
          <div class="mat-lbl">R in &#x2192; R out</div>
          <div class="ctrl-row">
            <input type="range" min="-110" max="0" value="0" id="sl-r2r" oninput="onMatrix('r2r',this.value)">
            <span class="ctrl-val" id="v-r2r">0 dB</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- SYSTEM -->
<div class="card" id="card-system">
  <div class="card-hdr">
    <span class="card-title">&#x25BA; SYSTEM</span>
    <div class="eq-hdr-ctrls">
      <div class="sys-led" id="sys-health-led"></div>
      <span id="sys-health-txt" style="font-size:0.58rem;color:var(--mut)">Checking&hellip;</span>
    </div>
  </div>
  <div class="card-body">
    <div class="sys-stat-grid">
      <div class="sys-stat-card">
        <div class="sys-stat-lbl">Temperature</div>
        <div class="sys-stat-val" id="sys-temp">&#x2014;</div>
      </div>
      <div class="sys-stat-card">
        <div class="sys-stat-lbl">PVDD</div>
        <div class="sys-stat-val ok" id="sys-pvdd">OK</div>
      </div>
      <div class="sys-stat-card">
        <div class="sys-stat-lbl">Faults</div>
        <div class="sys-stat-val ok" id="sys-fault-count">0</div>
      </div>
      <div class="sys-stat-card">
        <div class="sys-stat-lbl">Status</div>
        <div class="sys-stat-val ok" id="sys-status-txt">Healthy</div>
      </div>
    </div>
    <div class="faults-section-title">Fault Monitor</div>
    <div class="faults-grid" id="faults-grid"></div>
    <div class="save-row">
      <button class="save-btn" onclick="saveSettings()">&#9632; Save to chip (survive reboot)</button>
      <span class="status" id="status"></span>
    </div>
  </div>
</div>

</div><!-- .content -->

</div><!-- .columns -->

</div><!-- .app -->

<script>
const BANDS = __BAND_LABELS__;
const FAULT_DEFS = __FAULT_DEFS__;

// ── Helpers ────────────────────────────────────────────────────────────────────
function dbStr(v) {
  const n = parseFloat(v).toFixed(1);
  return (parseFloat(n) >= 0 ? '+' : '') + n;
}
function freqShort(lbl) {
  if (lbl.includes('k')) return lbl;
  const hz = parseInt(lbl);
  if (hz >= 10000) return (hz/1000).toFixed(0)+'k';
  if (hz >= 1000)  return (hz/1000).toFixed(1)+'k';
  return hz+'';
}
const DIRTY_ENDPOINTS = ['/api/band','/api/gain','/api/balance','/api/preset','/api/custom-preset/apply','/api/mixer','/api/eq-bypass'];
function post(url, data) {
  if (DIRTY_ENDPOINTS.indexOf(url) !== -1) markDirty();
  else if (url === '/api/store') clearDirty();
  return fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data ?? {})});
}
function showStatus(msg) {
  const el = document.getElementById('status');
  if (!el) return;
  el.textContent = msg;
  if (msg) setTimeout(() => { el.textContent = ''; }, 3000);
}

// ── Power (Restart / Shut down) ───────────────────────────────────────────────────
function togglePowerMenu(e){
  if (e) e.stopPropagation();
  document.getElementById('pwr-menu').classList.toggle('open');
}
function powerAction(action){
  const label = action === 'restart' ? 'Restart' : 'Shut down';
  document.getElementById('pwr-menu').classList.remove('open');
  if (!confirm(label + ' SquarePi now?')) return;
  showStatus(label + '…');
  post('/api/power', {action}).then(() => {
    showStatus(action === 'restart'
      ? 'Restarting — this page reconnects in ~30 s'
      : 'Shutting down — wait for activity to stop, then unplug');
  }).catch(() => showStatus(label + ' failed'));
}
// Close the power menu on any outside click
document.addEventListener('click', (ev) => {
  const menu = document.getElementById('pwr-menu');
  if (menu && menu.classList.contains('open') && !ev.target.closest('.pwr-wrap'))
    menu.classList.remove('open');
});

// ── Unsaved indicator ───────────────────────────────────────────────────────────
let suppressDirty = true;   // true during initial load so loadState() doesn't flag dirty
function markDirty(){ if(suppressDirty) return; const c=document.getElementById('unsaved-chip'); if(c) c.classList.add('show'); }
function clearDirty(){ const c=document.getElementById('unsaved-chip'); if(c) c.classList.remove('show'); }

// ── Theme engine ────────────────────────────────────────────────────────────────
const THEMES = {
  amber:{ '--acc':'#f59e0b','--acc-dim':'#78350f','--bg':'#080a0e','--sur':'#0d1117','--pan':'#0f1520','--bdr':'#1e293b','--txt':'#cbd5e1','--mut':'#475569','--dim':'#1e293b','--grn':'#22c55e','--red':'#ef4444','--blu':'#60a5fa','--eq-panel':'#05090f','--eq-track':'#1a2840','--label':'#7d90a8','--tick':'#4a6892' },
  blue:{ '--acc':'#38bdf8','--acc-dim':'#0c4a6e','--bg':'#060910','--sur':'#0d1420','--pan':'#101a2e','--bdr':'#1c2740','--txt':'#cbd5e1','--mut':'#4a5a72','--dim':'#1c2740','--grn':'#22c55e','--red':'#ef4444','--blu':'#818cf8','--eq-panel':'#060c16','--eq-track':'#19283f','--label':'#7d90a8','--tick':'#42587a' },
  green:{ '--acc':'#4ade80','--acc-dim':'#14532d','--bg':'#060a06','--sur':'#0c140c','--pan':'#0e1a0e','--bdr':'#1c2c1c','--txt':'#c8e6c8','--mut':'#4a6a4a','--dim':'#1c2c1c','--grn':'#4ade80','--red':'#ef4444','--blu':'#a3e635','--eq-panel':'#060e06','--eq-track':'#1c3320','--label':'#7da880','--tick':'#4a7a4a' },
  mcintosh:{ '--acc':'#2ea3f2','--acc-dim':'#0c3a66','--bg':'#04060a','--sur':'#0a0e16','--pan':'#0d1320','--bdr':'#16203a','--txt':'#d0d8e0','--mut':'#46566e','--dim':'#16203a','--grn':'#00e5b0','--red':'#ef4444','--blu':'#00e5b0','--eq-panel':'#05080f','--eq-track':'#15233c','--label':'#7488a8','--tick':'#3e5478' },
  graphite:{ '--acc':'#e8eaed','--acc-dim':'#52525b','--bg':'#0e0e10','--sur':'#17171a','--pan':'#1c1c20','--bdr':'#2c2c33','--txt':'#d4d4d8','--mut':'#6b6b72','--dim':'#2c2c33','--grn':'#22c55e','--red':'#ef4444','--blu':'#a1a1aa','--eq-panel':'#0f0f12','--eq-track':'#2a2a30','--label':'#8a8a93','--tick':'#5a5a62' },
  daylight:{ '--acc':'#d97706','--acc-dim':'#fde6c5','--bg':'#eef1f5','--sur':'#ffffff','--pan':'#f4f6f9','--bdr':'#d3d9e0','--txt':'#1e293b','--mut':'#7a8aa0','--dim':'#d3d9e0','--grn':'#16a34a','--red':'#dc2626','--blu':'#2563eb','--eq-panel':'#e9edf2','--eq-track':'#cbd5e1','--label':'#5a6678','--tick':'#7a8aa0' }
};
function applyTheme(name, save){
  const t = THEMES[name] || THEMES.amber;
  const root = document.documentElement;
  for (const k in t) root.style.setProperty(k, t[k]);
  if (save) { try { localStorage.setItem('squarepi-theme', name); } catch(e){} }
  const sel = document.getElementById('theme-sel'); if (sel) sel.value = name;
  if (typeof drawCurve === 'function') drawCurve();
  for (let i=0;i<15;i++){ const sl=document.getElementById('bs-'+i); if(sl) updateFaderFill(i, sl.value); }
}
function initTheme(){
  let name='amber';
  try { name = localStorage.getItem('squarepi-theme') || 'amber'; } catch(e){}
  if (!THEMES[name]) name='amber';
  applyTheme(name, false);
}
function themeColors(){
  const cs=getComputedStyle(document.documentElement);
  const g=(k,d)=>{ const v=cs.getPropertyValue(k); return (v&&v.trim())||d; };
  return { acc:g('--acc','#f59e0b'), cut:g('--blu','#3b82f6'), track:g('--eq-track','#1a2840'), tick:g('--tick','#4a6892'), panel:g('--eq-panel','#05090f') };
}
function hexToRgba(hex,a){
  hex=(hex||'').replace('#','').trim();
  if(hex.length===3) hex=hex.split('').map(c=>c+c).join('');
  const n=parseInt(hex||'0',16);
  return 'rgba('+((n>>16)&255)+','+((n>>8)&255)+','+(n&255)+','+a+')';
}

// ── Now playing strip ───────────────────────────────────────────────────────────
function pollNowPlaying(){
  fetch('/api/nowplaying').then(r=>r.json()).then(d=>{
    const wrap=document.getElementById('nowplay');
    const src=document.getElementById('np-src');
    const trk=document.getElementById('np-track');
    const vu=document.getElementById('np-vu');
    if(!wrap) return;
    if(d && d.playing){
      wrap.classList.remove('idle');
      src.textContent='Now playing'+(d.source?' · '+d.source:'');
      trk.textContent=(d.artist? d.artist+' — ':'')+(d.title||'');
      if(vu) vu.style.display='flex';
    } else {
      wrap.classList.add('idle');
      src.textContent='Not playing';
      trk.textContent='—';
      if(vu) vu.style.display='none';
    }
  }).catch(()=>{});
}
function animateNpVu(){
  const vu=document.getElementById('np-vu');
  if(vu && vu.style.display!=='none'){ [].forEach.call(vu.children,b=>{ b.style.height=(4+Math.random()*14)+'px'; }); }
}

// ── A/B compare ─────────────────────────────────────────────────────────────────
let abSlots={A:null,B:null}, abActive='A';
function abReadCurrent(){ const v=[]; for(let i=0;i<15;i++){ const sl=document.getElementById('bs-'+i); v.push(sl?parseInt(sl.value):0);} return v; }
function abUpdateUI(){ const a=document.getElementById('ab-a'), b=document.getElementById('ab-b'); if(a)a.classList.toggle('active',abActive==='A'); if(b)b.classList.toggle('active',abActive==='B'); }
function abInit(){ abSlots.A=abReadCurrent(); abActive='A'; abUpdateUI(); }
function abSwitch(slot){
  if(slot===abActive) return;
  abSlots[abActive]=abReadCurrent();
  abActive=slot;
  if(abSlots[slot]){ syncSliders(abSlots[slot]); post('/api/custom-preset/apply',{values:abSlots[slot]}); clearPresets(); }
  else { abSlots[slot]=abReadCurrent(); }
  abUpdateUI();
  showStatus('Comparing slot '+slot);
}
function abCopy(){ const other=abActive==='A'?'B':'A'; abSlots[other]=abReadCurrent(); showStatus('Copied '+abActive+' → '+other); }

// ── Preset sparklines ───────────────────────────────────────────────────────────
function sparkPath(vals){
  const W=28,H=12,mid=H/2,sc=(H/2-1)/15;
  return 'M'+vals.map((v,i)=>(1+i*((W-2)/14)).toFixed(1)+','+(mid-v*sc).toFixed(1)).join(' L');
}
function renderSparklines(){
  document.querySelectorAll('.pre-btn').forEach(btn=>{
    if(btn.classList.contains('custom')) return;
    if(btn.querySelector('.pre-spark')) return;
    const oc=btn.getAttribute('onclick')||'';
    const m=oc.match(/applyPreset\('([^']+)'\)/);
    if(!m) return;
    const vals=PRESET_VALUES[m[1]];
    if(!vals) return;
    const label=btn.textContent.trim();
    btn.innerHTML='<svg class="pre-spark" viewBox="0 0 28 12"><path d="'+sparkPath(vals)+'"/></svg><span>'+label+'</span>';
  });
}

// ── Drag the response curve ─────────────────────────────────────────────────────
// Grab the nearest band point on the graph and pull it vertically. Reuses onBand()
// so POST / preset-clear / unsaved-flag / redraw all happen exactly like a fader move.
function initCurveDrag(){
  const canvas=document.getElementById('eq-curve');
  if(!canvas) return;
  const padL=30, padR=30, padT=8, padB=22, H=180;
  let dragging=false, dragBand=-1;
  function bandValueFrom(e){
    const rect=canvas.getBoundingClientRect();
    const W=rect.width;
    const dH=H-padT-padB, midY=padT+dH/2;
    const x=e.clientX-rect.left;
    const y=(e.clientY-rect.top)*(H/rect.height);
    let i=Math.round((x-padL)/((W-padL-padR)/14));
    i=Math.max(0,Math.min(14,i));
    let v=Math.round(((midY-y)/(dH/2))*15);
    v=Math.max(-15,Math.min(15,v));
    return {i:i, v:v};
  }
  function apply(e){
    const r=bandValueFrom(e);
    const band=dragBand>=0?dragBand:r.i;
    const sl=document.getElementById('bs-'+band);
    if(!sl) return;
    if(parseInt(sl.value)!==r.v){ sl.value=r.v; onBand(band, r.v); }  // onBand posts only on integer change
  }
  canvas.addEventListener('pointerdown', e => {
    dragging=true; dragBand=bandValueFrom(e).i;
    try{ canvas.setPointerCapture(e.pointerId); }catch(_){}
    apply(e); e.preventDefault();
  });
  canvas.addEventListener('pointermove', e => { if(dragging){ apply(e); e.preventDefault(); } });
  function end(){ dragging=false; dragBand=-1; }
  canvas.addEventListener('pointerup', end);
  canvas.addEventListener('pointercancel', end);
}


// ── Fader fill — gradient on the track div ────────────────────────────────────
function updateFaderFill(i, v) {
  const track = document.getElementById('ft-' + i);
  if (!track) return;
  v = parseInt(v);
  const pct = ((15 - v) / 30 * 100).toFixed(1);
  const tc = themeColors();
  const dark = tc.track;
  if (v > 0) {
    track.style.background = `linear-gradient(to bottom,${dark} ${pct}%,${tc.acc} ${pct}%,${tc.acc} 50%,${dark} 50%)`;
  } else if (v < 0) {
    track.style.background = `linear-gradient(to bottom,${dark} 50%,${tc.cut} 50%,${tc.cut} ${pct}%,${dark} ${pct}%)`;
  } else {
    track.style.background = dark;
  }
}

// ── Frequency response curve ───────────────────────────────────────────────────
function drawCurve() {
  const canvas = document.getElementById('eq-curve');
  if (!canvas) return;
  const W = canvas.parentElement.clientWidth || 600;
  const H = 180;
  const padL = 30, padR = 30, padT = 8, padB = 22;
  const dH = H - padT - padB;
  const midY = padT + dH / 2;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = W * dpr; canvas.height = H * dpr;
  canvas.style.height = H + 'px';
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, W, H);
  const tc = themeColors();

  // dB grid lines + labels on both sides
  [-15,-10,-5,0,5,10,15].forEach(db => {
    const y = midY - (db / 15) * (dH / 2);
    ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(W - padR, y);
    ctx.strokeStyle = db === 0 ? hexToRgba(tc.tick,0.55) : hexToRgba(tc.tick,0.18);
    ctx.lineWidth = db === 0 ? 1.5 : 0.5; ctx.stroke();
    const lbl = (db > 0 ? '+' : '') + db;
    ctx.font = '9px monospace';
    ctx.fillStyle = tc.tick;
    ctx.textAlign = 'right'; ctx.fillText(lbl, padL - 4, y + 3);
    ctx.textAlign = 'left';  ctx.fillText(lbl, W - padR + 4, y + 3);
  });

  const vals = [];
  for (let i = 0; i < 15; i++) {
    const sl = document.getElementById('bs-' + i);
    vals.push(sl ? parseInt(sl.value) : 0);
  }
  const pts = vals.map((v, i) => ({
    x: padL + (i / 14) * (W - padL - padR),
    y: midY - (v / 15) * (dH / 2)
  }));

  // Smooth Catmull-Rom bezier path builder
  function smoothPath(p) {
    ctx.moveTo(p[0].x, p[0].y);
    for (let i = 0; i < p.length - 1; i++) {
      const p0 = p[Math.max(0, i-1)];
      const p1 = p[i];
      const p2 = p[i+1];
      const p3 = p[Math.min(p.length-1, i+2)];
      ctx.bezierCurveTo(
        p1.x + (p2.x - p0.x) / 6, p1.y + (p2.y - p0.y) / 6,
        p2.x - (p3.x - p1.x) / 6, p2.y - (p3.y - p1.y) / 6,
        p2.x, p2.y
      );
    }
  }

  // Gradient fill — opaque at extremes, transparent at zero line
  const grad = ctx.createLinearGradient(0, padT, 0, H - padB);
  grad.addColorStop(0,    hexToRgba(tc.acc,0.45));
  grad.addColorStop(0.48, hexToRgba(tc.acc,0.02));
  grad.addColorStop(0.5,  hexToRgba(tc.acc,0));
  grad.addColorStop(0.5,  hexToRgba(tc.cut,0));
  grad.addColorStop(0.52, hexToRgba(tc.cut,0.02));
  grad.addColorStop(1,    hexToRgba(tc.cut,0.45));

  ctx.beginPath();
  smoothPath(pts);
  ctx.lineTo(pts[pts.length-1].x, midY); ctx.lineTo(pts[0].x, midY); ctx.closePath();
  ctx.fillStyle = grad; ctx.fill();

  // Smooth curve line
  ctx.strokeStyle = tc.acc; ctx.lineWidth = 2; ctx.lineJoin = 'round';
  ctx.beginPath(); smoothPath(pts); ctx.stroke();

  // Band dots
  pts.forEach(p => {
    ctx.beginPath(); ctx.arc(p.x, p.y, 3, 0, Math.PI*2);
    ctx.fillStyle = tc.acc; ctx.fill();
    ctx.strokeStyle = tc.panel; ctx.lineWidth = 1; ctx.stroke();
  });

  // Frequency labels on X axis
  ctx.font = '8px monospace'; ctx.fillStyle = '#3a5570'; ctx.textAlign = 'center';
  pts.forEach((p, i) => ctx.fillText(freqShort(BANDS[i]), p.x, H - 5));
}

// ── EQ sliders ─────────────────────────────────────────────────────────────────
function buildEq(bandValues) {
  const grid = document.getElementById('eq-grid');
  grid.innerHTML = '';
  BANDS.forEach((lbl, i) => {
    const v = bandValues ? (bandValues[lbl] ?? 0) : 0;
    const dbCls = v > 0 ? ' pos' : v < 0 ? ' neg' : '';
    const col = document.createElement('div');
    col.className = 'band';
    col.innerHTML = `
      <div class="band-db${dbCls}" id="bd-${i}">${dbStr(v)}</div>
      <div class="fader-wrap">
        <div class="fader-track" id="ft-${i}"></div>
        <div class="fader-zero"></div>
        <input class="vsl" type="range" orient="vertical"
               min="-15" max="15" value="${v}" id="bs-${i}"
               oninput="onBand(${i},this.value)">
      </div>
      <div class="band-freq">${freqShort(lbl)}</div>`;
    grid.appendChild(col);
    updateFaderFill(i, v);
  });
  setTimeout(drawCurve, 60);
}

function onBand(i, v) {
  v = parseInt(v);
  const db = document.getElementById('bd-' + i);
  if (db) { db.textContent = dbStr(v); db.className = 'band-db' + (v > 0 ? ' pos' : v < 0 ? ' neg' : ''); }
  updateFaderFill(i, v);
  drawCurve();
  post('/api/band', {index: i, value: v});
  clearPresets();
}

function loadBands() {
  fetch('/api/bands').then(r => r.json()).then(data => {
    BANDS.forEach((lbl, i) => {
      const v = data[lbl] ?? 0;
      const sl = document.getElementById('bs-' + i);
      const db = document.getElementById('bd-' + i);
      if (sl) { sl.value = v; updateFaderFill(i, v); }
      if (db) { db.textContent = dbStr(v); db.className = 'band-db' + (v > 0 ? ' pos' : v < 0 ? ' neg' : ''); }
    });
    drawCurve();
  });
}

// ── Presets ─────────────────────────────────────────────────────────────────────
const PRESET_VALUES = {
  flat:       [ 0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0],
  bass_boost: [ 7,  6,  5,  4,  3,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0],
  treble:     [ 0,  0,  0,  0,  0,  0,  0,  0,  0,  2,  3,  4,  5,  6,  6],
  vocal:      [-3, -3, -2, -1,  0,  2,  3,  3,  2,  1,  0, -1, -2, -2, -2],
  night:      [-5, -5, -4, -2,  0,  0,  0, -1, -1, -1, -1, -2, -3, -4, -4],
  late_night: [ 6,  5,  3,  1,  0, -1, -1, -1,  0,  0,  1,  2,  3,  4,  5],
  rock:       [ 5,  4,  3,  2,  1, -1, -2, -2, -1,  1,  2,  3,  4,  5,  5],
  pop:        [ 2,  2,  1,  0, -1, -1,  0,  1,  2,  3,  3,  2,  2,  1,  1],
  jazz:       [ 3,  3,  2,  1,  0,  1,  2,  2,  1,  0, -1, -1, -2, -2, -3],
  classical:  [ 0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  1,  2,  3,  4,  4],
  club:       [ 8,  7,  6,  4,  2, -1, -2, -2, -1,  1,  2,  3,  4,  5,  6],
  hiphop:     [ 7,  7,  6,  5,  3,  1,  0,  0,  1,  2,  2,  2,  3,  3,  2],
  acoustic:   [-2, -2,  0,  1,  2,  2,  1,  0,  1,  2,  3,  3,  2,  1,  0],
};

function syncSliders(values) {
  BANDS.forEach((lbl, i) => {
    const v = Array.isArray(values) ? values[i] : (values[lbl] ?? 0);
    const sl = document.getElementById('bs-' + i);
    const db = document.getElementById('bd-' + i);
    if (sl) { sl.value = v; updateFaderFill(i, v); }
    if (db) { db.textContent = dbStr(v); db.className = 'band-db' + (v > 0 ? ' pos' : v < 0 ? ' neg' : ''); }
  });
  drawCurve();
}

function applyPreset(name) {
  clearPresets();
  document.querySelectorAll('.pre-btn').forEach(b => {
    if (b.getAttribute('onclick') && b.getAttribute('onclick').includes(name)) b.classList.add('active');
  });
  if (PRESET_VALUES[name]) syncSliders(PRESET_VALUES[name]);
  post('/api/preset', {preset: name}).then(() => showStatus('Preset applied'))
    .catch(() => showStatus('Error applying preset'));
}

function clearPresets() {
  document.querySelectorAll('.pre-btn').forEach(b => b.classList.remove('active'));
}

// ── Custom presets ──────────────────────────────────────────────────────────────
function renderCustomPresets(customs) {
  document.querySelectorAll('.pre-btn.custom').forEach(b => b.remove());
  const row = document.getElementById('preset-row');
  Object.keys(customs).forEach(name => {
    const btn = document.createElement('button');
    btn.className = 'pre-btn custom';
    btn.innerHTML = name + '<span class="del" onclick="deleteCustomPreset(event,\'' + name + '\')">&#x2715;</span>';
    btn.onclick = () => applyCustomPreset(name, customs[name]);
    row.appendChild(btn);
  });
}
function saveCustomPreset() {
  const name = document.getElementById('custom-name').value.trim();
  if (!name) { showStatus('Enter a name first'); return; }
  const values = [];
  for (let i = 0; i < 15; i++) {
    const sl = document.getElementById('bs-' + i);
    values.push(sl ? parseInt(sl.value) : 0);
  }
  post('/api/custom-preset/save', {name, values}).then(r => r.json()).then(data => {
    renderCustomPresets(data.customs);
    document.getElementById('custom-name').value = '';
    showStatus('Custom preset "' + name + '" saved');
  });
}
function applyCustomPreset(name, values) {
  clearPresets();
  syncSliders(values);
  post('/api/custom-preset/apply', {values}).then(() => showStatus('Preset "' + name + '" applied'))
    .catch(() => showStatus('Error'));
}
function deleteCustomPreset(e, name) {
  e.stopPropagation();
  post('/api/custom-preset/delete', {name}).then(r => r.json()).then(data => {
    renderCustomPresets(data.customs);
    showStatus('Preset "' + name + '" deleted');
  });
}
function loadCustomPresets() {
  fetch('/api/custom-presets').then(r => r.json()).then(data => { renderCustomPresets(data); });
}

// ── EQ bypass ──────────────────────────────────────────────────────────────────
function setEqBypass(on) {
  document.getElementById('eq-on').classList.toggle('active', on);
  document.getElementById('eq-off').classList.toggle('active', !on);
  post('/api/eq-bypass', {enabled: on});
}

// ── Gain & Balance ─────────────────────────────────────────────────────────────
function setGainDisplay(v) {
  const db = ((parseInt(v) - 31) * 0.5).toFixed(1);
  document.getElementById('v-gain').textContent = (db >= 0 ? '+' : '') + db + ' dB';
}
function onGain(v) {
  setGainDisplay(v);
  post('/api/gain', {value: parseInt(v)});
}

function setBalDisplay(v) {
  v = parseInt(v);
  const el = document.getElementById('v-bal');
  if (v === 0) el.textContent = 'Centre';
  else if (v > 0) el.textContent = 'R +' + v + ' dB';
  else el.textContent = 'L +' + Math.abs(v) + ' dB';
}
function onBalance(v) { setBalDisplay(v); post('/api/balance', {value: parseInt(v)}); }

function onBtVolume(v) {
  v = parseInt(v);
  document.getElementById('v-btvol').textContent = v + '%';
  post('/api/bt-volume', {value: v});
}

// ── Mixer mode ─────────────────────────────────────────────────────────────────
function setMode(mode) {
  document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
  const btn = document.getElementById('mb-' + mode);
  if (btn) btn.classList.add('active');
  document.getElementById('matrix').classList.toggle('open', mode === 'Custom');
  if (mode !== 'Custom') post('/api/mixer', {mode});
}
function onMatrix(key, v) {
  v = parseInt(v);
  document.getElementById('v-' + key).textContent = v === 0 ? '0 dB' : v + ' dB';
  post('/api/mixer', {custom: {[key]: v}});
}
function setMatrixDisplay(matrix) {
  ['l2l','r2l','l2r','r2r'].forEach(k => {
    const v = matrix[k] ?? 0;
    const sl = document.getElementById('sl-' + k);
    const vl = document.getElementById('v-' + k);
    if (sl) sl.value = v;
    if (vl) vl.textContent = v === 0 ? '0 dB' : v + ' dB';
  });
}

// ── Faults ─────────────────────────────────────────────────────────────────────
function updateHealthLed(faults) {
  const led = document.getElementById('sys-health-led');
  const txt = document.getElementById('sys-health-txt');
  if (!led || !faults) return;
  const hasErr  = FAULT_DEFS.filter(f => !f.warn).some(f => faults[f.key]);
  const hasWarn = FAULT_DEFS.filter(f =>  f.warn).some(f => faults[f.key]);
  if (hasErr)       { led.className = 'sys-led err';  txt.textContent = 'Fault detected'; }
  else if (hasWarn) { led.className = 'sys-led warn'; txt.textContent = 'Warning'; }
  else              { led.className = 'sys-led';       txt.textContent = 'All systems OK'; }
}
function buildFaults(faults) {
  const grid = document.getElementById('faults-grid');
  grid.innerHTML = '';
  FAULT_DEFS.forEach(f => {
    const v = faults ? (faults[f.key] ?? 0) : 0;
    const cls = v === 0 ? '' : (f.warn ? ' warn' : ' err');
    grid.innerHTML += `<div class="fault-item"><span class="fdot${cls}" id="fd-${f.key}"></span><span class="fault-name">${f.label}</span></div>`;
  });
  const errCount = faults ? FAULT_DEFS.filter(f => !f.warn && faults[f.key]).length : 0;
  const warnCount = faults ? FAULT_DEFS.filter(f => f.warn && faults[f.key]).length : 0;
  const total = errCount + warnCount;
  const fcEl = document.getElementById('sys-fault-count');
  const stEl = document.getElementById('sys-status-txt');
  const pvEl = document.getElementById('sys-pvdd');
  if (fcEl) { fcEl.textContent = total; fcEl.className = 'sys-stat-val ' + (errCount > 0 ? 'err' : warnCount > 0 ? 'warn' : 'ok'); }
  if (stEl) { stEl.textContent = errCount > 0 ? 'Fault' : warnCount > 0 ? 'Warning' : 'Healthy'; stEl.className = 'sys-stat-val ' + (errCount > 0 ? 'err' : warnCount > 0 ? 'warn' : 'ok'); }
  if (pvEl && faults) {
    const pvBad = FAULT_DEFS.some(f => f.key.includes('pvdd') && faults[f.key]);
    pvEl.textContent = pvBad ? 'FAULT' : 'OK';
    pvEl.className = 'sys-stat-val ' + (pvBad ? 'err' : 'ok');
  }
}
function updateFaults(faults) {
  FAULT_DEFS.forEach(f => {
    const dot = document.getElementById('fd-' + f.key);
    if (!dot) return;
    const v = faults[f.key] ?? 0;
    dot.className = 'fdot' + (v === 0 ? '' : (f.warn ? ' warn' : ' err'));
  });
}

// ── Save ───────────────────────────────────────────────────────────────────────
function saveSettings() {
  post('/api/store').then(() => showStatus('Saved — settings will survive reboot'));
}

// ── Load all state ─────────────────────────────────────────────────────────────
function loadState() {
  fetch('/api/state').then(r => r.json()).then(s => {
    buildEq(s.bands);
    const gainSl = document.getElementById('sl-gain');
    const gv = s.gain ?? 31;
    if (gainSl) { gainSl.value = gv; setGainDisplay(gv); }
    const balSl = document.getElementById('sl-bal');
    if (balSl) { balSl.value = s.balance ?? 0; setBalDisplay(balSl.value); }
    const btSl = document.getElementById('sl-btvol');
    const btVol = s.bt_volume ?? 25;
    if (btSl) { btSl.value = btVol; document.getElementById('v-btvol').textContent = btVol + '%'; }
    setEqBypass(s.eq_enabled !== false);
    setMode(s.mixer_mode ?? 'Stereo');
    if (s.matrix) setMatrixDisplay(s.matrix);
    buildFaults(s.faults ?? {});
    updateHealthLed(s.faults ?? {});
    abInit();
    suppressDirty = false;
  }).catch(() => { buildEq(null); buildFaults(null); suppressDirty = false; });
  loadSysInfo();
}

// ── Sysinfo ────────────────────────────────────────────────────────────────────
function loadSysInfo() {
  fetch('/api/sysinfo').then(r => r.json()).then(d => {
    const t = document.getElementById('sys-temp');
    if (t) { t.textContent = d.temp_c !== null ? d.temp_c + ' \xb0C' : 'N/A'; t.className = 'sys-stat-val' + (d.temp_c > 70 ? ' err' : d.temp_c > 55 ? ' warn' : ' ok'); }
  }).catch(() => {});
}

// ── Sidebar nav ────────────────────────────────────────────────────────────────
function navTo(id) {
  const el = document.getElementById('card-' + id);
  if (el) el.scrollIntoView({behavior: 'smooth', block: 'start'});
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const ni = document.querySelector('.nav-item[data-s="' + id + '"]');
  if (ni) ni.classList.add('active');
}

// ── EQ bypass toggle ───────────────────────────────────────────────────────────
function toggleBypass() {
  const btn = document.getElementById('bypass-btn');
  const isActive = btn.classList.toggle('active');
  setEqBypass(!isActive);
}

initTheme();
renderSparklines();
initCurveDrag();
loadCustomPresets();
setInterval(() => {
  fetch('/api/faults').then(r => r.json()).then(f => { updateFaults(f); updateHealthLed(f); }).catch(() => {});
}, 10000);
setInterval(() => {
  fetch('/api/bt-volume').then(r => r.json()).then(d => {
    const sl = document.getElementById('sl-btvol');
    const vl = document.getElementById('v-btvol');
    if (sl && document.activeElement !== sl) { sl.value = d.volume; }
    if (vl && document.activeElement !== sl) { vl.textContent = d.volume + '%'; }
  }).catch(() => {});
}, 3000);
window.addEventListener('resize', drawCurve);
setInterval(loadSysInfo, 8000);
pollNowPlaying();
setInterval(pollNowPlaying, 5000);
setInterval(animateNpVu, 360);
loadState();
</script>
</body>
</html>
"""


# ── HTTP server ────────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass

    def _json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n)) if n else {}

    def do_GET(self):
        p = self.path.split("?")[0]

        if p in ("/", "/index.html"):
            band_labels = json.dumps([b[0] for b in BANDS])
            fault_defs  = json.dumps([
                {"key": k, "label": lbl, "warn": w}
                for k, lbl, w in FAULT_CONTROLS
            ])
            page = (HTML
                    .replace("__BAND_LABELS__", band_labels)
                    .replace("__FAULT_DEFS__",  fault_defs)
                    .replace("__EQ_VER__",       EQ_SERVER_VER))
            self._html(page)

        elif p == "/api/state":
            self._json(get_state())

        elif p == "/api/bands":
            self._json({label: amixer_get(ctrl) for label, ctrl in BANDS})

        elif p == "/api/faults":
            self._json(get_faults())

        elif p == "/api/custom-presets":
            self._json(CUSTOM_PRESETS)

        elif p == "/api/bt-volume":
            self._json({"volume": get_bt_volume()})

        elif p == "/api/nowplaying":
            self._json(get_now_playing())

        elif p == "/api/sysinfo":
            temp_c = None
            try:
                with open("/sys/class/thermal/thermal_zone0/temp") as _f:
                    temp_c = round(int(_f.read().strip()) / 1000, 1)
            except Exception:
                pass
            self._json({"temp_c": temp_c})

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        p    = self.path.split("?")[0]
        data = self._body()

        if p == "/api/band":
            idx = int(data.get("index", 0))
            val = max(BAND_MIN, min(BAND_MAX, int(data.get("value", 0))))
            if 0 <= idx < len(BANDS):
                amixer_set(BANDS[idx][1], val)
            self._json({"ok": True})

        elif p == "/api/preset":
            name = data.get("preset", "flat")
            vals = PRESETS.get(name, PRESETS["flat"])
            for i, (_, ctrl) in enumerate(BANDS):
                amixer_set(ctrl, vals[i])
            band_values = {BANDS[i][0]: vals[i] for i in range(len(BANDS))}
            self._json({"ok": True, "bands": band_values})

        elif p == "/api/gain":
            val = max(0, min(31, int(data.get("value", 31))))
            amixer_set("Analog Gain", val)
            self._json({"ok": True})

        elif p == "/api/balance":
            set_balance(int(data.get("value", 0)))
            self._json({"ok": True})

        elif p == "/api/eq-bypass":
            enabled = data.get("enabled", True)
            amixer_set_enum("Equalizer", "On" if enabled else "Off")
            self._json({"ok": True})

        elif p == "/api/mixer":
            if "mode" in data:
                amixer_set_enum("Mixer Mode", data["mode"])
            elif "custom" in data:
                for key, val in data["custom"].items():
                    ctrl = MATRIX_CONTROLS.get(key)
                    if ctrl:
                        amixer_set(ctrl, max(-110, min(0, int(val))))
            self._json({"ok": True})

        elif p == "/api/bt-volume":
            pct = max(0, min(100, int(data.get("value", 70))))
            set_bt_volume(pct)
            self._json({"ok": True})

        elif p == "/api/store":
            subprocess.run(["alsactl", "store"], stderr=subprocess.DEVNULL)
            self._json({"ok": True})

        elif p == "/api/custom-preset/save":
            name = str(data.get("name", "")).strip()[:24]
            values = [max(BAND_MIN, min(BAND_MAX, int(v))) for v in data.get("values", [0]*15)]
            if name and len(values) == 15:
                CUSTOM_PRESETS[name] = values
                save_custom_presets(CUSTOM_PRESETS)
            self._json({"ok": True, "customs": CUSTOM_PRESETS})

        elif p == "/api/custom-preset/apply":
            values = [max(BAND_MIN, min(BAND_MAX, int(v))) for v in data.get("values", [0]*15)]
            for i, (_, ctrl) in enumerate(BANDS):
                if i < len(values):
                    amixer_set(ctrl, values[i])
            band_values = {BANDS[i][0]: values[i] for i in range(min(len(BANDS), len(values)))}
            self._json({"ok": True, "bands": band_values})

        elif p == "/api/custom-preset/delete":
            name = str(data.get("name", "")).strip()
            CUSTOM_PRESETS.pop(name, None)
            save_custom_presets(CUSTOM_PRESETS)
            self._json({"ok": True, "customs": CUSTOM_PRESETS})

        elif p == "/api/power":
            action = data.get("action")
            if action not in ("restart", "shutdown"):
                self._json({"ok": False, "error": "invalid action"}, status=400)
            else:
                power_off_or_reboot(action)
                self._json({"ok": True, "action": action})

        else:
            self.send_response(404)
            self.end_headers()


if __name__ == "__main__":
    threading.Thread(target=_bt_vol_restore_thread, daemon=True).start()
    server = HTTPServer(("0.0.0.0", 8081), Handler)
    print("[SquarePi DSP] Listening on http://0.0.0.0:8081")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
