# Govee Lamp Status Indicator — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make a Govee smart lamp change color based on Claude Code's state (idle/working/input required) using hooks and the Govee API v2.

**Architecture:** A single Python script (`govee_status.py`) is called by Claude Code hooks with a state argument. It reads device config from `config.json`, debounces duplicate calls, and sends color commands to the Govee API. A separate `setup_device.py` handles one-time device discovery.

**Tech Stack:** Python 3.13 (`C:\Users\bogda\AppData\Local\Programs\Python\Python313\python.exe`), `requests` library, Govee Developer API v2, Claude Code hooks in `~/.claude/settings.json`.

---

### Task 1: Create .gitignore and project scaffolding

**Files:**
- Create: `D:/vibes/Govee Lamp/.gitignore`

**Step 1: Create .gitignore**

```
config.json
__pycache__/
*.pyc
```

**Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: add gitignore for config and pycache"
```

---

### Task 2: Build the setup script (device discovery)

**Files:**
- Create: `D:/vibes/Govee Lamp/setup_device.py`

**Step 1: Write setup_device.py**

This script calls the Govee API to list devices, displays them, lets the user pick one, and writes `config.json`.

```python
#!/usr/bin/env python3
"""One-time setup: discover Govee devices and create config.json."""

import json
import sys
import requests

GOVEE_API_BASE = "https://openapi.api.govee.com"

def list_devices(api_key):
    resp = requests.get(
        f"{GOVEE_API_BASE}/router/api/v1/user/devices",
        headers={"Govee-API-Key": api_key},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["data"]

def main():
    api_key = input("Enter your Govee API key: ").strip()
    if not api_key:
        print("No API key provided. Exiting.")
        sys.exit(1)

    print("\nFetching devices...")
    try:
        devices = list_devices(api_key)
    except requests.RequestException as e:
        print(f"Error contacting Govee API: {e}")
        sys.exit(1)

    if not devices:
        print("No devices found on your account.")
        sys.exit(1)

    print(f"\nFound {len(devices)} device(s):\n")
    for i, dev in enumerate(devices, 1):
        print(f"  {i}. {dev['deviceName']} (SKU: {dev['sku']}, ID: {dev['device']})")

    while True:
        choice = input(f"\nPick a device [1-{len(devices)}]: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(devices):
            break
        print("Invalid choice, try again.")

    selected = devices[int(choice) - 1]
    config = {
        "api_key": api_key,
        "device": selected["device"],
        "sku": selected["sku"],
        "device_name": selected["deviceName"],
    }

    config_path = __file__.replace("setup_device.py", "config.json")
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    print(f"\nConfig saved! Device: {selected['deviceName']}")
    print("You're all set. The lamp will now react to Claude Code states.")

if __name__ == "__main__":
    main()
```

**Step 2: Run the script to test device discovery**

Run: `"C:\Users\bogda\AppData\Local\Programs\Python\Python313\python.exe" "D:/vibes/Govee Lamp/setup_device.py"`

Enter API key `2a4601b2-2900-45f0-b27d-9c4cc5840cd8` when prompted. Pick the desired lamp. Verify `config.json` is created with device info.

**Step 3: Commit**

```bash
git add setup_device.py
git commit -m "feat: add device discovery setup script"
```

---

### Task 3: Build the main status script

**Files:**
- Create: `D:/vibes/Govee Lamp/govee_status.py`

**Step 1: Write govee_status.py**

```python
#!/usr/bin/env python3
"""Set Govee lamp color based on Claude Code state."""

import json
import os
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
    "idle": (255, 200, 120),        # Warm white
    "working": (255, 160, 40),      # Amber
    "input_required": (255, 80, 60), # Soft red
}


def rgb_to_int(r, g, b):
    return (r << 16) | (g << 8) | b


def should_debounce(state):
    try:
        with open(DEBOUNCE_PATH, "r") as f:
            data = json.load(f)
        if data.get("state") == state and time.time() - data.get("time", 0) < DEBOUNCE_SECONDS:
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
    if len(sys.argv) != 2 or sys.argv[1] not in COLORS:
        print(f"Usage: {sys.argv[0]} <{'|'.join(COLORS.keys())}>", file=sys.stderr)
        sys.exit(1)

    state = sys.argv[1]

    if should_debounce(state):
        sys.exit(0)

    if not os.path.exists(CONFIG_PATH):
        print(f"Config not found. Run setup_device.py first.", file=sys.stderr)
        sys.exit(1)

    with open(CONFIG_PATH) as f:
        config = json.load(f)

    r, g, b = COLORS[state]
    try:
        set_color(config, r, g, b)
        save_state(state)
    except requests.RequestException as e:
        print(f"Govee API error: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
```

**Step 2: Test each state manually**

Run each of these and verify the lamp changes color:

```bash
"C:\Users\bogda\AppData\Local\Programs\Python\Python313\python.exe" "D:/vibes/Govee Lamp/govee_status.py" idle
"C:\Users\bogda\AppData\Local\Programs\Python\Python313\python.exe" "D:/vibes/Govee Lamp/govee_status.py" working
"C:\Users\bogda\AppData\Local\Programs\Python\Python313\python.exe" "D:/vibes/Govee Lamp/govee_status.py" input_required
```

**Step 3: Test debounce**

Run the same state twice rapidly — second call should exit immediately without hitting the API:

```bash
"C:\Users\bogda\AppData\Local\Programs\Python\Python313\python.exe" "D:/vibes/Govee Lamp/govee_status.py" working
"C:\Users\bogda\AppData\Local\Programs\Python\Python313\python.exe" "D:/vibes/Govee Lamp/govee_status.py" working
```

**Step 4: Commit**

```bash
git add govee_status.py
git commit -m "feat: add main status script with color control and debounce"
```

---

### Task 4: Add .gitignore entry for debounce file

**Files:**
- Modify: `D:/vibes/Govee Lamp/.gitignore`

**Step 1: Add .last_state to .gitignore**

Append `.last_state` to the existing `.gitignore`.

**Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: gitignore debounce state file"
```

---

### Task 5: Configure Claude Code hooks

**Files:**
- Modify: `C:\Users\bogda\.claude\settings.json`

**Step 1: Add hooks to settings.json**

The Python path is `C:\\Users\\bogda\\AppData\\Local\\Programs\\Python\\Python313\\python.exe`.
The script path is `D:\\vibes\\Govee Lamp\\govee_status.py`.

Add `hooks` key to the existing settings. Keep all existing keys (`enabledPlugins`, `autoUpdatesChannel`, `effortLevel`) intact.

```json
{
  "enabledPlugins": {
    "superpowers@claude-plugins-official": true
  },
  "autoUpdatesChannel": "latest",
  "effortLevel": "medium",
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\"C:\\Users\\bogda\\AppData\\Local\\Programs\\Python\\Python313\\python.exe\" \"D:\\vibes\\Govee Lamp\\govee_status.py\" idle",
            "async": true
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\"C:\\Users\\bogda\\AppData\\Local\\Programs\\Python\\Python313\\python.exe\" \"D:\\vibes\\Govee Lamp\\govee_status.py\" working",
            "async": true
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\"C:\\Users\\bogda\\AppData\\Local\\Programs\\Python\\Python313\\python.exe\" \"D:\\vibes\\Govee Lamp\\govee_status.py\" working",
            "async": true
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\"C:\\Users\\bogda\\AppData\\Local\\Programs\\Python\\Python313\\python.exe\" \"D:\\vibes\\Govee Lamp\\govee_status.py\" idle",
            "async": true
          }
        ]
      }
    ],
    "Notification": [
      {
        "matcher": "idle_prompt",
        "hooks": [
          {
            "type": "command",
            "command": "\"C:\\Users\\bogda\\AppData\\Local\\Programs\\Python\\Python313\\python.exe\" \"D:\\vibes\\Govee Lamp\\govee_status.py\" input_required",
            "async": true
          }
        ]
      }
    ]
  }
}
```

**Step 2: Verify hooks are recognized**

Start a new Claude Code session. The lamp should turn warm white on session start (SessionStart hook). Send a prompt — lamp should turn amber. When Claude finishes — lamp should go warm white again.

**Step 3: No git commit for this step** (settings.json is outside the repo)

---

### Task 6: Create CLAUDE.md

**Files:**
- Create: `D:/vibes/Govee Lamp/CLAUDE.md`

**Step 1: Write CLAUDE.md**

```markdown
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Govee smart lamp integration that reacts to Claude Code's states via hooks. The lamp changes color:
- Warm white (255, 200, 120) — Idle
- Amber (255, 160, 40) — Working
- Soft red (255, 80, 60) — Input required

## Key Files

- `govee_status.py` — Main script. Called with one arg: `idle`, `working`, or `input_required`. Sends color to Govee API with 2-second debounce.
- `setup_device.py` — One-time device discovery. Lists Govee devices, user picks one, writes `config.json`.
- `config.json` — Device ID, SKU, API key. Gitignored. Generated by `setup_device.py`.

## Govee API

- Base URL: `https://openapi.api.govee.com`
- Auth: `Govee-API-Key` header
- Control: `POST /router/api/v1/device/control`
- Color value: single integer `(R << 16) | (G << 8) | B`

## Python Path

`C:\Users\bogda\AppData\Local\Programs\Python\Python313\python.exe`

## Hooks

Configured in `~/.claude/settings.json` (global). All hooks are async. Hook events: SessionStart, UserPromptSubmit, PreToolUse, Stop, Notification (idle_prompt matcher).
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add CLAUDE.md"
```
