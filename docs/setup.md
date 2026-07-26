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
| `--all` | Everything (+ DLNA, Spotify, AirPlay) |

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

Use the **IP address, not a `.local` name**. Names can't be looked up early enough when the Pi reconnects to the share on its own after a restart, so the form rejects them. If you don't know the IP, your router's device list will show it.

A few things worth knowing:

- The share is mounted only when something reads it, so a NAS that's asleep or switched off never holds up startup — it simply reconnects next time it's needed.
- Large libraries take a while to scan the first time. Playback works as tracks appear.
- **Remove** unmounts the share and forgets the settings. Nothing on the NAS is touched.
- Your own `/etc/fstab` entries are left alone. SquarePi writes its own mount unit, so a manual setup you already have keeps working.
- The SMB password is stored on the Pi in a root-only file, which is what any unattended mount requires. Anyone on your network can reach the DSP interface, so give the speaker an account with read-only access to the music rather than an administrator one.

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
