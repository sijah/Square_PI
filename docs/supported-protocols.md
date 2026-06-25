# SquarePi — Supported Protocols

SquarePi supports seven audio input protocols. All sources pass through the **SquarePi Audio Engine™** — upscaled to 48kHz/24-bit, resampled, mixed, and equalized automatically.

All protocols can be active simultaneously. The **SquarePi Mixer™** handles multi-source sharing with no quality loss and no mutual interruption.

---

## Bluetooth A2DP (`--with-bt`)

**What it is:** Wireless audio streaming from any Bluetooth device.

**How to use:**
1. Open Bluetooth settings on your phone or tablet
2. Scan for devices — **SquarePi** appears in the list
3. Tap pair — no PIN required, pairing is automatic
4. Play audio — it routes immediately to SquarePi

**Key facts:**
- Codec: SBC (standard; AAC not available in Raspberry Pi OS `bluez-alsa-utils`)
- Auto-accept pairing: no PIN, no confirmation required on the Pi
- Always discoverable: the adapter stays discoverable and pairable after every reboot via `squarepi-bt-setup.service`
- Simultaneous: Bluetooth and other sources play at the same time via SquarePi Mixer™

**Troubleshooting:**

Check adapter state:
```bash
rfkill list
sudo rfkill unblock bluetooth
sudo bluetoothctl show
```

Check services:
```bash
systemctl status bluealsa
systemctl status squarepi-bt-agent
systemctl status squarepi-bt-setup
```

If pairing fails with `Authentication Failed`, remove the old pairing on both sides:
```bash
sudo bluetoothctl
devices
remove <MAC-address>
scan on
```

Restart Bluetooth:
```bash
sudo systemctl restart bluetooth squarepi-bt-agent squarepi-bt-setup
```

---

## DLNA / UPnP (`--with-dlna`)

**What it is:** Stream from any DLNA-compatible device or app on the same network.

**Compatible apps and devices:**
- Windows Media Player (Windows 10/11)
- Kodi
- VLC (Playback → Renderer → SquarePi-UPnP/AV)
- BubbleUPnP (Android)
- Any UPnP/DLNA controller

**How to use:**
1. Open your DLNA app
2. Select **SquarePi** as the playback renderer
3. Browse and play — audio streams to SquarePi

**Key facts:**
- Implemented via `upmpdcli` — bridges DLNA control to MPD
- Advertised via avahi/mDNS — appears automatically on the network
- protocolinfo restricts advertised formats to MP3/FLAC/OGG/MP4, preventing raw L16 PCM delivery from Windows Media Player (which would cause WiFi jitter at 1.5 Mbps)
- If avahi restarts, restart upmpdcli: `sudo systemctl restart upmpdcli`

**Known limitation:** Some DLNA controllers (WMP, Kodi) push a track to the MPD queue but do not auto-trigger play. If audio does not start, run `mpc play` on the Pi. This is a upmpdcli/OpenHome interaction issue under investigation.

**Troubleshooting:**
```bash
systemctl status upmpdcli
journalctl -u upmpdcli -n 30
```

---

## Spotify Connect (`--with-spotify`)

**What it is:** SquarePi appears as a speaker inside the official Spotify app — control playback directly without any extra app.

**How to use:**
1. Open Spotify on your phone, tablet, or desktop
2. Tap the **Devices** icon (bottom of player)
3. Select **SquarePi**
4. Playback routes immediately to SquarePi

**Key facts:**
- Requires Spotify Premium
- Implemented via `raspotify`
- Bitrate: 320 kbps
- MPD automatically pauses when Spotify starts playing

**Troubleshooting:**
```bash
systemctl status raspotify
journalctl -u raspotify -n 30
```

If SquarePi does not appear in Spotify, check that raspotify is running and the Pi is on the same network as your Spotify device.

---

## AirPlay (`--with-airplay`)

**What it is:** Stream from any Apple device or AirPlay-compatible app.

**How to use:**

On iPhone or iPad:
1. Swipe down for Control Centre
2. Tap the AirPlay icon in the Now Playing widget
3. Select **SquarePi**

On Mac:
1. Click the AirPlay icon in the menu bar
2. Select **SquarePi**

**Key facts:**
- Implemented via `shairport-sync`
- No Apple account required
- Works with any AirPlay-compatible app (Apple Music, Spotify, VLC, Doppler, etc.)
- MPD automatically pauses when an AirPlay session starts

**Troubleshooting:**
```bash
systemctl status shairport-sync
journalctl -u shairport-sync -n 30
```

---

## USB Drive

**What it is:** Plug in a USB drive and MPD scans it automatically.

**Supported formats:** FAT32, exFAT, ext4 (exfatprogs installed automatically by the installer)

**How to use:**
1. Plug in the USB drive
2. Mount it (see below)
3. Point MPD at the mount point
4. Run `mpc update` to scan

**Quick mount (testing):**

```bash
lsblk -f          # find drive — usually /dev/sda1
sudo mkdir -p /mnt/usb-music
sudo mount -o uid=mpd,gid=audio,umask=0022 /dev/sda1 /mnt/usb-music
```

**Persistent mount (fstab):**

Get the UUID:
```bash
sudo blkid /dev/sda1
```

Add to `/etc/fstab` (replace `YOUR-UUID`):
```fstab
# FAT32 or exFAT
UUID=YOUR-UUID /mnt/usb-music vfat defaults,nofail,uid=mpd,gid=audio,umask=0022,x-systemd.automount 0 0

# ext4
UUID=YOUR-UUID /mnt/usb-music ext4 defaults,nofail,x-systemd.automount 0 2
```

Apply:
```bash
sudo systemctl daemon-reload
sudo mount -a
```

**Point MPD at the drive:**

```bash
sudo nano /etc/mpd.conf
# Set: music_directory "/mnt/usb-music"
sudo systemctl restart mpd
mpc update
```

---

## Internet Radio

**What it is:** Stream internet radio stations directly through MPD.

**How to use:**

In myMPD:
1. Browse → Webradio
2. Add a station URL or search the built-in directory
3. Play

**Direct MPD:**
```bash
mpc add http://some-stream-url/stream.mp3
mpc play
```

**Key facts:**
- No extra software needed — MPD handles HTTP streams natively
- 2 MB HTTP input cache buffers streams against WiFi jitter (`input_cache` in mpd.conf)
- 8 MB output buffer prevents underruns during high-quality streams (`audio_buffer_size`)
- Any SHOUTcast/Icecast stream URL works

---

## MPD Clients

**What it is:** Any MPD-compatible music player app can connect to SquarePi directly.

**Auto-discovery:** MPD advertises itself via Zeroconf (`_mpd._tcp`). Apps that support auto-discovery will find SquarePi without any manual server entry.

**Compatible apps:**

| App | Platform |
|---|---|
| [M.A.L.P](https://f-droid.org/packages/org.gateshipone.malp/) | Android |
| MPDroid | Android |
| Cantata | Linux / Windows |
| ncmpcpp | Terminal |
| mpc | Terminal (included in SquarePi install) |

**Manual connection:** `squarepi.local` · port `6600`

**mpc quick reference:**
```bash
mpc status          # show current state
mpc play            # start playback
mpc pause           # pause
mpc stop            # stop
mpc next            # next track
mpc prev            # previous track
mpc volume 70       # set volume to 70%
mpc update          # rescan music library
mpc ls              # list music directory
mpc add path/to/song.flac   # add to queue
mpc clear           # clear queue
```
