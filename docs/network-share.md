# SquarePi — Network Share (NAS) Guide

Play music straight off a NAS, or a shared folder on a computer, with no files copied to the Pi. Set up entirely in the browser — no SSH, no `/etc/fstab`.

Requires **v1.6.5 or later**. Check the version in the DSP interface footer, or:

```bash
grep VERSION /etc/squarepi-release
```

---

## Quick setup

1. Open the DSP interface: `http://squarepi.local:8081`
2. Click **NETWORK** in the sidebar (or scroll to the **NETWORK SHARE** card)
3. Fill in four fields:

| Field | What to enter | Example |
|---|---|---|
| **Type** | `SMB / Windows share` for a NAS, Windows, or macOS shared folder. `NFS` if your NAS offers it | SMB |
| **Server** | The **IP address** of the machine holding the music | `192.168.1.50` |
| **Folder** | The share name, exactly as the server advertises it | `Music` |
| **User** / **Password** | The share's credentials. Leave both empty for a public share. NFS needs neither | `music-reader` |

4. Press **Test connection**. It reports how many items it can see, or exactly what went wrong.
5. Press **Connect & save**.

The share appears in myMPD as **`nas`**, alongside your existing library. Large libraries take a while to scan — tracks appear as they're found.

> **Use the IP address, not a `.local` name.** mDNS names can't be resolved at the moment the share is remounted after a restart, so the form rejects them. Your router's device list will show the IP.

---

## Finding the details on your server

### Synology / QNAP / most NAS boxes

The share name is what appears in **Control Panel → Shared Folder** — typically `music`, `Music`, or `media`. Use that name alone, not the internal path like `/volume1/music`.

Create a dedicated user with **read-only** access to just the music folder rather than reusing an admin account. See [Security](#security) below.

### Windows

Right-click the folder → **Properties → Sharing → Advanced Sharing → Share this folder**. The **Share name** shown there is what goes in the Folder field.

Windows accounts tied to a Microsoft account can be awkward to authenticate against. If credentials are rejected, create a local account on the Windows machine for the speaker to use, or enable a guest/everyone share.

Find the IP with `ipconfig` in Command Prompt — the **IPv4 Address** on your active adapter.

### macOS

**System Settings → General → Sharing → File Sharing**, add the folder, and check the user under **Users & Groups** has at least read access. The share name is the folder's name.

### Another Raspberry Pi or a Linux box

Install Samba and add a share:

```bash
sudo apt install -y samba
```

```bash
sudo tee -a /etc/samba/smb.conf >/dev/null <<'EOF'

[Music]
   path = /home/pi/music
   browseable = yes
   read only = yes
   guest ok = no
EOF
```

Set the share password — this is a **separate** password database from the login account:

```bash
sudo smbpasswd -a pi
sudo systemctl restart smbd
hostname -I
```

---

## Troubleshooting

Always start with **Test connection**. It reports the real reason rather than leaving you to guess, and it changes nothing on the Pi.

| What you see | What it means | What to do |
|---|---|---|
| *The NAS rejected that username or password* | Credentials refused | Retype the password. Some NAS boxes need the domain or workgroup prefixed: `WORKGROUP\username` |
| *The server is reachable but has no share by that name* | Wrong folder name | Use the share name the server advertises (`Music`), not the path on its disks (`/volume1/Music`) |
| *No answer from the server* | Wrong IP, or the server is off | Confirm with `ping <ip>` from the Pi |
| *The server refused the connection* | File sharing is off, or a firewall is blocking it | Enable file sharing on the server; allow SMB (445) or NFS (2049) |
| *`.local` names can't be resolved…* | You entered a hostname | Use the IP address |
| *Support for this share type isn't installed* | `cifs-utils` / `nfs-common` missing | `sudo apt install cifs-utils nfs-common`, or re-run the SquarePi updater |
| *The server didn't answer in time* | Slow or unreachable server | Check the IP; try again once the NAS is fully awake |

### Connected, but nothing appears in myMPD

Check whether MPD itself can read the share:

```bash
sudo -u mpd ls /var/lib/mpd/music/nas
```

- **Files are listed** — the mount is fine, the library just hasn't been scanned. Run `mpc update nas` and wait; a large library takes minutes, not seconds.
- **Empty, but `findmnt /var/lib/mpd/music/nas` shows it mounted** — MPD's service is isolating mounts. Fix with:

  ```bash
  sudo mount --make-shared /var/lib/mpd/music/nas
  ```

### The share came back but the music is gone

Expected, and fixable in one command:

```bash
mpc update nas
```

While the NAS is unreachable MPD can't see those files, so it removes them from its database — which also clears them from the play queue. Once the NAS is back, a rescan restores everything.

This is the same behaviour as unplugging a USB drive mid-play. It's the cost of MPD noticing new files by itself, and it isn't specific to network shares.

### Playback stutters or drops out

Network audio depends on the link holding up. In rough order of likelihood:

- **Weak WiFi on the Pi.** Check signal strength in the DSP interface under **SYSTEM → Host Health**. A Pi Zero 2W tucked behind a metal enclosure is a common cause.
- **High-bitrate files.** A 24-bit FLAC needs roughly 20× the bandwidth of an MP3. Opus and MP3 are far more forgiving of a marginal link.
- **A NAS spinning up from sleep.** The first few seconds of the first track can stutter while the disks wake.

Wired Ethernet on either end removes most of these.

### Checking the mount directly

```bash
findmnt /var/lib/mpd/music/nas
systemctl status var-lib-mpd-music-nas.automount
systemctl status var-lib-mpd-music-nas.mount
```

The **automount** should be `active (running)`. The **mount** may show inactive until something reads the folder — that's correct, not a fault. `ls /var/lib/mpd/music/nas` triggers it.

---

## How it works

The DSP server writes two systemd units for `/var/lib/mpd/music/nas` — a `.mount` describing the share, and a `.automount` that triggers it — then runs `mpc update nas`.

The mount point sits **inside** MPD's music directory, so MPD sees it as a subfolder with no `mpd.conf` change and your built-in library stays visible. This is the same approach USB auto-mount uses.

**Mounted on first access, not at boot.** A NAS that's asleep, switched off, or slow never delays startup. Once mounted it stays mounted — an unmounted automount path reads as an *empty* folder, and MPD treats an empty folder as files that have been deleted.

**MPD's own user and group are applied as the mount's ownership.** SMB carries no Unix ownership of its own, so these options *are* the ownership. Getting this wrong is the classic hand-written-mount failure: the share reads fine as `pi` and appears empty to MPD.

**`/etc/fstab` is deliberately left alone.** A bad line there can stop the Pi booting, and it's a file you may keep your own entries in. Any manual fstab mount you already have keeps working and isn't interfered with.

Files involved:

| Path | Purpose |
|---|---|
| `/var/lib/mpd/music/nas` | Mount point |
| `/etc/systemd/system/var-lib-mpd-music-nas.mount` | The share definition |
| `/etc/systemd/system/var-lib-mpd-music-nas.automount` | Mounts it on first access |
| `/etc/squarepi-nas.cred` | SMB credentials, root-only (0600) |
| `/var/lib/squarepi/nas.json` | Server, folder, username — **no password** |

---

## Security

The DSP interface has **no password**, so anyone on your network can open the share form.

- Give the speaker a **read-only** account with access to the music folder only — never an administrator account.
- SMB passwords are stored on the Pi in a root-only credentials file. This is what any unattended mount requires, and it's the same thing an `/etc/fstab` setup does. The password is never sent back to the browser.
- NFS avoids stored credentials entirely, if your NAS offers it and you can restrict access by IP.

---

## Removing a share

Press **Remove** in the NETWORK SHARE card. That unmounts the share, deletes both units and the credentials file, and forgets the settings. **Nothing on the NAS is touched.**

To confirm:

```bash
findmnt /var/lib/mpd/music/nas   # should print nothing
ls /etc/systemd/system/var-lib-mpd-music-nas.*   # should not exist
```

`uninstall.sh` removes all of the above automatically.

---

## Limitations

- **One share at a time.** The card manages a single share at `nas`. Additional shares need manual `/etc/fstab` entries.
- **SMB 3.0 minimum.** Devices that only speak SMB 1 won't connect — and shouldn't be exposed to your network anyway.
- **An outage costs a rescan.** See [The share came back but the music is gone](#the-share-came-back-but-the-music-is-gone).
- **Only the DSP interface can set this up.** There's no command-line equivalent beyond writing the mount units yourself.

---

## See also

- [setup.md](setup.md) — full SquarePi setup guide
- [supported-protocols.md](supported-protocols.md) — every input SquarePi accepts
- [audio-engine.md](audio-engine.md) — what happens to the audio after it arrives
