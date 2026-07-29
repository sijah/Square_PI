# SquarePi — Full Setup Guide

This guide covers everything from a blank SD card to music playing through your speakers.

---

## What you need

- Raspberry Pi Zero 2W, 3B+, or 4B (Pi 5 not yet supported — the installer detects Pi 5 and refuses to run)
- SquarePi HAT
- SD card (8GB minimum, 16GB+ recommended)
- 12–24V DC power supply, barrel jack (3A minimum at 12V)
- 4–8Ω passive speakers
- WiFi network (or Ethernet for Pi 3B+/4B)

---

## Step 1 — Flash the OS

Download and install [Raspberry Pi Imager](https://www.raspberrypi.com/software/).

**OS to select:**
- Raspberry Pi OS Lite (64-bit) — Bookworm or Trixie
- Do **not** use the Desktop version — it installs PulseAudio which conflicts with ALSA

**In the imager, before flashing — click the gear icon and configure:**
- Hostname: `squarepi`
- Enable SSH: yes, with password authentication
- WiFi SSID and password (your network)
- Username: `pi` (or any name you prefer)
- Password: choose a secure password

Flash the SD card. Insert it into the Pi.

---

## Step 2 — Attach the HAT

**Power off completely before attaching hardware.**

1. Align the SquarePi HAT's 40-pin header with the Pi's GPIO pins
2. Press firmly and evenly — both ends simultaneously
3. The HAT sits flat against the Pi, no gap

Speaker wiring:

| Terminal | Connection |
|---|---|
| `LP` | Left speaker + |
| `LN` | Left speaker − |
| `RN` | Right speaker − |
| `RP` | Right speaker + |

> Double-check polarity. Use 4–8Ω passive speakers only. Never connect or disconnect speakers with the system powered on.

---

## Step 3 — First boot and SSH

Power on with the SD card inserted. Wait 60–90 seconds for first boot to complete.

Find the Pi on your network:
```bash
ping squarepi.local
```

If mDNS is not working on your computer, find the IP from your router's DHCP list, then:
```bash
ping 192.168.x.x
```

SSH in:
```bash
ssh pi@squarepi.local
```

Accept the host key fingerprint when prompted.

---

## Step 4 — Run the installer

### Install (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/sijah/Square_PI/main/squarepi-installer/install.sh | sudo bash
```

Every install includes **Bluetooth and the visual DSP interface** alongside MPD, myMPD, EQ presets, and the sleep timer — these are core features and can't be removed. DLNA, Spotify Connect, and AirPlay are opt-in.

### Flags

| Command | Effect |
|---|---|
| *(no flags)* | MPD + myMPD + **Bluetooth** + **EQ UI** + presets + sleep timer |
| `--with-dlna` | Add DLNA/UPnP renderer |
| `--with-spotify` | Add Spotify Connect |
| `--with-airplay` | Add AirPlay |
| `--with-display` | Add the local display (ST7735 TFT + KY-040 encoder) — needs the hardware wired, see [Optional: Local display](#optional-local-display-st7735--ky-040) |
| `--all` | Everything (+ DLNA, Spotify, AirPlay, local display) |

`--with-bt` / `--with-eq` are still accepted as harmless no-ops (BT and the EQ UI are always installed). Mix and match the opt-in flags freely:
```bash
... | sudo bash -s -- --with-dlna --with-airplay
```

If a BlueALSA package isn't available on your OS image, the installer warns and continues — the core install never aborts.

An unrecognised flag stops the installer with a list of the valid ones, rather than
running to completion without the feature you asked for.

### Adding a feature later

Decided you want Spotify after all? Re-run the installer with the flag for the new
feature. It takes a few minutes, but nothing is lost — your music, playlists, EQ
settings and paired Bluetooth devices all stay put.

```bash
cd ~/Square_PI/squarepi-installer && sudo bash install.sh --with-spotify
```

You only need the flag for what you're **adding**. Anything already installed is
detected and kept, and the installer prints what it kept so you can see it
happened. To remove a feature, use `uninstall.sh`.

### Clone and run locally (alternative)

```bash
git clone https://github.com/sijah/Square_PI.git
cd Square_PI/squarepi-installer
sudo bash install.sh
```

### What the installer does

1. Detects TAS5805M I²C address (scans 0x2c–0x2f on buses 1 and 2)
2. Backs up `/boot/firmware/config.txt`
3. Enables I2S, disables onboard Pi audio, adds tas58xx overlay
4. Installs and configures MPD with 48kHz/24-bit pipeline and SoXR resampling
5. Installs myMPD and starts it on port 8080
6. Writes all 13 EQ preset Lua scripts to myMPD
7. Writes sleep timer scripts (30/60/90 min + cancel) to myMPD
8. Writes Power control scripts (Restart / Shut down) to myMPD
9. Sets MPD volume to 25% (safe first-boot default)
10. Installs a first-boot EQ init service (sets all 15 bands to 0 dB and Analog Gain to −10 dB, runs once)
11. Installs Bluetooth and the EQ server by default; DLNA, Spotify, AirPlay when requested
12. Sets up USB auto-mount (udev + systemd) so drives mount on insert, and installs the SMB/NFS helpers used by network shares
13. Verifies myMPD responds on port 8080
14. Writes install metadata to `/etc/squarepi-release`

---

## Step 5 — Reboot

```bash
sudo reboot
```

Wait 30–60 seconds for all services to start.

---

## Step 6 — Verify

### Check the audio card loaded

```bash
aplay -l
```

You should see a card named `LouderRaspberry`. If it's missing:
```bash
dmesg | grep -i tas58
lsmod | grep tas
```

### Test audio output

```bash
speaker-test -D plughw:LouderRaspberry,0 -t sine -f 1000 -c 2
```

You should hear a 1kHz sine tone from both speakers.

### Check MPD

```bash
mpc status
```

Should show `volume: 25%` and `state: stop`.

### Open myMPD

In a browser on the same network:
```
http://squarepi.local:8080
```

If your browser redirects to HTTPS, use `https://squarepi.local:8443` and accept the self-signed certificate. Mobile browsers work — no app required.

### Open the DSP interface (installed by default)

```
http://squarepi.local:8081
```

The DSP interface also has a **Power menu** (top right) for Restart / Shut down — it mutes the amp before halting so there's no speaker thump. The same two actions are installed as `Power_Restart` / `Power_Shutdown` tiles in myMPD under Scripts.

---

## Step 7 — Add music

**Copy files to the Pi:**
```bash
scp -r /path/to/music pi@squarepi.local:/var/lib/mpd/music/
```

On the Pi, fix ownership and rescan:
```bash
sudo chown -R mpd:audio /var/lib/mpd/music
mpc update
```

**Use a USB drive — just plug it in:**

SquarePi auto-mounts the drive and it appears in MPD under `usb` within a few seconds — no commands needed. FAT32, exFAT, NTFS, and ext4 all work, any label or size. Unplug to remove it.

```bash
# optional — confirm it mounted and force a rescan
systemctl status 'squarepi-usb-mount@*'
mpc update
```

Prefer to pin a specific drive manually (by UUID) instead? See **USB Drive → Advanced** in [supported-protocols.md](supported-protocols.md) for the correct per-filesystem fstab lines.

**Play from a NAS or a shared folder:**

Open the DSP interface at `http://squarepi.local:8081`, expand **NETWORK SHARE**, and fill in three things:

| Field | What to put | Example |
|---|---|---|
| Type | `SMB / Windows share` for a NAS or a Windows/Mac shared folder; `NFS` if your NAS offers it | SMB |
| Server | The **IP address** of the machine holding the music | `192.168.1.50` |
| Folder | The share name, as the NAS advertises it | `Music` |

For SMB, add the username and password the NAS expects; leave both empty if the share is open to everyone. NFS needs neither.

Press **Test connection** first — it tries the share and tells you what happened, including how many items it could see. Then **Connect & save**. The share appears in myMPD as `nas` within a few seconds.

Setting one up on a Synology, Windows, macOS or Samba box, or hitting an error? See the dedicated guide: **[network-share.md](network-share.md)**.

Use the **IP address, not a `.local` name**. Names can't be looked up early enough when the Pi reconnects to the share on its own after a restart, so the form rejects them. If you don't know the IP, your router's device list will show it.

A few things worth knowing:

- The share is mounted only when something reads it, so a NAS that's asleep or switched off never holds up startup — it simply reconnects next time it's needed.
- Large libraries take a while to scan the first time. Playback works as tracks appear.
- **Remove** unmounts the share and forgets the settings. Nothing on the NAS is touched.
- Your own `/etc/fstab` entries are left alone. SquarePi writes its own mount unit, so a manual setup you already have keeps working.
- The SMB password is stored on the Pi in a root-only file, which is what any unattended mount requires. Anyone on your network can reach the DSP interface, so give the speaker an account with read-only access to the music rather than an administrator one.

---

## Optional: Local display (ST7735 + KY-040)

A 1.8" ST7735 SPI TFT and a KY-040 rotary encoder give the player a front panel, so it works without a phone or a browser. This is entirely optional — SquarePi is complete without it.

Add it at first install or later on a running system:

```bash
sudo bash install.sh --with-display
```

The installer enables SPI, installs the Python dependencies (`gpiozero`, `adafruit-circuitpython-rgb-display`, `adafruit-blinka`, `pillow`), copies the module to `/usr/local/lib/squarepi-display`, adds an additive `fifo` output to `/etc/mpd.conf` to feed the VU meter, and enables a `squarepi-display` service. If the dependencies can't be installed, it warns and skips the display — the core install still finishes.

**A reboot is required afterwards**, because SPI only comes up at boot.

### Wiring — display

| Display pin | Pi GPIO | Physical pin | Notes |
|---|---|---|---|
| `VCC` | 3V3 | 1 or 17 | |
| `GND` | GND | 6, 9, 14, 20, 25, 30, 34, 39 | any ground |
| `SCL` / `SCK` / `CLK` | GPIO11 (SCLK) | 23 | hardware SPI0 |
| `SDA` / `MOSI` / `DIN` | GPIO10 (MOSI) | 19 | hardware SPI0 |
| `CS` | GPIO8 (CE0) | 24 | hardware SPI0 |
| `DC` / `A0` | GPIO24 | 18 | ordinary GPIO, not SPI |
| `RES` / `RST` | GPIO25 | 22 | ordinary GPIO, not SPI |
| `BL` / `LED` | 3V3 | 1 or 17 | backlight, always on |

Some ST7735 boards silkscreen the data/command select pin as **`A0`** rather than `DC`. It is the same signal under a different vendor label — wire it to GPIO24 either way.

Only `CS`, `MOSI`, and `SCLK` are hardware SPI pins and have to be these. `DC`/`A0` and `RES` are ordinary GPIOs; any free pin works if you edit `st7735_driver.py` to match.

### Wiring — encoder

| Encoder pin | Pi GPIO | Physical pin |
|---|---|---|
| `CLK` / `A` | GPIO17 | 11 |
| `DT` / `B` | GPIO27 | 13 |
| `SW` | GPIO22 | 15 |
| `+` / `VCC` | 3V3 | 1 or 17 |
| `GND` | GND | any ground |

### Controls

Three gestures on one encoder. **Long press (0.6 s) is Menu from Home, and Back on every other screen** — so you can always get out of wherever you are by holding the knob.

Home is the default screen and the one you return to.

| Screen | Rotate | Short press | Long press |
|---|---|---|---|
| Home (Now Playing) | volume | play / pause | Main Menu |
| Main Menu | move cursor | open the item | Home |
| Play / Music | scroll the list | play the highlighted entry | back to Menu |
| Playback Queue | scroll the queue | play that track | back to Menu |
| EQ Preset | scroll the 13 presets | apply it (then shows the curve) | back to Menu |
| VU Meter | volume | open the style browser | back to Menu |
| VU Style | change meter style (19 of them) | back to VU Meter | back to Menu |
| Settings | move cursor | open the item | back to Menu |
| Network / System Info | — | refresh | back to Settings |

Screens fall back to Home on their own after a spell with no input — 20 seconds for most, 30 for Settings — so the panel doesn't sit on a menu indefinitely.

Skipping tracks lives in the volume overlay's third row — see below. To jump to a particular track rather than the next one, use the **Playback Queue** screen.

#### EQ presets on the panel

The EQ Preset screen lists the 13 built-in presets followed by any presets you saved in the EQ web UI, marked with a small tick in the left margin and sorted by name. The list is re-read each time you open the screen, so a preset saved in the browser is there by the time you reach the knob — no restart needed.

The display only ever reads that file; the web UI owns it. Building presets stays a web-UI job, and the panel applies them.

#### Regional language track names

Titles, artists, albums, queue entries and playlist names display correctly in **Malayalam, Hindi (Devanagari) and Tamil**, mixed freely with Latin in the same line. `--with-display` installs `fonts-noto-core`, which carries all three with bold cuts and is hinted for screens — worth having at this size. If a font is missing the affected text shows as empty boxes and everything else keeps working; `journalctl -u squarepi-display` reports which scripts it found at startup.

On a tight SD card, `SQUAREPI_DISPLAY_FONTS=lohit ./install.sh --with-display` installs `fonts-lohit-*` instead: about 2 MB against Noto's ~100 MB. The trade is that Lohit has no bold cut, so a regional title renders in regular weight where a Latin one would be bold. The installer also falls back to Lohit on its own if `fonts-noto-core` can't be fetched.

Fonts are found by name wherever the packages put them, so installing any other Noto or Lohit face by hand works too.

Two limits worth knowing. Menu labels and screen headings stay in English. And if your files' tags aren't UTF-8 — some older ID3v1 tags aren't — they arrive as mojibake and no font can repair that; the fix is retagging the files.

#### Long titles

A title too wide for the panel scrolls: it holds still for about two seconds so you can read the start, then slides left and wraps around, taking roughly 10 seconds for a typical long title and about 20 for an extreme one. Both edges fade out instead of cutting a letter in half. Artist and album stay truncated with an ellipsis — the title is the field whose end usually matters, and two lines moving at once is hard to read.

Titles that fit don't move at all, and the panel goes back to refreshing once a second.

#### Volume

Both volumes live in one overlay rather than on their own screens. Rotate the knob on Home or the VU Meter and it appears over whatever you were looking at, showing **both** levels — MPD and Bluetooth — with one of them focused. Rotate to adjust the focused one, **press to switch which one the knob drives**, and it disappears on its own about two seconds after you stop turning. The choice sticks until the next power cycle, and comes back as MPD after a reboot.

There is deliberately no automatic guessing about which source you meant. Bluetooth playback cannot be detected reliably — some phones never report track metadata, and the Bluetooth volume control itself only exists in ALSA once Bluetooth has actually played — so a knob that routed itself by guesswork would sometimes move the wrong path silently. Showing both levels and letting you pick is honest about it. When Bluetooth has no volume control yet, its row shows `--` and pressing skips over it.

While the overlay is up, press switches rows instead of pausing. Play/pause is available the moment it hides.

#### Next and previous track

The overlay has a third row, **TRACK**, showing your position in the queue (`14/550`). Press round to it and rotate: forward skips ahead, back skips back, and a fast spin moves that many tracks at once rather than firing a skip per click.

It behaves differently from the two volume rows in one deliberate way — **it doesn't stick.** When the overlay hides, the knob goes back to whichever volume row you last actually turned. If TRACK stuck the way the volume choice does, then reaching for volume later would skip tracks instead and you'd lose your place.

The row is skipped over when there's no queue to move through, and shows `SKIP IS MPD ONLY` when the source is Bluetooth: MPD's skip command has no effect on what a phone is playing. Skipping a Bluetooth track from the panel isn't supported yet.

#### Starting music from the display

Home controls whatever is already queued, so on a cold boot with an empty queue its play/pause has nothing to act on. The **Play / Music** screen is what starts playback without reaching for a phone or laptop. It lists, in order:

1. **Resume Queue** — appears only when tracks are already sitting in the queue and playback isn't running. One press starts them, leaving the queue exactly as it is. This is the entry to use when you built a queue in myMPD earlier and just want sound now; it's listed first precisely because it's the one action that destroys nothing.
2. **Shuffle All Music** — always present. One press clears the queue, adds your whole library, shuffles it, and plays. The "just play something" button.
3. **Your saved MPD playlists**, sorted alphabetically. One press clears the queue, loads that playlist, and plays it.

The two actions stay accent-coloured even when not highlighted, so they read as actions rather than as more playlist names.

Apart from Resume Queue, pressing an entry *replaces* the queue rather than appending to it. Either way the screen then jumps to Home so you can see that it worked.

The list is flat, with no artist/album/track drilldown — not for want of a back gesture any more, but because a list of a few hundred albums is miserable to scroll with a knob. Anything you want one-press access to should be saved as a playlist in myMPD; the display picks up new playlists the next time you open the screen. With no playlists saved, the screen shows Shuffle All Music on its own. To pick an individual track, use the **Playback Queue** screen.

If MPD can't be reached at all, the screen says so rather than offering buttons that would do nothing.

Related: when a queue is loaded but stopped, Home shows the current track with a **STOPPED — press to play** marker instead of "Nothing playing", so a short press there is also enough to get going.

#### Equalizer

The display applies presets; it does not edit them. Rotate through the 13 built-in presets, press to apply, and the screen confirms with the preset name and a picture of its actual 15-band curve. A dot marks the one currently applied. Building or tweaking a curve is the EQ web UI's job — see [Open the DSP interface](#open-the-dsp-interface-installed-by-default) — because dialling 15 bands with a single knob would be a worse version of a tool you already have.

Only the 13 built-in presets appear here. Presets you save in the web UI are not listed yet.

#### After a power cycle

MPD saves the queue and playback position to `/var/lib/mpd/state`, so queueing music in myMPD and then powering off does not lose it. What you see on the next boot:

| You powered off while… | On the next boot |
|---|---|
| Playing, paused, or stopped | Queue is intact and **paused** — press on Now Playing, or use **Resume Queue** on the Music screen |
| Queue was empty | Nothing to resume; use **Shuffle All Music** or a playlist |

The state file is flushed every 30 s (`state_file_interval`). A clean shutdown always flushes it, so use the Power menu or `sudo poweroff` when convenient — pulling the plug within 30 s of building a queue can still lose it, and then only Shuffle All or a saved playlist will get you going.

**The player never starts playing on its own at boot.** That's `restore_paused "yes"`, and it is deliberate. USB drives are mounted by udev *after* `mpd.service` starts, so a restored queue of USB tracks would have MPD trying to open files that aren't mounted yet and erroring through them. Restoring paused keeps the queue intact and waiting; by the time a human presses anything the drive is long since mounted. If all your music is on the SD card and you would rather it resume playback by itself, set `restore_paused "no"` and restart MPD — re-running `install.sh` regenerates `mpd.conf`, so re-apply it afterwards.

##### If your music is on a USB drive

USB drives are mounted inside MPD's library at `<music_directory>/usb/<device>`, so MPD indexes them with no config change. One consequence is worth knowing about: unmounting a drive refreshes MPD's database, which removes those songs — and MPD drops them from the play queue too, keeping only the track currently playing.

That is correct behaviour when you unplug a drive, but on shutdown it used to destroy the queue. `squarepi-usb-mount@.service` was ordered `After=mpd.service`, and systemd stops units in reverse — so the drive was unmounted while MPD was still running, MPD's `auto_update` inotify watch noticed, and it purged and pruned before saving its state file. The unit is now ordered `Before=mpd.service`, so MPD is stopped first and is already gone when the drive goes away.

If you see an empty queue after every reboot, that ordering is the first thing to check:

```bash
grep -E '^(Before|After)=' /etc/systemd/system/squarepi-usb-mount@.service
```

It must read `Before=mpd.service`. If it says `After=`, re-run the installer.

The VU Meter screen and all 19 VU styles only animate while MPD itself is playing — a Bluetooth, AirPlay, or Spotify stream doesn't pass through MPD's fifo, so the meters stay flat for those sources.

### Testing and troubleshooting

Test the parts by hand before trusting the service. Stop the service first, or it will still be holding the GPIO pins:

```bash
sudo systemctl stop squarepi-display
cd /usr/local/lib/squarepi-display
python3 test_tft_hello.py          # display only
python3 test_encoder_hello.py      # encoder only
python3 demo_cycle_screens.py      # every screen + real navigation, fake data
python3 demo_auto_cycle.py         # same screens on a timer, no encoder needed
```

**Exit these with Ctrl+C, not Ctrl+Z.** Ctrl+Z only suspends the process, and a suspended process keeps its GPIO claim, so the next script fails with `lgpio.error: 'GPIO busy'`. If that happens, find the suspended process (state `Tl`) and kill it:

```bash
ps aux | grep -i python
sudo kill -9 <PID>
```

Then restart the service when you're done: `sudo systemctl start squarepi-display`.

Service logs:

```bash
systemctl status squarepi-display
journalctl -u squarepi-display -n 30
```

If the display works but the VU meter never moves, check that MPD's fifo output is still in place — a later hand-edit of `mpd.conf` can lose it:

```bash
grep -A5 vu_meter /etc/mpd.conf
```

---

## Network defaults

| Interface | Address |
|---|---|
| myMPD | `http://squarepi.local:8080` · `https://squarepi.local:8443` |
| DSP UI | `http://squarepi.local:8081` |
| MPD | `squarepi.local:6600` |
| DLNA renderer | Appears as `SquarePi` in DLNA apps |

---

## Resume after a restart

If the power goes out while music is playing, SquarePi picks the same track back
up on the next boot — same position in the song, same volume, same queue. This is
on by default.

It applies to your own music library only. Bluetooth, AirPlay and Spotify are
controlled by the phone or laptop that sent the audio, so there is nothing on the
SquarePi end to resume — start those from the sending device as usual.

Playback resumes only if music was actually playing when the box went down. If you
paused it, or stopped it, or the queue was empty, it stays quiet and waits for you.

To turn it off, open the DSP UI and use **SYSTEM → Startup → Resume playback after
restart**. Over SSH:

```bash
echo 0 | sudo tee /var/lib/squarepi/resume_on_boot
```

A few things worth knowing:

- **Music on a USB drive still works.** The drive is mounted a moment after MPD
  starts, so resume waits for the file to actually be there before playing.
- **If the drive is missing**, nothing plays. The queue is still loaded and paused
  — plug the drive back in and press play.
- **If a phone is already connected over Bluetooth** when the Pi boots, resume
  stands down so it doesn't start on top of whatever you're about to play.
- **It gives up after about a minute.** If MPD or the drive never turn up in that
  window, the queue stays paused rather than playing something unexpected.

---

## Optional: Custom hostname and branding

```bash
sudo SQUAREPI_HOSTNAME=livingroom \
     SQUAREPI_BT_NAME="Living Room" \
     bash install.sh --all
```

| Variable | Effect |
|---|---|
| `SQUAREPI_HOSTNAME` | Sets Pi hostname (e.g. `livingroom.local`) |
| `SQUAREPI_BT_NAME` | Bluetooth device display name |
| `SQUAREPI_BRAND_NAME` | Name shown in installer banner |
| `SQUAREPI_AUTO_REBOOT` | Set `1` to reboot automatically after install |

---

## Troubleshooting

### Audio card not found (`aplay -l` shows no LouderRaspberry)

```bash
dmesg | grep -i tas58
lsmod | grep tas
cat /boot/firmware/config.txt | grep tas
```

Check that the overlay line is present:
```
dtoverlay=tas58xx,i2creg=0x2c
```

If not, re-run the installer or add the line manually and reboot.

### No sound from speakers

```bash
speaker-test -D plughw:LouderRaspberry,0 -t sine -f 1000 -c 2
```

If you hear the test tone, the hardware is working. Check MPD volume:
```bash
mpc volume 70
mpc play
```

### MPD not working

```bash
sudo systemctl status mpd
journalctl -u mpd -n 50
mpc status
```

MPD's `audio_output` device is normally `"squarepi_mix"` (the shared dmix/BT mixer set up during Bluetooth install), not a raw `plughw:` device. If ALSA card name differs from expected:
```bash
aplay -l    # note actual card name
sudo nano /etc/asound.conf
# update the slave.pcm "hw:LouderRaspberry,0" line inside pcm.squarepi_mix
sudo systemctl restart mpd
```
Only edit `/etc/mpd.conf`'s `device` line directly if Bluetooth failed to install and MPD is still pointed at `plughw:<card-name>,0`.

### myMPD not loading

```bash
sudo systemctl status mympd
curl -fs http://127.0.0.1:8080
```

Restart myMPD:
```bash
sudo systemctl restart mympd
```

### DSP UI not loading

```bash
systemctl status squarepi-eq
journalctl -u squarepi-eq -n 30
curl http://127.0.0.1:8081
```

### Bluetooth device not visible

```bash
rfkill list
sudo rfkill unblock bluetooth
sudo systemctl status bluetooth squarepi-bt-agent squarepi-bt-setup
```

If still not visible:
```bash
sudo systemctl restart bluetooth squarepi-bt-agent squarepi-bt-setup
```

### Bluetooth pairing fails (Authentication Failed)

Remove old pairing on both sides, then re-pair:
```bash
sudo bluetoothctl
devices
remove <MAC-address>
exit
sudo systemctl restart squarepi-bt-agent
```

Then pair fresh from the phone.

### Pi does not boot after install

Mount the SD card boot partition on another computer. Open `config.txt` and comment out the SquarePi overlay lines:

```conf
# dtparam=i2s=on
# dtoverlay=tas58xx,i2creg=...
```

A timestamped backup was created automatically: `config.txt.squarepi.bak.YYYYMMDDHHMMSS`. You can restore it if needed.

### squarepi.local not resolving

mDNS (`avahi-daemon`) must be running:
```bash
sudo systemctl status avahi-daemon
```

On Windows, install [Bonjour Print Services](https://support.apple.com/kb/DL999) or use the Pi's IP address instead.

On Linux, `avahi-daemon` must be running on the client machine too.

### USB drive not visible in MPD

Auto-mount drops the drive at `/var/lib/mpd/music/usb/<dev>`. Check what happened:
```bash
lsblk -f                                    # is the drive detected? which fs type?
systemctl status 'squarepi-usb-mount@*'     # did the mount service run?
findmnt /var/lib/mpd/music/usb/sda1         # is it mounted?
sudo -u mpd ls /var/lib/mpd/music/usb/sda1  # can MPD read the files?
```

Common causes:
- **Unsupported/blank filesystem** — only vfat, exFAT, NTFS, ext2/3/4 are auto-mounted; others are skipped.
- **MPD can't see the mount** — if `sudo -u mpd ls …` is empty but `findmnt` shows it mounted, MPD's service is isolating mounts; run `sudo mount --make-shared /var/lib/mpd/music/usb/sda1` (or restart mpd).
- **Library not scanned** — run `mpc update`.
- Whole-disk-formatted drives mount from `/dev/sda` (no partition); the service handles this automatically.

### Network share not working

Start with **Test connection** in the DSP interface — it reports the actual reason rather than leaving you guessing. If you need to look deeper:

```bash
findmnt /var/lib/mpd/music/nas            # is it mounted?
systemctl status var-lib-mpd-music-nas.mount
sudo -u mpd ls /var/lib/mpd/music/nas     # can MPD read it?
```

Common causes:
- **"The NAS rejected that username or password"** — some NAS boxes need the domain or workgroup prefixed, as `WORKGROUP\username`.
- **"No share by that name"** — use the share name as the NAS advertises it, not the folder path on the NAS's own disks. `Music`, not `/volume1/Music`, for SMB.
- **Mounted, but MPD sees nothing** — as with USB, run `sudo mount --make-shared /var/lib/mpd/music/nas` or restart MPD.
- **Nothing appears in myMPD** — the first scan of a large library takes time; `mpc update nas` restarts it.
- **The share came back but the music is gone from myMPD** — expected, and fixable in one command. While the NAS is unreachable MPD can't see those files, so it removes them from its database, which also clears them from the play queue. Once the NAS is back:

  ```bash
  mpc update nas
  ```

  Everything returns. Large libraries take a while to re-scan. This is the same behaviour as unplugging a USB drive mid-play, and it's the cost of MPD noticing new files automatically.
- **Very old NAS** — SquarePi asks for SMB 3.0. Devices that only speak SMB 1 won't connect, and shouldn't be exposed to your network anyway.

---

## Uninstall

```bash
curl -fsSL https://raw.githubusercontent.com/sijah/Square_PI/main/squarepi-installer/uninstall.sh | sudo bash
```

Removes: driver, boot overlay, MPD, myMPD, EQ server, DLNA renderer, Bluetooth services, Spotify, AirPlay, all SquarePi scripts and services.

Prompts before removing MPD music data and before rebooting. Music files are not deleted unless you explicitly confirm.

---

## Service reference

| Service | Purpose | Check with |
|---|---|---|
| `mpd` | Music Player Daemon | `systemctl status mpd` |
| `mympd` | Web UI | `systemctl status mympd` |
| `squarepi-eq` | EQ web server | `systemctl status squarepi-eq` |
| `squarepi-alsa-restore` | Restores EQ state on boot | `systemctl status squarepi-alsa-restore` |
| `squarepi-eq-init` | First-boot EQ flat init | `systemctl status squarepi-eq-init` |
| `squarepi-resume-mark` | Records pre-boot playback state | `systemctl status squarepi-resume-mark` |
| `squarepi-resume` | Resumes playback after a restart | `systemctl status squarepi-resume` |
| `var-lib-mpd-music-nas.automount` | Mounts the network share on first access | `systemctl status var-lib-mpd-music-nas.automount` |
| `bluetooth` | Bluetooth stack | `systemctl status bluetooth` |
| `bluealsa` | BT audio routing | `systemctl status bluealsa` |
| `squarepi-bt-agent` | Auto-pair agent | `systemctl status squarepi-bt-agent` |
| `squarepi-bt-setup` | Keeps adapter discoverable | `systemctl status squarepi-bt-setup` |
| `upmpdcli` | DLNA renderer | `systemctl status upmpdcli` |
| `raspotify` | Spotify Connect | `systemctl status raspotify` |
| `shairport-sync` | AirPlay | `systemctl status shairport-sync` |
| `avahi-daemon` | mDNS (`squarepi.local`) | `systemctl status avahi-daemon` |
