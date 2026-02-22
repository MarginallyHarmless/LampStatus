#!/usr/bin/env python3
"""Set Govee lamp color based on Claude Code state."""

import json
import os
import subprocess
import sys
import time
import uuid
import requests

GOVEE_API_BASE = "https://openapi.api.govee.com"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")
DEBOUNCE_PATH = os.path.join(SCRIPT_DIR, ".last_state")
DEBOUNCE_SECONDS = 2

COLORS = {
    "idle": (255, 220, 200),            # Warm white
    "working": (255, 220, 200),         # Warm white (same as idle)
    "input_required": (255, 0, 0),      # Red
}


def rgb_to_int(r, g, b):
    return (r << 16) | (g << 8) | b


def should_debounce(state):
    try:
        with open(DEBOUNCE_PATH, "r") as f:
            data = json.load(f)
        last_state = data.get("state")
        elapsed = time.time() - data.get("time", 0)
        if last_state == state and elapsed < DEBOUNCE_SECONDS:
            return True
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    return False


def save_state(state):
    with open(DEBOUNCE_PATH, "w") as f:
        json.dump({"state": state, "time": time.time()}, f)


def set_color(config, r, g, b):
    requests.post(
        f"{GOVEE_API_BASE}/router/api/v1/device/control",
        headers={
            "Govee-API-Key": config["api_key"],
            "Content-Type": "application/json",
        },
        json={
            "requestId": str(uuid.uuid4()),
            "payload": {
                "sku": config["sku"],
                "device": config["device"],
                "capability": {
                    "type": "devices.capabilities.color_setting",
                    "instance": "colorRgb",
                    "value": rgb_to_int(r, g, b),
                },
            },
        },
        timeout=5,
    )


def main():
    # Child mode: send a color to the API and exit
    if len(sys.argv) == 5 and sys.argv[1] == "--send":
        r, g, b = int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
        with open(CONFIG_PATH) as f:
            config = json.load(f)
        try:
            set_color(config, r, g, b)
        except requests.RequestException:
            pass
        return

    if len(sys.argv) != 2 or sys.argv[1] not in COLORS:
        print(f"Usage: {sys.argv[0]} <{'|'.join(COLORS.keys())}>", file=sys.stderr)
        sys.exit(1)

    state = sys.argv[1]

    if should_debounce(state):
        sys.exit(0)

    if not os.path.exists(CONFIG_PATH):
        print("Config not found. Run setup_device.py first.", file=sys.stderr)
        sys.exit(1)

    r, g, b = COLORS[state]
    save_state(state)

    # Fire-and-forget: spawn detached child to make the API call
    subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "--send", str(r), str(g), str(b)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
    )

if __name__ == "__main__":
    main()
