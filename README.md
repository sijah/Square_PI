# SquarePi

SquarePi is an open-source Raspberry Pi audio streamer with a built-in 2×30W DSP amplifier. One installer turns any Pi into a headless network player — no config files, no IP addresses to remember.

**Stream from:** Bluetooth · Spotify Connect · AirPlay · DLNA · MPD  
**Control with:** 15-band EQ web interface · EQ presets · Sleep timer · Real-time fault monitor

*From square wave to every corner.* — Sijah AK

![SquarePi v1.0 wiring diagram](docs/images/squarepi-v1-wiring-diagram.png)

---

## Hardware

SquarePi hardware revision: **v1.0**

A compact Class-D amplifier HAT for Raspberry Pi, built around the Texas Instruments TAS5805M DSP amplifier chip.

### Specifications

- **Output power:** 2×13W into 4Ω at 12V · 2×23W into 8Ω at 24V · 2×30W into 4Ω at 24V
- **Audio input:** I2S digital from Raspberry Pi GPIO
- **DSP control:** I2C — EQ, DRC, crossover, gain, all programmable
- **Supply:** 12–24V DC, single barrel jack input
- **Form factor:** Standard Raspberry Pi HAT, 40-pin GPIO passthrough
- **Output:** Screw terminal speaker connectors
- **Extras:** IR receiver footprint, status LEDs, HAT EEPROM

### Raspberry Pi compatibility

Raspberry Pi 5 · 4B · 3B+ · 3B · Zero 2 W · Zero W

### Power wiring

| Supply voltage | Min current | Output |
|---|---|---|
| 12V | 3A | ~13W/ch into 4Ω |
| 19V | 3A | ~20W/ch into 8Ω |
| 24V | 3A | ~23W/ch into 8Ω |

### Speaker terminals

| Terminal | Connection |
|---|---|
| `LP` | Left speaker + |
| `LN` | Left speaker − |
| `RN` | Right speaker − |
| `RP` | Right speaker + |

> Check polarity before powering on. Use passive 4–8Ω speakers only. Never connect speakers while powered.

### Thermal guidance

SquarePi is designed for heatsink-less operation. For best long-term reliability:

- Use **12V with 8Ω speakers** for cool, continuous operation
- Avoid sustained high-volume playback with 4Ω speakers above 12V
- The TAS5805M includes automatic thermal foldback — it reduces output power at high temperature and recovers automatically

| Parameter | Recommended |
|---|---|
| Supply | 12V DC |
| Speakers | 8Ω preferred, 4Ω supported |
| Continuous power | 6–7W per channel |
| Ambient | ≤35°C for sustained loud playback |

---

## Requirements

- Raspberry Pi (Zero 2 W, 3, 4, or 5)
- Raspberry Pi OS Lite — Bookworm (Debian 12) or Trixie (Debian 13)
- SquarePi HAT connected
- Internet connection on the Pi
- SSH or local terminal access
- Run as root with `sudo`

---

## Quick install

SSH into your Pi and choose the combination that fits.

### Base install — MPD + myMPD

Music player with web UI, mDNS discovery, 13 EQ presets, and sleep timer via myMPD Scripts.

```bash
curl -fsSL https://raw.githubusercontent.com/sijah/Square_PI/main/squarepi-installer/install.sh | sudo bash
```

### With Bluetooth A2DP

Adds wireless audio streaming from any phone or tablet.

```bash
curl -fsSL https://raw.githubusercontent.com/sijah/Square_PI/main/squarepi-installer/install.sh | sudo bash -s -- --with-bt
```

### With Advanced DSP web interface

Adds a full-page DSP control panel at `http://squarepi.local:8081` — 15-band EQ, gain, balance, mixer, and real-time fault monitoring.

```bash
curl -fsSL https://raw.githubusercontent.com/sijah/Square_PI/main/squarepi-installer/install.sh | sudo bash -s -- --with-eq
```

### With Spotify Connect

Stream directly from the Spotify app — no phone Bluetooth needed.

```bash
curl -fsSL https://raw.githubusercontent.com/sijah/Square_PI/main/squarepi-installer/install.sh | sudo bash -s -- --with-spotify
```

### With AirPlay

Receive audio from any Apple device or AirPlay-capable app.

```bash
curl -fsSL https://raw.githubusercontent.com/sijah/Square_PI/main/squarepi-installer/install.sh | sudo bash -s -- --with-airplay
```

### With DLNA renderer

Adds a UPnP/DLNA renderer — stream from any DLNA-capable app or device on the network.

```bash
curl -fsSL https://raw.githubusercontent.com/sijah/Square_PI/main/squarepi-installer/install.sh | sudo bash -s -- --with-dlna
```

### Everything together

```bash
curl -fsSL https://raw.githubusercontent.com/sijah/Square_PI/main/squarepi-installer/install.sh | sudo bash -s -- --all
```

### Or clone and run locally

```bash
git clone https://github.com/sijah/Square_PI.git
cd Square_PI/squarepi-installer

sudo bash install.sh                                             # MPD + myMPD only
sudo bash install.sh --with-bt                                   # + Bluetooth A2DP
sudo bash install.sh --with-spotify                              # + Spotify Connect
sudo bash install.sh --with-airplay                              # + AirPlay
sudo bash install.sh --with-eq                                   # + Advanced DSP UI
sudo bash install.sh --with-dlna                                 # + DLNA/UPnP renderer
sudo bash install.sh --with-bt --with-spotify --with-airplay     # all streaming sources
sudo bash install.sh --all                                       # everything
```

Reboot after the installer finishes:

```bash
sudo reboot
```

To opt into automatic reboot:

```bash
sudo SQUAREPI_AUTO_REBOOT=1 bash install.sh --with-bt --with-eq
```

---

## After reboot

Verify the audio card is loaded:

```bash
aplay -l
```

You should see a card named `LouderRaspberry`. If it is missing, check `dmesg | grep -i tas58`.

Test audio output:

```bash
speaker-test -D plughw:LouderRaspberry,0 -t sine -f 1000 -c 2
```

Open myMPD:

```
http://squarepi.local:8080
```

Open the DSP interface (if installed with `--with-eq`):

```
http://squarepi.local:8081
```

> **First boot defaults:** MPD starts at **25% volume**. EQ is initialised to **flat** (all bands 0 dB). Adjust volume in myMPD and use the DSP UI or myMPD Scripts to apply an EQ preset.

---

## What gets installed

### Always installed

| Component | Purpose |
|---|---|
| `tas58xx` kernel driver | SquarePi I2S/I2C amplifier driver |
| Boot overlay | Enables I2S, loads the SquarePi audio overlay |
| `mpd` | Music Player Daemon |
| `mpc` | MPD command-line client |
| `alsa-utils` | `aplay`, `alsamixer`, `speaker-test` |
| `mympd` | Mobile-friendly web UI for MPD |
| `avahi-daemon` | mDNS — makes `squarepi.local` work on any network |
| `exfatprogs` | exFAT USB flash drive support |
| EQ preset Lua scripts | 13 one-tap presets in myMPD under Scripts |
| Sleep timer Lua scripts | Sleep 30 / 60 / 90 min + Cancel in myMPD under Scripts |
| `squarepi-eq-init.service` | Sets EQ to flat on first boot, then disables itself |

### With `--with-bt`

| Component | Purpose |
|---|---|
| `bluez` + `bluez-tools` | Bluetooth stack |
| `bluez-alsa-utils` | BlueALSA, routes Bluetooth audio to ALSA |
| `squarepi-bt-agent` | Auto-accept pairing, no PIN required |
| `squarepi-bt-monitor` | Pauses MPD automatically when a BT device connects |

### With `--with-spotify`

| Component | Purpose |
|---|---|
| `raspotify` (librespot) | Spotify Connect receiver, streams from Spotify app |
| `squarepi-spotify-event.sh` | Pauses MPD when Spotify starts; updates source indicator |

### With `--with-airplay`

| Component | Purpose |
|---|---|
| `shairport-sync` | AirPlay receiver, streams from Apple devices and apps |
| `squarepi-airplay-event.sh` | Pauses MPD when AirPlay starts; updates source indicator |

### With `--with-eq`

| Component | Purpose |
|---|---|
| `squarepi-eq-server.py` | DSP web UI served on port 8081 |
| `squarepi-eq.service` | Systemd unit, starts after sound target |
| `squarepi-alsa-restore.service` | Restores saved EQ state at every boot |

### With `--with-dlna`

| Component | Purpose |
|---|---|
| `upmpdcli` | UPnP/DLNA renderer, bridges MPD to DLNA |

---

## Network access

After reboot SquarePi is reachable by hostname — no IP address needed.

| Interface | Address |
|---|---|
| myMPD web UI | `http://squarepi.local:8080` |
| Advanced DSP UI | `http://squarepi.local:8081` *(if `--with-eq`)* |
| MPD (music apps) | `squarepi.local:6600` |
| DLNA renderer | Appears as `SquarePi` in DLNA/UPnP apps *(if `--with-dlna`)* |
| Spotify Connect | Appears as `SquarePi` in Spotify device list *(if `--with-spotify`)* |
| AirPlay | Appears as `SquarePi` in AirPlay device list *(if `--with-airplay`)* |

MPD advertises itself via Zeroconf (`_mpd._tcp`). Apps like [M.A.L.P](https://f-droid.org/packages/org.gateshipone.malp/), MPDroid, and Cantata auto-discover SquarePi — no manual server entry needed.

Set a custom hostname during install:

```bash
sudo SQUAREPI_HOSTNAME=squarepi bash install.sh
```

---

## DSP and EQ

SquarePi uses the TAS5805M onboard DSP — 15 fully programmable biquad EQ bands, 3-band DRC, automatic gain limiting, and thermal foldback. All controlled over I²C with no external DSP chip.

### Option 1 — EQ presets in myMPD (everyone)

All 13 presets are installed for everyone — no extra flag needed. Find them in myMPD under **Scripts**:

| Preset | Character |
|---|---|
| EQ Flat | Neutral reference |
| EQ Bass Boost | Warm bass emphasis |
| EQ Treble | Bright, airy detail |
| EQ Vocal | Mid-forward, clear voices |
| EQ Night Mode | Gentle, low-fatigue listening |
| EQ Late Night | Boosted bass and air, low mids |
| EQ Rock | Punchy low-end, scooped mids |
| EQ Pop | Clear vocals, sparkly highs |
| EQ Jazz | Warm, slightly rolled-off |
| EQ Classical | Flat with gentle treble lift |
| EQ Club | Heavy bass, extended highs |
| EQ Hip-Hop | Deep sub-bass, forward mids |
| EQ Acoustic | Natural room character |

### Option 2 — Advanced DSP web interface (`--with-eq`)

Install with `--with-eq` and open `http://squarepi.local:8081` for full real-time DSP control.

![SquarePi DSP Control Interface](docs/images/EQ_UI.png)

#### GAIN & BALANCE

- **Analog Gain** — hardware output level trim (0 to −15.5 dB in 0.5 dB steps)
- **Balance** — continuous L/R pan, centre to ±100% per channel

#### EQUALIZER — 15 Band

- **ON / OFF** — enable or bypass the EQ (bypass passes audio flat through the DSP)
- **13 presets** — Flat · Bass · Treble · Vocal · Night · Late Night · Rock · Pop · Jazz · Classical · Club · Hip-Hop · Acoustic
- **Custom preset** — dial in your own curve, name it, and save it for later
- **Frequency response graph** — live smooth curve with dB grid, frequency labels, and colour-coded fill (amber = boost, blue = cut)
- **15 fader sliders** — 20 Hz to 16 kHz, ±15 dB per band, real-time DSP update on every move

| Band | Freq | Band | Freq | Band | Freq |
|---|---|---|---|---|---|
| 1 | 20 Hz | 6 | 200 Hz | 11 | 2 kHz |
| 2 | 32 Hz | 7 | 315 Hz | 12 | 3.15 kHz |
| 3 | 50 Hz | 8 | 500 Hz | 13 | 5 kHz |
| 4 | 80 Hz | 9 | 800 Hz | 14 | 8 kHz |
| 5 | 125 Hz | 10 | 1.25 kHz | 15 | 16 kHz |

#### MIXER

| Mode | Description |
|---|---|
| Stereo | Normal L/R output |
| Mono | Both channels carry a mono mix |
| Left Only | Left channel signal on both outputs |
| Right Only | Right channel signal on both outputs |
| Custom | Full L/R crossfeed matrix with per-path dB control |

#### SYSTEM — real-time fault monitor

![SquarePi System Fault Monitor](docs/images/System.png)

Live readout direct from the TAS5805M chip registers:

- **Temperature** — Pi CPU thermal zone, live °C
- **PVDD** — power rail status (OK / fault)
- **Faults** — active fault count
- **Status** — Healthy / Warning / Fault
- **Sources** — live chips showing which sources are installed and which is active (MPD / BT / Spotify / AirPlay)

The fault monitor grid shows 13 individual hardware fault flags from the TAS5805M:

| Fault | Meaning |
|---|---|
| Left / Right Channel OC | Output overcurrent — speaker short or overload |
| Left / Right Channel DC | DC fault on output — amp protection triggered |
| PVDD Undervoltage | Supply voltage too low |
| PVDD Overvoltage | Supply voltage too high |
| Clock | I2S clock fault — audio interface issue |
| OTP CRC Error | Internal chip configuration error |
| Over Temperature Shutdown | Chip too hot, output disabled |
| Warning 112°C / 122°C / 134°C / 146°C | Thermal warning thresholds |

Green dot = clear. Red = active fault. All faults self-clear when the condition resolves.

#### Save to chip

The **Save to chip** button writes the current EQ and gain settings via `alsactl store` — settings survive a full power cycle. EQ state is also auto-saved when the service stops cleanly (reboot or shutdown).

### Option 3 — Terminal access (alsamixer)

The 15-band EQ is directly accessible from the terminal without the web UI:

```bash
alsamixer
```

![SquarePi AlsaMixer EQ](docs/images/squarepi-alsamixer-eq.png)

Press `F6` to select the SquarePi card (`LouderRaspberry`). Use arrow keys to navigate bands, up/down to adjust.

To save changes so they survive a reboot:

```bash
sudo alsactl store
```

---

## Bluetooth A2DP (`--with-bt`)

After reboot:

1. Open Bluetooth on your phone or tablet
2. Scan for devices — **SquarePi** will appear
3. Tap pair — no PIN required
4. Play audio — it routes directly to SquarePi

All sources share the same ALSA output. MPD is paused automatically whenever Bluetooth, Spotify, or AirPlay starts — resume it manually from myMPD when you're done with the other source.

**Notes:**
- Codec: SBC (AAC is not available in the Raspberry Pi OS `bluez-alsa-utils` package)
- Bluetooth adapter is unblocked via `rfkill` on every boot

### Troubleshooting Bluetooth

Check adapter status:

```bash
rfkill list
sudo rfkill unblock bluetooth
sudo bluetoothctl show
```

Check services:

```bash
systemctl status bluealsa
systemctl status squarepi-bt-agent
```

If pairing fails with `Authentication Failed`, remove the old pairing on both sides and pair again.

On the Pi:

```bash
sudo bluetoothctl
power on
pairable on
discoverable on
devices
remove <MAC-address>
scan on
```

Then restart and try again:

```bash
sudo systemctl restart bluetooth squarepi-bt-agent
sudo bluetoothctl pairable on
sudo bluetoothctl discoverable on
```

---

## Spotify Connect (`--with-spotify`)

After reboot, SquarePi appears as **`SquarePi`** in the Spotify app device list.

1. Open Spotify on any device on the same Wi-Fi network
2. Tap the **Devices** icon (bottom bar)
3. Select **SquarePi**
4. Play — audio streams directly to SquarePi over the network

MPD is paused automatically when Spotify starts playing. Resume from myMPD when done.

**Note:** Requires a Spotify Premium account. Spotify Connect is a Premium feature.

---

## AirPlay (`--with-airplay`)

After reboot, SquarePi appears as **`SquarePi`** in the AirPlay device list on any Apple device or AirPlay-compatible app.

1. Tap the AirPlay / cast icon in your app (Music, Spotify, YouTube, Podcasts, etc.)
2. Select **SquarePi**
3. Play — audio streams directly to SquarePi

MPD is paused automatically when an AirPlay session starts. Resume from myMPD when done.

**Works with:** iPhone, iPad, Mac, Apple TV, HomePod, and any third-party app with AirPlay support.

---

## DLNA renderer (`--with-dlna`)

After reboot, SquarePi appears as a **DLNA / UPnP renderer** named `SquarePi` in any compatible app — BubbleUPnP, Kodi, VLC, Windows Media Player, and most smart TV remotes.

Select SquarePi as the playback device in your app and start streaming.

---

## Sleep timer

Sleep timer scripts are installed for everyone — no extra flag needed. Find them in myMPD under **Scripts**:

| Script | Action |
|---|---|
| Sleep_30min | Stop playback after 30 minutes |
| Sleep_60min | Stop playback after 60 minutes |
| Sleep_90min | Stop playback after 90 minutes |
| Sleep_Cancel | Cancel a running sleep timer |

Setting a new timer automatically cancels the previous one.

---

## Adding music

Default MPD library path is `/var/lib/mpd/music`:

```bash
sudo cp -r /path/to/music/* /var/lib/mpd/music/
sudo chown -R mpd:audio /var/lib/mpd/music
mpc update
```

Internet radio streams can be added from myMPD under **Browse > Webradio**.

---

## Mount a USB flash drive

The installer creates `/mnt/usb-music` as a standard mount point. USB drives are not auto-mounted — Raspberry Pi OS Bookworm/Trixie does not ship a reliable `usbmount` package. The steps below are the most reliable approach.

### 1. Plug in the drive and find it

```bash
lsblk -f
```

Look for a removable partition such as `/dev/sda1`. Note its filesystem type and UUID.

### 2. Create the mount point

```bash
sudo mkdir -p /mnt/usb-music
```

(The installer does this automatically — skip if it already exists.)

### 3. Mount for testing

FAT32 or exFAT (`exfatprogs` is installed automatically by the SquarePi installer):

```bash
sudo mount -o uid=mpd,gid=audio,umask=0022 /dev/sda1 /mnt/usb-music
```

ext4:

```bash
sudo mount /dev/sda1 /mnt/usb-music
sudo chown -R mpd:audio /mnt/usb-music
```

Check that the files are visible:

```bash
ls /mnt/usb-music
```

### 4. Make it persistent — edit `/etc/fstab`

Get the UUID:

```bash
sudo blkid /dev/sda1
```

Open fstab:

```bash
sudo nano /etc/fstab
```

Add one line (replace `YOUR-UUID` with the real UUID):

```fstab
# FAT32
UUID=YOUR-UUID /mnt/usb-music vfat defaults,nofail,uid=mpd,gid=audio,umask=0022,x-systemd.automount 0 0

# exFAT
UUID=YOUR-UUID /mnt/usb-music exfat defaults,nofail,uid=mpd,gid=audio,umask=0022,x-systemd.automount 0 0

# ext4
UUID=YOUR-UUID /mnt/usb-music ext4 defaults,nofail,x-systemd.automount 0 2
```

Test the fstab entry:

```bash
sudo systemctl daemon-reload
sudo mount -a
findmnt /mnt/usb-music
```

### 5. Point MPD to the drive

Open the MPD config:

```bash
sudo nano /etc/mpd.conf
```

Set:

```conf
music_directory "/mnt/usb-music"
```

Restart MPD and rescan:

```bash
sudo systemctl restart mpd
mpc update
```

---

## Installer behaviour

The installer (v1.1.0):

- Auto-detects the TAS5805M I2C address (`0x2c`–`0x2f` on buses 1 and 2)
- Updates the apt package index but does not do a full OS upgrade
- Backs up the Pi boot config before editing it
- Enables I2S in `/boot/firmware/config.txt` or `/boot/config.txt`
- Disables onboard Pi audio to avoid I2S conflicts
- Disables `w1-gpio` if present (can conflict with GPIO4)
- Adds `dtoverlay=tas58xx,i2creg=<address>` without `pdn_gpio`
- Configures MPD to run as user `mpd` with software volume mixer
- Sets MPD audio output to `plughw:LouderRaspberry,0`
- Sets initial MPD volume to **25%** (safe default — adjust to taste in myMPD)
- Installs a first-boot service that initialises all EQ bands to **0 dB (flat)** on the first reboot, then disables itself
- Triggers an initial MPD database scan
- Checks that myMPD responds on port `8080`
- Writes install metadata to `/etc/squarepi-release`

Optional flags add their own steps:

| Flag | What it installs |
|---|---|
| `--with-bt` | Bluetooth A2DP stack, auto-pairing agent, MPD source manager |
| `--with-spotify` | raspotify (Spotify Connect), MPD pause hook |
| `--with-airplay` | shairport-sync (AirPlay), MPD pause hook |
| `--with-eq` | DSP web UI on port 8081, ALSA state restore service |
| `--with-dlna` | upmpdcli DLNA/UPnP renderer |

All flags can be combined freely.

---

## Hardware defaults

| Setting | Value |
|---|---|
| TAS5805M I2C address | Auto-detected, fallback `0x2c` |
| PDN GPIO | Not set — SquarePi v1 pulls PDN high in hardware |
| MPD music directory | `/var/lib/mpd/music` |
| MPD audio device | `plughw:LouderRaspberry,0` |
| MPD volume (initial) | 25% |
| MPD volume control | Software mixer |
| myMPD port | `8080` |
| DSP UI port | `8081` |
| Device name (BT / Spotify / AirPlay) | `SquarePi` |
| Bluetooth codec | SBC |
| Release metadata | `/etc/squarepi-release` |

### Branding options

| Variable | Purpose |
|---|---|
| `SQUAREPI_HOSTNAME` | Sets the Pi hostname |
| `SQUAREPI_BT_NAME` | Device name for Bluetooth, Spotify Connect, and AirPlay |
| `SQUAREPI_BRAND_NAME` | Name shown in banners |
| `SQUAREPI_TAGLINE` | Tagline in installer banner |
| `SQUAREPI_PROJECT_URL` | Docs URL in final summary |
| `SQUAREPI_SUPPORT_URL` | Support URL in final summary |

Example:

```bash
sudo SQUAREPI_HOSTNAME=squarepi SQUAREPI_BT_NAME="Living Room" bash install.sh --with-bt --with-eq
```

---

## Troubleshooting

### Pi does not boot after install

Mount the boot partition on another computer and comment out the SquarePi lines in `config.txt`:

```conf
# dtparam=i2s=on
# dtoverlay=tas58xx,i2creg=...
```

A timestamped backup is created automatically: `config.txt.squarepi.bak.YYYYMMDDHHMMSS`

### Audio card not found

```bash
aplay -l
dmesg | grep -i tas58
lsmod | grep tas
```

### MPD not working

```bash
sudo systemctl status mpd
journalctl -u mpd -n 50
mpc status
```

If the ALSA card name differs from `LouderRaspberry`, update `/etc/mpd.conf`:

```conf
device "plughw:<card-name>,0"
```

### DSP UI not loading

```bash
systemctl status squarepi-eq
journalctl -u squarepi-eq -n 30
curl http://127.0.0.1:8081
```

### USB drive not visible in MPD

```bash
lsblk -f
findmnt /mnt/usb-music
sudo -u mpd ls /mnt/usb-music
```

Common fixes: use `/dev/sda1` not `/dev/sda`, use UUID in fstab, include `uid=mpd,gid=audio` for FAT/exFAT, run `mpc update` after mounting.

### myMPD not reachable

```bash
sudo systemctl status mympd
curl -fs http://127.0.0.1:8080
```

### Bluetooth not visible

```bash
rfkill list
sudo rfkill unblock bluetooth
sudo systemctl restart bluetooth squarepi-bt-agent
sudo bluetoothctl pairable on
sudo bluetoothctl discoverable on
```

### Spotify Connect not visible in app

```bash
systemctl status raspotify
journalctl -u raspotify -n 30
```

Spotify Connect requires a **Premium** account and the Pi to be on the same network as the Spotify app.

### AirPlay not visible

```bash
systemctl status shairport-sync
journalctl -u shairport-sync -n 30
```

If the device name doesn't appear, restart the service:

```bash
sudo systemctl restart shairport-sync
```

---

## Uninstall

```bash
curl -fsSL https://raw.githubusercontent.com/sijah/Square_PI/main/squarepi-installer/uninstall.sh | sudo bash
```

Or from the cloned repo:

```bash
cd Square_PI/squarepi-installer
sudo bash uninstall.sh
```

Removes: SquarePi driver, boot overlay, MPD, myMPD, EQ server, Spotify Connect, AirPlay, DLNA renderer, and all SquarePi scripts and services. Prompts before removing MPD music data and before rebooting. Music files are not deleted unless you confirm.

---

## DSP technical specs

| Parameter | Value |
|---|---|
| THD+N | ≤ 0.03% at 1W, 1kHz |
| SNR | ≥ 107 dB (A-weighted) |
| Dynamic range | 106 dB (A-weighted) |
| Crosstalk | −100 dB at 1kHz |
| Idle noise | < 40 µVRMS |
| Parametric EQ | 15 bands per channel, full biquad |
| DRC | 3-band, 4th-order |
| Volume range | +24 dB to −103 dB, 0.5 dB steps |
| Sample rates | 32 / 44.1 / 48 / 88.2 / 96 kHz |
| Switching frequency | 384 / 480 / 576 / 768 kHz |

Driver: [sonocotta/tas5805m-driver-for-raspbian](https://github.com/sonocotta/tas5805m-driver-for-raspbian)

Hardware files (Gerbers, BOM, KiCad): [GitHub Releases](https://github.com/sijah/Square_PI/releases)

---

## License

MIT
