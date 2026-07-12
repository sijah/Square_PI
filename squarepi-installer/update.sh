#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 sijah
# =============================================================================
#  SquarePi Updater — brings ANY older SquarePi install up to the latest
#  release IN PLACE, without the destructive full reinstall.
#
#  This script is CUMULATIVE, not a one-shot migration for a single version
#  pair. It is fetched fresh from `main` on every run (see README's `curl |
#  sudo bash` one-liner), so whatever is the latest committed version of this
#  file is what every user — cloned or not — runs. That only stays true if
#  every release adds its deltas here instead of replacing them. See
#  "ADDING THE NEXT RELEASE'S DELTA" below before editing this file.
#
#  What it PRESERVES (never resets): your saved EQ curve, your chosen Analog
#  Gain, and your BT volume. It only enforces safety ceilings and service fixes.
#
#  Idempotent — safe to run more than once, and safe to run from ANY older
#  installed version straight to the latest (every step below checks system
#  state before acting, not the installed version number — so skipping
#  releases is fine).
#
#  Usage:
#    sudo bash update.sh
#
# =============================================================================
#  ADDING THE NEXT RELEASE'S DELTA (do this every time you cut a release)
# =============================================================================
#  1. Bump TARGET_VER below to the new version. This is the only line that
#     MUST change every release.
#  2. Add a new "### vX.Y.Z DELTA" block further down, just above the
#     "ALWAYS-LAST STEPS" marker near the bottom of this file. Copy the
#     v1.6.0 block's shape exactly:
#       if version_lt "${CURRENT_VER}" "vX.Y.Z"; then
#         ...your steps, each ALSO guarded on system state (unit_exists,
#         grep -q, a control's current value, dkms status)...
#         APPLIED+=("bullet describing what this block did" ...)
#       else
#         info "vX.Y.Z delta already applied ... — skipping"
#       fi
#     The outer version_lt gate means an install already past vX.Y.Z skips
#     the whole block on every future run (fast) instead of re-checking it
#     forever; the inner state guards are a second layer that self-heals if
#     something in here ever got reverted by hand. Both layers matter.
#  3. Do NOT delete, rewrite, or renumber a prior release's DELTA block. An
#     install that skipped straight from 1.5.2 to the new version still needs
#     every block in between to run — each one's own version_lt gate decides
#     for itself whether it's still needed.
#  4. If the change is user-visible, it belongs in APPLIED (shows in the
#     "Applied:" summary automatically — no separate list to maintain) plus
#     the changelog/README update section.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(realpath "$0")")" && pwd)"

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
TARGET_VER="1.6.0"  # <-- bump this every release (see guide above)
CARD="LouderRaspberry"
RELEASE_FILE="/etc/squarepi-release"
EQ_SERVER_DEST="/usr/local/bin/squarepi-eq-server.py"
MYMPD_SCRIPTS_DIR="/var/lib/mympd/scripts"
RAW_BASE="https://raw.githubusercontent.com/sijah/Square_PI/main/squarepi-installer"
TAS_DRIVER_REPO="https://github.com/sonocotta/tas5805m-driver-for-raspbian"

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

# A service exists on this system?
unit_exists() { [[ -f "/etc/systemd/system/$1" ]]; }

# -----------------------------------------------------------------------------
# Banner
# -----------------------------------------------------------------------------
echo -e "${BOLD}${CYAN}"
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║            SquarePi Updater                  ║"
printf "  ║  %-30s by Sijah AK  ║\n" "→ v${TARGET_VER}"
echo "  ╚══════════════════════════════════════════════╝"
echo -e "${NC}"

# -----------------------------------------------------------------------------
# 1. Root + sanity
# -----------------------------------------------------------------------------
step "Checking permissions"
[[ $EUID -ne 0 ]] && error "Please run as root: sudo bash update.sh"
success "Running as root"

CURRENT_VER="unknown"
if [[ -f "${RELEASE_FILE}" ]]; then
  CURRENT_VER="$(sed -n 's/^VERSION=//p' "${RELEASE_FILE}" | head -n1)"
  [[ -z "${CURRENT_VER}" ]] && CURRENT_VER="unknown"
else
  warn "${RELEASE_FILE} not found — this doesn't look like a SquarePi install."
  warn "If this is a fresh system, run install.sh instead. Continuing anyway (best effort)."
fi

# -----------------------------------------------------------------------------
# 1b. Check whether an update is actually needed, and ask before touching
#     anything. `version_lt A B` is true when A is strictly older than B
#     (GNU sort -V, present on Raspberry Pi OS / Debian). "unknown" always
#     counts as older than any real version, so a fresh/undetected install
#     runs every delta block below. This same helper is what each release's
#     delta block is gated on further down — see the guide above.
# -----------------------------------------------------------------------------
version_lt() {
  [[ "$1" == "unknown" ]] && return 0
  [[ "$1" != "$2" ]] && [[ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -n1)" == "$1" ]]
}

# Bullet lines actually applied this run — each gated delta block below
# appends to this; the closing summary prints only what really happened.
APPLIED=()

if ! version_lt "${CURRENT_VER}" "${TARGET_VER}"; then
  success "Already up to date — installed version is ${CURRENT_VER} (latest is ${TARGET_VER})"
  info "Nothing to do. Exiting."
  exit 0
fi

echo ""
echo -e "  ${BOLD}Update available:${NC} ${CURRENT_VER} → ${GREEN}${TARGET_VER}${NC}"
echo ""
if [[ "${SQUAREPI_YES:-0}" == "1" ]]; then
  info "SQUAREPI_YES=1 — proceeding without prompting"
else
  printf "  Update SquarePi to v${TARGET_VER} now? [Y/n] "
  read -r DO_UPDATE < /dev/tty 2>/dev/null || DO_UPDATE="n"
  if [[ "${DO_UPDATE}" =~ ^[Nn]$ ]]; then
    info "Update cancelled — nothing was changed."
    exit 0
  fi
fi
info "Updating ${CURRENT_VER} → ${TARGET_VER}"

# Source the new eq-server.py / repo files from the local checkout when present
# (a `git pull` on the Pi gives you the newest ones); otherwise fetch from GitHub.
fetch_repo_file() {  # fetch_repo_file <name> <dest>
  local name="$1" dest="$2"
  if [[ -f "${SCRIPT_DIR}/${name}" ]]; then
    cp "${SCRIPT_DIR}/${name}" "${dest}"
  else
    curl -fsSL "${RAW_BASE}/${name}" -o "${dest}" || return 1
  fi
}

# =============================================================================
# ### v1.6.0 DELTA — in-place updater, mandatory BT/EQ, EQ gain-read fix
# ### (released 2026-07-12; brings any 1.5.x install forward)
# ###
# ### Gated on version, not just internal state: an install already at 1.6.0+
# ### skips this whole block on every future run instead of re-checking/
# ### re-writing units it already fixed. (The internal unit_exists/grep -q/
# ### dkms-status guards inside stay too, as a second layer — self-healing if
# ### something in here ever got reverted by hand.)
# =============================================================================
if version_lt "${CURRENT_VER}" "1.6.0"; then

if [[ -f "${EQ_SERVER_DEST}" ]] || unit_exists squarepi-eq.service; then
  step "Updating EQ web server"
  if fetch_repo_file "eq-server.py" "${EQ_SERVER_DEST}"; then
    chmod +x "${EQ_SERVER_DEST}"
    success "eq-server.py updated"
  else
    warn "Could not fetch eq-server.py — leaving the existing one in place"
  fi
else
  info "EQ web server not installed — skipping eq-server.py update"
fi

# -----------------------------------------------------------------------------
# 3. squarepi-eq.service — remove the shutdown store-on-stop
#    (it captured the transient -15.5 dB mute and restored the amp near-silent)
# -----------------------------------------------------------------------------
if unit_exists squarepi-eq.service; then
  step "Fixing EQ service (drop shutdown mute persistence)"
  if grep -qE '^\s*ExecStop=.*alsactl store' /etc/systemd/system/squarepi-eq.service; then
    sed -i '/^\s*ExecStop=.*alsactl store/d' /etc/systemd/system/squarepi-eq.service
    success "Removed ExecStop=alsactl store from squarepi-eq.service"
  else
    info "squarepi-eq.service already clean — nothing to remove"
  fi
fi

# -----------------------------------------------------------------------------
# 4. Boot-ordering safety — gain must land before ANY audio source can play.
#    Rewrite alsa-restore + eq-init units to the canonical v1.6.0 ordering.
#    Only rewrite units that already exist (some older installs may lack the EQ UI).
# -----------------------------------------------------------------------------
AUDIO_PRODUCERS="mpd.service squarepi-eq.service bluealsa-aplay.service shairport-sync.service raspotify.service upmpdcli.service"

if unit_exists squarepi-alsa-restore.service; then
  step "Updating ALSA-restore ordering (gain before every source)"
  cat > /etc/systemd/system/squarepi-alsa-restore.service <<EOF
[Unit]
Description=SquarePi ALSA state restore
After=sound.target
# Restore the saved (safe) gain BEFORE any audio producer can emit I2S signal —
# not just MPD but every source path (BT, AirPlay, Spotify, DLNA).
Before=${AUDIO_PRODUCERS}

[Service]
Type=oneshot
ExecStart=/usr/sbin/alsactl restore
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
  systemctl enable squarepi-alsa-restore >/dev/null 2>&1 || true
  success "squarepi-alsa-restore.service ordered before all sources"
fi

if unit_exists squarepi-eq-init.service; then
  step "Updating first-boot init (card-wait + ordering)"
  # Refresh the init script — it is guarded by /etc/squarepi-initialized, so on an
  # already-initialised system this does NOT re-run and does NOT touch your gains.
  cat > /usr/local/bin/squarepi-eq-init.sh <<'INITEOF'
#!/bin/bash
# Sets all 15 EQ bands to 0 dB (flat) on first boot, then marks itself done.
CARD="LouderRaspberry"
BANDS=("00020 Hz" "00032 Hz" "00050 Hz" "00080 Hz" "00125 Hz" "00200 Hz"
       "00315 Hz" "00500 Hz" "00800 Hz" "01250 Hz" "02000 Hz" "03150 Hz"
       "05000 Hz" "08000 Hz" "16000 Hz")

# Wait for the card + its "Analog Gain" control before touching anything. If it
# never appears, bail WITHOUT marking first-boot done so the next boot retries —
# otherwise Analog Gain would be left at the chip default (0 dB = full output).
for _try in $(seq 1 30); do
  if amixer -c "$CARD" cget "name=Analog Gain" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
if ! amixer -c "$CARD" cget "name=Analog Gain" >/dev/null 2>&1; then
  echo "squarepi-eq-init: card '$CARD' not ready after 30s — will retry next boot" >&2
  exit 0
fi

for b in "${BANDS[@]}"; do
  amixer -c "$CARD" sset "$b" 0 2>/dev/null || true
done

# Pin Digital Volume to 0 dB (value 103); above that applies up to +24 dB boost.
amixer -c "$CARD" cset "name=Digital Volume" 103 2>/dev/null || true
# First-boot Analog Gain default: -10 dB (value 11 on the 0..31 / -15.5..0 scale).
amixer -c "$CARD" cset "name=Analog Gain" 11 2>/dev/null || true

alsactl store 2>/dev/null || true
touch /etc/squarepi-initialized
INITEOF
  chmod +x /usr/local/bin/squarepi-eq-init.sh

  cat > /etc/systemd/system/squarepi-eq-init.service <<UNITEOF
[Unit]
Description=SquarePi first-boot EQ initialisation (flat)
After=sound.target
# Every audio producer starts AFTER the safe first-boot gain is applied.
Before=${AUDIO_PRODUCERS}
ConditionPathExists=!/etc/squarepi-initialized

[Service]
Type=oneshot
ExecStart=/usr/local/bin/squarepi-eq-init.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
UNITEOF
  systemctl enable squarepi-eq-init >/dev/null 2>&1 || true
  success "squarepi-eq-init hardened (card-wait) and ordered before all sources"
fi

# -----------------------------------------------------------------------------
# 5. Power-control Lua tiles for myMPD (Restart / Shut down)
# -----------------------------------------------------------------------------
if unit_exists squarepi-eq.service && [[ -d "${MYMPD_SCRIPTS_DIR}" ]]; then
  step "Installing Power control tiles for myMPD"
  cat > "${MYMPD_SCRIPTS_DIR}/Power_Restart.lua" <<'LUAEOF'
-- {"order":18,"file":"","version":0,"arguments":[]}
os.execute([[curl -s -X POST -H "Content-Type: application/json" -d '{"action":"restart"}' http://127.0.0.1:8081/api/power]])
LUAEOF
  chmod 644 "${MYMPD_SCRIPTS_DIR}/Power_Restart.lua"

  cat > "${MYMPD_SCRIPTS_DIR}/Power_Shutdown.lua" <<'LUAEOF'
-- {"order":19,"file":"","version":0,"arguments":[]}
os.execute([[curl -s -X POST -H "Content-Type: application/json" -d '{"action":"shutdown"}' http://127.0.0.1:8081/api/power]])
LUAEOF
  chmod 644 "${MYMPD_SCRIPTS_DIR}/Power_Shutdown.lua"
  systemctl restart mympd 2>/dev/null || true
  success "Power_Restart / Power_Shutdown tiles installed"
fi

# -----------------------------------------------------------------------------
# 6. mpd.conf — predictable per-track level
# -----------------------------------------------------------------------------
if [[ -f /etc/mpd.conf ]]; then
  step "Setting replaygain to off (predictable levels)"
  if grep -qE '^\s*replaygain' /etc/mpd.conf; then
    sed -i 's/^\s*replaygain.*/replaygain          "off"/' /etc/mpd.conf
  else
    echo 'replaygain          "off"' >> /etc/mpd.conf
  fi
  success "replaygain set to off"
fi

# -----------------------------------------------------------------------------
# 7. Runtime gain ceiling — enforce the SAFE CEILING only, never reset choices.
#    Digital Volume is lowered to 103 ONLY if it is currently higher (boost).
#    Analog Gain is deliberately left untouched (it's the owner's choice).
# -----------------------------------------------------------------------------
if amixer -c "$CARD" cget "name=Digital Volume" >/dev/null 2>&1; then
  step "Enforcing safe Digital Volume ceiling"
  DIGVOL="$(amixer -c "$CARD" cget "name=Digital Volume" 2>/dev/null \
            | sed -n 's/.*: values=\([0-9-]*\).*/\1/p' | head -n1)"
  if [[ -n "${DIGVOL}" && "${DIGVOL}" -gt 103 ]]; then
    amixer -c "$CARD" cset "name=Digital Volume" 103 >/dev/null 2>&1 || true
    alsactl store 2>/dev/null || true
    success "Digital Volume was ${DIGVOL} (boost) — capped to 103 (0 dB) and saved"
  else
    info "Digital Volume already at/below the 0 dB ceiling (${DIGVOL:-?}) — left as-is"
  fi
  info "Analog Gain left untouched (your chosen level is preserved)"
else
  warn "Audio card '${CARD}' not present — skipping runtime gain check (re-run after a reboot)"
fi

# -----------------------------------------------------------------------------
# 8. DKMS driver migration — only if the driver isn't already DKMS-managed.
#    This is the 1.5.1 fix (module survives kernel updates). Non-fatal.
# -----------------------------------------------------------------------------
step "Checking audio driver (DKMS)"
if command -v dkms >/dev/null 2>&1 && dkms status tas58xx 2>/dev/null | grep -q .; then
  success "Driver already managed by DKMS — no migration needed"
else
  warn "Driver is NOT under DKMS — migrating so it survives kernel updates"
  if apt-get install -y -qq dkms; then
    DRV_NAME="tas58xx"; DRV_VER="1.0"; DRV_SRC="/usr/src/${DRV_NAME}-${DRV_VER}"
    dkms remove -m "${DRV_NAME}" -v "${DRV_VER}" --all 2>/dev/null || true
    rm -rf "${DRV_SRC}"
    if git clone --depth=1 "${TAS_DRIVER_REPO}" "${DRV_SRC}" 2>/dev/null; then
      cat > "${DRV_SRC}/dkms.conf" <<EOF
PACKAGE_NAME="${DRV_NAME}"
PACKAGE_VERSION="${DRV_VER}"
BUILT_MODULE_NAME[0]="${DRV_NAME}"
DEST_MODULE_LOCATION[0]="/updates"
MAKE[0]="make KDIR=/lib/modules/\${kernelver}/build"
CLEAN="make KDIR=/lib/modules/\${kernelver}/build clean"
AUTOINSTALL="yes"
EOF
      if dkms add -m "${DRV_NAME}" -v "${DRV_VER}" 2>/dev/null \
         && dkms build -m "${DRV_NAME}" -v "${DRV_VER}" \
         && dkms install -m "${DRV_NAME}" -v "${DRV_VER}" --force; then
        # ONLY now that DKMS has a working module installed (in /updates) is it safe
        # to remove the old pre-DKMS module — a 1.5.0 `make install` lands it in
        # .../extra/ (older builds may use kernel/). Doing this before a successful
        # build would risk deleting a working driver and leaving no audio.
        find /lib/modules -name "tas58xx.ko*" \
             \( -path "*/extra/*" -o -path "*/kernel/*" \) -delete 2>/dev/null || true
        depmod -a 2>/dev/null || true
        success "Driver migrated to DKMS (auto-rebuilds on kernel updates)"
      else
        warn "DKMS build/install failed (kernel headers?) — your existing module is left untouched and still works; retry later"
      fi
    else
      warn "Could not clone driver repo — skipped DKMS migration (existing module still works)"
    fi
  else
    warn "dkms package install failed — skipped migration (existing module still works)"
  fi
fi

APPLIED+=(
  "Power control + latest EQ web server"
  "Shutdown-mute persistence fix"
  "Boot ordering — gain applied before every source"
  "First-boot init hardened (card-wait)"
  "Digital Volume 0 dB ceiling + replaygain off"
  "DKMS driver check/migration"
)

else
  info "v1.6.0 delta already applied (installed version ${CURRENT_VER}) — skipping"
fi
# --- end v1.6.0 gate ---

# =============================================================================
# ### END v1.6.0 DELTA
# ###
# ### >>> The next release's "### vX.Y.Z DELTA" block goes HERE, above this
# ###     line. Do not add new steps below — steps 9-10 below must always run
# ###     last, after every release's delta has been applied. <<<
# =============================================================================

# =============================================================================
# ALWAYS-LAST STEPS — run after every delta block above, every release.
# =============================================================================

# -----------------------------------------------------------------------------
# 9. Reload units + restart the services we touched
# -----------------------------------------------------------------------------
step "Reloading systemd and restarting services"
systemctl daemon-reload
if unit_exists squarepi-eq.service && systemctl is-enabled --quiet squarepi-eq 2>/dev/null; then
  systemctl restart squarepi-eq 2>/dev/null || true
  info "squarepi-eq restarted"
fi
success "systemd reloaded"

# -----------------------------------------------------------------------------
# 10. Bump the recorded version
# -----------------------------------------------------------------------------
if [[ -f "${RELEASE_FILE}" ]]; then
  if grep -q '^VERSION=' "${RELEASE_FILE}"; then
    sed -i "s/^VERSION=.*/VERSION=${TARGET_VER}/" "${RELEASE_FILE}"
  else
    echo "VERSION=${TARGET_VER}" >> "${RELEASE_FILE}"
  fi
  success "Recorded version ${TARGET_VER} in ${RELEASE_FILE}"
fi

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo ""
echo -e "${BOLD}${GREEN}"
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║        Update to v${TARGET_VER} complete!            ║"
echo "  ╚══════════════════════════════════════════════╝"
echo -e "${NC}"
if [[ ${#APPLIED[@]} -gt 0 ]]; then
  echo -e "  ${BOLD}Applied:${NC}"
  for line in "${APPLIED[@]}"; do
    echo -e "    ✓ ${line}"
  done
else
  echo -e "  ${BOLD}Applied:${NC} nothing new — every delta was already in place."
fi
echo ""
echo -e "  ${BOLD}Preserved:${NC} your EQ curve, Analog Gain, and BT volume."
echo ""
echo -e "  ${YELLOW}A reboot is recommended so the new service ordering takes effect.${NC}"
echo ""
if [[ "${SQUAREPI_YES:-0}" == "1" ]]; then
  REBOOT_NOW="n"
else
  printf "  Reboot now? [y/N] "
  read -r REBOOT_NOW < /dev/tty 2>/dev/null || REBOOT_NOW="n"
fi
if [[ "${REBOOT_NOW}" =~ ^[Yy]$ ]]; then
  info "Rebooting..."
  sleep 2
  reboot
else
  info "Reboot skipped. Run 'sudo reboot' when ready."
fi
