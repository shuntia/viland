# Rust Rewrite TODO

## Phase 1: Project Setup

- [ ] Create new Rust project: `cargo new viland-rs`
- [ ] Add dependencies to Cargo.toml
- [ ] Set up logging with tracing
- [ ] Create basic CLI with clap
- [ ] Test compilation

## Phase 2: Core Infrastructure

### config.rs
- [ ] Define Config struct with serde
- [ ] Implement load_config() from TOML
- [ ] Add default values
- [ ] Add config validation

### state.rs
- [ ] Define Mode enum (Insert, Normal, Command)
- [ ] Define State struct
- [ ] Implement double_tap detection
- [ ] Implement pressed_keys tracking

### devices.rs
- [ ] Discover keyboards via evdev
- [ ] Filter out non-keyboard devices
- [ ] Filter out ydotoold device
- [ ] Implement async read with tokio
- [ ] Implement grab/ungrab

## Phase 3: Input Handling

### keyboard.rs
- [ ] Define key mapping table
- [ ] Implement caps2esc logic
- [ ] Implement modifier detection (only true modifiers)
- [ ] Implement normal mode key mapping
- [ ] Implement insert mode pass-through
- [ ] Return Vec<OutputEvent> for batched output

### uinput.rs
- [ ] Create uinput device
- [ ] Implement emit_key()
- [ ] Implement emit_keys() for sequences
- [ ] Test basic key injection

## Phase 4: Features

### Command Mode
- [ ] Spawn wofi/fuzzel subprocess
- [ ] Parse command input
- [ ] Map commands to key sequences
- [ ] Add 5 second timeout

### Mode Switching
- [ ] Double-tap capslock → normal mode
- [ ] Double-tap escape → normal mode
- [ ] i/a in normal → insert mode
- [ ] Escape in normal → no action (user must use i/a)

### System Integration
- [ ] Write PID file on start
- [ ] Check PID on start (prevent duplicates)
- [ ] Ctrl+Alt+Q to exit daemon
- [ ] Cleanup all keys on exit

## Phase 5: Testing & Polish

### Testing
- [ ] Test key latency (< 1ms target)
- [ ] Test mode switching
- [ ] Test caps2esc (tap → esc, hold+key → ctrl+key)
- [ ] Test all normal mode keys
- [ ] Test command mode
- [ ] Test key release on exit
- [ ] Test multiple key combinations

### Performance
- [ ] Benchmark key injection latency
- [ ] Profile memory usage
- [ ] Check CPU usage

### Polish
- [ ] Add file logging
- [ ] Add config hot-reload (SIGHUP)
- [ ] Add systemd service file
- [ ] Document all key bindings