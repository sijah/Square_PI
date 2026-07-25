#!/usr/bin/env python3
# Hardware bring-up test for KY-040 rotary encoder. Wiring: CLK=GPIO17, DT=GPIO27, SW=GPIO22.
# Install deps: sudo apt install python3-gpiozero (usually preinstalled on Raspberry Pi OS)
# If direction feels backwards, swap the CLK/DT pin numbers below.

from signal import pause

from gpiozero import Button, RotaryEncoder

encoder = RotaryEncoder(17, 27, max_steps=0)
button = Button(22, pull_up=True, bounce_time=0.05)

encoder.when_rotated = lambda: print(f"position: {encoder.steps}")
button.when_pressed = lambda: print("button pressed")

print("Turn the knob or press the button. Ctrl+C to exit.")
pause()
