# Viland Rust Rewrite - Specification

## Goals

- Sub-millisecond key latency (< 1ms)
- Direct uinput injection (no subprocess)
- True async parallel device polling
- All features from Python implementation
- Production-ready reliability

---

## Architecture

### Project Structure

```
viland-rs/
├── Cargo.toml
├── src/
│   ├── main.rs          # Entry point, CLI args
│   ├── lib.rs           # Library exports
│   ├── config.rs       # Config loading
│   ├── state.rs        # Mode state machine
│   ├── devices.rs       # Input device management
│   ├── keyboard.rs     # Key handling, mapping
│   ├── command.rs      # Command mode (wofi)
│   └── uinput.rs       # Direct uinput injection
└── viland.service      # systemd service
```

### Dependencies (Cargo.toml)

```toml
[package]
name = "viland"
version = "0.1.0"
edition = "2021"

[dependencies]
tokio = { version = "1", features = ["full"] }
evdev = "0.5"
uinput = "0.5"
serde = { version = "1", features = ["derive"] }
toml = "0.8"
tracing = "0.1"
tracing-subscriber = "0.3"
tracing-appender = "0.2"
clap = { version = "4", features = ["derive"] }
directories = "5"
```

---

## Module Specification

### 1. config.rs

```rust
pub struct Config {
    pub double_tap_timeout: f64,
    pub caps2esc: bool,
    pub notification: NotificationType,
    pub tray: bool,
    pub keys: HashMap<String, String>,
}

pub fn load_config(path: Option<PathBuf>) -> Config;
```

- Load from ~/.config/viland/config.toml
- Default values if file doesn't exist
- Validate on load

### 2. state.rs

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Mode {
    Insert,
    Normal,
    Command,
}

pub struct State {
    pub mode: Mode,
    pub last_trigger_time: f64,
    pub last_trigger_key: u16,
    pub pressed_keys: HashSet<u16>,
}

impl State {
    pub fn new() -> Self;
    pub fn toggle_normal(&mut self);
    pub fn exit_normal(&mut self);
    pub fn check_double_tap(&self, now: f64, key: u16) -> bool;
}
```

### 3. devices.rs

```rust
pub struct Device {
    fd: RawFd,
    name: String,
    path: String,
}

pub struct InputManager {
    devices: Vec<Device>,
    selector: Selector,
}

impl InputManager {
    pub fn new() -> Result<Self>;
    pub fn grab_all(&mut self);
    pub fn ungrab_all(&mut self);
    pub async fn read_event(&mut self) -> Option<InputEvent>;
}
```

- Async device polling with tokio
- Auto-discover keyboards
- Filter out ydotoold device

### 4. keyboard.rs

```rust
pub struct KeyHandler {
    config: Config,
    state: State,
    caps_lock_time: f64,
    caps_as_ctrl: bool,
}

impl KeyHandler {
    pub fn new(config: Config) -> Self;
    pub fn handle_event(&mut self, event: InputEvent) -> Vec<OutputEvent>;
}

pub struct OutputEvent {
    pub code: u16,
    pub pressed: bool,
}
```

- Mode-specific key handling
- caps2esc logic
- Double-tap detection
- Key mapping lookup

### 5. uinput.rs

```rust
pub struct UinputDevice {
    device: uinput::Device,
}

impl UinputDevice {
    pub fn new() -> Result<Self>;
    pub fn emit_key(&self, code: u16, pressed: bool) -> Result<()>;
    pub fn emit_keys(&self, codes: &[u16]) -> Result<()>;
}
```

- Direct uinput injection
- No subprocess
- Batch key sequences

### 6. command.rs

```rust
pub async fn run_command_mode() -> Option<String>;

pub enum Command {
    Quit,
    QuitAll,
    Delete,
    Save,
    SaveQuit,
    Close,
    TabNew,
    TabNext,
    TabPrev,
    Help,
    Unknown,
}

pub fn parse_command(input: &str) -> Command;
```

- Spawn wofi/fuzzel
- Parse user input
- Execute mapped action

---

## Key Mapping Table

### Insert Mode

| Input | Output | Notes |
|-------|--------|-------|
| capslock tap | escape | capslock → esc |
| capslock hold + key | ctrl + key | modifier |
| escape tap | escape | pass through |
| any key | key | re-emit via uinput |

### Normal Mode

| Key | Action |
|-----|--------|
| h | left (105) |
| j | down (108) |
| k | up (103) |
| l | right (106) |
| w | ctrl+right |
| b | ctrl+left |
| e | end (107) |
| i | exit to insert |
| a | exit + right |
| ; | command mode |
| / | command mode |
| 0 | home (102) |
| $ | end (107) |
| g | home (102) |
| gg | home (double tap) |

### Command Mode

| Command | Action | Keys |
|---------|--------|------|
| q | close | Alt+F4 |
| qa | quit all | Ctrl+Q |
| d | delete | backspace |
| w | save | Ctrl+S |
| x | save+quit | Ctrl+S, Alt+F4 |
| c | close | Alt+F4 |
| tab | new tab | Ctrl+T |
| tn | next tab | Ctrl+Tab |
| tp | prev tab | Ctrl+Shift+Tab |
| h | help | notify |

---

## Modifier Keys

Only these are true modifiers:
- 29: leftctrl
- 97: rightctrl
- 42: leftshift
- 54: rightshift
- 56: leftalt
- 100: rightalt
- 125: leftmeta
- 126: rightmeta
- 58: capslock

---

## System Integration

### PID File
- Path: ~/.config/viland/viland.pid
- Write on start, delete on exit
- Check on startup to prevent duplicates

### Logging
- Path: ~/.config/viland/viland.log
- Use tracing-subscriber with file appender
- Format: "[TIMESTAMP] [LEVEL] message"
- Rotate on size (10MB max)

### Config File
- Path: ~/.config/viland/config.toml
- TOML format
- Watch for changes (reload on SIGHUP)

### Exit Override
- Ctrl+Alt+Q → exit daemon
- Check pressed_keys set

### Cleanup on Exit
- Release all pressed keys
- Ungrab devices
- Delete PID file

---

## Performance Targets

- Key latency: < 1ms (Python: 10-50ms)
- Device poll: < 1ms (Python: 10-100ms)
- Memory: < 10MB
- CPU: < 1% idle

---

## Async Flow

```rust
#[tokio::main]
async fn main() {
    // Initialize
    let config = load_config();
    let mut devices = InputManager::new()?;
    devices.grab_all();
    let uinput = UinputDevice::new()?;
    let mut state = State::new();

    // Main loop
    loop {
        tokio::select! {
            event = devices.read_event() => {
                if let Some(event) = event {
                    let outputs = handle_key_event(&mut state, event, &config);
                    for out in outputs {
                        uinput.emit_key(out.code, out.pressed);
                    }
                }
            }
            _ = tokio::signal::ctrl_c() => {
                break;
            }
        }
    }

    // Cleanup
    cleanup(&mut state, &mut devices);
}
```

---

## TODO

### Phase 1: Core
- [ ] Project setup with Cargo
- [ ] Config loading
- [ ] Device discovery
- [ ] Basic event loop

### Phase 2: Input/Output
- [ ] uinput device creation
- [ ] Key event handling
- [ ] Mode state machine

### Phase 3: Features
- [ ] caps2esc implementation
- [ ] Normal mode key mappings
- [ ] Command mode (wofi)

### Phase 4: Polish
- [ ] Logging to file
- [ ] PID file handling
- [ ] Exit override
- [ ] Cleanup on exit

### Phase 5: Testing
- [ ] Latency benchmark
- [ ] Key release test
- [ ] Mode switching test
- [ ] Command mode test