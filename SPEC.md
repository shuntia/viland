# Viland - Minimal Modal Keyboard Daemon for Wayland

## Specification v0.2

---

## Design Philosophy

Viland IS:
- a low-latency keyboard remapper
- a modal input layer  
- a reliable caps2esc implementation
- a simple finite-state machine over evdev input

Viland is NOT:
- a compositor plugin
- a general-purpose automation framework
- a full Vim emulation system
- using async runtime (NO TOKIO)

Primary goals:
1. Reliability
2. Low latency (< 1ms)
3. Simplicity
4. Recoverability

---

## Architecture

```
evdev devices → grab → read EV_KEY → transform → emit via uinput → compositor
```

### Directory Structure

```
viland/
├── Cargo.toml
├── src/
│   ├── main.rs
│   ├── config.rs
│   ├── device.rs
│   ├── event.rs
│   ├── state.rs
│   ├── keymap.rs
│   ├── remap.rs
│   ├── uinput.rs
│   └── errors.rs
├── config/
│   └── default.toml
└── systemd/
    └── viland.service
```

---

## Threading Model

NO TOKIO.

Model:
- one polling thread (epoll)
- one processing thread

Or single-threaded epoll loop.

---

## Event Model

```rust
struct Event {
    device_id: u32,
    key_code: u16,
    key_state: KeyState,  // Press, Release, Repeat
    timestamp: u64,
}

enum KeyState {
    Press,
    Release, 
    Repeat,
}
```

Only EV_KEY events processed. EV_SYN ignored.

---

## Key State Tracking

Three sets maintained:
- `physical_pressed`: actual keys from hardware
- `virtual_pressed`: keys emitted to uinput  
- `modifiers_active`: currently active modifiers

---

## Modes

Two modes only:
1. **Insert** (default)
2. **Normal**

No command mode in v0.2.

---

## Caps2Esc Specification

### State Machine

```
Idle → (caps press) → PendingTap
PendingTap → (caps release, no other key) → emit Escape → Idle
PendingTap → (other key pressed while caps held) → emit Ctrl down → HeldCtrl
HeldCtrl → (caps released) → emit Ctrl up → Idle
```

Key points:
- Ctrl ONLY emitted when another key is pressed
- Do NOT emit Ctrl immediately on caps press

---

## Normal Mode Entry

Trigger: **double tap CapsLock**

NOT escape. Escape is too heavily used.

Timing: 300ms default (configurable)

---

## Normal Mode Exit

Exit keys:
- `i` → return to Insert
- `a` → return to Insert + emit RightArrow

---

## Normal Mode Mappings

| Key | Action |
|-----|--------|
| h | Left |
| j | Down |
| k | Up |
| l | Right |
| w | Ctrl+Right |
| b | Ctrl+Left |
| 0 | Home |
| $ | End |

Unmapped keys are IGNORED (not passed through).

---

## Key Repeat Policy

Insert mode: pass repeats through normally

Normal mode: repeats allowed for navigation keys (h/j/k/l)

---

## Uinput Strategy

Single virtual keyboard device named "viland virtual keyboard".

All standard keyboard keys registered at startup.

DO NOT dynamically register keys.

---

## Emission Rules

Every press MUST eventually receive release.

Invariant: `virtual_pressed` must be empty on shutdown.

Chord ordering (Ctrl+S):
1. Ctrl down
2. S down  
3. S up
4. Ctrl up

---

## Emergency Exit

**Ctrl+Alt+Backspace** 

Bypasses modal handling. Immediate shutdown, release all keys, ungrab devices.

---

## Configuration

Location: `~/.config/viland/config.toml`

```toml
double_tap_timeout_ms = 300

[caps]
enabled = true

[normal]
h = "left"
j = "down"
k = "up"
l = "right"
```

---

## Implementation Phases

### PHASE 1: Foundation
- device enumeration
- grabbing
- uinput creation
- raw passthrough

### PHASE 2: Caps2Esc
- caps2esc state machine

### PHASE 3: Normal Mode
- normal mode mappings

### PHASE 4: Recovery
- cleanup/recovery
- emergency exit

---

## Testing Checklist

1. Single tap caps emits escape
2. Hold caps acts as ctrl
3. Ctrl+C works correctly
4. Double tap caps enters normal mode
5. hjkl navigation works
6. i/a exit normal mode
7. No stuck modifiers after crash
8. Emergency exit always functions
9. Key repeats function properly
10. Shutdown releases all keys

---

## Success Criteria

- feels instant (< 1ms latency)
- never leaves stuck keys
- survives normal desktop usage
- works across compositors
- users forget it exists