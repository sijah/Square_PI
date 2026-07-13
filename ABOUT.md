# SquarePi — About This Project

*This document is for journalists, bloggers, reviewers, and anyone who wants to write about or feature SquarePi.*

---

SquarePi is an open-source Raspberry Pi HAT that turns any Pi into a 2×30W hi-fi wireless speaker system — playable from Bluetooth, Spotify, AirPlay, DLNA, USB, and internet radio, all controlled from a browser with no app install.

> *From square wave to every corner.*

---

## What It Is

SquarePi is a custom PCB — designed from scratch in KiCad — that plugs onto a Raspberry Pi's 40-pin GPIO header and turns it into a complete headless hi-fi music player.

The board is built around the Texas Instruments TAS5805M: a Class-D amplifier with a full hardware DSP built in. That chip alone handles 2×30W of output power plus 15-band parametric EQ, DRC, and gain control — all over I²C, zero extra hardware.

The software side is a one-command installer that configures everything automatically: audio driver, music player, web UI, Bluetooth, DLNA, Spotify Connect, AirPlay, and a visual EQ interface. After one reboot it's reachable at `squarepi.local` from any device on the same network. No IP address. No app install. No account.

---

## The SquarePi Audio Engine™

Every audio source — Bluetooth audio from a phone, a 44.1kHz FLAC file from a USB stick, a 320kbps Spotify stream — passes through four automatic processing stages before it reaches the speakers.

### SquarePi Upscaler™
All incoming audio is automatically upscaled to **48kHz / 24-bit**. No user configuration required. The Raspberry Pi hardware clock runs approximately 10× more accurately at 48kHz than at 44.1kHz, making this the optimal operating point for the Pi's audio clock hardware.

### SquarePi Resampler™
Rate conversion uses **SoXR** — a polyphase resampling library used in professional mastering tools. 44.1kHz material resamples to 48kHz via a 160:147 integer ratio at "very high" quality.

### SquarePi Mixer™
Multiple simultaneous sources — Bluetooth from a phone and DLNA from a laptop at the same time — share the output via ALSA dmix at 48kHz / S32_LE. No source pauses another.

### SquarePi EQ™
15-band parametric EQ running inside the TAS5805M chip over I²C. The Pi CPU handles no audio processing for equalization. 13 built-in presets, full manual control via browser, settings saved across power cycles. The browser interface adds six colour themes, a draggable response curve, a now-playing strip, A/B curve comparison, live fault monitoring, and a Power menu (Restart / Shut down, also available as myMPD Scripts tiles).

---

## Key Specifications

| Parameter | Value |
|---|---|
| Output power | 2×30W stereo Class-D (4Ω at 24V) |
| Audio pipeline | 48kHz / 24-bit, automatic on all sources |
| Resampling | SoXR polyphase, "very high" quality |
| EQ | 15-band hardware DSP in TAS5805M, ±15 dB per band |
| THD+N | ≤ 0.03% at 1W, 1kHz |
| SNR | up to 107 dB (A-weighted, 24V / 8Ω) |
| Dynamic range | up to 106 dB (A-weighted, 24V / 8Ω) |
| Crosstalk | −100 dB at 1kHz |
| Board | 65×61mm, 2-layer, standard RPi 40-pin HAT |
| Power input | 12–24V DC, barrel jack (powers Pi too — no separate Pi power supply needed) |
| Parts cost | Under $30 |
| Design | KiCad |

---

## Supported Protocols

| Protocol | Notes |
|---|---|
| Bluetooth A2DP | Auto-pair, no PIN, always discoverable, SBC codec |
| DLNA / UPnP | Windows Media Player, Kodi, VLC, BubbleUPnP, any DLNA app |
| Spotify Connect | Native Spotify app control, 320kbps, Premium required |
| AirPlay | iPhone, iPad, Mac, no Apple account needed |
| USB Drive | Mount and scan with `mpc update`, FAT32/exFAT/ext4 |
| Internet Radio | Built-in via MPD, add streams in myMPD |
| MPD clients | Any MPD-compatible app, auto-discovered via Zeroconf |

---

## EQ Presets (13)

Flat · Bass Boost · Treble · Vocal · Night Mode · Late Night · Rock · Pop · Jazz · Classical · Club · Hip-Hop · Acoustic

All presets available in myMPD Scripts (tap to apply) and in the visual DSP interface. Custom presets: dial in any curve and save it.

---

## Control Interfaces

| Interface | URL | Notes |
|---|---|---|
| myMPD web UI | `http://squarepi.local:8080` | Mobile-optimised, always installed |
| SquarePi EQ™ DSP | `http://squarepi.local:8081` | Visual 15-band EQ, installed by default |
| MPD | `squarepi.local:6600` | For dedicated music player apps |
| DLNA renderer | Appears in DLNA apps as `SquarePi` | Optional (`--with-dlna`) |

Sleep timer: 30 / 60 / 90 min + cancel — one tap in myMPD Scripts, no extra install.

---

## Setup

```bash
curl -fsSL https://raw.githubusercontent.com/sijah/Square_PI/main/squarepi-installer/install.sh | sudo bash
```

The installer:
- Auto-detects the TAS5805M I²C address on buses 1 and 2 (0x2c–0x2f)
- Configures the audio driver, I2S overlay, and boot config
- Installs MPD, myMPD, ALSA utilities
- Configures 48kHz/24-bit audio pipeline with SoXR resampling
- Installs all 13 EQ presets and sleep timer scripts
- Sets up Bluetooth and the visual DSP UI by default; adds DLNA, Spotify Connect, AirPlay on request
- Sets hostname to `squarepi`, enables mDNS
- Starts all services and verifies they are running
- A reboot is required to load the audio driver; Bluetooth and the EQ web UI are core features and always installed

---

## Why It Exists

Commercial wireless speakers cost $150–$500, require cloud accounts, collect usage data, and push firmware updates that change or remove features. SquarePi costs under $30 in parts, runs entirely locally, collects nothing, and does exactly what it does forever — because you own the code.

It started as a personal project: a compact, good-sounding amp board for a Raspberry Pi Zero 2W that I could leave running in a room with no screen, no keyboard, and no ongoing attention. The design became a full system with a web UI and multi-protocol support, so it got open-sourced.

---

## Compatibility

| Pi Model | Status |
|---|---|
| Pi Zero 2W | Primary target — tested, recommended |
| Pi 3B+ | Tested |
| Pi 4B | Tested |
| Pi 5 | Not yet supported — installer detects Pi 5 and refuses to install |

Requires Raspberry Pi OS Lite — Bookworm (Debian 12) or Trixie (Debian 13).

---

## SquarePi vs Commercial Alternatives

| | **SquarePi** | Sonos Era 100 | Amazon Echo Studio |
|---|---|---|---|
| Price | **< $30 parts** | $249 | $199 |
| Cloud required | **Never** | Always | Always |
| Account required | **None** | Sonos account | Amazon account |
| Data collection | **None** | Yes | Yes |
| Subscription | **None** | Some features | Some features |
| Protocols | **7** (BT/DLNA/USB/Radio/MPD play concurrently; Spotify & AirPlay pause MPD while active) | Limited | Limited |
| EQ | **15-band hardware DSP** | 3-band app sliders | 3-band app sliders |
| 48kHz/24-bit upscaling | **SquarePi Upscaler™** | No | No |
| Open source | **Fully (GPLv3)** | No | No |
| Hackable / forkable | **Yes** | No | No |
| Setup | **One command** | App + account | App + account |

---

## Who It's For

- **Makers and hobbyists** who want a serious audio project with real specs
- **Non-technical families** who want wireless music without cloud lock-in
- **DIY audio community** — open hardware, open software, real datasheets
- **Privacy-conscious users** — no cloud, no account, no data collection, ever
- **Anyone who wants music they own and control** — on hardware they built

---

## Repository

**GitHub:** [github.com/sijah/Square_PI](https://github.com/sijah/Square_PI)

```
squarepi-installer/
  install.sh         — main installer (bash, self-contained)
  update.sh          — in-place updater (preserves user settings)
  uninstall.sh       — clean uninstaller
  eq-server.py       — DSP web UI server (Python stdlib, port 8081)
docs/
  audio-engine.md    — deep dive on SquarePi Audio Engine™
  supported-protocols.md
  setup.md
README.md
ABOUT.md             — this file
```

Hardware design files (Gerbers, BOM, KiCad project): [Releases](https://github.com/sijah/Square_PI/releases)

---

## License

GPL v3. Use it, fork it, build on it — modified versions you distribute must stay open under GPL v3.

---

*From square wave to every corner.* — [Sijah AK](https://github.com/sijah)
