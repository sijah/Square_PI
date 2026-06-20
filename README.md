# SquarePi Installer

Installer scripts for a Raspberry Pi based **SquarePi TAS5805M Class-D amplifier HAT** music player.

SquarePi turns a fresh Raspberry Pi OS Lite image into a headless MPD/myMPD audio player using the TAS5805M I2S amplifier driver. Optional Bluetooth A2DP receiver support is available with a command-line flag.

---

## Project scope

| Script | Purpose |
|---|---|
| `squarepi-installer/install.sh` | Installs TAS5805M driver, boot overlays, MPD/MPC, myMPD, and optionally Bluetooth A2DP |
| `squarepi-installer/uninstall.sh` | Removes services, driver, boot overlay, myMPD repository, and optional MPD data |

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
| `exfatprogs` | Best-effort exFAT USB flash drive support |

With `--with-bt`, the following are also installed:

| Component | Purpose |
|---|---|
| `bluez` + `bluez-tools` | Bluetooth stack |
| `bluez-alsa-utils` | BlueALSA, routes Bluetooth audio to ALSA |
| `squarepi-bt-agent` | Auto-accept pairing agent with no PIN |

---

## Requirements

- Raspberry Pi Zero 2 W, 3, 4, or 5
- Raspberry Pi OS Lite, Bookworm/Debian 12 or Trixie/Debian 13
- SquarePi TAS5805M HAT connected
- Internet connection on the Pi
- SSH or local terminal access

Run the installer as root with `sudo`.

---

## Quick install

SSH into the Pi and run one of these commands.

MPD + myMPD only:

```bash
curl -fsSL https://raw.githubusercontent.com/sijah/Square_PI/main/squarepi-installer/install.sh | sudo bash
```

MPD + myMPD + Bluetooth A2DP:

```bash
curl -fsSL https://raw.githubusercontent.com/sijah/Square_PI/main/squarepi-installer/install.sh | sudo bash -s -- --with-bt
```

Or clone and run locally:

```bash
git clone https://github.com/sijah/Square_PI.git
cd Square_PI/squarepi-installer

sudo bash install.sh            # MPD + myMPD only
sudo bash install.sh --with-bt  # MPD + myMPD + Bluetooth
```

The script does not reboot automatically by default. Reboot manually after it finishes:

```bash
sudo reboot
```

To opt into automatic reboot:

```bash
sudo SQUAREPI_AUTO_REBOOT=1 bash install.sh --with-bt
```

Optional branding settings:

```bash
sudo SQUAREPI_HOSTNAME=squarepi bash install.sh
sudo SQUAREPI_BT_NAME="Kitchen SquarePi" bash install.sh --with-bt
sudo SQUAREPI_BRAND_NAME="SquarePi" SQUAREPI_TAGLINE="DIY Raspberry Pi Hi-Fi Music Player" bash install.sh
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
- Creates `/mnt/usb-music` as a standard USB music mount point
- Attempts to install `exfatprogs` for exFAT USB flash drive support
- Can set a branded hostname when `SQUAREPI_HOSTNAME=<name>` is provided
- Writes install metadata to `/etc/squarepi-release`

With `--with-bt`, the installer additionally:

- Installs `bluez`, `bluez-tools`, and `bluez-alsa-utils`
- Configures BlueALSA for A2DP sink with SBC codec
- Sets the Bluetooth device name to `SquarePi`
- Unblocks the Bluetooth adapter via `rfkill` and persists the unblock in `/etc/rc.local`
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

```text
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

Internet radio streams can be added from myMPD under **Browse > Webradio**.

---

## Mount a USB flash drive

The installer creates `/mnt/usb-music` as a standard mount point. It does not auto-mount USB drives because Raspberry Pi OS Bookworm/Trixie systems do not always ship a reliable `usbmount` package. The most reliable setup is to mount the flash drive yourself and point MPD at it.

### 1. Plug in the drive and find it

```bash
lsblk -f
```

Look for a removable partition such as `/dev/sda1`. Note its filesystem type and UUID.

### 2. Create a mount point

```bash
sudo mkdir -p /mnt/usb-music
```

### 3. Mount it once for testing

For FAT32 or exFAT drives:

```bash
sudo apt-get install -y exfatprogs
sudo mount -o uid=mpd,gid=audio,umask=0022 /dev/sda1 /mnt/usb-music
```

For ext4 drives:

```bash
sudo mount /dev/sda1 /mnt/usb-music
sudo chown -R mpd:audio /mnt/usb-music
```

Check that the files are visible:

```bash
ls /mnt/usb-music
```

### 4. Make the mount persistent

Get the UUID:

```bash
sudo blkid /dev/sda1
```

Edit `/etc/fstab`:

```bash
sudo nano /etc/fstab
```

Add one line, replacing `YOUR-UUID-HERE` with the real UUID.

For FAT32:

```fstab
UUID=YOUR-UUID-HERE /mnt/usb-music vfat defaults,nofail,uid=mpd,gid=audio,umask=0022,x-systemd.automount 0 0
```

For exFAT:

```fstab
UUID=YOUR-UUID-HERE /mnt/usb-music exfat defaults,nofail,uid=mpd,gid=audio,umask=0022,x-systemd.automount 0 0
```

For ext4:

```fstab
UUID=YOUR-UUID-HERE /mnt/usb-music ext4 defaults,nofail,x-systemd.automount 0 2
```

Test the fstab entry:

```bash
sudo systemctl daemon-reload
sudo mount -a
findmnt /mnt/usb-music
```

### 5. Point MPD to the USB drive

Edit MPD config:

```bash
sudo nano /etc/mpd.conf
```

Set:

```conf
music_directory    "/mnt/usb-music"
```

Restart MPD and rescan:

```bash
sudo systemctl restart mpd
mpc update
```

Open myMPD and browse the library. If the library is empty, confirm that the `mpd` user can read the files:

```bash
sudo -u mpd ls /mnt/usb-music
```

To unmount the drive safely:

```bash
sudo systemctl stop mpd
sudo umount /mnt/usb-music
```

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
| Release metadata | `/etc/squarepi-release` |

To override the I2C address, edit the top of `install.sh` before running:

```bash
TAS_I2C_ADDR="0x2d"
```

Do not add `pdn_gpio` for SquarePi V1. PDN is pulled HIGH via a 10K resistor on the board.

### Branding options

These environment variables can be passed when running the installer:

| Variable | Purpose |
|---|---|
| `SQUAREPI_HOSTNAME` | Sets the Raspberry Pi hostname, for example `squarepi` |
| `SQUAREPI_BT_NAME` | Sets the Bluetooth device name when using `--with-bt` |
| `SQUAREPI_BRAND_NAME` | Changes the name shown in installer banners and MPD output |
| `SQUAREPI_TAGLINE` | Changes the tagline shown in the installer banner |
| `SQUAREPI_PROJECT_URL` | Changes the docs URL printed in the final summary |
| `SQUAREPI_SUPPORT_URL` | Changes the support/issues URL printed in the final summary |

Example:

```bash
sudo SQUAREPI_HOSTNAME=squarepi SQUAREPI_BT_NAME="Kitchen SquarePi" bash install.sh --with-bt
```

After install, metadata can be viewed with:

```bash
cat /etc/squarepi-release
```

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

1. Open Bluetooth settings on your phone or tablet.
2. Scan for devices. `SquarePi` will appear.
3. Tap pair. No PIN is required.
4. Play audio. It routes directly to the TAS5805M.

MPD and Bluetooth share the same TAS5805M output. Pause MPD before switching to Bluetooth playback.

### Bluetooth notes

- Codec is SBC. AAC is not compiled into `bluez-alsa-utils` on Raspberry Pi OS Bookworm and is not supported.
- The Bluetooth adapter is unblocked via `rfkill` on every boot through `/etc/rc.local`. If Bluetooth disappears after a reboot, check `rfkill list` and run `sudo rfkill unblock bluetooth` manually.
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

```text
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

### USB drive not visible in MPD

```bash
lsblk -f
findmnt /mnt/usb-music
sudo -u mpd ls /mnt/usb-music
journalctl -u mpd -n 50
```

Common fixes:

- Use the partition path, for example `/dev/sda1`, not the disk path `/dev/sda`.
- Use the UUID in `/etc/fstab` so the drive still mounts after reboot.
- For FAT32/exFAT, include `uid=mpd,gid=audio,umask=0022` in the fstab options.
- Run `mpc update` after adding or changing music files.

### myMPD not reachable

```bash
sudo systemctl status mympd
curl -fs http://127.0.0.1:8080
```

### Bluetooth not visible or not connecting

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

From the cloned repository:

```bash
cd Square_PI/squarepi-installer
sudo bash uninstall.sh
```

Or run directly from GitHub:

```bash
curl -fsSL https://raw.githubusercontent.com/sijah/Square_PI/main/squarepi-installer/uninstall.sh | sudo bash
```

The uninstaller removes myMPD, MPD/MPC, the TAS5805M kernel driver, boot overlay, and the myMPD apt repository. It prompts before removing MPD data under `/var/lib/mpd` and before rebooting. Music files are not deleted unless you confirm removal of MPD data.

---

## License

MIT
