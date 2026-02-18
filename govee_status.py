#!/usr/bin/env python3
"""Set Govee lamp color based on Claude Code state."""

import json
import os
import signal
import subprocess
import sys
import time
import uuid
import requests

GOVEE_API_BASE = "https://openapi.api.govee.com"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")
DEBOUNCE_PATH = os.path.join(SCRIPT_DIR, ".last_state")
PULSE_PID_PATH = os.path.join(SCRIPT_DIR, ".pulse_pid")
DEBOUNCE_SECONDS = 2
PULSE_INTERVAL = 3  # seconds between pulse color changes

COLORS = {
    "idle": (255, 220, 200),            # Warm white
    "working": (255, 140, 20),          # Warm amber/orange
    "input_required": (255, 0, 0),      # Red
}

PULSE_COLORS = [
    (255, 0, 0),    # Bright red
    (40, 0, 0),     # Dim red
]

SCENE_KEYWORDS = ["breathe", "pulse", "aurora", "candle"]


def rgb_to_int(r, g, b):
    return (r << 16) | (g << 8) | b


def should_debounce(state):
    try:
        with open(DEBOUNCE_PATH, "r") as f:
            data = json.load(f)
        last_state = data.get("state")
        elapsed = time.time() - data.get("time", 0)
        # Same state within debounce window: skip
        if last_state == state and elapsed < DEBOUNCE_SECONDS:
            return True
        # Don't let "working" override "input_required" within a short window
        # (prevents async PreToolUse race with Stop hook)
        if last_state == "input_required" and state == "working" and elapsed < DEBOUNCE_SECONDS:
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


def set_scene(config, scene_value):
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
                    "type": "devices.capabilities.dynamic_scene",
                    "instance": "lightScene",
                    "value": scene_value,
                },
            },
        },
        timeout=5,
    )


def pick_scene(scenes):
    """Pick the best scene from cached list by keyword match."""
    for keyword in SCENE_KEYWORDS:
        for scene in scenes:
            name = scene.get("name", "").lower()
            if keyword in name:
                return scene["value"]
    return None


def discover_scenes(config):
    """Query Govee API for dynamic scenes available on the configured device."""
    resp = requests.get(
        f"{GOVEE_API_BASE}/router/api/v1/user/devices",
        headers={"Govee-API-Key": config["api_key"]},
        timeout=10,
    )
    resp.raise_for_status()
    devices = resp.json()["data"]

    for dev in devices:
        if dev["device"] == config["device"] and dev["sku"] == config["sku"]:
            for cap in dev.get("capabilities", []):
                if cap.get("type") == "devices.capabilities.dynamic_scene" and cap.get("instance") == "lightScene":
                    options = cap.get("parameters", {}).get("options", [])
                    scenes = [{"name": opt["name"], "value": opt["value"]} for opt in options]
                    return scenes
    return []


def save_scenes_to_config(config, scenes):
    """Save discovered scenes to config.json."""
    config["scenes"] = scenes
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


def stop_pulse():
    """Kill any running pulse background process."""
    # Kill by PID file
    try:
        with open(PULSE_PID_PATH, "r") as f:
            pid = int(f.read().strip())
        os.kill(pid, signal.SIGTERM)
    except (FileNotFoundError, ValueError, ProcessLookupError, OSError):
        pass
    try:
        os.remove(PULSE_PID_PATH)
    except FileNotFoundError:
        pass
    # Kill any orphaned pulse-loop processes by command line
    try:
        script = os.path.basename(os.path.abspath(__file__))
        subprocess.run(
            ["wmic", "process", "where",
             f"commandline like '%{script}%--pulse-loop%'",
             "call", "terminate"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def start_pulse():
    """Spawn a background process that pulses the lamp red."""
    stop_pulse()
    script = os.path.abspath(__file__)
    proc = subprocess.Popen(
        [sys.executable, script, "--pulse-loop"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
    )
    with open(PULSE_PID_PATH, "w") as f:
        f.write(str(proc.pid))


def set_color_async(config, r, g, b):
    """Fire a color change request without waiting for the response."""
    import threading
    t = threading.Thread(target=set_color, args=(config, r, g, b), daemon=True)
    t.start()


def pulse_loop():
    """Background loop: alternate between bright and dim red."""
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    i = 0
    while True:
        r, g, b = PULSE_COLORS[i % len(PULSE_COLORS)]
        try:
            set_color_async(config, r, g, b)
        except Exception:
            pass
        i += 1
        time.sleep(PULSE_INTERVAL)


def main():
    # Background pulse loop (internal, not user-facing)
    if len(sys.argv) == 2 and sys.argv[1] == "--pulse-loop":
        pulse_loop()
        return

    # Handle --discover-scenes flag
    if len(sys.argv) == 2 and sys.argv[1] == "--discover-scenes":
        if not os.path.exists(CONFIG_PATH):
            print("Config not found. Run setup_device.py first.", file=sys.stderr)
            sys.exit(1)
        with open(CONFIG_PATH) as f:
            config = json.load(f)
        print("Discovering scenes...")
        try:
            scenes = discover_scenes(config)
        except requests.RequestException as e:
            print(f"Govee API error: {e}", file=sys.stderr)
            sys.exit(1)
        save_scenes_to_config(config, scenes)
        print(f"Found {len(scenes)} scene(s).")
        for s in scenes:
            print(f"  - {s['name']}")
        return

    if len(sys.argv) != 2 or sys.argv[1] not in COLORS:
        print(f"Usage: {sys.argv[0]} <{'|'.join(COLORS.keys())}|--discover-scenes>", file=sys.stderr)
        sys.exit(1)

    state = sys.argv[1]

    if should_debounce(state):
        sys.exit(0)

    if not os.path.exists(CONFIG_PATH):
        print("Config not found. Run setup_device.py first.", file=sys.stderr)
        sys.exit(1)

    with open(CONFIG_PATH) as f:
        config = json.load(f)

    try:
        stop_pulse()
        if state == "input_required":
            start_pulse()
        elif state == "working":
            scenes = config.get("scenes", [])
            scene_value = pick_scene(scenes)
            if scene_value is not None:
                set_scene(config, scene_value)
            else:
                r, g, b = COLORS["working"]
                set_color(config, r, g, b)
        else:
            r, g, b = COLORS[state]
            set_color(config, r, g, b)
        save_state(state)
    except requests.RequestException as e:
        print(f"Govee API error: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
