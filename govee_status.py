#!/usr/bin/env python3
"""Set Govee lamp color/scene based on Claude Code state."""

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

# Each state maps to a Govee capability dict
STATES = {
    "idle": {
        "type": "devices.capabilities.dynamic_scene",
        "instance": "lightScene",
        "value": {"id": 1258, "paramId": 1333},  # Fire
    },
    "working": {
        "type": "devices.capabilities.dynamic_scene",
        "instance": "lightScene",
        "value": {"id": 1258, "paramId": 1333},  # Fire
    },
    "input_required": {
        "type": "devices.capabilities.color_setting",
        "instance": "colorRgb",
        "value": (255 << 16) | (140 << 8) | 50,  # Deep amber
    },
}


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


def send_capability(config, capability):
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
                "capability": capability,
            },
        },
        timeout=5,
    )


def main():
    # Child mode: send a capability to the API and exit
    if len(sys.argv) == 3 and sys.argv[1] == "--send":
        capability = json.loads(sys.argv[2])
        with open(CONFIG_PATH) as f:
            config = json.load(f)
        try:
            send_capability(config, capability)
        except requests.RequestException:
            pass
        return

    if len(sys.argv) != 2 or sys.argv[1] not in STATES:
        print(f"Usage: {sys.argv[0]} <{'|'.join(STATES.keys())}>", file=sys.stderr)
        sys.exit(1)

    state = sys.argv[1]

    if should_debounce(state):
        sys.exit(0)

    if not os.path.exists(CONFIG_PATH):
        print("Config not found. Run setup_device.py first.", file=sys.stderr)
        sys.exit(1)

    capability = STATES[state]
    save_state(state)

    # Fire-and-forget: spawn detached child to make the API call
    subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "--send", json.dumps(capability)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
    )

if __name__ == "__main__":
    main()
