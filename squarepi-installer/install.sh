#!/usr/bin/env bash
# =============================================================================
#  SquarePi Installer
#  Installs TAS5805M driver, MPD, myMPD, and Bluetooth A2DP on RPi OS Lite
#  Tested on: Raspberry Pi OS Lite (Debian Bookworm / Trixie), RPi Zero 2W
#
#  Usage:
#    sudo bash install.sh              # MPD + myMPD only
#    sudo bash install.sh --with-bt   # MPD + myMPD + Bluetooth A2DP
#    sudo SQUAREPI_AUTO_REBOOT=1 bash install.sh --with-bt
# =============================================================================

set -euo pipefail

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

# -----------------------------------------------------------------------------
# Parse arguments
# -----------------------------------------------------------------------------
INSTALL_BT=0
for arg in "$@"; do
  [[ "$arg" == "--with-bt" ]] && INSTALL_BT=1
done

# -----------------------------------------------------------------------------
# SquarePi hardware config — edit here if your HAT differs
# -----------------------------------------------------------------------------
TAS_I2C_ADDR=""               # Auto-detected (0x2c/0x2d/0x2e/0x2f); override if needed
TAS_DRIVER_REPO="https://github.com/sonocotta/tas5805m-driver-for-raspbian"
MPD_MUSIC_DIR="/var/lib/mpd/music"
MYMPD_HTTP_PORT="8080"
CONFIG_BACKUP=""

BT_DEVICE_NAME="SquarePi"
ALSA_SINK="hw:LouderRaspberry,0"

# -----------------------------------------------------------------------------
# Banner
# -----------------------------------------------------------------------------
echo -e "${BOLD}"
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║         SquarePi Software Installer          ║"
echo "  ║   TAS5805M HAT + MPD + myMPD on RPi OS Lite  ║"
if [[ $INSTALL_BT -eq 1 ]]; then
echo "  ║        + Bluetooth A2DP Receiver              ║"
fi
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
  warn "TAS5805M not detected on I2C. Defaulting to 0x2c."
  warn "Check HAT seating and verify with: i2cdetect -y 1"
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

if [[ "${ID}" != "debian" && "${ID_LIKE}" != *"debian"* ]]; then
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
fi

# -----------------------------------------------------------------------------
# 4. Update package index
# -----------------------------------------------------------------------------
step "Updating package index"
apt-get update -qq
success "Package index updated"

# -----------------------------------------------------------------------------
# 5. Detect architecture for kernel headers
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
# 6. Install core audio packages
# -----------------------------------------------------------------------------
step "Installing MPD, MPC, ALSA utilities and kernel headers"
apt-get install -y -qq \
  mpd \
  mpc \
  alsa-utils \
  curl \
  git \
  build-essential \
  "${KERNEL_HEADERS_PKG}" || \
  warn "Kernel headers install failed — TAS5805M driver build may fail"
success "Core packages installed"

# -----------------------------------------------------------------------------
# 7. Build and install TAS5805M kernel driver
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
# 8. Configure /boot/firmware/config.txt
# -----------------------------------------------------------------------------
step "Configuring boot overlay"

OVERLAY_DIR="/boot/overlays"
if [[ ! -f "${OVERLAY_DIR}/tas58xx.dtbo" ]]; then
  error "tas58xx.dtbo was not installed in ${OVERLAY_DIR}; refusing to edit boot config"
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

# Add TAS5805M overlay
if grep -q "dtoverlay=tas58xx" "${CONFIG_FILE}"; then
  sed -i "s|dtoverlay=tas58xx.*|dtoverlay=tas58xx,i2creg=${TAS_I2C_ADDR}|" "${CONFIG_FILE}"
  info "Updated existing TAS5805M overlay (addr=${TAS_I2C_ADDR})"
else
  cat >> "${CONFIG_FILE}" <<EOF

# SquarePi TAS5805M HAT
# pdn_gpio omitted — PDN pulled HIGH via 10K resistor to 3V3 on SquarePi V1
dtoverlay=tas58xx,i2creg=${TAS_I2C_ADDR}
EOF
  success "TAS5805M overlay added to ${CONFIG_FILE}"
fi

# -----------------------------------------------------------------------------
# 9. Configure MPD
# -----------------------------------------------------------------------------
step "Configuring MPD"

if ! aplay -l 2>/dev/null | grep -q "Louder"; then
  warn "TAS5805M audio card not detected by ALSA yet (expected before reboot)"
fi

mkdir -p "${MPD_MUSIC_DIR}" /var/lib/mpd/playlists /var/log/mpd
chown -R mpd:audio /var/lib/mpd /var/log/mpd 2>/dev/null || true
info "Music directory: ${MPD_MUSIC_DIR}"

cat > /etc/mpd.conf <<EOF
# MPD configuration for SquarePi (TAS5805M HAT)
# Generated by squarepi-installer

music_directory    "${MPD_MUSIC_DIR}"
playlist_directory "/var/lib/mpd/playlists"
db_file            "/var/lib/mpd/tag_cache"
state_file         "/var/lib/mpd/state"
log_file           "/var/log/mpd/mpd.log"

user               "mpd"
bind_to_address    "0.0.0.0"
port               "6600"

audio_output {
    type            "alsa"
    name            "SquarePi TAS5805M"
    device          "plughw:LouderRaspberry,0"
    format          "44100:16:2"
    mixer_type      "software"
}

replaygain          "auto"
volume_normalization "no"

input {
    plugin          "curl"
}
EOF

success "MPD configured at /etc/mpd.conf"

info "Validating MPD configuration..."
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
# 10. Enable and start MPD
# -----------------------------------------------------------------------------
step "Enabling MPD service"
systemctl enable mpd 2>/dev/null || true
systemctl restart mpd 2>/dev/null || true
sleep 2
if systemctl is-active --quiet mpd; then
  success "MPD is running"
  mpc update || true
else
  warn "MPD may not have started correctly. Check: journalctl -u mpd -n 20"
fi

# -----------------------------------------------------------------------------
# 11. Install myMPD
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
# 12. Enable and start myMPD
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
# 13. USB auto-mount (optional)
# -----------------------------------------------------------------------------
step "Setting up USB drive auto-mount"
apt-get install -y -qq usbmount 2>/dev/null || \
  warn "usbmount not available — USB drives will need manual mounting"

# =============================================================================
# BLUETOOTH A2DP SETUP (only if --with-bt passed)
# =============================================================================
if [[ $INSTALL_BT -eq 1 ]]; then

# -----------------------------------------------------------------------------
# BT-1. Install Bluetooth packages
# -----------------------------------------------------------------------------
step "[BT] Installing Bluetooth stack"

BLUEALSA_PKG=""
for pkg in bluez-alsa-utils bluealsa-utils bluealsa; do
  if apt-cache show "$pkg" &>/dev/null 2>&1; then
    BLUEALSA_PKG="$pkg"
    break
  fi
done

[[ -z "$BLUEALSA_PKG" ]] && error "No BlueALSA package found. Use Raspberry Pi OS Bookworm or enable a repo containing bluez-alsa-utils."

apt-get install -y -qq \
  bluez \
  bluez-tools \
  "${BLUEALSA_PKG}" \
  python3-dbus \
  python3-gi

apt-get install -y -qq bluealsa-aplay 2>/dev/null || \
  info "bluealsa-aplay bundled in ${BLUEALSA_PKG} — OK"

success "Bluetooth packages installed"

# -----------------------------------------------------------------------------
# BT-2. Configure BlueALSA (v4 compatible — SBC only, no AAC)
# -----------------------------------------------------------------------------
step "[BT] Configuring BlueALSA service"

# Detect bluealsa version to pick correct flag syntax
BLUEALSA_VER=$(bluealsa --version 2>&1 | grep -oP '\d+\.\d+' | head -1 || echo "0.0")
BLUEALSA_MAJOR=$(echo "$BLUEALSA_VER" | cut -d. -f1)

mkdir -p /etc/systemd/system/bluealsa.service.d

# v4+ dropped the --codec= flag for AAC when not compiled in; use -S and -p (short flag still works in v4)
# SBC only — AAC is not compiled into bluez-alsa-utils on RPi OS Bookworm
cat > /etc/systemd/system/bluealsa.service.d/override.conf <<EOF
[Service]
ExecStart=
ExecStart=/usr/bin/bluealsa -S -p a2dp-sink
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
# BT-3. bluealsa-aplay routing — let stock unit handle it (already correct on Bookworm)
# -----------------------------------------------------------------------------
step "[BT] Enabling A2DP → TAS5805M routing"

# The stock bluealsa-aplay.service on Bookworm is correct; just enable it.
# We do NOT override it — it starts after bluealsa and handles reconnects.
systemctl enable bluealsa-aplay 2>/dev/null || true
systemctl restart bluealsa-aplay 2>/dev/null || true
sleep 1

if systemctl is-active --quiet bluealsa-aplay; then
  success "bluealsa-aplay routing active"
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
Discoverable = true
Pairable = true
EOF

systemctl restart bluetooth
sleep 2

# Set alias via bluetoothctl to ensure name shows immediately (survives hostname mismatch)
bluetoothctl system-alias "${BT_DEVICE_NAME}" 2>/dev/null || true

success "Adapter configured as '${BT_DEVICE_NAME}'"

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
usermod -aG bluetooth "${SUDO_USER:-pi}" 2>/dev/null || true
success "Group permissions set"

fi  # end INSTALL_BT

# =============================================================================
# Final summary
# =============================================================================
trap - EXIT

PI_IP=$(hostname -I | awk '{print $1}')

echo ""
echo -e "${BOLD}${GREEN}"
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║           Installation Complete!             ║"
echo "  ╚══════════════════════════════════════════════╝"
echo -e "${NC}"
echo -e "  ${BOLD}myMPD Web UI:${NC}   http://${PI_IP}:${MYMPD_HTTP_PORT}"
echo -e "  ${BOLD}MPD Port:${NC}       ${PI_IP}:6600"
echo -e "  ${BOLD}Music folder:${NC}   ${MPD_MUSIC_DIR}"
echo -e "  ${BOLD}Boot backup:${NC}    ${CONFIG_BACKUP}"

if [[ $INSTALL_BT -eq 1 ]]; then
echo ""
echo -e "  ${BOLD}Bluetooth name:${NC}  ${BT_DEVICE_NAME}"
echo -e "  ${BOLD}Pairing:${NC}         Auto-accept (no PIN needed)"
echo -e "  ${BOLD}Codec:${NC}           SBC"
echo -e "  ${BOLD}BT Output:${NC}       TAS5805M (${ALSA_SINK})"
echo ""
echo -e "  ${CYAN}To connect: Bluetooth Settings → Scan → Tap '${BT_DEVICE_NAME}'${NC}"
echo -e "  ${YELLOW}Note: Pause MPD before switching to Bluetooth.${NC}"
fi

echo ""
echo -e "  ${YELLOW}⚠  A reboot is required to load the TAS5805M driver.${NC}"
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
