# Govee Lamp Status Indicator for Claude Code — Design

## Goal

Make a Govee smart lamp react to Claude Code's states (Idle, Working, Input Required) using Claude Code hooks and the Govee Developer API v2.

## Architecture

```
Claude Code Hooks (~/.claude/settings.json)
    │
    ├── SessionStart ──────→ python govee_status.py idle
    ├── UserPromptSubmit ──→ python govee_status.py working
    ├── PreToolUse ────────→ python govee_status.py working
    ├── Stop ──────────────→ python govee_status.py idle
    └── Notification(idle) → python govee_status.py input_required
```

All hooks run with `"async": true` so they never block Claude Code.

## Components

| File | Purpose |
|---|---|
| `govee_status.py` | Main script. Accepts state arg (`idle`, `working`, `input_required`), calls Govee API. |
| `setup_device.py` | One-time setup. Lists Govee devices, user picks one, writes `config.json`. |
| `config.json` | Stores device ID, SKU, API key. Gitignored. |

## Color Mapping

| State | Color | RGB |
|---|---|---|
| Idle | Warm white | (255, 200, 120) |
| Working | Amber | (255, 160, 40) |
| Input Required | Soft red | (255, 80, 60) |

## Govee API Details

- **Base URL:** `https://openapi.api.govee.com`
- **Auth:** `Govee-API-Key` header
- **Control endpoint:** `POST /router/api/v1/device/control`
- **Color format:** Single integer `(R << 16) | (G << 8) | B`
- **Rate limit:** 10,000 requests/day

## Debounce

Script checks a temp file for last state + timestamp. If same state was sent <2 seconds ago, skip the API call. Prevents spamming during rapid tool use.

## Session End Behavior

Lamp stays on warm white (idle color) after session ends — doubles as ambient lighting.

## Hook Configuration

Hooks go in `~/.claude/settings.json` (global, all projects). Each hook entry runs `python <absolute-path>/govee_status.py <state>`.

## Error Handling

- Govee API unreachable: fail silently (stderr), don't block Claude
- `config.json` missing: print setup instructions, exit
- Device offline: API queues the command, no special handling

## Dependencies

- Python 3.x
- `requests` library
