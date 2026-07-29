# Changelog

All notable changes to the SquarePi installer are documented here.

---

## [2.0.0] — 2026-07-25

### Added
- **Local on-device display support (opt-in via `--with-display`).** A 2nd-gen SquarePi with an ST7735 1.8" SPI TFT + KY-040 rotary encoder wired up now gets a real on-device UI, no phone or browser required: Home (title/artist/album, format badges, transport state, position), Play / Music, Playback Queue, EQ Preset, VU Meter with 19 selectable styles, Settings, Network, and System Info. The installer enables SPI, installs the Python display stack (`gpiozero`, `adafruit-circuitpython-rgb-display`, `adafruit-blinka`, `pillow`), adds an additive MPD `fifo` output for the real VU meter, and runs it as a new `squarepi-display` systemd service. Fails soft (skips display, keeps the core install) if the dependencies or the `display/` source can't be found — same pattern as DLNA/Spotify/AirPlay.
- **Long press is Menu from Home and Back everywhere else**, replacing a model where long press cycled through a fixed screen order. Cycling spent the only spare gesture on navigation, which is why every list had to be flat and why there was no way out of a screen except going all the way around. There is now a real navigation stack (`nav.py`, kept separate from `main.py` so the state machine is testable without GPIO), and screens fall back to Home on their own after 20 s — 30 s for Settings, 2 s for the EQ confirmation — so the panel doesn't sit on a menu indefinitely. Holding the knob always gets you out of wherever you are.
- **Both volumes merged into one overlay, replacing the separate MPD Volume and BT Volume screens.** Rotating on Home or the VU Meter raises a HUD over whatever is on screen showing both levels at once, with one focused; rotate adjusts it, short press switches which path the knob drives, and it hides about two seconds after the last detent. The chosen target sticks until power cycle and starts as MPD on boot. There is deliberately no auto-detection of the active source: Bluetooth playback can't be identified reliably — AVRCP metadata is absent on some phones, and the `BT Volume` softvol control only exists in ALSA once Bluetooth has actually played — so routing by guesswork would silently move the wrong path. Showing both and letting the user pick is honest about what the system can actually know. This is a UI merge only; both mixer paths are untouched, with no master control inserted anywhere in the chain. Detents are also coalesced and applied on the render loop rather than one subprocess per detent from the encoder callback, since a brisk spin is 20+ detents a second.
- **Now Playing shows what the file actually is.** Codec, bit depth and sample rate (`FLAC 16bit 44.1k`) come from fields MPD's status already returned and the display simply discarded. Nothing is guessed: formats that report no meaningful bit depth, and streams with no file extension, show fewer badges rather than invented ones.
- **Presets you save in the EQ web UI now appear on the display.** The panel listed only the 13 built-ins, so a curve you built in the browser was unreachable from the knob. It now reads `/etc/squarepi-custom-presets.json` — the file eq-server already writes — and appends your presets after the built-ins, marked with a tick in the left margin and sorted by name. Built-ins keep their positions so the applied marker can't drift onto the wrong row when you add or delete a custom, and the file is re-read when you enter the screen rather than at startup, so a preset saved in the browser is on the list by the time you walk to the knob. The display only reads that file; eq-server stays its sole writer, so the two can't race and a display crash can't cost you a preset. Entries are validated rather than trusted — the file is root-writable and hand-editable, and a short value list handed to `amixer` would have set only the bands it covered while leaving the rest wherever the previous preset left them. Malformed content costs the custom list only, never the built-ins.
- **Track titles in Malayalam, Hindi and Tamil render properly on the panel.** They previously showed as `.notdef` boxes: the bundled DejaVu faces have no glyphs for these scripts, Pillow has no font fallback, and a Pi had **0** Indic fonts installed. The installer now adds `fonts-noto-core` — it carries all three scripts with bold cuts, so a regional title renders in the same weight a Latin one does, and it's hinted for screens, which matters at 15 px on a 160×128 panel. `SQUAREPI_DISPLAY_FONTS=lohit` installs `fonts-lohit-*` instead for a tight card (~2 MB against ~100 MB, at the cost of the bold cut), and that's also the automatic fallback if Noto can't be fetched. Fonts are located by filename across the standard font directories rather than by hardcoded path, because Debian has moved Noto's files between directories and naming conventions across releases — a path list would have been a guess that silently degrades to boxes. The display picks a font per script *run* — so `Kaanthaa ചലനം (Remastered)` draws its Latin with DejaVu and its Malayalam with the Malayalam face, in one line. Text measuring is script-aware too, which matters more than it sounds: elision and the marquee both compute widths, and using DejaVu's idea of a Malayalam string's width would make a title stop scrolling before its end. Truncation is cluster-safe — cutting between a consonant and its vowel sign used to leave the mark orphaned onto whatever followed, and spacing vowel signs (`Mc`) needed testing separately from non-spacing ones (`Mn`) because most carry a zero combining class. The title marquee's tile grew from 21 to 24 px: Latin ink occupies rows 3–16 at that size but Malayalam reaches row 0 and Devanagari row 20, using the vertical room Latin leaves empty. Correct rendering also requires Pillow built against libraqm, which reorders vowel signs and forms conjuncts — verified present on the Pi (Pillow 12.3.0, `raqm: True`). Without it the glyphs appear in codepoint order, which is wrong while still looking like text, so the service logs which script fonts it found and whether shaping is available. Nothing changes for a Latin-tagged library: an all-ASCII string takes the same path it always did. UI labels stay in English — that's a separate job, and letterspaced caps is both meaningless and technically wrong for these scripts.
- **Next and previous track from the panel, as a third row in the volume overlay.** Home has drawn ⏮ ⏸ ⏭ icons since this release was started, but they were decorative — the display could pause and it could pick a track from the queue, and nothing could skip one. The overlay now has a `TRACK` row alongside MPD and BT showing position (`14/550`), reached by the same press that switches between the volume paths, and rotating on it skips. It reuses Home's existing skip glyphs rather than introducing a second pair. This was chosen over a double-press on Home, which would have made play/pause wait to see whether a second press was coming, and over a dedicated Transport screen, which put an instant action four steps deep. Unlike the volume target the row is deliberately **not** sticky: it reverts when the overlay hides, and it reverts to whichever volume row was last actually turned rather than one merely pressed through — otherwise the knob's resting action on Home would silently become "skip tracks" and reaching for volume would cost you your place in the queue. Detents coalesce into one net skip per spin, the row is skipped over entirely when there's no queue to move through, and it says `SKIP IS MPD ONLY` when Bluetooth is the source, since MPD's `next` does nothing to a phone's playback.
- **Long track titles scroll instead of being cut off.** A 148px-wide title field truncated most classical movements, remasters and anything with a parenthetical, and the elided version was often identical between two different tracks. The Now Playing title now pauses for about two seconds so the start is readable, then slides left at 26 px/s and wraps around, with both edges fading into the background rather than clipping mid-glyph. Artist and album still truncate: two lines sliding at once reads as a news ticker, and it's the title whose tail actually carries information. This costs nothing when it isn't needed — the title is measured each frame and the panel only repaints at 12 Hz while one genuinely overruns, staying at one repaint per second otherwise, and it stops entirely when the display timeout blanks the panel.
- **Playback Queue, Network, and System Info screens.** The queue lists tracks with artist and duration and opens with the cursor on whatever is playing, so picking a specific track no longer needs a browser. Network shows SSID, IP, signal and hostname; System Info shows firmware, board, CPU temperature, uptime, and memory/storage use. All reads are best-effort and show `--` rather than failing when a value isn't available.
- **Restart and Shut down from the panel**, under Settings → Power, each behind a confirmation screen. Volume is muted before the halt, matching the existing `/api/power` behaviour, since cutting an amp mid-signal thumps.
- **The VU style is named on screen when you change it.** Rotating through 19 styles was previously blind — the names existed in code but only the demos displayed them. The name and position now stamp over the meter for two seconds after a change, rather than permanently covering the meter they describe.
- **The display can start music on its own.** A new Music screen lists **Resume Queue** (only when tracks are already queued and stopped), **Shuffle All Music**, and your saved MPD playlists; rotate to scroll, short-press to start, and it jumps to Now Playing so you can see it work. Until now the display could only command music that something else had already queued — on a cold boot with an empty queue, its play/pause and skip actions had nothing to act on and you had to open myMPD just to get sound out of the box. Resume Queue is listed first and plays the existing queue untouched, so a queue built in myMPD isn't destroyed just because you reached for the knob; the other two entries replace the queue. The list stays flat: a back gesture now exists, but scrolling a few hundred albums with a knob would be miserable, and picking an individual track is what the Playback Queue screen is for. Playlists and the queue count are re-read whenever you enter the screen. When MPD is unreachable the screen says so instead of offering actions that would fail silently.
- **The play queue now survives a reboot when music is on a USB drive.** A long-standing bug that nothing had ever surfaced, because nothing before the Music screen asked what was in the queue after a boot. `squarepi-usb-mount@.service` was ordered `After=mpd.service`, and systemd stops units in reverse — so on shutdown the drive was unmounted while MPD was still running. MPD noticed (`auto_update` keeps an inotify watch on the mount point), purged every song on the drive from its database, pruned those songs from the play queue keeping only the one playing, and then wrote that emptied queue to its state file. Measured on a 550-track drive: the queue went from 550 to 1. The unit is now ordered `Before=mpd.service`, so MPD is stopped first and is already gone when the drive goes away; at boot it also means MPD waits for the mount when udev has queued it, so restored queue entries point at files that are actually present. The unmount helper additionally skips its explicit database refresh during shutdown, though the ordering is what does the real work — a genuine hot-unplug still refreshes as before.
- **USB mounts no longer stall boot by minutes.** `squarepi-usb-mount.sh` refreshed MPD's database with `mpc update` straight after mounting. Once the mount unit was reordered `Before=mpd.service` that call started running while MPD was still down, and `mpc` blocking on a daemon that isn't listening pushed MPD's start from 21:44 to 21:47 on a test box — and probably caused MPD to be SIGKILLed part-way through writing its state file during shutdown, leaving a 0-byte file. The refresh is now skipped unless `systemctl is-active mpd` succeeds. Nothing is lost by skipping it: the tag cache already lists the drive's songs, and once MPD is up `auto_update`'s inotify watch tracks any changes.
- **MPD now restores its queue paused instead of resuming playback (`restore_paused "yes"`).** With the queue-loss bug fixed, restoring in the `play` state exposed the other half of the ordering problem: udev mounts USB drives *after* `mpd.service` starts, so MPD would try to open queued files that were not mounted yet and error through them. Restoring paused keeps the queue intact and waiting for the local display's **Resume Queue** or a press on Now Playing, by which point the drive is up. Side effect some will consider a feature: the speaker no longer starts playing by itself at power-on. Set `restore_paused "no"` in `/etc/mpd.conf` to get the old behaviour if all your music is on the SD card.
- **Rotating on Home no longer spams MPD's log, because it no longer skips tracks.** Rotation used to fire `mpc next`/`mpc prev` per detent, and MPD rejected each one against an empty queue with `exception: Not playing` — one spin wrote dozens of lines to `mpd.log` and buried genuine errors while debugging. Rotation on Home is volume now, and skipping moved to the Playback Queue screen, where a track is chosen explicitly.
- **Now Playing no longer claims "Nothing playing" when a queue is sitting there stopped.** `get_mpd_now_playing()` treated any state other than `play`/`pause` as nothing at all, so a loaded-but-stopped queue — the exact state myMPD leaves behind, and the exact moment you'd reach for the knob — rendered as an empty screen. A short press did in fact start it; there was simply nothing on screen to suggest so. It now shows the current track with a **STOPPED — press to play** marker. A genuinely empty queue has no current song and still reads as nothing playing. The VU meter stays flat while stopped, as before.
- **19 full-screen VU meter styles, selectable on-device.** A 6th screen (VU Style) cycles through every style built during the display's visual exploration phase — LED ladder, horizontal/gradient bars, analog needle, radial arcs, 16-band spectrum, peak-hold ladder, mirrored bars, VFD dots, goniometer, oscilloscope, beat-pulse ring, circular waveform, dual-trace scope, mirrored waveform fill, particle bursts, starfield, beat ripples, and a vintage dB/W power meter — all fed from the real MPD audio, not fake data. Level styles read the peak over a ~4.5 ms window through attack/release ballistics (fast rise, slow fall, like an analog needle); trace styles read the sample buffer directly. Metering is MPD-only by design — Bluetooth, AirPlay, and Spotify don't pass through MPD's fifo, so the meter stays flat for those sources. (The 16-band spectrum is a derived approximation, not a true FFT — true per-band decomposition is a separate future decision.)

### Fixed
- **A Bluetooth volume write that ALSA refuses is now reported instead of faked.** `bt_volume_set()` sent stderr to `/dev/null` and returned nothing, so a rejected write was indistinguishable from a successful one and the overlay would display a level it had never set. It now returns whether the write landed, retries once after 50 ms, and the overlay shows `BT VOLUME LOCKED` when it didn't. The retry is there because the rejection is real but transient: `BT Volume` is a softvol control owned by `bluealsa-aplay`, and while that process holds the element lock (visible as `l` in `amixer`'s access flags) other writers get `EPERM`. Non-root writers are refused regardless, which is worth knowing when testing by hand as the `pi` user — the display service itself runs as root.
- **The display no longer reports "MPD" while Bluetooth is playing.** `get_now_playing()` preferred MPD whenever MPD had a current song at all, including `pause` and `stop` — and since `restore_paused "yes"` leaves MPD paused with a track on every boot, that condition was true almost always. Playing from a phone over Bluetooth after a reboot therefore showed the MPD source badge and the paused MPD track. MPD now only wins when it is actually playing, with Bluetooth checked next, and a paused MPD still preferred over nothing at all. A separate `bt_connected()` check reads BlueZ's `Connected` property rather than AVRCP metadata, so it also works on devices that never report track info.
- **A mistyped flag no longer installs the wrong thing in silence.** The argument parser tested each argument against the known flags and ignored anything else, so `--with display` (two words), `--with_display`, or `--with-dispaly` all sailed through: the install succeeded, reported success, and simply lacked the feature that was asked for. Unrecognised arguments are now a hard error up front, listing the valid flags. `--with-bt` / `--with-eq` remain accepted no-ops, and a bare `--` is still allowed.
- **`/etc/squarepi-release` could claim features that had silently skipped themselves.** The release metadata was written partway through the install, before the optional-feature blocks ran — and each of those blocks is fail-soft, resetting its own flag to 0 when a dependency is missing. A box where BlueALSA was unavailable therefore recorded `BLUETOOTH_ENABLED=1` regardless. Every `*_ENABLED` flag is now reconciled at the end of the install, once each block has had its say. This matters beyond bookkeeping: the EQ web UI reads this file to decide which panels to show, so a stale flag surfaced as a control for hardware that wasn't there.

### Changed
- **The MPD queue is flushed to disk every 30 s instead of every 120 s.** `state_file_interval` was left at MPD's default, so pulling the power within two minutes of queueing tracks lost them — and with them the local display's ability to resume anything on the next boot. The state file is a few KB, so the extra writes are negligible next to being able to trust the queue survived. A clean shutdown (the Power menu, `reboot`, `poweroff`) always flushed correctly and still does; this only narrows the window for a physical plug-pull.
- **`squarepi-display.service` is now ordered after `mpd.service`.** It only declared `After=network.target sound.target`, so on a fast boot the display could come up before MPD was listening and show "MPD unreachable" on its first frame. It self-corrected within a second or two, but there was no reason to show it at all. `Wants=` rather than `Requires=`, since the display is still worth running with MPD down.
- **Shuffle All verifies the queue actually grew.** Which URI means "the whole library" has varied across MPD versions, so rather than trusting one spelling of `add`, it now tries the root forms, checks `playlistlength`, and falls back to adding each top-level entry from `lsinfo`. Adding nothing and then calling `play` would have been indistinguishable from broken hardware at the front panel.
- **Uninstall now removes the local display too.** `uninstall.sh` stops and deletes `squarepi-display.service`, removes `/usr/local/lib/squarepi-display/`, and strips the `vu_meter` `fifo` block out of `mpd.conf` — without which an uninstalled system was left with a service restart-looping every 5 seconds and an MPD output pointing at a deleted pipe. `dtparam=spi=on` is deliberately left in `config.txt`, since other SPI devices on the header may depend on it.
- **The display's visual design was rebuilt around one accent colour and three type weights.** Colour previously encoded category — green for MPD, blue for Bluetooth, purple for EQ — which read as a debug tool rather than an audio product; source is now stated as a word and a single teal accent marks whatever is selected or live. Selected rows use a 2px accent edge on a panel instead of a full-width filled pill, level indicators use fine 1px tick scales instead of thick filled bars, and every screen carries the same status strip, so they read as one instrument. `fonts/` previously held only the bold face, meaning every glyph on the panel was bold; the regular and mono cuts of DejaVu are now bundled alongside it (same permissive license, `LICENSE_DEJAVU` included), with mono used for numerals so counting values don't jitter sideways as digits change.
- **`display/` split into testable pieces.** Navigation lives in `nav.py` and system/network reads in `sysinfo.py`, both importable on a dev box; `screens.py` renderers are pure functions of their arguments with no I/O or module state, so all 9 screens plus the overlay can be rendered and checked headless. `demo_cycle_screens.py` now drives the real `nav.py` with fake data, which makes it a genuine test of navigation, timeouts and the overlay on hardware before MPD or Bluetooth are involved; its power confirmations are deliberately inert.
- **`update.sh` can now refresh the display module.** Previously the updater could only replace single named files, so display code was unreachable to it. It now refreshes the module in place when the display is installed, and when it isn't, the "add it with `--with-display`" hint is no longer version-gated — it keeps appearing on later updates instead of scrolling past exactly once.
## [1.6.8] — 2026-07-26

### Fixed
- **The POWER menu couldn't be used on a phone.** Tapping POWER appeared to do nothing: the top bar was set to scroll sideways when it ran out of room, which had the side effect of cutting off anything drawn below it — including the Restart / Shut down menu, and the UPDATE menu alongside it. The bar now wraps onto a second line instead of scrolling, so both menus open normally. Restart and Shut down were unreachable from a phone before this.
- **The NETWORK SHARE form was cramped on a phone.** Labels sat beside their fields as they do on a desktop, which left an IP address roughly 150 pixels to fit into. On narrow screens the labels now sit above their fields and each field uses the full width of the card.
- **The NETWORK SHARE card was hard to find on a phone.** It starts folded away, and the side navigation that would lead you to it is hidden on narrow screens — so the only way in was spotting a collapsed heading well down the page. On a phone the card now starts open.

---

## [1.6.7] — 2026-07-26

### Fixed
- **Adding a network share could stop the web UI (myMPD) from coming back after a reboot.** With a share configured, the speaker would sometimes boot with music playing but the myMPD control page refusing to load — and it came and went between reboots, which made it look like several different faults. The cause was the share's automount unit: it was told to wait for the network, but an automount has to be ready very early in boot, before the network exists. That contradiction made systemd quietly drop a core part of the startup sequence to resolve it, and myMPD depended on the part that got dropped. The automount no longer waits for the network — it doesn't need to, because it does nothing until something actually reads the folder, and only *then* does the real mount (which does wait for the network) happen. Reproduced and confirmed on hardware. If you already have a share configured, the SquarePi updater repairs the existing unit in place; the fix applies fully on the next reboot.
- **A network share could empty the play queue on shutdown.** The share was being disconnected while MPD was still running, so MPD saw the folder vanish, treated those tracks as deleted, and saved an emptied queue — the same fault USB drives had before 1.6.4, now closed for network shares too by stopping MPD first.
- **The NETWORK SHARE card showed "Connected" when nothing was actually mounted.** The status check treated the always-present automount point as a live mount, so the indicator went green as soon as a share was saved, even after a reboot before the share had been touched or while the NAS was switched off. It now reports connected only when a real share is mounted.

### Known limitation
- With the NAS powered **off**, its tracks stay listed in the library across a reboot — MPD keeps them from its cache and doesn't re-scan the missing folder (confirmed on hardware) — they simply can't play until the NAS is back on. They only drop out of the library if a rescan (`mpc update`) runs while the share is unreachable; `mpc update nas` restores them once it is back. A share that disappears *while the speaker is running* is the harder case — MPD's live folder-watch notices and purges it — and is tracked separately.

---

## [1.6.6] — 2026-07-26

### Fixed
### Added
- **A dedicated network share guide**, [docs/network-share.md](docs/network-share.md). Setup instructions per server type (Synology/QNAP, Windows, macOS, Samba on another Pi), a troubleshooting table covering every error the card can report, what to check when a share mounts but myMPD stays empty, stutter causes, the files and units involved, and security guidance. The share content that was scattered across three documents now has one place to point people at.

### Fixed
- **Network share fields were pushed to the far right of the card.** The width cap that stops an IP address sitting in a box wide enough for a sentence was applied to the form's label column rather than to the fields themselves. A CSS grid column sized `auto` absorbs whatever space is left over, so the labels stretched and carried every input across to the right edge, far from the label describing it. The cap now sits on the fields.

---

## [1.6.5] — 2026-07-26

### Added
- **Play music from a network share, set up in the web UI.** A **NETWORK SHARE** card in the DSP interface connects the speaker to a NAS or a shared folder on a computer — SMB/Windows shares and NFS. Fill in the server's IP address, the folder name and (for SMB) a username and password, and it appears in myMPD as `nas` alongside the built-in library. Previously this meant an SSH session, installing `cifs-utils` by hand and writing an `/etc/fstab` line, where a single mistake either produced an empty folder with no explanation or stopped the Pi from booting.

  **Test connection** mounts the share, reports what it found, and unmounts again, so a wrong password says so instead of leaving a folder that silently stays empty. Nothing is saved until a connection has actually succeeded. The two mistakes that made hand-written entries fail are handled rather than documented: MPD's own user and group are looked up and applied as the mount's ownership — SMB has no real Unix ownership, so those options *are* the ownership, and getting them wrong is what produces a share that `pi` can read and MPD cannot — and `.local` server names are rejected with an explanation, because they cannot be resolved at the point the share is mounted after a restart.

  The share is mounted only when something reads it, so a NAS that is asleep, switched off or simply slow never delays startup — and once mounted it stays mounted, which matters more than it sounds: an unmounted automount path reads as an empty folder, and MPD treats an empty folder as files that have been deleted. `cifs-utils` and `nfs-common` are now installed as standard.

  If the NAS does go away while the speaker is on, those tracks disappear from myMPD and from the play queue, because MPD can no longer see them. Running `mpc update nas` once the NAS is back restores everything. This is the same behaviour as pulling a USB drive mid-play, and it is the price of MPD picking up new files by itself.

  `/etc/fstab` is deliberately left untouched; SquarePi writes its own systemd mount unit, which `uninstall.sh` removes cleanly. A hand-written fstab entry, if you already have one, keeps working and is not interfered with. SMB passwords are stored on the Pi in a root-only credentials file — unavoidable for an unattended mount, and the same thing an fstab setup does — and are never sent back to the browser.

---

## [1.6.4] — 2026-07-26

### Added
- **Playback resumes after a restart.** If the power goes out mid-song, the same track picks up where it left off on the next boot — same position, same volume, same queue. Applies to your own music library only; Bluetooth, AirPlay and Spotify are controlled by the device that sent them, so there is nothing on this end to resume. On by default, with a toggle in the EQ web UI under **SYSTEM → Startup**.

  Two small services do the work. The first runs before MPD and records whether MPD was playing when the box last went down — it has to read that before MPD overwrites it, and reading the saved state rather than writing a marker at shutdown is what makes this survive a pulled plug, which is the case that matters. The second runs after MPD and waits for playback to actually be safe: MPD answering, the track's file present (USB drives are mounted after MPD starts), and no phone already connected over Bluetooth. If any of that never comes good within a minute it gives up quietly and leaves the queue paused, rather than playing the wrong thing.

### Fixed
- **The EQ web UI took seconds to appear on first load.** The page's opening request, `/api/state`, read every amp control one at a time — 15 EQ bands, analog gain, both channel gains, two enums, four matrix cells and 13 fault flags, each its own `amixer` process, all back to back. Thirty-seven process spawns before the page could paint, which on a Pi Zero 2W is most of the wait. It's now a single `amixer contents` call, parsed once. The `/api/faults` poller got the same treatment (13 spawns → 1). Nothing else changed: if the batched read comes back empty, every control falls through to its old individual read, so the page fills in correctly either way. This only ever affected first paint — once loaded, the page's pollers were always cheap, which is why it felt fast afterwards.
- **The EQ web server handled one request at a time.** The page fires three requests the moment it loads, and they queued behind whichever was slowest. It's now a `ThreadingHTTPServer`.
- **Saving a custom EQ preset could be seen half-written.** The preset file was truncated and rewritten in place, so anything reading it at that instant got an empty or partial document — and the local display, which reads the same file and fails soft, would show no custom presets at all. Writes now go to a temp file and are renamed into place, which is atomic.
- **The play queue never survived a reboot when your music was on a USB drive.** systemd stops units in reverse start order, so the USB mount unit — ordered `After=mpd.service` — was torn down while MPD was still running. MPD's `auto_update` inotify watch saw the drive disappear, purged every song on it from the database, and pruning those songs from the play queue left only whatever was playing. MPD then wrote that emptied queue to its state file. Four coordinated changes fix it: the mount unit is now ordered `Before=mpd.service` so MPD is stopped first; the unmount helper skips its database refresh while the system is shutting down; the mount helper only refreshes when MPD is actually running (at boot it now runs while MPD is still down, and blocking on a daemon that isn't listening delayed boot by minutes); and MPD flushes its state every 30s rather than the 120s default, so a power cut loses less.
- **Adding one feature to an existing install disabled the others.** The optional-feature flags started from zero on every run, so re-running the installer with `--with-spotify` on a box that already had DLNA wrote `DLNA_ENABLED=0` to `/etc/squarepi-release`. Nothing was actually uninstalled — upmpdcli kept running — but that file is what the DSP web UI reads to decide which panels to show, so the feature vanished from the interface. The installer now reads what's already recorded and merges: features already installed stay installed, and it prints which ones it kept. Flags are additive; `uninstall.sh` is still the way to remove something.
- **Typo'd installer flags were silently ignored.** `--with spotify` (two words) or `--with_spotify` used to sail straight through: the install succeeded, said nothing, and simply lacked the feature that was asked for. Unrecognised arguments are now a hard error that lists the valid flags. `--with-bt` and `--with-eq` remain accepted no-ops.

### Changed
- **MPD restores paused instead of playing.** USB drives are mounted by udev *after* `mpd.service` starts, so a restored queue of USB tracks would otherwise have MPD erroring through files that aren't there yet. The queue now comes back intact and waiting. This is what makes resume-after-restart safe: rather than MPD starting the moment it loads, playback is started deliberately, a few seconds later, once the files are actually reachable. With resume switched off, the queue simply waits for you to press play.

---

## [1.6.3] — 2026-07-15

### Fixed
- **Card section headers showed a "collapse" arrow that didn't collapse anything.** Every card title (`GAIN & BALANCE`, `EQUALIZER`, `MIXER`, `SYSTEM`) displayed a right-pointing arrow — the universal "click to expand/collapse" convention — with no click handler behind it. Now genuinely wired: click a title to collapse or expand that card, state persists across reloads. Fixed a bug this surfaced along the way: the EQ curve canvas sizes itself from its container's on-screen dimensions, which are 0×0 while collapsed, so expanding a previously-collapsed EQ card now explicitly redraws the curve instead of leaving it blank.

### Added
- **Mixer's Custom routing matrix explains itself.** The 4 raw cross-channel dB sliders had no explanation and no way back except manually resetting each one by hand. Added a one-line caption plus a "Reset to Stereo" button.
- **Discoverability hint on the EQ curve graph.** The frequency-response curve has been directly draggable since v1.4.2, but nothing on the page said so — a small "drag to shape, or use faders below" hint now sits above the graph.

### Changed
- **Removed the topbar's duplicate PRESETS dropdown.** It was a pure duplicate of the EQ card's own preset selector (identical option list, identical handler) — the EQ card still has its dropdown and the full preset button row (which also does something the dropdowns didn't: shows which preset is currently active). The topbar's **SAVE TO CHIP** button regained a save icon on its own label now that it's the only save-to-chip control left.

---

## [1.6.2] — 2026-07-14

### Added
- **Update-available badge in the EQ web UI.** A background check (once every 24h, never blocking a page load) compares `/etc/squarepi-release` against SquarePi's GitHub tags and shows a green **UPDATE** badge next to POWER when a newer version exists. Notify-only by design — clicking it shows the exact `update.sh` command to run over SSH; it never runs the update itself, so it adds no new root-triggerable action to the web UI. (Note: this reads the repo's git tags directly rather than GitHub's "latest release" API, since releases here are pushed as tags, not published as GitHub Releases — the releases endpoint would have returned a stale, unrelated result.)
- **Host Health panel in the SYSTEM card.** Below the existing amp Fault Monitor, a second grid checks the Pi side of the stack: DSP card/driver detected, SD card free space, WiFi signal (shows "N/A" rather than a false warning on wired installs), Bluetooth adapter powered, and the four core services (MPD, BlueALSA, BlueALSA-aplay, mDNS). Every check fails soft — a missing tool or unreachable service shows as a status dot, never crashes the page. The SYSTEM card's existing health LED now reflects both amp faults and host issues together, so one glance still tells the whole story. Aimed at surfacing "why doesn't it work" problems before a non-technical user has to ask.

### Changed
- **EQ web UI's Save buttons, consolidated.** There were 5 buttons that said "Save" in some form but only 2 distinct actions: 3 identical shortcuts to "commit current settings so they survive a reboot" (topbar SAVE button, a topbar floppy-disk icon, and a SYSTEM-card button) and 2 identical shortcuts to "save the current EQ curve as a named preset" (one in the EQ card header, one next to the preset-name field). Down to one of each now — topbar **SAVE TO CHIP** (tooltip explains what it commits) and the EQ card's **Save as preset** (tooltip clarifies it doesn't affect what survives a reboot, next to the name field where it contextually belongs).

---

## [1.6.1] — 2026-07-14

### Fixed
- **EQ web UI was unusable on phone-width screens.** The main content column and the 15-band EQ grid used CSS Grid `1fr` tracks, which by default won't shrink below their content's minimum width; the unshrinkable EQ rack forced the whole content column ~200px wider than the viewport. Because the page also disables all scrolling (`overflow:hidden` on `html`/`body`) as its normal desktop layout, that overflow was invisible rather than reachable — on a phone this clipped the **POWER** button (and Restart/Shut down with it) off the top bar entirely, along with the EQ card's **ON/OFF**, **SAVE EQ**, **RESET** and **BYPASS** controls, and 4 of the 15 EQ bands (3.15k–16k). `.content` now has `min-width:0` so it stops fighting the viewport; below 680px width the top bar and the EQ fader rack each get their own horizontal scroll region instead of clipping, and the EQ card's header buttons wrap onto additional lines (already-present `flex-wrap` just wasn't being reached). Also added `touch-action:none` to the per-band fader sliders, matching the frequency-response curve, so dragging a fader on a touchscreen can't be hijacked by the page's scroll gesture.

---

## [1.6.0] — 2026-07-12

### Added
- **In-place updater (`update.sh`).** Existing installs can move to a newer version without the destructive full reinstall: `git pull` then `sudo bash squarepi-installer/update.sh`. It applies only the deltas — Power control + latest EQ server, the shutdown-mute fix, the boot-ordering safety, the first-boot card-wait, the Digital Volume 0 dB ceiling, `replaygain off`, and the DKMS driver migration (only if the driver isn't already DKMS-managed). It **preserves** your saved EQ curve, your chosen Analog Gain, and your BT volume — it enforces safety ceilings and service fixes, never resets your levels. It first checks your installed version against the latest, tells you what's changing (`1.5.2 → 1.6.0`), and asks for confirmation before touching anything — if you're already current it exits immediately with no changes. Idempotent and safe to re-run, and built to carry any older install straight to the newest release, not just one version step at a time.

### Fixed
- **"Save to chip" icon looked identical to the power controls.** The topbar's Save-to-chip icon reused the same power-symbol glyph as the POWER button and the "Shut down" menu item, sitting right next to them — an easy mis-click that silently saved settings instead of triggering (or instead of appearing to trigger) a shutdown, with no confirmation either way. Save-to-chip now uses a distinct floppy-disk icon.
- **Uninstaller aborted halfway through.** Run the documented way (`curl … | sudo bash`), stdin is the pipe, so the "Remove MPD library cache?" prompt hit instant EOF; under `set -e` the failing `read` killed the whole script right after MPD was removed — leaving the driver, boot overlay, EQ/Bluetooth/USB/DLNA/AirPlay/Spotify stack and release file behind. All remaining prompts now read from `/dev/tty` (with safe defaults, honouring `SQUAREPI_YES=1`), matching the initial confirmation prompt. A failing `apt-get update` during uninstall is also no longer fatal.
- **Analog Gain stuck at 0 dB (full output) on first boot.** The first-boot init service ran too early — the DKMS-built TAS5805M card usually wasn't enumerated yet, so every `amixer` call failed silently, yet the service still marked first-boot done and never retried. Analog Gain was left at the chip power-up default (0 dB = maximum). Init now waits for the card and its `Analog Gain` control to appear before applying anything, and exits *without* marking done if the card never shows — so it retries on the next boot instead of leaving the amp at full output.
- **Amp came back muted after every Restart or Shut down, again — a second source of the v1.5.1 bug.** The Power menu mutes Analog Gain to −15.5 dB before halting so the speakers don't thump; v1.5.1 stopped `squarepi-eq.service` from ever persisting that mute, but the *stock* `alsa-utils` package's own `alsa-restore.service` was never addressed — it ships `ExecStop=alsactl store`, gets pulled in by udev as soon as the sound card is detected, and stays active until systemd stops it on every halt/reboot, silently storing the transient mute and restoring the amp near-silent on the next boot. `alsa-restore.service` is now masked at install/update time; `squarepi-alsa-restore.service` already fully replaces its restore-on-boot job with correct producer ordering, so this is pure redundant-risk removal.
- **EQ UI's Mixer Mode (Stereo/Mono/Left/Right) and matrix sliders never did anything.** The stock TAS5805M driver overlay hardcodes `ti,mixer-mode = <0>` (Stereo) in its device tree — the driver's own source treats that property's presence as "lock the mode, don't expose runtime controls," so the `Mixer Mode` and `Mixer L2L/R2L/L2R/R2R Gain` ALSA controls were never registered at all (`amixer: Unable to find simple control 'Mixer Mode'`). The EQ UI's Output Mode panel had nothing to talk to, so clicking Mono/Left Only/Right Only changed nothing audibly. The overlay is now patched to omit that property before compiling — the boot-time default is still Stereo either way (the driver's no-DT-property fallback matches), it just also exposes the controls so they're actually adjustable. **Requires a reboot** to take effect (device tree overlays only load at boot); `update.sh` calls this out explicitly when it applies.

### Changed
- **Bluetooth and the EQ web UI are now core, non-removable features.** They are the two things that define a SquarePi, so the `--without-bt` / `--without-eq` opt-outs have been removed — every install includes both. `--with-bt` / `--with-eq` are still accepted as harmless no-ops. DLNA, Spotify, and AirPlay remain opt-in. (The internal fail-soft still applies: if no BlueALSA package is available on the OS image, the installer warns and continues rather than aborting.)
- **No un-vetted gain window at boot (defence in depth).** Analog gain only matters while I2S signal is flowing, and the only signal sources are MPD, Bluetooth, AirPlay, Spotify and DLNA. Every one of those services is now ordered **after** a safe-gain step: the first-boot init on first boot, and `alsactl restore` on every boot (previously only MPD waited for the gain restore). This closes the last paths where a source could play before the safe gain landed — the speakers can never blast at full output during startup.

---

## [1.5.1] — 2026-07-05

### Added
- **Power control — restart and shut down from the UI.** The EQ web interface now has a **POWER** menu (Restart / Shut down) in the header, and myMPD gains two matching script tiles (`Power_Restart`, `Power_Shutdown`). Both mute the amp first — so the speakers don't thump when the TAS5805M loses its clock — then reboot or halt the Pi cleanly, giving a non-technical owner a safe way to power down instead of yanking the plug. Backed by a new `POST /api/power` endpoint on the EQ server (runs as root, so no sudo); the myMPD tiles `curl` it.

### Fixed
- **Driver now survives kernel updates (DKMS).** The TAS5805M module was built with a one-off `make install`, so any `apt upgrade` that bumped the kernel silently left the module behind on the next boot — dead audio, unrecoverable for a non-technical owner. It's now packaged with **DKMS** and rebuilds automatically on every kernel change. (The device-tree overlay already lived in `/boot` and was unaffected.)
- **Amp came back near-silent after a Power-menu shutdown.** The shutdown mute lowers `Analog Gain` to −15.5 dB so the speakers don't thump — but the EQ service's `ExecStop=/usr/sbin/alsactl store` saved that muted value on halt, and `alsactl restore` brought it back muted on the next boot, leaving playback ~15.5 dB quieter (needing far more MPD volume for the same loudness). Removed the store-on-stop; ALSA state now persists only via the UI **Save** and first-boot init, so the transient mute is never captured.
- **Uninstall could wipe a plugged-in USB drive.** USB drives auto-mount inside `/var/lib/mpd/music/usb/<dev>`; the "remove MPD cache" step ran `rm -rf /var/lib/mpd` before unmounting them, so a mounted pendrive was deleted along with it. Uninstall now detaches every USB drive up front (and again at the delete), and the `rm` uses `--one-file-system` so it can never cross into a mounted drive.

### Changed
- **Gain-staging safety.** `Digital Volume` is now pinned to 0 dB (value 103) on first boot and persisted — values above that apply up to +24 dB of digital boost (guaranteed clipping, possible speaker damage). `replaygain` changed `auto` → `off` for predictable per-track levels (auto did nothing for untagged files and caused jumps on tagged ones). See the new gain-staging notes in [docs/audio-engine.md](docs/audio-engine.md); for real loudness normalisation, tag the library once with `loudgain`.
- **Analog Gain first-boot default set to −10 dB** (value 11) instead of full output, so the very first playback on unfamiliar speakers is a moderate level, never a full-output blast. This is only the first-boot default — the owner can raise or lower it in the EQ UI and their choice persists.

---

## [1.5.0] — 2026-06-30

### Added
- **USB auto-mount on insert** — plug a drive in and it mounts automatically and shows up in MPD under `usb`; no SSH, no fstab editing. Handles **FAT32, exFAT, NTFS, and ext4**, any label, any size, and multiple partitions/drives (each mounts under its own folder). Drives mount *inside* MPD's library, so the built-in music is preserved and no `mpd.conf` change is needed. Unplugging auto-unmounts and rescans. Built from a udev rule + a templated systemd service; `ntfs-3g` is now installed alongside `exfatprogs`.

### Fixed
- **exFAT manual-mount docs were wrong** — the fstab example used type `vfat`, which fails on exFAT. Documentation now gives correct per-filesystem lines (`vfat`, `exfat`, `ntfs-3g`, `ext4`).

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
