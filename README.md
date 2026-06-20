# SquarePi Installer

Installer script for a Raspberry Pi based **SquarePi TAS5805M Class-D amplifier HAT** music player.

Turns a fresh Raspberry Pi OS Lite image into a headless MPD/myMPD audio player using the TAS5805M I2S amplifier driver. Bluetooth A2DP receiver support is built in as an optional flag.

---

## Project scope

| Script | Purpose |
|---|---|
| `install.sh` | Installs TAS5805M driver, boot overlays, MPD/MPC, myMPD, and optionally Bluetooth A2DP |
| `uninstall.sh` | Removes services, driver, boot overlay, myMPD repository, and optional MPD data |

This project does not provide a custom web UI, music library manager, DSP tuning presets, or a desktop audio setup. It is intended for a headless Raspberry Pi OS Lite appliance.

---

## What `install.sh` installs

| Component | Purpose |
|---|---|
| `tas58xx` kernel driver | TAS5805M I2S/I2C amplifier driver |
| Raspberry Pi boot overlay | Enables I2S and loads the TAS5805M overlay |
| `mpd` | Music Player Daemon playback engine |
| `mpc` | MPD command-line client |
| `alsa-utils` | ALSA tools such as `aplay`, `alsamixer`, and `speaker-test` |
| `mympd` | Mobile-friendly web UI for MPD |
| `usbmount` | Best-effort optional USB auto-mount support |

With `--with-bt`, the following are also installed:

| Component | Purpose |
|---|---|
| `bluez` + `bluez-tools` | Bluetooth stack |
| `bluez-alsa-utils` | BlueALSA — routes BT audio to ALSA |
| `squarepi-bt-agent` | Auto-accept pairing agent (no PIN required) |

---

## Requirements

- Raspberry Pi Zero 2 W, 3, 4, or 5
- Raspberry Pi OS Lite, Bookworm/Debian 12 or Trixie/Debian 13
- SquarePi TAS5805M HAT connected
- Internet connection on the Pi
- SSH or local terminal access

Run as root with `sudo`.

---

## Quick install

SSH into the Pi and run:

```bash
# MPD + myMPD only
curl -fsSL https://raw.githubusercontent.com/YOUR_USERNAME/squarepi-installer/main/install.sh | sudo bash

# MPD + myMPD + Bluetooth A2DP
curl -fsSL https://raw.githubusercontent.com/YOUR_USERNAME/squarepi-installer/main/install.sh | sudo bash -s -- --with-bt
```

Or clone and run locally:

```bash
git clone https://github.com/YOUR_USERNAME/squarepi-installer
cd squarepi-installer

sudo bash install.sh              # MPD + myMPD only
sudo bash install.sh --with-bt   # MPD + myMPD + Bluetooth
```

The script does not reboot automatically by default. Reboot manually after it finishes:

```bash
sudo reboot
```

To opt into automatic reboot:

```bash
sudo SQUAREPI_AUTO_REBOOT=1 bash install.sh --with-bt
```

---

## Installer behaviour

The installer:

- Auto-detects the TAS5805M I2C address from `0x2c`, `0x2d`, `0x2e`, or `0x2f`
- Updates the apt package index but does not perform a full OS upgrade
- Backs up the Raspberry Pi boot config before editing it
- Refuses to edit boot config if `tas58xx.dtbo` was not installed
- Enables I2S in `/boot/firmware/config.txt` or `/boot/config.txt`
- Disables onboard Raspberry Pi audio to avoid I2S conflicts
- Disables `w1-gpio` if present because it can claim GPIO4
- Adds `dtoverlay=tas58xx,i2creg=<detected-address>` without `pdn_gpio`
- Builds and installs the TAS5805M kernel driver
- Configures MPD to run as user `mpd`
- Uses `/var/lib/mpd/music` as the default music directory
- Uses `plughw:LouderRaspberry,0` for MPD audio output
- Validates `/etc/mpd.conf` before starting MPD
- Triggers an initial MPD database scan with `mpc update`
- Checks that myMPD responds on port `8080`

With `--with-bt`, the installer additionally:

- Installs `bluez`, `bluez-tools`, and `bluez-alsa-utils`
- Configures BlueALSA for A2DP sink with SBC codec (compatible with `bluez-alsa-utils` v4 on Bookworm)
- Sets the Bluetooth device name to `SquarePi` via both `main.conf` and `bluetoothctl system-alias`
- Unblocks the BT adapter via `rfkill` and persists the unblock in `/etc/rc.local`
- Installs a systemd pairing agent that auto-accepts all pair requests with no PIN
- Enables the stock `bluealsa-aplay` service to route A2DP audio to the TAS5805M

---

## After reboot

Find the Pi IP address:

```bash
hostname -I
```

Verify the TAS5805M card is visible to ALSA:

```bash
aplay -l
```

You should see a card named `LouderRaspberry` or similar.

Test audio output:

```bash
speaker-test -D plughw:LouderRaspberry,0 -t sine -f 1000 -c 2
```

Open myMPD in a browser:

```
http://<your-pi-ip>:8080
```

MPD also listens on port `6600` for any MPD client.

---

## Adding music

The default MPD library path is `/var/lib/mpd/music`. Copy music there and rescan:

```bash
sudo cp -r /path/to/music/* /var/lib/mpd/music/
sudo chown -R mpd:audio /var/lib/mpd/music
mpc update
```

For a USB drive, mount it and either copy music into the library directory, or update `/etc/mpd.conf`:

```conf
music_directory    "/media/usb"
```

Then restart MPD and rescan:

```bash
sudo systemctl restart mpd
mpc update
```

Internet radio streams can be added from myMPD under Browse → Webradio.

---

## Hardware defaults

| Setting | Value |
|---|---|
| TAS5805M I2C address | Auto-detected, fallback `0x2c` |
| PDN GPIO | Not configured; SquarePi V1 pulls PDN high in hardware |
| MPD music directory | `/var/lib/mpd/music` |
| MPD audio device | `plughw:LouderRaspberry,0` |
| MPD service user | `mpd` |
| myMPD web port | `8080` |
| Bluetooth device name | `SquarePi` |
| Bluetooth codec | SBC |

To override the I2C address, edit the top of `install.sh` before running:

```bash
TAS_I2C_ADDR="0x2d"
```

Do not add `pdn_gpio` for SquarePi V1 — PDN is pulled HIGH via a 10K resistor on the board.

---

## DSP and EQ

The `tas58xx` driver exposes TAS5805M controls through ALSA:

```bash
alsamixer
```

Controls available depending on driver version: digital volume, analog gain, parametric EQ, mixer mode, modulation mode, bridge/PBTL mode.

Driver source: [sonocotta/tas5805m-driver-for-raspbian](https://github.com/sonocotta/tas5805m-driver-for-raspbian)

---

## Bluetooth A2DP

Bluetooth A2DP receiver is installed with the `--with-bt` flag. After reboot:

1. Open Bluetooth settings on your phone or tablet
2. Scan for devices — `SquarePi` will appear
3. Tap pair — no PIN required
4. Play audio — it routes directly to the TAS5805M

MPD and Bluetooth share the same TAS5805M output. Pause MPD before switching to Bluetooth playback.

### Bluetooth notes

- Codec is SBC. AAC is not compiled into `bluez-alsa-utils` on Raspberry Pi OS Bookworm and is not supported.
- The Bluetooth adapter is unblocked via `rfkill` on every boot through `/etc/rc.local`. If BT disappears after a reboot, check `rfkill list` and run `sudo rfkill unblock bluetooth` manually.
- To check Bluetooth status: `sudo bluetoothctl show`
- To check BlueALSA: `systemctl status bluealsa`
- To check the pairing agent: `systemctl status squarepi-bt-agent`

---

## Troubleshooting

### Pi does not boot after install

Power it off and mount the boot partition on another computer. Comment out the SquarePi changes in `config.txt`:

```conf
# dtparam=i2s=on
# dtoverlay=tas58xx,i2creg=...
```

The installer creates a timestamped backup next to the boot config file:

```
config.txt.squarepi.bak.YYYYMMDDHHMMSS
```

### Audio card not found

```bash
aplay -l
aplay -L | grep -i louder
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

Then restart MPD:

```bash
sudo systemctl restart mpd
```

### myMPD not reachable

```bash
sudo systemctl status mympd
curl -fs http://127.0.0.1:8080
```

### Bluetooth not visible / not connecting

```bash
rfkill list
sudo rfkill unblock bluetooth
sudo bluetoothctl
  power on
  discoverable on
  show
```

Check BlueALSA logs if audio does not play after pairing:

```bash
journalctl -xeu bluealsa.service --no-pager | tail -30
```

---

## Uninstall

```bash
sudo bash uninstall.sh
```

Removes myMPD, MPD/MPC, the TAS5805M kernel driver, boot overlay, and the myMPD apt repository. Prompts before removing MPD data under `/var/lib/mpd` and before rebooting. Music files are not deleted unless you confirm removal of MPD data.

---

## License

MIT
