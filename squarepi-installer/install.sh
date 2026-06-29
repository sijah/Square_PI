#!/usr/bin/env bash
# =============================================================================
#  SquarePi Installer
#  Installs SquarePi audio driver, MPD, myMPD, and Bluetooth A2DP on RPi OS Lite
#  Tested on: Raspberry Pi OS Lite (Debian Bookworm / Trixie), RPi Zero 2W
#
#  Usage:
#    sudo bash install.sh                 # MPD + myMPD + Bluetooth + EQ UI (default)
#    sudo bash install.sh --without-bt    # skip Bluetooth
#    sudo bash install.sh --without-eq    # skip the EQ web UI
#    sudo bash install.sh --with-dlna --with-spotify --with-airplay
#    sudo bash install.sh --all           # everything (BT, EQ, DLNA, Spotify, AirPlay)
#    sudo SQUAREPI_HOSTNAME=squarepi bash install.sh
#    sudo SQUAREPI_BT_NAME="Kitchen SquarePi" bash install.sh
# =============================================================================

set -euo pipefail

# Capture script directory immediately — before any cd commands in the script
SCRIPT_DIR="$(cd "$(dirname "$(realpath "$0")")" && pwd)"

# -----------------------------------------------------------------------------
# Colour helpers
# -----------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }
step()    { echo -e "\n${BOLD}${CYAN}>>> $*${NC}"; }
box_line() { printf "  ║ %-44.44s ║\n" "$*"; }

# -----------------------------------------------------------------------------
# Parse arguments
# -----------------------------------------------------------------------------
# Bluetooth and the EQ web UI are installed by default (the two defining features).
# DLNA, Spotify, and AirPlay remain opt-in. Use --without-bt / --without-eq to skip.
INSTALL_BT=1
INSTALL_EQ=1
INSTALL_DLNA=0
INSTALL_SPOTIFY=0
INSTALL_AIRPLAY=0
for arg in "$@"; do
  # --with-bt / --with-eq are kept as no-op aliases for backward compatibility
  [[ "$arg" == "--with-bt"      ]] && INSTALL_BT=1
  [[ "$arg" == "--with-eq"      ]] && INSTALL_EQ=1
  [[ "$arg" == "--without-bt"   ]] && INSTALL_BT=0
  [[ "$arg" == "--without-eq"   ]] && INSTALL_EQ=0
  [[ "$arg" == "--with-dlna"    ]] && INSTALL_DLNA=1
  [[ "$arg" == "--with-spotify" ]] && INSTALL_SPOTIFY=1
  [[ "$arg" == "--with-airplay" ]] && INSTALL_AIRPLAY=1
  if [[ "$arg" == "--all" ]]; then
    INSTALL_BT=1; INSTALL_EQ=1; INSTALL_DLNA=1
    INSTALL_SPOTIFY=1; INSTALL_AIRPLAY=1
  fi
done

# -----------------------------------------------------------------------------
# SquarePi branding and hardware config — edit here if your HAT differs
# -----------------------------------------------------------------------------
INSTALLER_VER="1.4.0"

BRAND_NAME="${SQUAREPI_BRAND_NAME:-SquarePi}"
BRAND_TAGLINE="${SQUAREPI_TAGLINE:-From square wave to every corner.}"
PROJECT_URL="${SQUAREPI_PROJECT_URL:-https://github.com/sijah/Square_PI}"
SUPPORT_URL="${SQUAREPI_SUPPORT_URL:-${PROJECT_URL}/issues}"
RELEASE_FILE="/etc/squarepi-release"
HOSTNAME_REQUESTED="${SQUAREPI_HOSTNAME:-}"

TAS_I2C_ADDR=""               # Auto-detected (0x2c/0x2d/0x2e/0x2f); override if needed
TAS_DRIVER_REPO="https://github.com/sonocotta/tas5805m-driver-for-raspbian"
MPD_MUSIC_DIR="/var/lib/mpd/music"
USB_MUSIC_DIR="/mnt/usb-music"
MYMPD_HTTP_PORT="8080"
CONFIG_BACKUP=""

BT_DEVICE_NAME="${SQUAREPI_BT_NAME:-${BRAND_NAME}}"
ALSA_SINK="plughw:LouderRaspberry,0"

# -----------------------------------------------------------------------------
# Banner
# -----------------------------------------------------------------------------
INSTALL_LINE="MPD · myMPD"
[[ $INSTALL_BT      -eq 1 ]] && INSTALL_LINE="${INSTALL_LINE} · Bluetooth"
[[ $INSTALL_EQ      -eq 1 ]] && INSTALL_LINE="${INSTALL_LINE} · EQ UI"
[[ $INSTALL_DLNA    -eq 1 ]] && INSTALL_LINE="${INSTALL_LINE} · DLNA"
[[ $INSTALL_SPOTIFY -eq 1 ]] && INSTALL_LINE="${INSTALL_LINE} · Spotify"
[[ $INSTALL_AIRPLAY -eq 1 ]] && INSTALL_LINE="${INSTALL_LINE} · AirPlay"

echo -e "${BOLD}${CYAN}"
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║                                              ║"
echo "  ║   ┌──┐  ┌──┐  ┌──┐                           ║"
echo "  ║   │  │  │  │  │  │  S Q U A R E  P I         ║"
echo "  ║   │  └──┘  └──┘  └─────────────────          ║"
echo "  ║                                              ║"
echo "  ║   From square wave to every corner.          ║"
echo "  ║                                              ║"
echo "  ╠══════════════════════════════════════════════╣"
printf "  ║  %-44s║\n" "${INSTALL_LINE}"
printf "  ║  %-30s by Sijah AK  ║\n" "installer v${INSTALLER_VER}"
echo "  ╚══════════════════════════════════════════════╝"
echo -e "${NC}"

# -----------------------------------------------------------------------------
# 1. Root check
# -----------------------------------------------------------------------------
step "Checking permissions"
[[ $EUID -ne 0 ]] && error "Please run as root: sudo bash install.sh"
success "Running as root"

# -----------------------------------------------------------------------------
# 2. Auto-detect TAS5805M I2C address
# -----------------------------------------------------------------------------
step "Auto-detecting TAS5805M I2C address"

if ! command -v i2cdetect &>/dev/null; then
  apt-get update -qq
  apt-get install -y -qq i2c-tools
fi

for BUS in 1 2; do
  for ADDR in 0x2c 0x2d 0x2e 0x2f; do
    HEX="${ADDR#0x}"
    if i2cdetect -y "${BUS}" 2>/dev/null | grep -q "${HEX}"; then
      TAS_I2C_ADDR="${ADDR}"
      info "Found TAS5805M at ${ADDR} on I2C bus ${BUS}"
      break 2
    fi
  done
done

if [[ -z "${TAS_I2C_ADDR}" ]]; then
  warn "TAS5805M not detected on I2C — this is normal on first install (I2C not yet enabled in boot config)."
  warn "Defaulting to 0x2c. After reboot verify with: i2cdetect -y 1"
  TAS_I2C_ADDR="0x2c"
else
  success "Using I2C address: ${TAS_I2C_ADDR}"
fi

# -----------------------------------------------------------------------------
# 3. OS check
# -----------------------------------------------------------------------------
step "Checking operating system"

[[ ! -f /etc/os-release ]] && error "Cannot detect OS. /etc/os-release not found."

. /etc/os-release

if [[ "${ID}" != "debian" && "${ID_LIKE:-}" != *"debian"* ]]; then
  error "This installer requires Raspberry Pi OS (Debian-based). Detected: ${ID}"
fi

DEBIAN_VERSION="${VERSION_ID}"
info "Detected: ${PRETTY_NAME} (Debian ${DEBIAN_VERSION})"

if [[ "${DEBIAN_VERSION}" != "12" && "${DEBIAN_VERSION}" != "13" ]]; then
  warn "Untested Debian version: ${DEBIAN_VERSION}. Proceeding anyway..."
fi

if ! grep -q "Raspberry Pi" /proc/device-tree/model 2>/dev/null; then
  warn "Could not confirm Raspberry Pi hardware. Proceeding anyway..."
else
  PI_MODEL=$(cat /proc/device-tree/model | tr -d '\0')
  success "Hardware: ${PI_MODEL}"
  if echo "${PI_MODEL}" | grep -q "Raspberry Pi 5"; then
    error "Pi 5 detected. The TAS5805M overlay requires I²S via the RP1 southbridge, which uses different device tree overlays — Pi 5 is not yet supported."
  fi
fi

# -----------------------------------------------------------------------------
# 4. Optional hostname branding
# -----------------------------------------------------------------------------
step "Checking hostname branding"

if [[ -n "${HOSTNAME_REQUESTED}" ]]; then
  if [[ ! "${HOSTNAME_REQUESTED}" =~ ^[A-Za-z0-9][A-Za-z0-9-]{0,62}$ || "${HOSTNAME_REQUESTED}" == *- ]]; then
    warn "Invalid SQUAREPI_HOSTNAME '${HOSTNAME_REQUESTED}' — keeping current hostname"
  elif command -v hostnamectl &>/dev/null; then
    CURRENT_HOSTNAME=$(hostname)
    if [[ "${CURRENT_HOSTNAME}" == "${HOSTNAME_REQUESTED}" ]]; then
      info "Hostname already set to ${HOSTNAME_REQUESTED}"
    else
      if hostnamectl set-hostname "${HOSTNAME_REQUESTED}"; then
        # Keep /etc/hosts in sync — avoids "sudo: unable to resolve host" warnings
        if grep -q "^127\.0\.1\.1" /etc/hosts; then
          sed -i "s/^127\.0\.1\.1.*/127.0.1.1\t${HOSTNAME_REQUESTED}/" /etc/hosts
        else
          echo -e "127.0.1.1\t${HOSTNAME_REQUESTED}" >> /etc/hosts
        fi
        # Remove any stale entry for the old hostname (127.0.0.1 line sometimes has it)
        sed -i "s/\b${CURRENT_HOSTNAME}\b/${HOSTNAME_REQUESTED}/g" /etc/hosts
        success "Hostname set to ${HOSTNAME_REQUESTED} (/etc/hostname + /etc/hosts updated)"
      else
        warn "Could not set hostname to ${HOSTNAME_REQUESTED}"
      fi
    fi
  else
    warn "hostnamectl not available — skipping hostname change"
  fi
else
  info "Hostname unchanged. To set it, rerun with SQUAREPI_HOSTNAME=squarepi"
fi

# -----------------------------------------------------------------------------
# 5. Update package index
# -----------------------------------------------------------------------------
step "Updating package index"
apt-get update -qq
success "Package index updated"

# -----------------------------------------------------------------------------
# 6. Detect architecture for kernel headers
# -----------------------------------------------------------------------------
step "Detecting hardware architecture"

ARCH=$(uname -m)
KERNEL=$(uname -r)
info "Kernel  : ${KERNEL}"
info "Arch    : ${ARCH}"

KERNEL_HEADERS_PKG=""
if apt-cache show raspberrypi-kernel-headers &>/dev/null 2>&1; then
  KERNEL_HEADERS_PKG="raspberrypi-kernel-headers"
  info "Bookworm detected — using raspberrypi-kernel-headers"
else
  case "${ARCH}" in
    aarch64) KERNEL_HEADERS_PKG="linux-headers-rpi-v8" ;;
    armv7l)
      if echo "${KERNEL}" | grep -q "v7l"; then
        KERNEL_HEADERS_PKG="linux-headers-rpi-v7l"
      else
        KERNEL_HEADERS_PKG="linux-headers-rpi-v7"
      fi
      ;;
    armv6l) KERNEL_HEADERS_PKG="linux-headers-rpi" ;;
    *) warn "Unknown architecture: ${ARCH}"; KERNEL_HEADERS_PKG="linux-headers-$(uname -r)" ;;
  esac
  if ! apt-cache show "${KERNEL_HEADERS_PKG}" &>/dev/null 2>&1; then
    warn "${KERNEL_HEADERS_PKG} not in apt cache — trying linux-headers-$(uname -r)"
    KERNEL_HEADERS_PKG="linux-headers-$(uname -r)"
  fi
fi

info "Kernel headers: ${KERNEL_HEADERS_PKG}"

# -----------------------------------------------------------------------------
# 7. Install core audio packages
# -----------------------------------------------------------------------------
step "Installing MPD, MPC, ALSA utilities and kernel headers"
apt-get install -y -qq \
  mpd \
  mpc \
  alsa-utils \
  avahi-daemon \
  curl \
  git \
  build-essential \
  "${KERNEL_HEADERS_PKG}" || \
  warn "Kernel headers install failed — TAS5805M driver build may fail"

systemctl enable avahi-daemon 2>/dev/null || true
systemctl restart avahi-daemon 2>/dev/null || true
success "Core packages installed (mDNS via avahi-daemon enabled)"

# -----------------------------------------------------------------------------
# 8. Build and install TAS5805M kernel driver
# -----------------------------------------------------------------------------
step "Building TAS5805M kernel driver from source"

TMP_DIR=$(mktemp -d)
info "Cloning driver into ${TMP_DIR}"
git clone --depth=1 "${TAS_DRIVER_REPO}" "${TMP_DIR}/tas5805m" 2>&1 | \
  grep -E "(Cloning|done)" || true

cd "${TMP_DIR}/tas5805m"
info "Compiling kernel module..."
make all || error "Driver build failed"
info "Installing kernel module..."
make install || error "Driver install failed"
info "Compiling device tree overlay..."
bash compile-overlay.sh || error "Device tree overlay build failed"
cd /
rm -rf "${TMP_DIR}"
success "TAS5805M driver built and installed"

# -----------------------------------------------------------------------------
# 9. Configure /boot/firmware/config.txt
# -----------------------------------------------------------------------------
step "Configuring boot overlay"

OVERLAY_DIR=""
for _d in /boot/firmware/overlays /boot/overlays; do
  [[ -f "${_d}/tas58xx.dtbo" ]] && { OVERLAY_DIR="${_d}"; break; }
done
if [[ -z "${OVERLAY_DIR}" ]]; then
  error "tas58xx.dtbo not found in /boot/firmware/overlays or /boot/overlays; refusing to edit boot config"
fi

# Detect boot config location (Bookworm uses /boot/firmware/)
if [[ -f /boot/firmware/config.txt ]]; then
  CONFIG_FILE="/boot/firmware/config.txt"
elif [[ -f /boot/config.txt ]]; then
  CONFIG_FILE="/boot/config.txt"
else
  error "Cannot find boot config.txt"
fi

CONFIG_BACKUP="${CONFIG_FILE}.squarepi.bak.$(date +%Y%m%d%H%M%S)"
cp "${CONFIG_FILE}" "${CONFIG_BACKUP}"
info "Boot config backed up to ${CONFIG_BACKUP}"

# Enable I2S
if grep -q "^#dtparam=i2s=on" "${CONFIG_FILE}"; then
  sed -i 's/^#dtparam=i2s=on/dtparam=i2s=on/' "${CONFIG_FILE}"
  info "Enabled I2S (uncommented dtparam=i2s=on)"
elif ! grep -q "^dtparam=i2s=on" "${CONFIG_FILE}"; then
  echo "dtparam=i2s=on" >> "${CONFIG_FILE}"
  info "Added dtparam=i2s=on"
else
  info "I2S already enabled"
fi

# Disable onboard audio
if grep -q "^dtparam=audio=on" "${CONFIG_FILE}"; then
  sed -i 's/^dtparam=audio=on/dtparam=audio=off/' "${CONFIG_FILE}"
  info "Disabled onboard audio"
elif ! grep -q "^dtparam=audio" "${CONFIG_FILE}"; then
  echo "dtparam=audio=off" >> "${CONFIG_FILE}"
  info "Added dtparam=audio=off"
else
  info "Onboard audio already disabled"
fi

# Disable w1-gpio (GPIO4 conflict)
if grep -q "^dtoverlay=w1-gpio" "${CONFIG_FILE}"; then
  sed -i 's|^dtoverlay=w1-gpio|#dtoverlay=w1-gpio  # Disabled: GPIO4 conflict with TAS5805M PDN (SquarePi)|' "${CONFIG_FILE}"
  warn "Disabled w1-gpio (GPIO4 conflict)"
fi

if grep -q "^dtoverlay=vc4-kms-v3d" "${CONFIG_FILE}"; then
  warn "vc4-kms-v3d found — may conflict with I2S on some setups"
fi

# Add SquarePi audio overlay
if grep -q "dtoverlay=tas58xx" "${CONFIG_FILE}"; then
  sed -i "s|dtoverlay=tas58xx.*|dtoverlay=tas58xx,i2creg=${TAS_I2C_ADDR}|" "${CONFIG_FILE}"
  info "Updated existing SquarePi audio overlay (addr=${TAS_I2C_ADDR})"
else
  cat >> "${CONFIG_FILE}" <<EOF

# SquarePi HAT
# pdn_gpio omitted — PDN pulled HIGH via 10K resistor to 3V3 on SquarePi V1
dtoverlay=tas58xx,i2creg=${TAS_I2C_ADDR}
EOF
  success "SquarePi audio overlay added to ${CONFIG_FILE}"
fi

# -----------------------------------------------------------------------------
# 10. Configure MPD
# -----------------------------------------------------------------------------
step "Configuring MPD"

if ! aplay -l 2>/dev/null | grep -q "Louder"; then
  warn "SquarePi audio card not detected by ALSA yet (expected before reboot)"
fi

mkdir -p "${MPD_MUSIC_DIR}" /var/lib/mpd/playlists /var/log/mpd
chown -R mpd:audio /var/lib/mpd /var/log/mpd 2>/dev/null || true
info "Music directory: ${MPD_MUSIC_DIR}"

cat > /etc/mpd.conf <<EOF
# MPD configuration for ${BRAND_NAME}
# Generated by squarepi-installer

music_directory    "${MPD_MUSIC_DIR}"
auto_update        "yes"
playlist_directory "/var/lib/mpd/playlists"
db_file            "/var/lib/mpd/tag_cache"
sticker_file       "/var/lib/mpd/sticker.db"
state_file         "/var/lib/mpd/state"
log_file           "/var/log/mpd/mpd.log"

user               "mpd"
bind_to_address    "0.0.0.0"
port               "6600"

audio_buffer_size  "8192"

audio_output {
    type            "alsa"
    name            "${BRAND_NAME}"
    device          "plughw:LouderRaspberry,0"
    format          "48000:24:2"
    mixer_type      "software"
}

resampler {
    plugin          "soxr"
    quality         "very high"
}

replaygain          "auto"
volume_normalization "no"

zeroconf_enabled    "yes"
zeroconf_name       "${BRAND_NAME}"

input {
    plugin          "curl"
}

input_cache {
    size            "2 MB"
}
EOF

success "MPD configured at /etc/mpd.conf"

info "Validating MPD configuration..."
systemctl stop mpd 2>/dev/null || true   # ensure port 6600 is free for the test
MPD_TEST_LOG="/tmp/mpd_test.log"
set +e
timeout 10s mpd --no-daemon --stdout /etc/mpd.conf >"${MPD_TEST_LOG}" 2>&1
MPD_TEST_STATUS=$?
set -e
if [[ ${MPD_TEST_STATUS} -ne 0 && ${MPD_TEST_STATUS} -ne 124 ]]; then
  cat "${MPD_TEST_LOG}"
  error "Generated MPD configuration is invalid"
fi
rm -f "${MPD_TEST_LOG}"
success "MPD configuration validated"

# -----------------------------------------------------------------------------
# 11. Enable and start MPD
# -----------------------------------------------------------------------------
step "Enabling MPD service"
systemctl enable mpd 2>/dev/null || true
systemctl restart mpd 2>/dev/null || true
sleep 2
if systemctl is-active --quiet mpd; then
  success "MPD is running"
  mpc update || true
  mpc volume 25 2>/dev/null || true   # safe default — avoids full-blast on first play
else
  warn "MPD may not have started correctly. Check: journalctl -u mpd -n 20"
fi

# -----------------------------------------------------------------------------
# 12. Install myMPD
# -----------------------------------------------------------------------------
step "Adding myMPD repository"

KEYRING="/usr/share/keyrings/jcorporation.github.io.gpg"

if [[ "${DEBIAN_VERSION}" == "13" ]]; then
  curl -fsSL "http://download.opensuse.org/repositories/home:/jcorporation/Debian_${DEBIAN_VERSION}/Release.key" \
    | gpg --dearmor --output "${KEYRING}"
else
  curl -fsSL "http://download.opensuse.org/repositories/home:/jcorporation/Debian_${DEBIAN_VERSION}/Release.key" \
    | gpg --no-default-keyring --keyring "${KEYRING}" --import 2>/dev/null || \
  curl -fsSL "http://download.opensuse.org/repositories/home:/jcorporation/Debian_${DEBIAN_VERSION}/Release.key" \
    | gpg --dearmor --output "${KEYRING}"
fi

chmod 644 "${KEYRING}"
cat > /etc/apt/sources.list.d/jcorporation.list <<EOF
deb [signed-by=${KEYRING}] http://download.opensuse.org/repositories/home:/jcorporation/Debian_${DEBIAN_VERSION}/ ./
EOF

apt-get update -qq
apt-get install -y -qq mympd
success "myMPD installed"

# -----------------------------------------------------------------------------
# 13. Enable and start myMPD
# -----------------------------------------------------------------------------
step "Enabling myMPD service"
systemctl enable mympd 2>/dev/null || true
systemctl restart mympd 2>/dev/null || true
sleep 2
if systemctl is-active --quiet mympd; then
  success "myMPD is running"
  if curl -fs "http://127.0.0.1:${MYMPD_HTTP_PORT}" >/dev/null; then
    success "myMPD web UI is reachable"
  else
    warn "myMPD service running but web UI did not respond on port ${MYMPD_HTTP_PORT}"
  fi
else
  warn "myMPD may not have started. Check: journalctl -u mympd -n 20"
fi

# -----------------------------------------------------------------------------
# 14. Install myMPD EQ preset scripts
# -----------------------------------------------------------------------------
step "Installing EQ preset scripts into myMPD"

MYMPD_SCRIPTS_DIR="/var/lib/mympd/scripts"
mkdir -p "${MYMPD_SCRIPTS_DIR}"
# myMPD uses DynamicUser — state dir is owned by nobody:nogroup via private bind mount
chown nobody:nogroup "${MYMPD_SCRIPTS_DIR}" 2>/dev/null || true

# Helper: writes one preset Lua script
# Args: name, order, band values (space-separated, -15 to 15 where 0=flat)
# myMPD v10+ requires JSON metadata on line 1 for scripts to appear in the UI
write_eq_preset() {
  local name="$1"; local order="$2"; shift 2
  local vals=("$@")
  local bands=("00020 Hz" "00032 Hz" "00050 Hz" "00080 Hz" "00125 Hz"
               "00200 Hz" "00315 Hz" "00500 Hz" "00800 Hz" "01250 Hz"
               "02000 Hz" "03150 Hz" "05000 Hz" "08000 Hz" "16000 Hz")
  local file="${MYMPD_SCRIPTS_DIR}/${name}.lua"
  {
    echo '-- {"order":'"${order}"',"file":"","version":0,"arguments":[]}'
    for i in "${!bands[@]}"; do
      echo "os.execute('amixer -c LouderRaspberry sset \"${bands[$i]}\" -- ${vals[$i]} 2>/dev/null')"
    done
    echo "os.execute('alsactl store 2>/dev/null')"
  } > "${file}"
  chmod 644 "${file}"
}

# ALSA range -15 to 15; 0 = flat (0 dB), 1 unit = 1 dB
write_eq_preset "EQ Flat"        1   0  0  0  0  0  0  0  0  0  0  0  0  0  0  0
write_eq_preset "EQ Bass Boost"  2   7  6  5  4  3  0  0  0  0  0  0  0  0  0  0
write_eq_preset "EQ Treble"      3   0  0  0  0  0  0  0  0  0  2  3  4  5  6  6
write_eq_preset "EQ Vocal"       4  -3 -3 -2 -1  0  2  3  3  2  1  0 -1 -2 -2 -2
write_eq_preset "EQ Night Mode"  5  -5 -5 -4 -2  0  0  0 -1 -1 -1 -1 -2 -3 -4 -4
write_eq_preset "EQ Late Night"  6   6  5  3  1  0 -1 -1 -1  0  0  1  2  3  4  5
write_eq_preset "EQ Rock"        7   5  4  3  2  1 -1 -2 -2 -1  1  2  3  4  5  5
write_eq_preset "EQ Pop"         8   2  2  1  0 -1 -1  0  1  2  3  3  2  2  1  1
write_eq_preset "EQ Jazz"        9   3  3  2  1  0  1  2  2  1  0 -1 -1 -2 -2 -3
write_eq_preset "EQ Classical"  10   0  0  0  0  0  0  0  0  0  0  1  2  3  4  4
write_eq_preset "EQ Club"       11   8  7  6  4  2 -1 -2 -2 -1  1  2  3  4  5  6
write_eq_preset "EQ Hip-Hop"    12   7  7  6  5  3  1  0  0  1  2  2  2  3  3  2
write_eq_preset "EQ Acoustic"   13  -2 -2  0  1  2  2  1  0  1  2  3  3  2  1  0

# Sleep timer script
cat > /usr/local/bin/squarepi-sleep-timer.sh <<'STEOF'
#!/bin/bash
PIDFILE="/tmp/squarepi-sleep.pid"
MARKER="/tmp/squarepi-sleep.active"
case "${1:-}" in
  start)
    rm -f "$MARKER"
    if [[ -f "$PIDFILE" ]]; then kill "$(cat "$PIDFILE")" 2>/dev/null || true; rm -f "$PIDFILE"; fi
    touch "$MARKER"
    (sleep "${2:-1800}"; if [[ -f "$MARKER" ]]; then mpc stop 2>/dev/null || true; rm -f "$MARKER" "$PIDFILE"; fi) &
    echo $! > "$PIDFILE"
    ;;
  cancel)
    rm -f "$MARKER" "$PIDFILE"
    ;;
esac
STEOF
chmod +x /usr/local/bin/squarepi-sleep-timer.sh

# Sleep timer Lua scripts for myMPD
order=14
for entry in "Sleep_30min:1800" "Sleep_60min:3600" "Sleep_90min:5400"; do
  label="${entry%%:*}"
  secs="${entry##*:}"
  { echo '-- {"order":'"${order}"',"file":"","version":0,"arguments":[]}'
    echo "os.execute('/usr/local/bin/squarepi-sleep-timer.sh start ${secs}')"
  } > "${MYMPD_SCRIPTS_DIR}/${label}.lua"
  chmod 644 "${MYMPD_SCRIPTS_DIR}/${label}.lua"
  (( order++ ))
done
{ echo '-- {"order":17,"file":"","version":0,"arguments":[]}'
  echo "os.execute('/usr/local/bin/squarepi-sleep-timer.sh cancel')"
} > "${MYMPD_SCRIPTS_DIR}/Sleep_Cancel.lua"
chmod 644 "${MYMPD_SCRIPTS_DIR}/Sleep_Cancel.lua"

# Restart myMPD so it picks up the new scripts
systemctl restart mympd 2>/dev/null || true
success "EQ presets + sleep timer installed — find them in myMPD under Scripts"

# -----------------------------------------------------------------------------
# 15. Prepare USB music mount point
# -----------------------------------------------------------------------------
step "Preparing USB music mount point"
mkdir -p "${USB_MUSIC_DIR}"
chmod 755 "${USB_MUSIC_DIR}"
success "USB music mount point ready: ${USB_MUSIC_DIR}"

if apt-cache show exfatprogs &>/dev/null 2>&1; then
  apt-get install -y -qq exfatprogs || \
    warn "exfatprogs install failed — exFAT USB drives may need manual package setup"
else
  warn "exfatprogs not available — exFAT USB drives may need manual package setup"
fi

info "USB drives are not auto-mounted by this installer."
info "Mount a drive at ${USB_MUSIC_DIR}, then set MPD music_directory to that path if desired."

# -----------------------------------------------------------------------------
# 16. First-boot EQ initialisation (flat, runs once after driver loads)
# -----------------------------------------------------------------------------
step "Installing first-boot EQ initialisation service"

cat > /usr/local/bin/squarepi-eq-init.sh <<'INITEOF'
#!/bin/bash
# Sets all 15 EQ bands to 0 dB (flat) on first boot, then marks itself done.
CARD="LouderRaspberry"
BANDS=("00020 Hz" "00032 Hz" "00050 Hz" "00080 Hz" "00125 Hz" "00200 Hz"
       "00315 Hz" "00500 Hz" "00800 Hz" "01250 Hz" "02000 Hz" "03150 Hz"
       "05000 Hz" "08000 Hz" "16000 Hz")

for b in "${BANDS[@]}"; do
  amixer -c "$CARD" sset "$b" 0 2>/dev/null || true
done
alsactl store 2>/dev/null || true
touch /etc/squarepi-initialized
INITEOF
chmod +x /usr/local/bin/squarepi-eq-init.sh

cat > /etc/systemd/system/squarepi-eq-init.service <<'UNITEOF'
[Unit]
Description=SquarePi first-boot EQ initialisation (flat)
After=sound.target
ConditionPathExists=!/etc/squarepi-initialized

[Service]
Type=oneshot
ExecStart=/usr/local/bin/squarepi-eq-init.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
UNITEOF

systemctl daemon-reload
systemctl enable squarepi-eq-init
success "First-boot EQ init service installed (runs once after reboot)"

# -----------------------------------------------------------------------------
# 17. Write SquarePi release metadata
# -----------------------------------------------------------------------------
step "Writing ${BRAND_NAME} release metadata"
cat > "${RELEASE_FILE}" <<EOF
NAME="${BRAND_NAME}"
TAGLINE="${BRAND_TAGLINE}"
VERSION=${INSTALLER_VER}
HARDWARE="SquarePi HAT"
PROJECT_URL="${PROJECT_URL}"
SUPPORT_URL="${SUPPORT_URL}"
INSTALL_DATE="$(date -Iseconds)"
HOSTNAME="${HOSTNAME_REQUESTED:-$(hostname)}"
MPD_MUSIC_DIR="${MPD_MUSIC_DIR}"
USB_MUSIC_DIR="${USB_MUSIC_DIR}"
MYMPD_HTTP_PORT="${MYMPD_HTTP_PORT}"
BLUETOOTH_ENABLED=${INSTALL_BT}
BLUETOOTH_NAME="${BT_DEVICE_NAME}"
EQ_ENABLED=${INSTALL_EQ}
DLNA_ENABLED=${INSTALL_DLNA}
SPOTIFY_ENABLED=${INSTALL_SPOTIFY}
AIRPLAY_ENABLED=${INSTALL_AIRPLAY}
EOF
chmod 644 "${RELEASE_FILE}"
success "Release metadata written to ${RELEASE_FILE}"

# =============================================================================
# BLUETOOTH A2DP SETUP (installed by default; skip with --without-bt)
# =============================================================================
if [[ $INSTALL_BT -eq 1 ]]; then

# -----------------------------------------------------------------------------
# BT-1. Install Bluetooth packages (fail-soft: skip BT, keep core install)
# -----------------------------------------------------------------------------
step "[BT] Installing Bluetooth stack"

BLUEALSA_PKG=""
for pkg in bluez-alsa-utils bluealsa-utils bluealsa; do
  if apt-cache show "$pkg" &>/dev/null 2>&1; then
    BLUEALSA_PKG="$pkg"
    break
  fi
done

if [[ -z "$BLUEALSA_PKG" ]]; then
  warn "No BlueALSA package found — skipping Bluetooth. Core install continues."
  warn "To add BT later, enable a repo with bluez-alsa-utils and rerun the installer."
  INSTALL_BT=0
elif ! apt-get install -y -qq bluez bluez-tools "${BLUEALSA_PKG}" python3-dbus python3-gi; then
  warn "Bluetooth packages failed to install — skipping Bluetooth. Core install continues."
  INSTALL_BT=0
else
  apt-get install -y -qq bluealsa-aplay 2>/dev/null || \
    info "bluealsa-aplay bundled in ${BLUEALSA_PKG} — OK"
  success "Bluetooth packages installed"
fi

fi  # end BT package install

# Remaining Bluetooth configuration only runs if packages installed cleanly
if [[ $INSTALL_BT -eq 1 ]]; then

# -----------------------------------------------------------------------------
# BT-2. Configure BlueALSA (v4 compatible — SBC only, no AAC)
# -----------------------------------------------------------------------------
step "[BT] Configuring BlueALSA service"

# Detect bluealsa version to pick correct flag syntax
BLUEALSA_VER=$(bluealsa --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1 || echo "0.0")

mkdir -p /etc/systemd/system/bluealsa.service.d

# v4+ dropped the --codec= flag for AAC when not compiled in; use -S and -p (short flag still works in v4)
# SBC only — AAC is not compiled into bluez-alsa-utils on RPi OS Bookworm
cat > /etc/systemd/system/bluealsa.service.d/override.conf <<EOF
[Service]
ExecStart=
ExecStart=/usr/bin/bluealsa -S -p a2dp-sink --a2dp-volume --initial-volume=25
EOF

systemctl daemon-reload
systemctl enable bluealsa
systemctl restart bluealsa
sleep 2

if systemctl is-active --quiet bluealsa; then
  success "BlueALSA configured and running (SBC, v${BLUEALSA_VER})"
else
  warn "BlueALSA failed to start. Check: journalctl -xeu bluealsa.service"
fi

# -----------------------------------------------------------------------------
# BT-3. ALSA dmix shared mixer + bluealsa-aplay override
# -----------------------------------------------------------------------------
step "[BT] Creating ALSA shared mixer (dmix) for MPD + Bluetooth"

# MPD holds plughw:LouderRaspberry,0 exclusively; bluealsa-aplay can't open it.
# dmix lets both share the hardware at a fixed rate via software mixing.
cat > /etc/asound.conf <<'EOF'
pcm.squarepi_mix {
    type plug
    slave {
        pcm {
            type dmix
            ipc_key 1025
            ipc_perm 0666
            slave {
                pcm "hw:LouderRaspberry,0"
                rate 48000
                format S32_LE
                period_size 4096
                buffer_size 65536
            }
        }
    }
}

pcm.squarepi_bt_vol {
    type softvol
    slave.pcm "squarepi_mix"
    control {
        name "BT Volume"
        card LouderRaspberry
    }
    min_dB -40.0
    max_dB 0.0
    resolution 100
}

ctl.squarepi_mix {
    type hw
    card LouderRaspberry
}

pcm.!default {
    type plug
    slave.pcm "squarepi_mix"
}

ctl.!default {
    type hw
    card LouderRaspberry
}
EOF

# Switch MPD from plughw: to the shared dmix device
sed -i 's|device\s*"plughw:LouderRaspberry,0"|device          "squarepi_mix"|' /etc/mpd.conf
systemctl restart mpd
success "ALSA dmix mixer created; MPD switched to squarepi_mix"

# Override bluealsa-aplay to route to squarepi_mix (fixes "Master elem not found" too)
mkdir -p /etc/systemd/system/bluealsa-aplay.service.d
cat > /etc/systemd/system/bluealsa-aplay.service.d/override.conf <<'EOF'
[Service]
ExecStart=
ExecStart=/usr/bin/bluealsa-aplay -S --pcm=squarepi_bt_vol
EOF

systemctl daemon-reload
systemctl enable bluealsa-aplay 2>/dev/null || true
systemctl restart bluealsa-aplay
sleep 1

# BT Volume default persisted via file; softvol control only exists during BT playback
mkdir -p /var/lib/squarepi
[[ -f /var/lib/squarepi/bt_volume ]] || echo "50" > /var/lib/squarepi/bt_volume
alsactl store 2>/dev/null || true

if systemctl is-active --quiet bluealsa-aplay; then
  success "bluealsa-aplay routing active (→ squarepi_bt_vol @ 50%)"
else
  warn "bluealsa-aplay not running yet — it will connect once a BT device pairs"
fi

# -----------------------------------------------------------------------------
# BT-4. Configure Bluetooth adapter
# -----------------------------------------------------------------------------
step "[BT] Configuring Bluetooth adapter"

cat > /etc/bluetooth/main.conf <<EOF
[Policy]
AutoEnable=true

[General]
Name = ${BT_DEVICE_NAME}
Class = 0x200414
DiscoverableTimeout = 0
PairableTimeout = 0
EOF

# Install a systemd oneshot that re-applies discoverable/pairable after every
# bluetooth.service start. Discoverable/Pairable are NOT valid keys in [General]
# on newer bluez — they silently do nothing, so runtime bluetoothctl is the only
# reliable mechanism.
cat > /etc/systemd/system/squarepi-bt-setup.service <<EOF
[Unit]
Description=SquarePi Bluetooth adapter setup (discoverable + pairable)
After=bluetooth.service
Requires=bluetooth.service

[Service]
Type=oneshot
ExecStart=/bin/bash -c 'bluetoothctl power on; bluetoothctl pairable on; bluetoothctl discoverable on; bluetoothctl system-alias "${BT_DEVICE_NAME}"'
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable squarepi-bt-setup
systemctl restart bluetooth
sleep 2
systemctl start squarepi-bt-setup

success "Adapter configured as '${BT_DEVICE_NAME}' (discoverable + pairable persisted via systemd)"

# -----------------------------------------------------------------------------
# BT-5. Fix rfkill — unblock BT and persist across reboots
# -----------------------------------------------------------------------------
step "[BT] Fixing rfkill and ensuring BT comes up on boot"

rfkill unblock bluetooth || true
hciconfig hci0 up 2>/dev/null || true

# Add rfkill unblock to rc.local for persistence across reboots
RC_LOCAL="/etc/rc.local"
if [[ ! -f "$RC_LOCAL" ]]; then
  cat > "$RC_LOCAL" <<'EOF'
#!/bin/bash
exit 0
EOF
  chmod +x "$RC_LOCAL"
fi

if ! grep -q "rfkill unblock bluetooth" "$RC_LOCAL"; then
  sed -i '/^exit 0/i rfkill unblock bluetooth\nhciconfig hci0 up\n' "$RC_LOCAL"
  info "Added rfkill unblock to ${RC_LOCAL}"
fi

success "rfkill unblock configured"

# -----------------------------------------------------------------------------
# BT-6. Auto-accept pairing agent
# -----------------------------------------------------------------------------
step "[BT] Installing auto-pairing agent"

cat > /usr/local/bin/squarepi-bt-agent.py <<'PYEOF'
#!/usr/bin/env python3
"""SquarePi Bluetooth pairing agent — auto-accepts all pair requests."""
import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib

BUS_NAME    = 'org.bluez'
AGENT_IFACE = 'org.bluez.Agent1'
AGENT_PATH  = '/squarepi/agent'

class Agent(dbus.service.Object):
    @dbus.service.method(AGENT_IFACE, in_signature='o',  out_signature='')
    def RequestAuthorization(self, device):
        print(f'[BT] Auto-authorizing {device}')

    @dbus.service.method(AGENT_IFACE, in_signature='os', out_signature='')
    def AuthorizeService(self, device, uuid):
        print(f'[BT] Authorizing service {uuid} for {device}')

    @dbus.service.method(AGENT_IFACE, in_signature='o',  out_signature='s')
    def RequestPinCode(self, device):
        return '0000'

    @dbus.service.method(AGENT_IFACE, in_signature='o',  out_signature='u')
    def RequestPasskey(self, device):
        return dbus.UInt32(0)

    @dbus.service.method(AGENT_IFACE, in_signature='ouq', out_signature='')
    def DisplayPasskey(self, device, passkey, entered):
        print(f'[BT] Passkey: {passkey:06d}')

    @dbus.service.method(AGENT_IFACE, in_signature='ou', out_signature='')
    def RequestConfirmation(self, device, passkey):
        print(f'[BT] Auto-confirming passkey {passkey:06d}')

    @dbus.service.method(AGENT_IFACE, in_signature='', out_signature='')
    def Release(self): pass

    @dbus.service.method(AGENT_IFACE, in_signature='', out_signature='')
    def Cancel(self): pass

if __name__ == '__main__':
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus     = dbus.SystemBus()
    agent   = Agent(bus, AGENT_PATH)
    manager = dbus.Interface(bus.get_object(BUS_NAME, '/org/bluez'),
                             'org.bluez.AgentManager1')
    manager.RegisterAgent(AGENT_PATH, 'NoInputNoOutput')
    manager.RequestDefaultAgent(AGENT_PATH)
    print('[BT Agent] Running — auto-accepting all pairing requests')
    GLib.MainLoop().run()
PYEOF

chmod +x /usr/local/bin/squarepi-bt-agent.py

cat > /etc/systemd/system/squarepi-bt-agent.service <<EOF
[Unit]
Description=SquarePi Bluetooth auto-pairing agent
Requires=bluetooth.service
After=bluetooth.service

[Service]
Type=simple
ExecStart=/usr/local/bin/squarepi-bt-agent.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable squarepi-bt-agent
systemctl start squarepi-bt-agent
sleep 1

if systemctl is-active --quiet squarepi-bt-agent; then
  success "Auto-pairing agent running"
else
  warn "Pairing agent not running — check: journalctl -u squarepi-bt-agent"
fi

# -----------------------------------------------------------------------------
# BT-7. Group permissions
# -----------------------------------------------------------------------------
step "[BT] Setting audio group permissions"
usermod -aG audio bluetooth 2>/dev/null || true
TARGET_USER="${SUDO_USER:-$(logname 2>/dev/null || echo '')}"
if [[ -n "${TARGET_USER}" ]] && id "${TARGET_USER}" &>/dev/null 2>&1; then
  usermod -aG bluetooth "${TARGET_USER}" 2>/dev/null || true
  info "Added ${TARGET_USER} to bluetooth group"
else
  warn "Could not detect logged-in user — add yourself to the bluetooth group manually: sudo usermod -aG bluetooth \$USER"
fi
success "Group permissions set"

fi  # end INSTALL_BT

# =============================================================================
# ADVANCED EQ WEB SERVER (installed by default; skip with --without-eq)
# =============================================================================
if [[ $INSTALL_EQ -eq 1 ]]; then

step "[EQ] Installing advanced EQ web server"

# Require Python 3 (already on RPi OS Bookworm/Trixie)
if ! command -v python3 &>/dev/null; then
  apt-get install -y -qq python3
fi

EQ_SERVER_DEST="/usr/local/bin/squarepi-eq-server.py"

# Locate eq-server.py — check next to install.sh first, then GitHub
if [[ -f "${SCRIPT_DIR}/eq-server.py" ]]; then
  cp "${SCRIPT_DIR}/eq-server.py" "${EQ_SERVER_DEST}"
else
  # Fallback: download from GitHub if running via curl pipe
  curl -fsSL "https://raw.githubusercontent.com/sijah/Square_PI/main/squarepi-installer/eq-server.py" \
    -o "${EQ_SERVER_DEST}" || error "Could not fetch eq-server.py"
fi

chmod +x "${EQ_SERVER_DEST}"
success "EQ server installed to ${EQ_SERVER_DEST}"

# State directory for eq-server persistence (BT volume saved here)
mkdir -p /var/lib/squarepi
[[ -f /var/lib/squarepi/bt_volume ]] || echo "50" > /var/lib/squarepi/bt_volume

# systemd unit for EQ server
cat > /etc/systemd/system/squarepi-eq.service <<EOF
[Unit]
Description=SquarePi Advanced EQ Web Server
After=network.target sound.target

[Service]
Type=simple
ExecStartPre=/bin/sleep 5
ExecStart=/usr/bin/python3 ${EQ_SERVER_DEST}
ExecStop=/usr/sbin/alsactl store
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Separate one-shot unit: restore ALSA EQ state on boot
cat > /etc/systemd/system/squarepi-alsa-restore.service <<EOF
[Unit]
Description=SquarePi ALSA state restore
After=sound.target
Before=mpd.service squarepi-eq.service

[Service]
Type=oneshot
ExecStart=/usr/sbin/alsactl restore
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable squarepi-alsa-restore
systemctl enable squarepi-eq
systemctl start squarepi-eq
sleep 2

if systemctl is-active --quiet squarepi-eq; then
  success "EQ web server running on port 8081"
else
  warn "EQ server not running yet — it needs audio card (available after reboot)"
fi

EQ_HTTP_PORT="8081"

fi  # end INSTALL_EQ

# =============================================================================
# DLNA/UPnP RENDERER (only if --with-dlna passed)
# =============================================================================
if [[ $INSTALL_DLNA -eq 1 ]]; then

step "[DLNA] Adding upmpdcli repository"

UPMPDCLI_KEY="/usr/share/keyrings/upmpdcli.gpg"
UPMPDCLI_FINGERPRINT="F8E3347256922A8AE767605B7808CE96D38B9201"

# Try multiple keyservers in case one is unreachable
UPMPDCLI_KEY_OK=0
for KS in keyserver.ubuntu.com keys.openpgp.org hkps://keyserver.ubuntu.com; do
  if gpg --keyserver "${KS}" --recv-keys "${UPMPDCLI_FINGERPRINT}" 2>/dev/null; then
    gpg --export "${UPMPDCLI_FINGERPRINT}" | gpg --dearmor -o "${UPMPDCLI_KEY}"
    UPMPDCLI_KEY_OK=1
    break
  fi
done
[[ ${UPMPDCLI_KEY_OK} -eq 0 ]] && error "Could not fetch upmpdcli GPG key from any keyserver. Check internet access."

OS_CODENAME="$(. /etc/os-release && echo "${VERSION_CODENAME}")"

# upmpdcli may not publish packages for every Debian/Pi OS version — fall back to bookworm
for CODENAME in "${OS_CODENAME}" bookworm; do
  echo "deb [signed-by=${UPMPDCLI_KEY}] http://www.lesbonscomptes.com/upmpdcli/downloads/raspbian/ ${CODENAME} main" \
    > /etc/apt/sources.list.d/upmpdcli.list
  if apt-get update -qq 2>/dev/null && apt-cache show upmpdcli &>/dev/null 2>&1; then
    success "upmpdcli repository added (${CODENAME})"
    OS_CODENAME="${CODENAME}"
    break
  fi
  warn "upmpdcli repo for '${CODENAME}' did not work — trying fallback"
done

if ! apt-cache show upmpdcli &>/dev/null 2>&1; then
  error "upmpdcli not available for this OS version. Install manually from lesbonscomptes.com/upmpdcli"
fi

step "[DLNA] Installing upmpdcli UPnP/DLNA renderer"

apt-get install -y -qq upmpdcli || error "upmpdcli install failed"
success "upmpdcli installed"

step "[DLNA] Configuring upmpdcli"

cat > /etc/upmpdcli.conf <<EOF
# SquarePi UPnP/DLNA renderer
# Generated by squarepi-installer

friendlyname     = ${BRAND_NAME}
mpdhost          = localhost
mpdport          = 6600
logfilename      = /var/log/upmpdcli.log
loglevel         = 2
protocolinfo     = http-get:*:audio/mpeg:*,http-get:*:audio/flac:*,http-get:*:audio/ogg:*,http-get:*:audio/mp4:*
EOF

chmod 644 /etc/upmpdcli.conf
success "upmpdcli configured as '${BRAND_NAME}'"

step "[DLNA] Enabling upmpdcli service"
systemctl daemon-reload
systemctl enable upmpdcli
systemctl restart upmpdcli
sleep 2

if systemctl is-active --quiet upmpdcli; then
  success "upmpdcli running — SquarePi visible as DLNA renderer on the network"
else
  warn "upmpdcli not running yet — check: journalctl -u upmpdcli -n 20"
fi

DLNA_HTTP_PORT="8200"

fi  # end INSTALL_DLNA

# =============================================================================
# SPOTIFY CONNECT (only if --with-spotify passed)
# =============================================================================
if [[ $INSTALL_SPOTIFY -eq 1 ]]; then

step "[Spotify] Adding raspotify repository"

RASPOTIFY_KEY="/usr/share/keyrings/raspotify.gpg"
curl -fsSL https://dtcooper.github.io/raspotify/key.asc \
  | gpg --dearmor -o "${RASPOTIFY_KEY}"
echo "deb [signed-by=${RASPOTIFY_KEY}] https://dtcooper.github.io/raspotify raspotify main" \
  > /etc/apt/sources.list.d/raspotify.list
apt-get update -qq
success "raspotify repository added"

step "[Spotify] Installing raspotify (librespot)"
apt-get install -y -qq raspotify
success "raspotify installed"

step "[Spotify] Configuring Spotify Connect"

# Event script: pause MPD when Spotify starts, clean up state on stop
cat > /usr/local/bin/squarepi-spotify-event.sh <<'SPEOF'
#!/bin/bash
case "${PLAYER_EVENT:-}" in
  start|play|preloading)
    touch /tmp/squarepi-source-spotify
    mpc pause 2>/dev/null || true
    ;;
  stop|endoftrack)
    rm -f /tmp/squarepi-source-spotify
    ;;
esac
SPEOF
chmod 755 /usr/local/bin/squarepi-spotify-event.sh

cat > /etc/raspotify/conf <<EOF
LIBRESPOT_NAME="${BT_DEVICE_NAME}"
LIBRESPOT_BITRATE="320"
LIBRESPOT_FORMAT="S16"
LIBRESPOT_DEVICE_TYPE="speaker"
LIBRESPOT_DEVICE="squarepi_mix"
LIBRESPOT_ONEVENT="/usr/local/bin/squarepi-spotify-event.sh"
EOF

systemctl daemon-reload
systemctl enable raspotify
systemctl restart raspotify
sleep 2

if systemctl is-active --quiet raspotify; then
  success "Spotify Connect running — '${BT_DEVICE_NAME}' visible in Spotify app"
else
  warn "raspotify not running yet — check: journalctl -u raspotify -n 20"
fi

fi  # end INSTALL_SPOTIFY

# =============================================================================
# AIRPLAY (only if --with-airplay passed)
# =============================================================================
if [[ $INSTALL_AIRPLAY -eq 1 ]]; then

step "[AirPlay] Installing shairport-sync"
apt-get install -y -qq shairport-sync
success "shairport-sync installed"

step "[AirPlay] Configuring AirPlay receiver"

# Event script — runs as shairport-sync user; state files must be in /tmp/
cat > /usr/local/bin/squarepi-airplay-event.sh <<'APEOF'
#!/bin/bash
case "${1:-}" in
  start)
    touch /tmp/squarepi-source-airplay
    mpc pause 2>/dev/null || true
    ;;
  stop)
    rm -f /tmp/squarepi-source-airplay
    ;;
esac
APEOF
chmod 755 /usr/local/bin/squarepi-airplay-event.sh

cat > /etc/shairport-sync.conf <<APCEOF
general = {
  name = "${BT_DEVICE_NAME}";
  output_backend = "alsa";
};

alsa = {
  output_device = "squarepi_mix";
  mixer_control_name = "Master";
};

sessioncontrol = {
  run_this_before_play_begins = "/usr/local/bin/squarepi-airplay-event.sh start";
  run_this_after_play_ends    = "/usr/local/bin/squarepi-airplay-event.sh stop";
};
APCEOF

systemctl daemon-reload
systemctl enable shairport-sync
systemctl restart shairport-sync
sleep 2

if systemctl is-active --quiet shairport-sync; then
  success "AirPlay running — '${BT_DEVICE_NAME}' visible in AirPlay device list"
else
  warn "shairport-sync not running yet — check: journalctl -u shairport-sync -n 20"
fi

fi  # end INSTALL_AIRPLAY

# =============================================================================
# Final summary
# =============================================================================
trap - EXIT

PI_IP=$(hostname -I | awk '{print $1}')
MDNS_HOST="${HOSTNAME_REQUESTED:-$(hostname)}"

echo ""
echo -e "${BOLD}${GREEN}"
echo "  ╔══════════════════════════════════════════════╗"
box_line "${BRAND_NAME} is ready"
echo "  ╚══════════════════════════════════════════════╝"
echo -e "${NC}"
echo -e "  ${BOLD}myMPD Web UI:${NC}   http://${PI_IP}:${MYMPD_HTTP_PORT}"
echo -e "  ${BOLD}mDNS URL:${NC}       http://${MDNS_HOST}.local:${MYMPD_HTTP_PORT}  ${CYAN}(no IP needed)${NC}"
echo -e "  ${BOLD}MPD (apps):${NC}     ${PI_IP}:6600  or  ${MDNS_HOST}.local:6600"
echo -e "  ${BOLD}Music folder:${NC}   ${MPD_MUSIC_DIR}"
echo -e "  ${BOLD}USB mount:${NC}      ${USB_MUSIC_DIR}"
echo -e "  ${BOLD}Boot backup:${NC}    ${CONFIG_BACKUP}"
echo -e "  ${BOLD}Release file:${NC}   ${RELEASE_FILE}"
echo -e "  ${BOLD}Docs:${NC}           ${PROJECT_URL}"
echo -e "  ${BOLD}Support:${NC}        ${SUPPORT_URL}"
if [[ $INSTALL_EQ -eq 1 ]]; then
echo ""
echo -e "  ${BOLD}Advanced EQ:${NC}    http://${PI_IP}:${EQ_HTTP_PORT:-8081}"
echo -e "  ${BOLD}EQ mDNS:${NC}        http://${MDNS_HOST}.local:${EQ_HTTP_PORT:-8081}"
echo -e "  ${CYAN}EQ presets also available in myMPD under Scripts.${NC}"
fi

if [[ $INSTALL_DLNA -eq 1 ]]; then
echo ""
echo -e "  ${BOLD}DLNA renderer:${NC}  http://${PI_IP}:${DLNA_HTTP_PORT:-8200}"
echo -e "  ${BOLD}DLNA mDNS:${NC}      http://${MDNS_HOST}.local:${DLNA_HTTP_PORT:-8200}"
fi

if [[ $INSTALL_BT -eq 1 ]]; then
echo ""
echo -e "  ${BOLD}Bluetooth name:${NC}  ${BT_DEVICE_NAME}"
echo -e "  ${BOLD}Pairing:${NC}         Auto-accept (no PIN needed)"
echo -e "  ${BOLD}Codec:${NC}           SBC"
echo -e "  ${CYAN}To connect: Bluetooth Settings → Scan → Tap '${BT_DEVICE_NAME}'${NC}"
fi

if [[ $INSTALL_SPOTIFY -eq 1 ]]; then
echo ""
echo -e "  ${BOLD}Spotify Connect:${NC} Open Spotify → Devices → '${BT_DEVICE_NAME}'"
fi

if [[ $INSTALL_AIRPLAY -eq 1 ]]; then
echo ""
echo -e "  ${BOLD}AirPlay:${NC}         Select '${BT_DEVICE_NAME}' in AirPlay device list"
fi

echo ""
echo -e "  ${CYAN}Sleep timer: open myMPD → Scripts → Sleep_30min / 60min / 90min${NC}"

echo ""
echo -e "  ${YELLOW}⚠  A reboot is required to load the SquarePi audio driver.${NC}"
echo -e "  ${YELLOW}   After reboot, verify with: aplay -l${NC}"
echo ""

if [[ "${SQUAREPI_AUTO_REBOOT:-0}" == "1" ]]; then
  echo -e "  ${CYAN}Rebooting in 10 seconds (SQUAREPI_AUTO_REBOOT=1)... Ctrl+C to cancel.${NC}"
  echo ""
  sleep 10
  reboot
else
  echo -e "  ${CYAN}Auto-reboot skipped. Run 'sudo reboot' when ready.${NC}"
  echo ""
fi
