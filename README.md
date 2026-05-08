# Viland

Viland is a keyboard remapping and mode-switching daemon designed to improve workflow efficiency through modal editing.

## Architecture

Viland operates as a background daemon that intercepts raw input events and maps them to custom actions based on the current active mode.

### Components
- **Event Loop**: Monitors raw keyboard input devices for `Press`, `Release`, and `Repeat` events.
- **State Machine**: Tracks the current input mode (e.g., `Normal`, `Insert`) and maintains the state of "virtually pressed" keys.
- **Keymap**: A configuration layer that defines actions triggered by specific key combinations or sequences.
- **Action Dispatcher**: Executes defined `Action` types:
  - `PassThrough`: Allows events to pass to the system unmodified.
  - `Emit`: Emits a single key event.
  - `EmitChord`: Triggers multiple keys simultaneously (e.g., `META` + `key`).
  - `Sequence`: Executes a series of key actions (e.g., `Tap(key)` then `SwitchMode`).
  - `SwitchMode`: Changes the active state (Normal/Insert).

## Normal Mode Keybinds

In Normal mode, the following mappings are active:

### Navigation
- `h`: Left
- `j`: Down
- `k`: Up
- `l`: Right

### Mode Switching
- `i`: Switch to Insert mode
- `a`: Tap `Right` and switch to Insert mode

### Editing
- `y`: Copy (`CTRL` + `C`)
- `p`: Paste (`CTRL` + `V`)
- `u`: Undo (`CTRL` + `Z`)
- `/`: Find (`CTRL` + `F`)

### Chords (META)
Pressing number keys in Normal mode emits a `META` + `Number` chord:
- `1` - `0`: Emits `META` + `1` - `0` (as a tapped event).

### Special
- `w`: `CTRL` + `Right`
- `b`: `CTRL` + `Left`
