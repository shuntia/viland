# Viland Specification

## Current State: Python Implementation (Issues)

### Known Issues
1. Keys not releasing correctly on shutdown
2. Poll frequency too low (use selectors instead of select with timeout)
3. Subprocess per key (ydotool) is slow - should use direct uinput
4. Modifier detection treats non-modifiers as modifiers
5. Keys sometimes pass through incorrectly in normal mode
6. Caps2esc behavior inconsistent

### Python Todo

- [ ] Fix key release on shutdown - ensure all pressed_keys are emitted as release
- [ ] Replace selector-based polling with more efficient event-driven approach
- [ ] Use python-uinput directly instead of ydotool subprocess
- [ ] Fix modifier detection to only use: leftctrl(29), rightctrl(97), leftshift(42), rightshift(54), leftalt(56), rightalt(100), leftmeta(125), rightmeta(126), capslock(58)
- [ ] Ensure normal mode fully masks all keys
- [ ] Ensure insert mode properly passes all keys through via uinput
- [ ] Fix caps2esc: capslock tap -> escape, hold + key -> ctrl
- [ ] Fix escape: single tap -> capslock, double tap -> normal mode
- [ ] Prevent key doubling in insert mode
- [ ] Add proper cleanup on daemon exit

## Desired Features

### Input Handling
- [ ] Grab devices at startup
- [ ] Read all key events (EV_KEY) from all keyboards
- [ ] Track currently pressed keys
- [ ] Only treat true modifiers as modifiers

### Modes

#### Insert Mode (Default)
- [ ] All keys pass through to application
- [ ] Keys re-emitted via uinput (not original device)
- [ ] caps2esc: tap capslock -> escape, hold + key -> ctrl+key
- [ ] escape tap -> capslock (enable caps), double-tap -> normal mode
- [ ] capslock double-tap -> normal mode

#### Normal Mode
- [ ] All keys masked (not passed through)
- [ ] h/j/k/l -> arrow keys
- [ ] w/b/e -> word navigation
- [ ] i/a -> exit to insert mode
- [ ] ; or / -> command mode (wofi)
- [ ] esc -> nothing (don't exit to insert)

### Command Mode
- [ ] Triggered by ; or / in normal mode
- [ ] Opens wofi/fuzzel with ":" prompt
- [ ] Commands: q, qa, d, w, x, c, tab, tn, tp, h, e, r, y, p, s, z, m
- [ ] 5 second timeout

### System Integration
- [ ] PID file at ~/.config/viland/viland.pid
- [ ] Log file at ~/.config/viland/viland.log
- [ ] Prevent multiple instances
- [ ] Ctrl+Alt+Q to exit daemon
- [ ] System tray (optional, disabled by default)
- [ ] Config file at ~/.config/viland/config.toml

### Rust Implementation (Future)

#### Architecture
- [ ] Use tokio for async runtime
- [ ] Parallel device polling with tokio::select!
- [ ] Direct uinput for key injection (no subprocess)
- [ ] Event-driven key processing

#### Performance Targets
- < 1ms latency per key
- Batch key processing
- True parallel device reading
- No subprocess overhead

#### Structure
```
src/
├── main.rs          - Entry point, CLI args
├── config.rs        - Config loading
├── devices.rs       - Input device management
├── state.rs         - Mode state machine
├── keymap.rs        - Key mapping logic
├── command.rs      - Command mode with wofi
├── uinput.rs        - Direct uinput injection
└── lib.rs           - Library exports
```

#### Features (Same as Python)
- [ ] All mode functionality
- [ ] All key bindings
- [ ] Command mode
- [ ] caps2esc
- [ ] Config file
- [ ] Logging
- [ ] PID file
- [ ] Multiple instance prevention