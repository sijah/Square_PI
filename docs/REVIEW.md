# SquarePi Code Review

**Living document — reflects current state as of the date below. Re-assess and edit in place at each release: mark resolved items Fixed, add newly-found items, update line numbers. Do not create a new file per release.**

Last full audit: 2026-07-12, branch `dev/v1.6.0` (commit `df3cfcd`)

---

## How to use this doc

- Each item is tagged `[OPEN]`, `[FIXED]`, or `[PARKED]` (parked = known, deliberately deferred, not a regression to chase).
- File:line references are point-in-time — verify against current code before acting, they drift as the codebase changes.
- The **Review Log** at the bottom is the only append-only part: one short dated entry per release summarizing what changed since the prior audit.

---

## 1. Security

### 1.1 Open findings

| # | Finding | Location | Severity | Notes |
|---|---------|----------|----------|-------|
| S1 | **Stored XSS via custom EQ preset name.** Preset name from `/api/custom-presets` is written into `innerHTML` unescaped, plus a second `onclick="...'"+name+"'..."` string-breakout. | `eq-server.py:1291` (`renderCustomPresets`), server-side only length-clamps to 24 chars at `eq-server.py:1630`, never escapes | High | LAN attacker (or anyone with network access to port 8081) plants a preset name like `"><img src=x onerror=...>` via unauthenticated POST; JS runs in the owner's browser next time they open the EQ UI. Fix: `textContent` instead of `innerHTML` on the client, plus server-side allow-list sanitize (`[A-Za-z0-9 _-]`) on save. |
| S2 | **No CSRF protection on any POST endpoint**, including the new **`/api/power`** (reboot/shutdown). | `do_POST`, `eq-server.py:1577-1661`; power handler `eq-server.py:182-198`, endpoint `1651-1657` | High (escalated in v1.6.0) | Previously this only let a malicious site the owner visits silently change EQ/volume settings. Since v1.6.0 added `/api/power`, the same CSRF gap now lets any page the owner's browser visits **reboot or power off the device**. `_body()` parses JSON regardless of `Content-Type`, so a "simple request" (no preflight) still works cross-origin. Fix: require a custom header (e.g. `X-SquarePi: 1`) that only same-origin JS sends; reject POSTs lacking it. |
| S3 | **USB auto-mount missing `nosuid,nodev,noexec`.** | `install.sh:647-668` (`squarepi-usb-mount.sh` mount-option construction) | High | ext4 branch sets no mount options at all; FAT/NTFS branch only sets `uid=/gid=/umask=`. A USB stick with a setuid-root binary, plugged into a device with physical access, is plug-and-pwn local root. Cheap, high-value fix — add the three flags to every `opts=` branch. |
| S4 | **Shell-metacharacter injection via `SQUAREPI_BT_NAME`/`SQUAREPI_BRAND_NAME`** into a root systemd unit. | `install.sh:973-986`, esp. line 981 (`ExecStart=/bin/bash -c '... bluetoothctl system-alias "${BT_DEVICE_NAME}"'`) | Medium | `BT_DEVICE_NAME` is interpolated into a single-quoted `bash -c` string with no character-set validation (unlike `HOSTNAME_REQUESTED`, which is regex-validated at `install.sh:181`). A value containing a single quote breaks out and injects shell that runs as root on every boot. Low likelihood today (operator sets their own env var), but a real hazard if this value is ever sourced from a less-trusted input (web provisioning, fleet config). Fix: apply the same allow-list regex used for `HOSTNAME_REQUESTED`. |
| S5 | **Argument-injection gap: missing `--` before value in `amixer_set_enum`.** | `eq-server.py:174-179` | Medium | Sibling function `amixer_set` (`137-142`) correctly passes `"--", str(value)`; `amixer_set_enum` does not. Reachable via `/api/mixer`'s unvalidated `mode` string (`eq-server.py:1611-1612`) — a value starting with `-` is passed straight through as an amixer flag. Cheap fix: add `"--"` to match the sibling function. |
| S6 | **No subprocess timeout anywhere in eq-server.py**, and the same gap is now duplicated in the new display module. | `eq-server.py`: `_run` (104-110), `amixer_set` (137-142), `amixer_set_enum` (174-179), BT restore thread (288-291), `/api/store`'s `alsactl store` (1626), `power_off_or_reboot`'s `systemctl` call (196). `display/audio_control.py:24` (`mpc()`), `display/audio_control.py:157` (`bt_volume_set`), `display/eq_presets.py:35,37` (15× `amixer sset` + `alsactl store`) | Medium | A wedged ALSA/I2C bus hangs the single-threaded HTTP server indefinitely (`Restart=on-failure` catches crashes, not hangs). In the display module the same class of bug is worse: it blocks the physical rotary-encoder callback thread, freezing the whole local UI, not just one HTTP request. Fix: `timeout=2` on every subprocess call site, both files. Keep `HTTPServer` single-threaded (see S8 — do not add `ThreadingHTTPServer` as a workaround). |
| S7 | **No integrity verification on curl-fetched executable content**, root-executed. | Fallback fetch of `eq-server.py`: `install.sh:1144-1147`; `update.sh:86-93` (`fetch_repo_file`, `curl -fsSL ... -o "${dest}"`, no checksum/signature); third-party driver source: `git clone --depth=1 "${TAS_DRIVER_REPO}"` at `install.sh:287-288`, no commit/tag pin, then `dkms install --force`'d as root | Medium (supply-chain) | Not a `curl \| bash` pipe (content lands on disk before execution), but still unauthenticated fetch-and-run-as-root from a third-party GitHub source. A compromised account/MITM/CDN-poisoning scenario yields root-equivalent code execution on every Pi that updates. Consider pinning a commit SHA + checksum for the driver clone, and a checksum manifest for the raw-fetched `eq-server.py`. |
| S8 | **`update.sh` writes the live `eq-server.py` non-atomically** (no temp-file + `mv`). | `update.sh:91` (`curl -fsSL "${RAW_BASE}/${name}" -o "${dest}"`, writes directly to `/usr/local/bin/squarepi-eq-server.py`) | Medium (reliability, not exploit) | If the connection drops or the process is killed mid-transfer (Wi-Fi blip, SSH disconnect, power loss — all plausible on a Pi being updated), the destination file is left truncated. The DSP web UI silently fails to start on next restart/reboot until the owner manually re-runs the updater. Fix: fetch to `mktemp`, then `mv` into place (atomic rename). Same pattern would help the various heredoc unit-file writes in `update.sh` (133-148, 157-190, 193-208, 218-227), though those are lower-risk (systemd just refuses a malformed unit, doesn't silently half-apply). |
| S9 | **Predictable, non-`mktemp` temp files used by root, then read/deleted.** | `install.sh:453,455,459,462` (`MPD_TEST_LOG="/tmp/mpd_test.log"`); lower-severity siblings: `install.sh:572-573` (sleep-timer PID/active files), `install.sh:1316/1320,1364/1368` (Spotify/AirPlay event-marker files) | Low | Fixed, predictable filename in world-writable `/tmp`, no `mktemp`. Limited exploitability on stock RPi OS (`fs.protected_symlinks=1` blocks the classic symlink race), but worth fixing for defense-in-depth — the DKMS temp clone elsewhere (`uninstall.sh:262`) already does this correctly with `mktemp -d`. The non-root siblings are lower severity (local playback-state spoofing at most, not privilege escalation). |
| S10 | **Incomplete POST body validation** — malformed JSON / non-int `index`/`value`/`values` / non-dict `custom` / non-str `mode` raise unhandled exceptions (500 + stderr traceback, not RCE). | `eq-server.py` `do_POST`/`_body()` (1527-1661) | Low | Robustness, not a security hole — no shell involved, all subprocess calls are argv-list form. Fix: wrap `do_POST` in try/except → 400, guard `_body()`'s `json.loads` → `{}` on failure, whitelist `mode`. |

### 1.2 Confirmed safe

- **No RCE anywhere.** Repo-wide check across `eq-server.py`, `install.sh`, `uninstall.sh`, `update.sh`, and the display module: no `shell=True`, `eval`, `exec`, `os.system`, or `pickle`. Every subprocess call is argv-list form.
- **No path traversal.** The only user-controlled "name" string (custom EQ preset name) is used purely as a JSON dict key inside `/etc/squarepi-custom-presets.json`; `json.dump` escapes it, never used as a filesystem path.
- **`uninstall.sh` USB-drive protection is robust.** Layered design: `findmnt`-driven unmount of everything under `/var/lib/mpd` (mount-table-driven, not path-string matching, so immune to symlink/label spoofing) + a final `rm -rf --one-file-system /var/lib/mpd` as kernel-level backstop — `rm` refuses to cross a live mount boundary even if every unmount step upstream somehow failed. No exploitable gap found, including the TOCTOU window between detach and delete (the flag is precisely the mitigation for that window).
- **`update.sh` privilege check, quoting, and idempotency are solid.** Correct `EUID` root check (71-73); no unquoted-variable/path-with-spaces bugs found; `set -euo pipefail` + guarded `grep -q` checks before every `sed -i` mean a re-run after a partial failure safely re-applies (except the S8 non-atomic write). Data-preservation claim (EQ curve / Analog Gain / BT volume untouched, Digital Volume only lowered if over the ceiling) verified accurate against the code.
- **`install.sh`/`uninstall.sh` have no `wipefs`/`mkfs`/unsanitized `rm -rf`** built from device or label input — all destructive paths use fixed constants or `mktemp`-derived paths.
- **Display module has no `eval`/`exec`/`shell=True`/`os.system`**, and no shell string interpolation into subprocess args (all list-form `subprocess.run`).

---

## 2. Architecture / Robustness

| # | Finding | Location | Status |
|---|---------|----------|--------|
| A1 | **USB whole-disk + partition udev rules can both fire on one device.** Rules key off `KERNEL==` glob + `ENV{ID_FS_TYPE}!=""`, not the authoritative `ENV{DEVTYPE}=="disk"`/`"partition"`. A drive exposing a filesystem signature at both the whole-device and partition level double-mounts under two MPD library subtrees. | `install.sh:691-697` (`99-squarepi-usb.rules`) | `[OPEN]` |
| A2 | **`squarepi_mix` dmix definition still gated inside the BT install block**; now moot for the original scenario (BT is mandatory, can't be opted out — see below), but a **new edge case**: if the BlueALSA-unavailable fail-soft path trips (`install.sh:823-829`) and `INSTALL_BT` auto-drops to 0, `/etc/asound.conf` is never created, yet Spotify (`install.sh:1331`) and AirPlay (`install.sh:1381`) configs unconditionally point at `squarepi_mix`, which then doesn't exist. | `install.sh:839-1124` (asound.conf creation), `1331`, `1381` | `[OPEN]` (narrow — only triggers if BlueALSA packages are unavailable on the OS release) |
| A3 | **Hardcoded `"LouderRaspberry"` ALSA card name has spread.** Was 10 refs across 2 files (`install.sh`, `eq-server.py`) at last count; now **16 references across 6 files** — `install.sh` (10), `eq-server.py` (1), `uninstall.sh` (1), plus newly `display/audio_control.py` (1), `display/eq_presets.py` (1), `update.sh` (2). | repo-wide | `[PARKED]` — deliberately deferred (needs driver-rename fork), but flagging that the surface area is growing every time a new file needs the card name; if this is ever fixed, budget for 6 files not 2. |
| A4 | Bluetooth path uses ALSA plug's linear resampler, not soxr (soxr is MPD-only, configured in mpd.conf). Real but minor quality effect on non-44.1kHz-native BT sources. | `install.sh` mpd.conf soxr block vs BT `squarepi_mix` plug chain | `[PARKED]` |
| A5 | Transient `cget` failure in the BT-volume restore thread can cause a spurious absent→present re-apply, clobbering a concurrently-set value. Benign today (file is source of truth, AVRCP doesn't write this control). | `eq-server.py` `_bt_vol_restore_thread` | `[PARKED]` |
| A6 | BT-volume restore thread polls via `amixer` every 1s for the life of the process, even with no BT device connected (~86k subprocess/day on a Pi Zero 2W). | `eq-server.py` `_bt_vol_restore_thread` | `[PARKED]` |

---

## 3. New display/ module (`squarepi-installer/display/`, untracked WIP, "Local Display 2.0.0")

**Not wired into the installer or systemd at all** — no reference to `display/`, `main.py`, `st7735`, `rotary`, or `gpiozero` anywhere in `install.sh`/`uninstall.sh`/`update.sh`, and no `squarepi-display.service` unit exists. This is pure in-development code, not reachable by any installed system today — findings below are "fix before wiring in," not "urgent bug in production."

| # | Finding | Location | Status |
|---|---------|----------|--------|
| D1 | Unbounded subprocess calls on the interactive encoder-callback path (see S6 above) — worse here than the eq-server.py equivalent because a hang blocks physical knob input, not just one HTTP request. | `audio_control.py:24,157`; `eq_presets.py:35,37` (16 calls per preset apply) | `[OPEN]` — fix before wiring into installer |
| D2 | `CARD`, `BT_VOL_CONTROL`, and GPIO/SPI pin numbers are independently hardcoded and duplicated across 3+ files (`main.py`, `audio_control.py`, `eq_presets.py`, `demo_cycle_screens.py`, `test_encoder_hello.py`, `st7735_driver.py`, `test_tft_hello.py`) with no shared constants module. | throughout `display/` | `[OPEN]` |
| D3 | `EQ preset` static data (`eq_presets.py:14-28`) duplicates the Lua-baked preset values in `install.sh:514` — two sources of truth, flagged by the file's own header TODO. | `eq_presets.py`, `install.sh:514` | `[OPEN]` |
| D4 | Code duplication between `main.py` and the `demo_*.py` scripts: `FakeVuMeter`, `DemoState`, screen-index enum, and the screen-dispatch `render()` logic are each copy-pasted 2-3×. Acceptable if the demo scripts are scratch/bring-up tools meant to be dropped before merge; worth factoring out (~80 lines) if any are meant to persist as dev tools. | `demo_auto_cycle.py`, `demo_cycle_screens.py`, `main.py` | `[OPEN]` (low priority) |
| D5 | VU meter reads a second MPD FIFO output (`/tmp/mpd.fifo`) that `install.sh` does not yet create in its generated `mpd.conf` — degrades gracefully to a flat `(0.0, 0.0)` today, but will silently show a dead VU meter on a real install unless wired up. | `vu_meter.py:5-13,28`, `install.sh` mpd.conf generation | `[OPEN]` — needed before shipping |
| D6 | No resource leaks found: `VuMeter.close()` is correctly called in `main.py`'s `finally`; no busy-loops (uses `Event.wait(timeout=...)`); no `eval`/`exec`/`shell=True`. Minor nit: no explicit teardown of the SPI display handle or `gpiozero` encoder objects, harmless for a long-running daemon. | `main.py` | `[SAFE]` (nit noted, not urgent) |

---

## 4. Review Log

*(append one short entry per release here — what changed since the prior audit, not a full re-write)*

- **2026-07-12 (v1.6.0 audit, this document created):** Full first pass consolidating and re-verifying the 2026-07-04/05 findings against current code, plus first-ever review of `update.sh` (new in v1.6.0) and the untracked `display/` module. Re-checked items: S1 (XSS), S2 (CSRF — **severity escalated**, now covers the new `/api/power` reboot/shutdown endpoint), S3 (USB nosuid/nodev), S5 (amixer_set_enum `--` gap), S6 (subprocess timeouts), S10 (POST validation) — **all still open, none fixed since last review.** A2 (dmix/BT gating) — original scenario now moot (BT mandatory), but new narrower edge case identified. A1 (USB DEVTYPE) — still open. New findings this pass: S4 (BT-name shell injection), S7 (unverified curl-fetched executables), S8 (update.sh non-atomic write), S9 (predictable /tmp files), and the full D1-D6 set for the new display module.
