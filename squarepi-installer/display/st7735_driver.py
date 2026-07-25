#!/usr/bin/env python3
# Shared ST7735 init. Settings confirmed on hardware 2026-07: rotation=90 (landscape),
# x_offset=2/y_offset=1 clear the clone-board GRAM offset artifact. width/height stay
# 128x160 (native GRAM window) regardless of rotation -- the library rotates the
# image, not the window.
import board
import digitalio
from adafruit_rgb_display import st7735

BAUDRATE = 24_000_000
ROTATION = 90
X_OFFSET = 2
Y_OFFSET = 1
# Clone panels differ in color order. bgr=True fixes red-shows-as-blue
# (confirmed needed on this panel 2026-07); set False if colors ever come out
# swapped the other way on a replacement display.
BGR = True

WIDTH = 160
HEIGHT = 128


def init_display():
    cs_pin = digitalio.DigitalInOut(board.CE0)
    dc_pin = digitalio.DigitalInOut(board.D24)
    reset_pin = digitalio.DigitalInOut(board.D25)
    spi = board.SPI()
    return st7735.ST7735R(
        spi,
        cs=cs_pin,
        dc=dc_pin,
        rst=reset_pin,
        width=128,
        height=160,
        rotation=ROTATION,
        x_offset=X_OFFSET,
        y_offset=Y_OFFSET,
        bgr=BGR,
        baudrate=BAUDRATE,
    )
