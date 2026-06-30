# Changelog

All notable changes to the SquarePi installer are documented here.

---

## [1.4.2] — 2026-06-30

### Added
- **Draggable EQ curve** — grab any point on the frequency-response graph and pull it up or down to set that band directly (mouse and touch). Reuses the existing band handler, so it posts to the chip, clears the active preset, and flags unsaved exactly like the faders.

### Changed
- Relicensed from MIT to **GPL v3** (`GPL-3.0-or-later`); SPDX headers added to the scripts. See [LICENSE](LICENSE).

---

## [1.4.1] — 2026-06-29

### Added
- **Colour themes** — a theme selector in the EQ UI header with six palettes (Amber Cockpit, Studio Blue, Phosphor Green, McIntosh Blue, Graphite, Daylight light mode). Choice persists per browser via localStorage. Themes drive the canvas curve and faders too, not just CSS.
- **Now-playing strip** — shows the current track at the top of the EQ UI. Reads MPD over its socket and falls back to Bluetooth AVRCP metadata via D-Bus. New `GET /api/nowplaying` endpoint; fully fail-safe (never blocks the server, returns "not playing" on any error).
- **A/B compare** — store two EQ curves and flip between them to compare by ear, with a copy-to-other-slot action.
- **Unsaved indicator** — an "UNSAVED" chip appears when the live EQ/gain/mixer state differs from what's been saved to the chip; clears on Save.
- **Preset sparklines** — each preset button shows a mini curve of its shape.

### Fixed
- **EQ UI legibility.** Several labels in the DSP web interface were rendering at 6.7–8px — too small to read (band frequency labels, dB values, device info, system stats, fault names). Bumped to ~9–11px and raised contrast (some labels were using a near-invisible border color as their text color).
- Added a **favicon** — the browser tab now shows the SquarePi square-wave mark instead of the generic globe icon.

---

## [1.4.0] — 2026-06-28

### Changed
- **Bluetooth and the EQ web UI are now installed by default.** They are the two defining features, so `sudo bash install.sh` now sets up both alongside MPD/myMPD. DLNA, Spotify Connect, and AirPlay remain opt-in.
- New opt-out flags: `--without-bt` and `--without-eq`. The old `--with-bt` / `--with-eq` flags still work as no-op aliases for backward compatibility.

### Fixed
- **Critical: `--with-bt` and `--all` aborted on a fresh system.** The Bluetooth section wrote `/var/lib/squarepi/bt_volume` before the directory was created (the `mkdir` lived only in the EQ section). With `set -euo pipefail`, the redirect failure aborted the whole install. Added `mkdir -p /var/lib/squarepi` in the BT section.
- **Bluetooth setup now fails soft.** If the BlueALSA package is unavailable or its install fails, the installer logs a warning and continues without Bluetooth instead of aborting the entire core install. Important now that BT is on the default path.

---

## [1.3.4] — 2026-06-26

### Fixed
- **BT Volume slider now works** — amixer calls corrected from `sget`/`sset` (simple interface, not supported by softvol) to `cget`/`cset`. Moving the slider in the EQ UI now actually changes Bluetooth audio volume.
- **Removed `--volume=mixer` from bluealsa-aplay** — this flag caused a startup crash because the softvol ALSA control only exists while audio is playing, so the service failed to launch cleanly.
- **Blast protection on every reconnect** — the restore thread now runs for the lifetime of the process (not just once at startup). Every time a phone reconnects or audio restarts, the saved volume is applied within 1 second.
- Default BT volume raised from 25% (−30 dB, barely audible) to **50%** (−20 dB, comfortable level).

### Added
- EQ server version displayed in the top-left header of the EQ UI.

---

## [1.3.3] — 2026-06-26

### Added
- **Bluetooth AVRCP volume control** — bluealsa daemon now runs with `--a2dp-volume --initial-volume=25`. Phones that support AVRCP absolute volume (most Android and iOS devices) can control the output level directly from their volume slider.
- **BT Volume softvol layer** — new `squarepi_bt_vol` ALSA softvol PCM sits between bluealsa-aplay and dmix. Provides independent volume control for the Bluetooth audio path without affecting MPD or other sources.
- **BT Volume slider in EQ UI** — Gain & Balance section now includes a BT Volume slider (0–100%). Default 50%. Slider persists across reboots and reconnects via `/var/lib/squarepi/bt_volume`.

### Fixed
- Phones without AVRCP absolute volume (e.g. Xiaomi HyperOS) no longer connect at full amplitude — `--initial-volume=25` caps the starting level regardless of phone model.

---

## [1.3.2] — 2026-06-25

### Fixed
- EQ negative band values silently failed in both Lua preset scripts and `eq-server.py`. The `amixer` CLI parses negative values (e.g. `-1`) as unknown flags without a `--` separator; the fix adds `--` before the value in all amixer calls. Affected presets: Vocal, Night Mode, Late Night, Rock, Pop, Jazz, Acoustic — all had cuts below 0 dB that never applied.

---

## [1.3.1] — 2026-06-25

### Added
- `sticker_file` in mpd.conf — enables myMPD ratings, play counts, and last-played tracking.
- `auto_update "yes"` in mpd.conf — music library refreshes automatically when files change on disk.
- `audio_buffer_size "8192"` in mpd.conf — prevents DLNA stream underruns under load.
- `input_cache "2 MB"` in mpd.conf — buffers HTTP streams against WiFi jitter.

### Fixed
- upmpdcli `protocolinfo` restricted to MP3/FLAC/OGG — stops Windows Media Player from transcoding to raw L16 PCM, which was the root cause of the distorted "kilili" sound when pushing tracks via DLNA.

---

## [1.3.0] — 2026-06-24

### Added
- **48 kHz / 24-bit audio pipeline** — dmix fixed at 48000 Hz / S32_LE; MPD format `48000:24:2` with SoXR resampler at "very high" quality. Reduces Pi clock error to 0.16 ppm and eliminates sample-rate conversion for Bluetooth (A2DP is natively 48 kHz with this config).
- **Spotify Connect** (`--with-spotify`) — installs and configures raspotify with `librespot` backend, routed to the dmix mixer.
- **AirPlay** (`--with-airplay`) — installs and configures shairport-sync, routed to the dmix mixer.
- **Sleep timer** — myMPD Lua scripts for 30 / 60 / 90 min timers and cancel, installed as part of the base install.
- **`--all` flag** — runs all five optional installs (BT, EQ, DLNA, Spotify, AirPlay) in one pass.

---

## [1.2.0]

### Added
- **Bluetooth A2DP sink** with ALSA dmix shared output — MPD and Bluetooth can play simultaneously through a shared software mixer.
- Persistent discoverable/pairable state survives reboots.
- Auto-pairing agent (`squarepi-bt-agent.py`) accepts all Bluetooth pair requests automatically.

---

## [1.1.0]

### Added
- First-boot defaults for hostname, locale, and audio output.
- README overhaul with full installation guide.

---

## [1.0.0]

Initial release — MPD + myMPD + TAS5805M driver on Raspberry Pi OS Lite.
