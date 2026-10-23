#!/usr/bin/env python3
"""Write a 128-byte EDID for a monitor named "TV screen": 3840x2160 at 60 Hz, or 1920x1080.

tv-screen plugs this into the evdi virtual display, so the desktop sees a normal monitor.
Usage: python3 -I laptop/make-edid.py laptop/tv-screen-4k.edid [1080p]
With "1080p", 1920x1080 is the only detailed mode (the original version).
"""
import sys


def manufacturer(code):
    a, b, c = (ord(ch) - 64 for ch in code)
    return ((a << 10) | (b << 5) | c).to_bytes(2, "big")


def text_descriptor(tag, text):
    body = text.encode("ascii")[:13]
    if len(body) < 13:
        body += b"\n" + b" " * (12 - len(body))
    return bytes([0, 0, 0, tag, 0]) + body


edid = bytearray()
edid += bytes([0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00])  # header
edid += manufacturer("LNX")                       # same ID as the kernel's built-in EDIDs
edid += (1).to_bytes(2, "little")                 # product code
edid += (1).to_bytes(4, "little")                 # serial number
edid += bytes([1, 2026 - 1990])                   # week, year
edid += bytes([1, 3])                             # EDID 1.3
edid += bytes([0x80, 144, 81, 120, 0x0A])         # digital input, 144x81 cm, gamma 2.2, RGB, preferred timing
edid += bytes([0xEE, 0x91, 0xA3, 0x54, 0x4C, 0x99, 0x26, 0x0F, 0x50, 0x54])  # sRGB chromaticity
edid += bytes([0, 0, 0])                          # no established timings
edid += bytes([0xD1, 0xC0]) + bytes([1, 1]) * 7   # standard timing: 1920x1080 16:9 60 Hz
# Detailed timings, 1439x809 mm, separate sync H+ V+
# CEA-861 1080p60: 148.5 MHz, 1920+280 x 1080+45
dtd_1080p = bytes([0x02, 0x3A, 0x80, 0x18, 0x71, 0x38, 0x2D, 0x40,
                   0x58, 0x2C, 0x45, 0x00, 0x9F, 0x29, 0x53, 0x00, 0x00, 0x1E])
# CEA-861 2160p60 (VIC 97): 594 MHz, 3840+560 x 2160+90
dtd_2160p = bytes([0x08, 0xE8, 0x00, 0x30, 0xF2, 0x70, 0x5A, 0x80,
                   0xB0, 0x58, 0x8A, 0x00, 0x9F, 0x29, 0x53, 0x00, 0x00, 0x1E])
if sys.argv[2:] == ["1080p"]:
    edid += dtd_1080p
    # Range limits: 50-76 Hz vertical, 30-83 kHz horizontal, 170 MHz max pixel clock
    edid += bytes([0, 0, 0, 0xFD, 0, 50, 76, 30, 83, 17, 0, 0x0A] + [0x20] * 6)
    edid += text_descriptor(0xFC, "TV screen")
    edid += text_descriptor(0xFF, "0001")
else:
    edid += dtd_2160p + dtd_1080p                 # the first is the preferred mode
    # Range limits: 50-76 Hz vertical, 30-136 kHz horizontal, 600 MHz max pixel clock
    edid += bytes([0, 0, 0, 0xFD, 0, 50, 76, 30, 136, 60, 0, 0x0A] + [0x20] * 6)
    edid += text_descriptor(0xFC, "TV screen")
edid += bytes([0])                                # no extension blocks
edid += bytes([(-sum(edid)) % 256])               # checksum

assert len(edid) == 128
with open(sys.argv[1], "wb") as f:
    f.write(edid)
