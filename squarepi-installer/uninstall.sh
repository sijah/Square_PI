#!/usr/bin/env bash
# =============================================================================
#  SquarePi Uninstaller
#  Removes everything installed by install.sh
#  — myMPD, MPD, TAS5805M driver, boot overlay, repo keys
#
#  Usage:
#    sudo bash uninstall.sh
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
# Banner
# -----------------------------------------------------------------------------
echo -e "${BOLD}"
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║         SquarePi Software Uninstaller        ║"
echo "  ║   Removes TAS5805M driver, MPD and myMPD     ║"
echo "  ╚══════════════════════════════════════════════╝"
echo -e "${NC}"

# -----------------------------------------------------------------------------
# 1. Root check
# -----------------------------------------------------------------------------
step "Checking permissions"
[[ $EUID -ne 0 ]] && error "Please run as root: sudo bash uninstall.sh"
success "Running as root"

# -----------------------------------------------------------------------------
# 2. Confirm with user
# -----------------------------------------------------------------------------
echo -e "${YELLOW}"
echo "  This will remove:"
echo "    • myMPD (web UI)"
echo "    • MPD + MPC (music player daemon)"
echo "    • TAS5805M kernel driver (tas58xx.ko)"
echo "    • Boot overlay entry in config.txt"
echo "    • myMPD apt repository and key"
echo "    • /etc/squarepi-release"
echo ""
echo "  Your music files will NOT be deleted."
echo -e "${NC}"

read -r -p "  Are you sure you want to continue? [y/N] " CONFIRM
if [[ ! "${CONFIRM}" =~ ^[Yy]$ ]]; then
  echo ""
  info "Uninstall cancelled."
  exit 0
fi

# -----------------------------------------------------------------------------
# 3. Stop and disable myMPD
# -----------------------------------------------------------------------------
step "Stopping myMPD"

if systemctl is-active --quiet mympd 2>/dev/null; then
  systemctl stop mympd
  info "myMPD stopped"
fi

if systemctl is-enabled --quiet mympd 2>/dev/null; then
  systemctl disable mympd
  info "myMPD disabled"
fi

# -----------------------------------------------------------------------------
# 4. Remove myMPD package
# -----------------------------------------------------------------------------
step "Removing myMPD"

if dpkg -l mympd &>/dev/null 2>&1; then
  apt-get remove -y -qq mympd
  apt-get autoremove -y -qq
  success "myMPD removed"
else
  info "myMPD not installed — skipping"
fi

# -----------------------------------------------------------------------------
# 5. Remove myMPD repo and key
# -----------------------------------------------------------------------------
step "Removing myMPD apt repository"

if [[ -f /etc/apt/sources.list.d/jcorporation.list ]]; then
  rm -f /etc/apt/sources.list.d/jcorporation.list
  info "Removed /etc/apt/sources.list.d/jcorporation.list"
fi

if [[ -f /usr/share/keyrings/jcorporation.github.io.gpg ]]; then
  rm -f /usr/share/keyrings/jcorporation.github.io.gpg
  info "Removed GPG keyring"
fi

apt-get update -qq
success "apt repository cleaned"

# -----------------------------------------------------------------------------
# 6. Stop and disable MPD
# -----------------------------------------------------------------------------
step "Stopping MPD"

if systemctl is-active --quiet mpd 2>/dev/null; then
  systemctl stop mpd
  info "MPD stopped"
fi

if systemctl is-enabled --quiet mpd 2>/dev/null; then
  systemctl disable mpd
  info "MPD disabled"
fi

# Also stop mpd socket if active
if systemctl is-active --quiet mpd.socket 2>/dev/null; then
  systemctl stop mpd.socket
  systemctl disable mpd.socket 2>/dev/null || true
  info "MPD socket stopped"
fi

# -----------------------------------------------------------------------------
# 7. Remove MPD package
# -----------------------------------------------------------------------------
step "Removing MPD and MPC"

PKGS_TO_REMOVE=""
dpkg -l mpd  &>/dev/null 2>&1 && PKGS_TO_REMOVE="${PKGS_TO_REMOVE} mpd"
dpkg -l mpc  &>/dev/null 2>&1 && PKGS_TO_REMOVE="${PKGS_TO_REMOVE} mpc"

if [[ -n "${PKGS_TO_REMOVE}" ]]; then
  apt-get remove -y -qq ${PKGS_TO_REMOVE}
  apt-get autoremove -y -qq
  success "MPD and MPC removed"
else
  info "MPD/MPC not installed — skipping"
fi

# Ask about MPD data files
echo ""
read -r -p "  Remove MPD library cache and playlists? (/var/lib/mpd) [y/N] " REMOVE_DATA
if [[ "${REMOVE_DATA}" =~ ^[Yy]$ ]]; then
  rm -rf /var/lib/mpd
  rm -rf /var/log/mpd
  info "MPD data files removed"
else
  info "MPD data files kept at /var/lib/mpd"
fi

# -----------------------------------------------------------------------------
# 8. Remove TAS5805M kernel driver
# -----------------------------------------------------------------------------
step "Removing TAS5805M kernel driver"

TAS_DRIVER_REPO="https://github.com/sonocotta/tas5805m-driver-for-raspbian"
KERNEL=$(uname -r)
KO_PATH="/lib/modules/${KERNEL}/extra/tas58xx.ko"
OVERLAY_PATHS=(
  "/boot/overlays/tas58xx.dtbo"
  "/boot/firmware/overlays/tas58xx.dtbo"
)

# Unload module if currently loaded
if lsmod | grep -q "^tas58xx"; then
  modprobe -r tas58xx 2>/dev/null && info "Unloaded tas58xx module" || \
    warn "Could not unload tas58xx — will be gone after reboot"
fi

# Try make uninstall first (cleanest — mirrors what make install did)
if command -v git &>/dev/null && command -v make &>/dev/null; then
  TMP_DIR=$(mktemp -d)
  info "Re-cloning driver to run make uninstall..."
  if git clone --depth=1 "${TAS_DRIVER_REPO}" "${TMP_DIR}/tas5805m" 2>/dev/null; then
    cd "${TMP_DIR}/tas5805m"
    make uninstall 2>/dev/null && \
      info "make uninstall completed" || \
      warn "make uninstall failed — falling back to manual removal"
    cd /
  else
    warn "Could not clone repo — falling back to manual removal"
  fi
  rm -rf "${TMP_DIR}"
fi

# Manual fallback — remove .ko and .dtbo directly
if [[ -f "${KO_PATH}" ]]; then
  rm -f "${KO_PATH}"
  depmod -a
  info "Removed ${KO_PATH} and updated depmod"
else
  info "tas58xx.ko not found at ${KO_PATH} — already removed or never installed"
fi

for OVL in "${OVERLAY_PATHS[@]}"; do
  if [[ -f "${OVL}" ]]; then
    rm -f "${OVL}"
    info "Removed overlay: ${OVL}"
  fi
done

# Remove any modprobe config left behind
rm -f /etc/modprobe.d/tas58xx.conf 2>/dev/null || true

success "TAS5805M driver removed"

# -----------------------------------------------------------------------------
# 9. Clean up /boot/firmware/config.txt
# -----------------------------------------------------------------------------
step "Restoring boot config"

CONFIG_FILE="/boot/firmware/config.txt"
[[ ! -f "${CONFIG_FILE}" ]] && CONFIG_FILE="/boot/config.txt"

if [[ -f "${CONFIG_FILE}" ]]; then
  # Remove SquarePi overlay lines
  sed -i '/# SquarePi TAS5805M HAT/d' "${CONFIG_FILE}"
  sed -i '/dtoverlay=tas58xx/d'        "${CONFIG_FILE}"

  # Re-enable onboard audio if it was disabled by installer
  if grep -q "^dtparam=audio=off" "${CONFIG_FILE}"; then
    sed -i 's/^dtparam=audio=off/dtparam=audio=on/' "${CONFIG_FILE}"
    info "Re-enabled onboard audio"
  fi

success "config.txt restored"
else
  warn "config.txt not found — skipping boot config restore"
fi

# -----------------------------------------------------------------------------
# 10. Remove SquarePi release metadata
# -----------------------------------------------------------------------------
step "Removing SquarePi release metadata"
if [[ -f /etc/squarepi-release ]]; then
  rm -f /etc/squarepi-release
  success "Removed /etc/squarepi-release"
else
  info "/etc/squarepi-release not found — skipping"
fi

# -----------------------------------------------------------------------------
# 11. Final summary
# -----------------------------------------------------------------------------
echo ""
echo -e "${BOLD}${GREEN}"
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║          Uninstall Complete!                 ║"
echo "  ╚══════════════════════════════════════════════╝"
echo -e "${NC}"
echo -e "  ${BOLD}Removed:${NC}"
echo -e "    ✓ myMPD"
echo -e "    ✓ MPD + MPC"
echo -e "    ✓ TAS5805M kernel driver"
echo -e "    ✓ Boot overlay (config.txt)"
echo -e "    ✓ apt repository and GPG key"
echo ""
echo -e "  ${YELLOW}A reboot is recommended to fully unload the driver.${NC}"
echo ""
read -r -p "  Reboot now? [y/N] " REBOOT_NOW
if [[ "${REBOOT_NOW}" =~ ^[Yy]$ ]]; then
  echo ""
  info "Rebooting..."
  sleep 2
  reboot
else
  info "Reboot skipped. Run 'sudo reboot' when ready."
fi
