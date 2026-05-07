# Viland - Vim-like Binding Tool

## Project Overview
- **Project name**: Viland (Vim-like Hybrid Input Daemon)
- **Type**: Wayland daemon for keyboard input remapping
- **Core functionality**: Activates vim-like normal mode via double-tap caps lock, with macro layer for navigation
- **Target users**: Wayland users who want vim-style keybindings

## Technical Architecture

### Input Capture
- Use Python with `evdev` to capture keyboard events from `/dev/input`
- Listen to all input devices for keyboard events
- Requires user to be in `input` group or have permissions

### State Machine
- **Idle Mode**: Normal keyboard behavior
- **Vim Normal Mode**: Activated by double-tap caps lock within 500ms
- Key mappings active in normal mode

### Key Mapping (Macro Layer)
In vim normal mode:
| Input | Output |
|-------|--------|
| q | Left |
| h | Down |
| j | Left |
| k | Up |
| l | Right |
| i | Exit normal mode (to idle) |
| a | Exit normal mode + enter insert after cursor |

### Hyprland Integration
- Add global keybind in Hyprland to trigger daemon
- Daemon runs as background service
- Use socket/IPC for state communication

## Functionality Specification

### Core Features
1. **Double-tap Caps Lock Detection**
   - Monitor CAPS_LOCK key events
   - Track time between presses
   - Toggle normal mode if < 500ms between presses

2. **Key Remapping**
   - Intercept key events in normal mode
   - Map vim keys to arrow keys
   - Pass through modifier keys (Ctrl, Alt, Shift, Super)

3. **Mode Indication**
   - Visual feedback via Hyprland notification or status bar
   - Optional: change cursor shape in normal mode

4. **Exit Mechanisms**
   - `i`: Exit to idle mode
   - `a`: Exit to idle mode (ready for insert after)

### Configuration
- Config file: `~/.config/viland/config.toml`
- Configurable:
  - Double-tap timeout
  - Key mappings
  - Mode indication method

## File Structure
```
viland/
├── SPEC.md
├── pyproject.toml
├── src/viland/
│   ├── __init__.py
│   ├── daemon.py      # Main daemon
│   ├── input_handler.py  # evdev handling
│   ├── key_mapper.py  # Key mapping logic
│   └── state_machine.py  # Mode state
├── config/
│   └── config.toml.example
└── scripts/
    └── hyprland-keybind.sh  # Optional Hyprland integration
```

## Acceptance Criteria
1. Daemon starts and captures keyboard events
2. Double-tap caps lock (within 500ms) activates normal mode
3. In normal mode, q/h/j/k/l produce arrow key outputs
4. `i` or `a` exits normal mode
5. Visual indicator shows current mode
6. Works on Wayland (tested with Hyprland)