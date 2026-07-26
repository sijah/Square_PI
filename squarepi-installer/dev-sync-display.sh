#!/usr/bin/env bash
# =============================================================================
# dev-sync-display.sh -- DEVELOPMENT ONLY. Not part of any release.
#
# Pushes the display module from a working-tree checkout onto a running SquarePi
# and restarts the service, so you can test uncommitted changes without an
# uninstall/reinstall cycle. update.sh cannot do this: it fetches files from
# GitHub, so it only ever sees committed-and-pushed work.
#
# This does NOT replace install.sh. It assumes --with-display has already been
# installed once (packages, SPI, systemd unit, mpd fifo). It only refreshes what
# changes while you iterate.
#
# Usage (run on the Pi, from the squarepi-installer directory):
#   sudo bash dev-sync-display.sh              # sync code + restart service
#   sudo bash dev-sync-display.sh --unit       # also refresh the systemd unit
#   sudo bash dev-sync-display.sh --mpd        # also apply mpd.conf deltas
#   sudo bash dev-sync-display.sh --all        # code + unit + mpd
#   sudo bash dev-sync-display.sh --manual     # stop service, run in foreground
#   sudo bash dev-sync-display.sh --logs       # follow the service journal
#   sudo bash dev-sync-display.sh --status     # what's installed vs. what's here
# =============================================================================
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[..]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!!]${NC} $*"; }
die()     { echo -e "${RED}[ER]${NC} $*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALLER="${SCRIPT_DIR}/install.sh"
SRC="${SCRIPT_DIR}/display"
DEST="/usr/local/lib/squarepi-display"
UNIT="squarepi-display.service"
UNIT_FILE="/etc/systemd/system/${UNIT}"

DO_UNIT=0 DO_MPD=0 MODE="sync"
UNKNOWN=()
for arg in "$@"; do
  case "$arg" in
    --unit)   DO_UNIT=1 ;;
    --mpd)    DO_MPD=1 ;;
    --all)    DO_UNIT=1; DO_MPD=1 ;;
    --manual) MODE="manual" ;;
    --logs)   MODE="logs" ;;
    --status) MODE="status" ;;
    --src=*)  SRC="${arg#--src=}" ;;
    -h|--help)
      # Print the header comment, stopping at its closing rule line.
      sed -n '3,/^# =\{10,\}$/p' "${BASH_SOURCE[0]}" \
        | grep -v '^# =\{10,\}$' | sed 's/^# \?//'
      exit 0 ;;
    *)        UNKNOWN+=("$arg") ;;
  esac
done
if [[ ${#UNKNOWN[@]} -gt 0 ]]; then
  die "Unrecognised argument(s): ${UNKNOWN[*]}  (try --help)"
fi

[[ -d "${SRC}" ]] || die "No display source at ${SRC}. Run from the squarepi-installer directory, or pass --src=/path/to/display"
# --status only reads, so don't make the common "what's on the box?" check need sudo.
if [[ "${MODE}" != "status" ]]; then
  [[ $EUID -eq 0 ]] || die "Run with sudo -- this writes to ${DEST} and restarts a service."
fi

unit_installed() { [[ -f "${UNIT_FILE}" ]]; }
unit_active()    { systemctl is-active --quiet "${UNIT}"; }

# -----------------------------------------------------------------------------
# --logs / --status: read-only, handle and exit
# -----------------------------------------------------------------------------
if [[ "${MODE}" == "logs" ]]; then
  unit_installed || die "${UNIT} is not installed. Run: sudo bash install.sh --with-display"
  exec journalctl -u "${UNIT}" -f -n 40
fi

if [[ "${MODE}" == "status" ]]; then
  echo
  if unit_installed; then
    success "${UNIT} installed  ($(systemctl is-enabled "${UNIT}" 2>/dev/null || echo 'not enabled'), $(systemctl is-active "${UNIT}" 2>/dev/null || echo inactive))"
    grep -q "mpd.service" "${UNIT_FILE}" \
      && success "unit is ordered after mpd.service" \
      || warn "unit is NOT ordered after mpd.service -- run with --unit"
  else
    warn "${UNIT} not installed -- run: sudo bash install.sh --with-display"
  fi
  if [[ -f /etc/mpd.conf ]]; then
    grep -qE '^[[:space:]]*name[[:space:]]+"vu_meter"' /etc/mpd.conf \
      && success "mpd.conf has the vu_meter fifo output" \
      || warn "mpd.conf is MISSING the vu_meter fifo output -- run with --mpd (VU meters stay flat without it)"
    grep -q '^state_file_interval' /etc/mpd.conf \
      && success "mpd.conf sets state_file_interval ($(grep -m1 '^state_file_interval' /etc/mpd.conf | tr -s ' '))" \
      || warn "mpd.conf leaves state_file_interval at MPD's 120s default -- run with --mpd"
    grep -q '^restore_paused' /etc/mpd.conf \
      && success "mpd.conf sets restore_paused -- queue restores paused, not playing" \
      || warn "mpd.conf leaves restore_paused off -- MPD will try to play USB files before they mount; run with --mpd"
  fi
  if [[ -f /etc/systemd/system/squarepi-usb-mount@.service ]]; then
    grep -q '^Before=mpd.service' /etc/systemd/system/squarepi-usb-mount@.service \
      && success "USB mount unit stops after MPD -- queue survives reboot" \
      || warn "USB mount unit stops BEFORE MPD -- your queue is wiped on every shutdown; run with --mpd"
  fi
  if [[ -f /usr/local/bin/squarepi-usb-umount.sh ]]; then
    grep -q 'is-system-running' /usr/local/bin/squarepi-usb-umount.sh \
      && success "USB unmount helper has the shutdown guard" \
      || warn "USB unmount helper lacks the shutdown guard -- run with --mpd"
  else
    warn "/etc/mpd.conf not found"
  fi
  echo
  info "Installed vs. working tree:"
  if [[ -d "${DEST}" ]]; then
    CHANGED=0
    shopt -s nullglob
    for f in "${SRC}"/*.py; do
      base="$(basename "$f")"
      if [[ ! -f "${DEST}/${base}" ]]; then
        echo "    + ${base} (not installed)"; CHANGED=1
      elif ! cmp -s "$f" "${DEST}/${base}"; then
        echo "    M ${base}"; CHANGED=1
      fi
    done
    shopt -u nullglob
    [[ ${CHANGED} -eq 0 ]] && success "every .py file matches -- nothing to sync"
  else
    warn "${DEST} does not exist yet"
  fi
  echo
  exit 0
fi

# -----------------------------------------------------------------------------
# 1. Sync the code
# -----------------------------------------------------------------------------
unit_installed || warn "${UNIT} is not installed yet. Syncing files anyway, but you still need \
'sudo bash install.sh --with-display' once for packages, SPI and the service."

# Glob into an array rather than piping ls into wc: under `set -o pipefail` a
# failing ls would take the whole script down.
shopt -s nullglob
PY_FILES=("${SRC}"/*.py)
shopt -u nullglob
[[ ${#PY_FILES[@]} -gt 0 ]] || die "No .py files in ${SRC} -- wrong directory?"
info "Syncing ${#PY_FILES[@]} Python files from ${SRC}"
WAS_ACTIVE=0
if unit_active; then WAS_ACTIVE=1; fi

mkdir -p "${DEST}"
# Copy contents rather than rm -rf the directory: the running service has its cwd
# here, and pulling the directory out from under it makes for confusing failures.
cp -r "${SRC}/." "${DEST}/"
# Stale bytecode from a previous version shadows nothing useful and has caused
# "but I fixed that" confusion before.
find "${DEST}" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
success "Code synced to ${DEST}"

# -----------------------------------------------------------------------------
# 2. Optionally refresh the systemd unit
#    Extracted from install.sh rather than duplicated here, so the two can't drift.
# -----------------------------------------------------------------------------
if [[ ${DO_UNIT} -eq 1 ]]; then
  info "Regenerating ${UNIT} from install.sh"
  [[ -f "${INSTALLER}" ]] || die "install.sh not found next to this script; cannot regenerate the unit"

  # No mtime-based staleness check here on purpose. An earlier version compared
  # install.sh's mtime against the newest display/*.py to catch "you synced the
  # Python but not the installer" -- but scp stamps every copied file with the
  # copy time, so within a folder copy the mtimes land in arbitrary order and it
  # cried wolf on perfectly current checkouts. The diff and the "Resulting
  # ordering" line below are direct evidence of what was written, which is
  # strictly better than guessing from timestamps.
  UNIT_BLOCK="$(sed -n "\|^cat > ${UNIT_FILE} <<EOF\$|,/^EOF\$/p" "${INSTALLER}")"
  [[ -n "${UNIT_BLOCK}" ]] || die "Couldn't find the ${UNIT} heredoc in install.sh -- it may have been \
restructured. Re-run 'sudo bash install.sh --with-display' instead (no uninstall needed)."

  # Report what actually changed rather than a blanket success: "refreshed" while
  # writing byte-identical stale content is the kind of lie that costs an hour.
  UNIT_BEFORE="$(mktemp)"
  if [[ -f "${UNIT_FILE}" ]]; then cp "${UNIT_FILE}" "${UNIT_BEFORE}"; else : > "${UNIT_BEFORE}"; fi
  DISPLAY_DEST="${DEST}" eval "${UNIT_BLOCK}"
  if cmp -s "${UNIT_BEFORE}" "${UNIT_FILE}"; then
    info "Unit was already identical to install.sh's -- nothing changed"
  else
    systemctl daemon-reload
    success "Unit rewritten from install.sh. Changes:"
    { diff -u "${UNIT_BEFORE}" "${UNIT_FILE}" | tail -n +3 | sed 's/^/      /'; } || true
  fi
  rm -f "${UNIT_BEFORE}"
  info "Resulting ordering: $(grep -E '^(After|Wants)=' "${UNIT_FILE}" | tr '\n' ' ')"
fi

# -----------------------------------------------------------------------------
# 3. Optionally apply the mpd.conf deltas
# -----------------------------------------------------------------------------
if [[ ${DO_MPD} -eq 1 ]]; then
  [[ -f /etc/mpd.conf ]] || die "/etc/mpd.conf not found -- run install.sh first"
  MPD_TOUCHED=0

  if ! grep -qE '^[[:space:]]*name[[:space:]]+"vu_meter"' /etc/mpd.conf; then
    cat >> /etc/mpd.conf <<'EOF'

audio_output {
    type    "fifo"
    name    "vu_meter"
    path    "/tmp/mpd.fifo"
    format  "44100:16:2"
}
EOF
    success "Added the vu_meter fifo output"
    MPD_TOUCHED=1
  else
    info "vu_meter fifo output already present"
  fi

  if ! grep -q '^state_file_interval' /etc/mpd.conf; then
    if grep -q '^state_file' /etc/mpd.conf; then
      sed -i '/^state_file /a state_file_interval "30"' /etc/mpd.conf
    else
      echo 'state_file_interval "30"' >> /etc/mpd.conf
    fi
    success "Set state_file_interval to 30s (was MPD's 120s default)"
    MPD_TOUCHED=1
  else
    info "state_file_interval already set"
  fi

  # USB drives are mounted by udev AFTER mpd.service starts, so a queue of USB
  # tracks restored in the "play" state has MPD erroring through files that aren't
  # mounted yet. Restore paused and let the user (or the display's Resume Queue)
  # start it once the drive is up.
  if ! grep -q '^restore_paused' /etc/mpd.conf; then
    echo 'restore_paused     "yes"' >> /etc/mpd.conf
    success "Set restore_paused to yes (queue restores intact, but paused)"
    MPD_TOUCHED=1
  else
    info "restore_paused already set"
  fi

  # Regenerate the USB unmount helper from install.sh, for the shutdown guard.
  # Without it, systemd stops the mount unit before mpd, the refresh purges every
  # USB song from the database, MPD prunes those songs from the queue (keeping only
  # the one playing), and MPD then saves that emptied queue -- which is why the
  # queue never survived a reboot for anyone with music on a USB drive.
  # The mount unit's ordering relative to mpd.service is what actually protects the
  # queue: stopped before MPD, the drive vanishes while MPD is alive and MPD's
  # inotify watch purges those songs (and prunes them from the queue) before its
  # state file is written. Regenerated from install.sh so the two can't drift.
  USB_UNIT="/etc/systemd/system/squarepi-usb-mount@.service"
  USB_UNIT_BLOCK="$(sed -n "\|^cat > ${USB_UNIT} <<'EOF'\$|,/^EOF\$/p" "${INSTALLER}" || true)"
  if [[ -z "${USB_UNIT_BLOCK}" ]]; then
    warn "Couldn't find the USB mount unit heredoc in install.sh -- skipping it"
  else
    USB_UNIT_BEFORE="$(mktemp)"
    if [[ -f "${USB_UNIT}" ]]; then cp "${USB_UNIT}" "${USB_UNIT_BEFORE}"; else : > "${USB_UNIT_BEFORE}"; fi
    eval "${USB_UNIT_BLOCK}"
    if cmp -s "${USB_UNIT_BEFORE}" "${USB_UNIT}"; then
      info "USB mount unit already up to date"
    else
      systemctl daemon-reload
      success "USB mount unit rewritten. Changes:"
      { diff -u "${USB_UNIT_BEFORE}" "${USB_UNIT}" | tail -n +3 | sed 's/^/      /'; } || true
      # Running instances keep the old ordering until they are restarted, and a
      # restart means unmount+remount -- which is exactly the purge we're avoiding.
      # Safer to say so than to silently do it under a playing queue.
      shopt -s nullglob
      ACTIVE_MOUNTS=()
      while read -r u; do [[ -n "$u" ]] && ACTIVE_MOUNTS+=("$u"); done < <(
        systemctl list-units --state=active --no-legend 'squarepi-usb-mount@*' 2>/dev/null | awk '{print $1}')
      shopt -u nullglob
      if [[ ${#ACTIVE_MOUNTS[@]} -gt 0 ]]; then
        for u in "${ACTIVE_MOUNTS[@]}"; do info "Active mount unit: ${u}"; done
        info "daemon-reload recomputes dependencies for units that are already running,"
        info "so the new ordering should apply on this shutdown -- but if the queue is"
        info "still lost after the next reboot, try one more: a freshly started instance"
        info "definitely has it. (Restarting the unit now would unmount the drive and"
        info "trigger the very purge we're fixing, so this doesn't do that for you.)"
      fi
    fi
    rm -f "${USB_UNIT_BEFORE}"
    grep -q '^Before=mpd.service' "${USB_UNIT}" \
      && success "mount unit is ordered Before mpd.service (stops after MPD)" \
      || warn "mount unit is NOT ordered Before mpd.service -- install.sh is stale"
  fi

  # Both USB helper scripts, regenerated from install.sh.
  for HELPER in /usr/local/bin/squarepi-usb-mount.sh /usr/local/bin/squarepi-usb-umount.sh; do
    HBLOCK="$(sed -n "\|^cat > ${HELPER} <<EOF\$|,/^EOF\$/p" "${INSTALLER}" || true)"
    if [[ -z "${HBLOCK}" ]]; then
      warn "Couldn't find $(basename "${HELPER}") in install.sh -- skipping"
      continue
    fi
    HBEFORE="$(mktemp)"
    if [[ -f "${HELPER}" ]]; then cp "${HELPER}" "${HBEFORE}"; else : > "${HBEFORE}"; fi
    MUSIC_DIR="$(sed -n 's/^music_directory[[:space:]]*"\(.*\)".*/\1/p' /etc/mpd.conf | head -1)"
    [[ -n "${MUSIC_DIR}" ]] || MUSIC_DIR="/var/lib/mpd/music"
    USB_MOUNT_ROOT="${MUSIC_DIR}/usb" eval "${HBLOCK}"
    chmod +x "${HELPER}"
    if cmp -s "${HBEFORE}" "${HELPER}"; then
      info "$(basename "${HELPER}") already up to date"
    else
      success "$(basename "${HELPER}") rewritten"
    fi
    rm -f "${HBEFORE}"
  done
  grep -q 'is-active --quiet mpd' /usr/local/bin/squarepi-usb-mount.sh 2>/dev/null \
    && success "mount helper skips the DB refresh when MPD is down (no boot delay)" \
    || warn "mount helper will block boot waiting for a down MPD -- install.sh is stale"

  grep -q 'is-system-running' /usr/local/bin/squarepi-usb-umount.sh 2>/dev/null \
    && success "unmount helper skips the DB refresh during shutdown" \
    || warn "unmount helper lacks the shutdown guard -- install.sh is stale"

  if [[ ${MPD_TOUCHED} -eq 1 ]]; then
    systemctl restart mpd 2>/dev/null || warn "Could not restart mpd -- do it yourself"
    info "MPD restarted. Note this clears the current queue's playback position."
  fi
fi

# -----------------------------------------------------------------------------
# 4. Run it
# -----------------------------------------------------------------------------
if [[ "${MODE}" == "manual" ]]; then
  if unit_active; then
    info "Stopping ${UNIT} so it releases the GPIO pins"
    systemctl stop "${UNIT}"
    # gpiozero/lgpio hold the pins until the process is fully gone; starting a
    # second main.py too early fails with lgpio.error: 'GPIO busy'.
    for _ in $(seq 1 20); do
      unit_active || break
      sleep 0.25
    done
  fi
  echo
  warn "Foreground run. Ctrl+C to stop -- do NOT Ctrl+Z, a suspended process keeps"
  warn "the GPIO pins and the next run fails with lgpio.error: 'GPIO busy'."
  [[ ${WAS_ACTIVE} -eq 1 ]] && info "Afterwards: sudo systemctl start ${UNIT}"
  echo
  cd "${DEST}"
  exec python3 main.py
fi

if unit_installed; then
  info "Restarting ${UNIT}"
  systemctl restart "${UNIT}"
  sleep 2
  if unit_active; then
    success "${UNIT} is running"
  else
    warn "${UNIT} did not come up. Last 20 lines:"
    journalctl -u "${UNIT}" -n 20 --no-pager || true
    exit 1
  fi
fi

echo
success "Done. Follow logs with:  sudo bash dev-sync-display.sh --logs"
info "Run in the foreground to see tracebacks:  sudo bash dev-sync-display.sh --manual"
