# Viland - Vim-like Binding Daemon for Wayland

## Project Overview

- **Name**: Viland
- **Type**: Wayland keyboard input remapping daemon
- **Language**: Python (current), Rust (planned)
- **Purpose**: Vim-like keybindings with caps2esc functionality

## Current Issues (Python)

1. Keys don't release correctly on daemon exit
2. Subprocess overhead (ydotool) is slow
3. Modifier detection incorrect
4. Key pass-through inconsistent
5. Caps2esc behavior buggy

## SPEC.md and TODO

### Architecture

```
viland/
├── SPEC.md              # This file
├── TODO.md               # Detailed task list
├── pyproject.toml       # Python project config
├── config/
│   └── viland.toml      # Default config
├── src/viland/
│   ├── __init__.py
│   ├── config.py        # Config loading
│   ├── daemon.py       # Main daemon
│   ├── input_handler.py # evdev input
│   ├── key_mapper.py   # Key mapping
│   ├── state_machine.py # Mode state
│   ├── tray.py         # System tray (optional)
│   └── filter.py       # Interception filter (legacy)
├── scripts/
│   └── viland.sh       # Startup script
└── install.sh          # Installer
```

---

## Features Specification

### 1. Input Handling

- [x] Read keyboard events via evdev
- [x] Grab devices at startup to mask keys
- [ ] Use direct uinput instead of ydotool subprocess
- [x] Track pressed keys in set
- [x] Only treat true modifiers: {29, 97, 42, 54, 56, 100, 125, 126, 58}

### 2. Modes

#### Insert Mode (Default)
- [x] Keys pass through (re-emitted via ydotool)
- [ ] Fix key release on shutdown
- [ ] Ensure no key doubling
- [x] caps2esc: capslock tap → escape, hold + key → ctrl+key

#### Normal Mode (Activated via double-tap caps/esc)
- [x] All keys masked (consumed, not passed through)
- [x] h/j/k/l → arrow keys
- [x] w/b/e → word forward/back/end
- [x] i/a → exit to insert mode
- [x] ; or / → command mode
- [x] esc → don't exit (use i/a instead)

### 3. Command Mode

- [x] Triggered by ; or / in normal mode
- [x] Opens wofi/fuzzel with ":" prompt
- [x] 5 second timeout
- [x] Commands: q, qa, d, w, x, c, tab, tn, tp, h, e, r, y, p, s, z, m

### 4. System Integration

- [x] PID file at ~/.config/viland/viland.pid
- [x] Prevent multiple instances
- [x] Ctrl+Alt+Q to exit daemon
- [x] Config file at ~/.config/viland/config.toml
- [x] Notification on mode change
- [ ] Log file at ~/.config/viland/viland.log (partially working)
- [ ] System tray (doesn't work on Wayland without tray manager)

---

## Rust Implementation Plan

### Why Rust?

- Sub-millisecond latency (vs 10-50ms in Python)
- Direct uinput (no subprocess)
- True async parallel device polling
- No GIL

### Architecture

```
src/
├── main.rs          # Entry point, CLI
├── config.rs        # Config loading (serde)
├── devices.rs       # evdev device management
├── state.rs         # Mode state machine
├── keymap.rs        # Key mapping logic
├── command.rs       # Command mode (wofi)
├── uinput.rs        # Direct uinput injection
└── lib.rs           # Library exports
```

### Async Architecture

```rust
use tokio::select;
use std::collections::HashSet;

// Parallel device polling
async fn poll_devices() {
    loop {
        select! {
            event = device1.read_async() => handle(event),
            event = device2.read_async() => handle(event),
            _ = tokio::time::sleep(Duration::from_millis(1)) => continue,
        }
    }
}

// Direct uinput injection
fn emit_key(code: u16, pressed: bool) {
    device.emit(EV_KEY, code, pressed as i32);
    device.syn();
}
```

---

## Key Mappings

### Normal Mode
| Key | Action |
|-----|--------|
| h | left |
| j | down |
| k | up |
| l | right |
| w | ctrl+right (word forward) |
| b | ctrl+left (word back) |
| e | end (word end) |
| i | exit to insert |
| a | exit to insert + move right |
| ; | command mode |
| / | command mode |

### Command Mode (wofi)
| Command | Action |
|---------|--------|
| q | Alt+F4 (close) |
| qa | Ctrl+Q (quit all) |
| d | backspace (delete char) |
| w | Ctrl+S (save) |
| x | save + quit |
| c | close |
| tab | Ctrl+T (new tab) |
| tn | Ctrl+Tab (next tab) |
| tp | Ctrl+Shift+Tab (prev tab) |
| h | help |

---

## TODO List

### Python (Current - Fix Priority)

1. **HIGH**: Fix key release on shutdown - emit release for all pressed_keys
2. **HIGH**: Fix caps2esc: capslock tap → escape, hold+key → ctrl+key
3. **HIGH**: Fix escape: single tap → pass through, double tap → normal mode
4. **MEDIUM**: Use direct uinput instead of ydotool subprocess
5. **MEDIUM**: Fix modifier detection to only use true modifiers
6. **LOW**: Add proper logging to file
7. **LOW**: Test all command mode commands

### Rust (Future - Implementation)

1. Create Rust project with tokio
2. Implement async device polling
3. Implement direct uinput injection
4. Migrate all key mappings
5. Implement command mode
6. Test latency and performance

---

## Testing Checklist

- [ ] Double-tap caps → enter normal mode
- [ ] Double-tap escape → enter normal mode
- [ ] Single tap caps → escape (in insert mode)
- [ ] Single tap escape → pass through (in insert mode)
- [ ] h/j/k/l → arrows (in normal mode)
- [ ] i/a → exit to insert mode (in normal mode)
- [ ] ; → command mode (in normal mode)
- [ ] Ctrl+Alt+Q → exit daemon
- [ ] Keys release properly on daemon exit
- [ ] No key doubling in insert mode