# SquarePi — Supported Protocols

SquarePi accepts audio from seven sources. All are upscaled, resampled, and equalized automatically. Multiple protocols can be active at the same time — ALSA dmix mixes them in software so nothing pauses anything else.

---

## Bluetooth A2DP (installed by default)

Wireless audio from any phone, tablet, or laptop. A core feature — always installed.

1. Open Bluetooth settings on your device
2. Scan — **SquarePi** appears in the list
3. Tap pair — no PIN, no confirmation on the Pi
4. Play audio

Notes:
- Codec: SBC (AAC is not available in the Raspberry Pi OS `bluez-alsa-utils` package)
- The adapter stays discoverable and pairable after every reboot — `squarepi-bt-setup.service` handles it
- Plays alongside other sources without pausing either side

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

Stream from any DLNA-compatible app on the same network.

Compatible apps: Windows Media Player, Kodi, VLC (Playback → Renderer → SquarePi-UPnP/AV), BubbleUPnP, or any UPnP/DLNA controller.

1. Open your DLNA app
2. Select **SquarePi** as the playback renderer
3. Browse and play

Notes:
- Implemented via `upmpdcli`, which bridges DLNA control to MPD
- Appears on the network automatically via avahi/mDNS
- protocolinfo is set to restrict advertised formats to MP3/FLAC/OGG/MP4 — without this, Windows Media Player serves raw L16 PCM (1.5 Mbps) instead of MP3, which causes WiFi jitter
- If avahi restarts, upmpdcli needs a restart too: `sudo systemctl restart upmpdcli`

**Known issue:** Some DLNA controllers (WMP, Kodi) push a track to the MPD queue but don't trigger play. If audio doesn't start, run `mpc play` on the Pi. This is a upmpdcli/OpenHome interaction issue, not yet fixed.

**Troubleshooting:**
```bash
systemctl status upmpdcli
journalctl -u upmpdcli -n 30
```

---

## Spotify Connect (`--with-spotify`)

SquarePi appears as a speaker inside the Spotify app — no extra app or configuration needed.

1. Open Spotify on your phone, tablet, or desktop
2. Tap the **Devices** icon at the bottom of the player
3. Select **SquarePi**

Notes:
- Requires Spotify Premium
- Implemented via `raspotify`, 320 kbps
- MPD pauses automatically when Spotify starts

**Troubleshooting:**
```bash
systemctl status raspotify
journalctl -u raspotify -n 30
```

If SquarePi does not appear in Spotify, check that raspotify is running and the Pi is on the same network as your Spotify device.

---

## AirPlay (`--with-airplay`)

Stream from iPhone, iPad, Mac, or any AirPlay-compatible app.

On iPhone or iPad: swipe down → tap AirPlay in Now Playing → select **SquarePi**.

On Mac: click the AirPlay icon in the menu bar → select **SquarePi**.

Notes:
- Implemented via `shairport-sync`
- No Apple account required
- Works with Apple Music, Spotify, VLC, and any other AirPlay app
- MPD pauses automatically when an AirPlay session starts

**Troubleshooting:**
```bash
systemctl status shairport-sync
journalctl -u shairport-sync -n 30
```

---

## USB Drive

**Just plug it in.** SquarePi auto-mounts the drive and it appears in MPD under `usb` — no SSH, no fstab, no config change. Unplug it to remove it.

- Works with **FAT32, exFAT, NTFS, and ext4** — any label, any size.
- Multiple partitions or drives each mount under their own folder (`usb/sda1`, `usb/sdb1`, …).
- The drive mounts *inside* MPD's library, so your built-in music stays visible too.
- `exfatprogs` and `ntfs-3g` are installed automatically so exFAT/NTFS drives mount cleanly.

After plugging in, the new music appears within a few seconds. To force a rescan: `mpc update`.

**How it works:** a udev rule triggers a small systemd service (`squarepi-usb-mount@<dev>`) that detects the filesystem, mounts it at `/var/lib/mpd/music/usb/<dev>` with MPD-readable permissions, and runs `mpc update`. Check it with `systemctl status 'squarepi-usb-mount@*'`.

---

### Advanced: manual / permanent mount

If you'd rather pin a specific drive yourself, mount it by UUID. Get the UUID and filesystem:
```bash
sudo blkid /dev/sda1        # shows UUID and TYPE
```

Add to `/etc/fstab` (replace `YOUR-UUID`), using the line for your filesystem — **the type must match**:
```fstab
# FAT32
UUID=YOUR-UUID /mnt/usb-music vfat    defaults,nofail,uid=mpd,gid=audio,umask=0022,x-systemd.automount 0 0
# exFAT
UUID=YOUR-UUID /mnt/usb-music exfat   defaults,nofail,uid=mpd,gid=audio,umask=0022,x-systemd.automount 0 0
# NTFS
UUID=YOUR-UUID /mnt/usb-music ntfs-3g defaults,nofail,uid=mpd,gid=audio,umask=0022,x-systemd.automount 0 0
# ext4
UUID=YOUR-UUID /mnt/usb-music ext4    defaults,nofail,x-systemd.automount 0 2
```

Apply, then point MPD at it (this **replaces** the built-in library):
```bash
sudo systemctl daemon-reload && sudo mount -a
sudo sed -i 's|^music_directory.*|music_directory "/mnt/usb-music"|' /etc/mpd.conf
sudo systemctl restart mpd && mpc update
```

---

## Internet Radio

MPD handles HTTP streams natively — no extra software needed.

In myMPD: Browse → Webradio → add a station URL or search the built-in directory.

Or directly:
```bash
mpc add http://some-stream-url/stream.mp3
mpc play
```

Any SHOUTcast or Icecast URL works. MPD is configured with a 2 MB HTTP input cache to buffer against WiFi jitter, and an 8 MB output buffer to prevent underruns on high-bitrate streams.

---

## MPD Clients

Any MPD-compatible app can connect to SquarePi directly. MPD advertises itself via Zeroconf (`_mpd._tcp`), so apps that support auto-discovery find it without any manual server entry.

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
