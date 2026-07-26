#!/usr/bin/env python3
# Navigation stack + auto-return timers for the display service.
#
# Replaces the old model where long press cycled through a fixed SCREEN_ORDER.
# That model spent the only spare gesture on cycling, which is why the Play list
# had to stay flat with no way back. Now:
#   HOME  + long press -> push MENU
#   other + long press -> pop back toward HOME
#
# Kept out of main.py deliberately: main.py can't be imported on a dev box (it
# needs gpiozero and a real SPI panel), and this state machine is the part most
# worth testing. No I/O here, and time comes in as an argument so tests can drive
# the clock directly.

HOME = "home"
MENU = "menu"
PLAY = "play"
QUEUE = "queue"
EQ = "eq"
EQ_APPLIED = "eq_applied"
VU = "vu"
VU_STYLE = "vu_style"
SETTINGS = "settings"
NETWORK = "network"
SYSTEM = "system"
POWER = "power"
CONFIRM_RESTART = "confirm_restart"
CONFIRM_SHUTDOWN = "confirm_shutdown"

# Seconds of inactivity before falling back toward HOME. From the user's nav
# spec. HOME and the VU screens never time out: HOME is the destination, and the
# VU pages are something you deliberately sit and watch.
TIMEOUTS = {
    MENU: 20.0,
    PLAY: 20.0,
    QUEUE: 20.0,
    EQ: 20.0,
    EQ_APPLIED: 2.0,
    SETTINGS: 30.0,
    NETWORK: 20.0,
    SYSTEM: 20.0,
    POWER: 30.0,
    CONFIRM_RESTART: 10.0,
    CONFIRM_SHUTDOWN: 10.0,
}

# Screens where rotate is the screen's own action (scroll/select), so rotating
# must NOT raise the volume overlay. Everywhere else -- HOME and the VU pages --
# rotate is free and belongs to volume.
ROTATE_IS_NAVIGATION = frozenset({MENU, PLAY, QUEUE, EQ, SETTINGS, POWER, VU_STYLE})

# Screens that swallow the encoder entirely until dismissed.
MODAL = frozenset({CONFIRM_RESTART, CONFIRM_SHUTDOWN})


class Nav:
    """A stack whose bottom element is always HOME."""

    def __init__(self, now=0.0):
        self._stack = [HOME]
        self._last_input = now

    # ------------------------------------------------------------- queries
    @property
    def screen(self):
        return self._stack[-1]

    @property
    def depth(self):
        return len(self._stack)

    def at_home(self):
        return self.screen == HOME

    def rotate_adjusts_volume(self):
        return self.screen not in ROTATE_IS_NAVIGATION and self.screen not in MODAL

    # -------------------------------------------------------------- motion
    def touch(self, now):
        """Record activity so the auto-return timer restarts."""
        self._last_input = now

    def push(self, screen, now):
        # Re-pushing the current screen would make one long press need two to
        # escape, which feels like a stuck button.
        if self.screen != screen:
            self._stack.append(screen)
        self.touch(now)

    def pop(self, now):
        if len(self._stack) > 1:
            self._stack.pop()
        self.touch(now)
        return self.screen

    def go_home(self, now):
        self._stack = [HOME]
        self.touch(now)

    def long_press(self, now):
        """The one gesture common to every screen: Menu from home, Back elsewhere."""
        if self.at_home():
            self.push(MENU, now)
        else:
            self.pop(now)
        return self.screen

    # ------------------------------------------------------------ timeouts
    def timeout_for(self, screen=None):
        return TIMEOUTS.get(screen or self.screen)

    def expire(self, now):
        """Apply the auto-return rule. Returns True if the screen changed.

        A transient screen (EQ_APPLIED) falls back one level; everything else
        goes straight HOME rather than unwinding one screen per timeout, which
        would strand you three levels deep for a minute."""
        limit = self.timeout_for()
        if limit is None:
            return False
        if (now - self._last_input) < limit:
            return False
        before = self.screen
        if before == EQ_APPLIED:
            self.pop(now)
        else:
            self.go_home(now)
        return self.screen != before

    def seconds_until_expiry(self, now):
        """None when the current screen never expires. Lets the run loop sleep
        until something will actually happen instead of polling."""
        limit = self.timeout_for()
        if limit is None:
            return None
        return max(0.0, limit - (now - self._last_input))
