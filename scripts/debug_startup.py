#!/usr/bin/env python3
"""Debug script to find TUI startup slowness."""

import time
import sys

_start = time.time()

def log(msg):
    print(f"[{time.time() - _start:6.2f}s] {msg}")

log("Starting imports...")

log("  Importing textual...")
from textual.app import App
log("  Textual imported")

log("  Importing hwh.tui.app...")
from hwh.tui.app import HwhApp
log("  HwhApp imported")

log("  Importing detect...")
from hwh.detect import detect
log("  detect imported")

log("Running device detection...")
devices = detect()
log(f"Found {len(devices)} devices: {list(devices.keys())}")

log("Creating app instance...")
app = HwhApp()
log("App created")

log("")
log("Now starting app.run()...")
log("Press Ctrl+C to exit at any time")
log("")

try:
    app.run()
except KeyboardInterrupt:
    pass

log("App exited")
