#!/usr/bin/env python3
# Read-only system/network facts for the Network and System Info screens.
#
# Everything here is best-effort: a missing file or an absent tool yields None and
# the renderer shows "--". Nothing in this module writes, configures, or touches
# the audio path ([[feedback-audio-path-frozen]]).
#
# Values are cached because the display repaints far more often than any of these
# change, and some (df, iwconfig) fork a process.
import os
import re
import socket
import subprocess
import time

CACHE_SECONDS = 5.0
_cache = {}


def _cached(key, ttl, producer):
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and (now - hit[0]) < ttl:
        return hit[1]
    try:
        value = producer()
    except Exception:
        value = None
    _cache[key] = (now, value)
    return value


def _run(args, timeout=2):
    try:
        return subprocess.run(args, capture_output=True, text=True,
                              timeout=timeout).stdout.strip()
    except Exception:
        return ""


# ------------------------------------------------------------------- system

def cpu_temp():
    """Degrees C as a display string. thermal_zone0 is millidegrees."""
    def read():
        with open("/sys/class/thermal/thermal_zone0/temp") as fh:
            return f"{int(fh.read().strip()) / 1000:.0f} °C"
    return _cached("cpu_temp", CACHE_SECONDS, read)


def uptime():
    def read():
        with open("/proc/uptime") as fh:
            seconds = float(fh.read().split()[0])
        days, rem = divmod(int(seconds), 86400)
        hours, rem = divmod(rem, 3600)
        minutes = rem // 60
        if days:
            return f"{days}d {hours}h"
        if hours:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"
    return _cached("uptime", CACHE_SECONDS, read)


def memory_pct():
    def read():
        fields = {}
        with open("/proc/meminfo") as fh:
            for line in fh:
                key, _, rest = line.partition(":")
                fields[key] = float(rest.split()[0])
        total = fields.get("MemTotal", 0)
        available = fields.get("MemAvailable", 0)
        if not total:
            return None
        return round((total - available) / total * 100)
    return _cached("memory_pct", CACHE_SECONDS, read)


def storage_pct():
    def read():
        st = os.statvfs("/")
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        if not total:
            return None
        return round((total - free) / total * 100)
    return _cached("storage_pct", 60.0, read)


def board():
    """Pi model, shortened to fit the panel. /proc/device-tree/model is
    NUL-terminated, hence the rstrip."""
    def read():
        with open("/proc/device-tree/model") as fh:
            model = fh.read().rstrip("\x00").strip()
        model = model.replace("Raspberry Pi", "Pi").replace(" Rev", "")
        return re.sub(r"\s+", " ", model)[:16]
    return _cached("board", 3600.0, read)


def firmware():
    """SquarePi version, read from the installed VERSION file if present. Left as
    None rather than guessed -- a wrong version number on screen is worse than a
    dash, because it is what a user will quote in a bug report."""
    def read():
        for path in ("/opt/squarepi/VERSION", "/etc/squarepi/VERSION"):
            if os.path.exists(path):
                with open(path) as fh:
                    return fh.read().strip()[:12] or None
        return None
    return _cached("firmware", 3600.0, read)


def system_info():
    return {
        "firmware": firmware(),
        "board": board(),
        "cpu_temp": cpu_temp(),
        "uptime": uptime(),
        "memory_pct": memory_pct(),
        "storage_pct": storage_pct(),
    }


# ------------------------------------------------------------------ network

def hostname():
    return _cached("host", 3600.0, lambda: f"{socket.gethostname()}.local")


def ip_address():
    """Primary outbound IP. A UDP socket to a routable address picks the right
    interface without sending a packet -- parsing `ip addr` guesses wrong on a Pi
    with both wlan0 and a bridge up."""
    def read():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("192.0.2.1", 1))  # TEST-NET-1: reserved, never routed
            return s.getsockname()[0]
        finally:
            s.close()
    return _cached("ip", CACHE_SECONDS, read)


def ssid():
    return _cached("ssid", CACHE_SECONDS, lambda: _run(["iwgetid", "-r"]) or None)


def signal_dbm():
    def read():
        # /proc/net/wireless is cheaper than iwconfig and needs no parsing of
        # human-facing text. Column 4 is the signal level in dBm.
        with open("/proc/net/wireless") as fh:
            lines = fh.read().splitlines()
        for line in lines[2:]:
            parts = line.split()
            if len(parts) >= 4:
                return f"{int(float(parts[3]))} dBm"
        return None
    return _cached("signal", CACHE_SECONDS, read)


def network_info():
    ip = ip_address()
    return {
        "connected": bool(ip),
        "ssid": ssid(),
        "ip": ip,
        "signal": signal_dbm(),
        "host": hostname(),
    }


def status_flags(bt_connected=False):
    """The two status-strip icons. Wi-Fi is 'do we have an address', which is what
    a user means by connected."""
    return {"wifi": bool(ip_address()), "bt": bool(bt_connected)}
