#!/usr/bin/env python3
# Hardware bring-up test for ST7735 1.8" TFT. Wiring: CS=GPIO8(CE0), DC=GPIO24, RESET=GPIO25, MOSI=GPIO10, SCK=GPIO11.
# Install deps: sudo pip3 install --break-system-packages adafruit-circuitpython-rgb-display adafruit-blinka pillow
# Enable SPI first: sudo raspi-config -> Interface Options -> SPI (or add "dtparam=spi=on" to /boot/firmware/config.txt)

import board
import digitalio
from PIL import Image, ImageDraw
from adafruit_rgb_display import st7735

cs_pin = digitalio.DigitalInOut(board.CE0)
dc_pin = digitalio.DigitalInOut(board.D24)
reset_pin = digitalio.DigitalInOut(board.D25)
spi = board.SPI()

# Clone-board GRAM offset fix: a stray line at one edge means the panel's real
# addressable window doesn't start at (0,0). x_offset shifts along the native
# width(128) axis, y_offset along the native height(160) axis — these are NOT
# swapped by rotation, so after rotation=90 the offset that clears the visual
# "bottom" line vs the visual "side" line may not be the one you'd guess. Nudge
# both in small steps (0-3 range is typical for 128x160 panels) until both
# stray lines disappear.
X_OFFSET = 2
Y_OFFSET = 1

# width/height below are the panel's native (portrait) GRAM window and stay
# 128x160 regardless of rotation — the library rotates the image, not the window.
# If landscape comes out upside down, try rotation=270 instead of 90.
disp = st7735.ST7735R(
    spi,
    cs=cs_pin,
    dc=dc_pin,
    rst=reset_pin,
    width=128,
    height=160,
    rotation=90,
    x_offset=X_OFFSET,
    y_offset=Y_OFFSET,
    baudrate=24_000_000,
)

image = Image.new("RGB", (160, 128), (0, 0, 0))
draw = ImageDraw.Draw(image)
draw.text((45, 55), "Hello World", fill=(255, 255, 255))
disp.image(image)

print("Sent 'Hello World' to the display. Ctrl+C to exit.")
input()
