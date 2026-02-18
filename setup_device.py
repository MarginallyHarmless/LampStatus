#!/usr/bin/env python3
"""One-time setup: discover Govee devices and create config.json."""

import json
import os
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

    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    print(f"\nConfig saved! Device: {selected['deviceName']}")
    print("You're all set. The lamp will now react to Claude Code states.")

if __name__ == "__main__":
    main()
