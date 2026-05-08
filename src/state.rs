use std::collections::HashSet;
use std::time::Instant;

use crate::device::DeviceManager;
use crate::event::{KeyState, KEY_ESC, KEY_LEFTCTRL, KEY_LEFTALT, KEY_BACKSPACE};
use crate::keymap::{Action, KeyAction, Keymap, Mode};
use crate::VilandError;
use tracing::debug;

const DOUBLE_TAP_TIMEOUT_MS: u64 = 300;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum CapsState {
    Idle,
    PendingTap,
    HeldCtrl,
}

pub struct State {
    mode: Mode,
    keymap: Keymap,
    caps_state: CapsState,
    last_caps_press: Option<Instant>,
    last_caps_release: Option<Instant>,
    physical_pressed: HashSet<u16>,
    virtual_pressed: HashSet<u16>,
    exit_requested: bool,
}

impl State {
    pub fn new() -> Self {
        Self {
            mode: Mode::Insert,
            keymap: Keymap::new(),
            caps_state: CapsState::Idle,
            last_caps_press: None,
            last_caps_release: None,
            physical_pressed: HashSet::new(),
            virtual_pressed: HashSet::new(),
            exit_requested: false,
        }
    }

    pub fn should_exit(&self) -> bool {
        self.exit_requested
    }

    pub fn process_event(
        &mut self,
        ev: crate::event::Event,
        device_manager: &mut DeviceManager,
    ) -> Result<(), VilandError> {
        debug!("Processing: {} in mode {:?}", ev, self.mode);

        self.track_physical_key(ev.key_code, ev.key_state);

        if self.is_emergency_exit(&ev) {
            self.exit_requested = true;
            return Ok(());
        }

        match self.mode {
            Mode::Insert => self.handle_insert_mode(ev, device_manager),
            Mode::Normal => self.handle_normal_mode(ev, device_manager),
        }
    }

    fn handle_insert_mode(
        &mut self,
        ev: crate::event::Event,
        device_manager: &mut DeviceManager,
    ) -> Result<(), VilandError> {
        if ev.is_capslock() {
            return self.handle_caps_event(ev, device_manager);
        }

        if self.caps_state == CapsState::PendingTap && !ev.is_capslock() {
            device_manager.emit_key_press(KEY_LEFTCTRL)?;
            self.virtual_pressed.insert(KEY_LEFTCTRL);
            self.caps_state = CapsState::HeldCtrl;
            debug!("caps + key: ctrl activated");
        }

        if self.caps_state == CapsState::HeldCtrl && !ev.is_capslock() {
            if ev.key_state == KeyState::Press {
                device_manager.emit_key(ev.key_code, KeyState::Press)?;
                self.virtual_pressed.insert(ev.key_code);
            } else if ev.key_state == KeyState::Release {
                device_manager.emit_key(ev.key_code, KeyState::Release)?;
                self.virtual_pressed.remove(&ev.key_code);
            } else if ev.key_state == KeyState::Repeat {
                device_manager.emit_key(ev.key_code, KeyState::Repeat)?;
            }
            return Ok(());
        }

        match ev.key_state {
            KeyState::Press => {
                device_manager.emit_key_press(ev.key_code)?;
                self.virtual_pressed.insert(ev.key_code);
            }
            KeyState::Release => {
                device_manager.emit_key_release(ev.key_code)?;
                self.virtual_pressed.remove(&ev.key_code);
            }
            KeyState::Repeat => {
                device_manager.emit_key(ev.key_code, KeyState::Repeat)?;
            }
        }

        Ok(())
    }

    fn handle_normal_mode(
        &mut self,
        ev: crate::event::Event,
        device_manager: &mut DeviceManager,
    ) -> Result<(), VilandError> {
        let action = self.keymap.get_action(ev.key_code, self.mode);

        match action {
            Action::PassThrough => unreachable!(),
            Action::Ignore => {}
            Action::SwitchMode(new_mode) => {
                self.mode = new_mode;
                debug!("Switched to {:?}", self.mode);
            }
            Action::Emit(key) => {
                match ev.key_state {
                    KeyState::Press => {
                        device_manager.emit_key_press(key)?;
                        self.virtual_pressed.insert(key);
                    }
                    KeyState::Release => {
                        device_manager.emit_key_release(key)?;
                        self.virtual_pressed.remove(&key);
                    }
                    KeyState::Repeat => {
                        device_manager.emit_key(key, KeyState::Repeat)?;
                    }
                }
            }
            Action::EmitChord(actions) => {
                match ev.key_state {
                    KeyState::Press => {
                        for action in actions {
                            if let KeyAction::Press(key) = action {
                                device_manager.emit_key_press(key)?;
                                self.virtual_pressed.insert(key);
                            }
                        }
                    }
                    KeyState::Release => {
                        for action in actions.iter().rev() {
                            if let KeyAction::Press(key) = *action {
                                device_manager.emit_key_release(key)?;
                                self.virtual_pressed.remove(&key);
                            }
                        }
                    }
                    KeyState::Repeat => {
                        if let Some(&KeyAction::Press(last_key)) = actions.last() {
                            device_manager.emit_key(last_key, KeyState::Repeat)?;
                        }
                    }
                }
            }
            Action::Sequence(actions) => {
                match ev.key_state {
                    KeyState::Press => {
                        for action in actions {
                            match action {
                                KeyAction::Press(key) => {
                                    device_manager.emit_key_press(key)?;
                                    self.virtual_pressed.insert(key);
                                }
                                KeyAction::Tap(key) => {
                                    device_manager.emit_key_press(key)?;
                                    self.virtual_pressed.insert(key);
                                }
                                KeyAction::Release(_) => {}
                            }
                        }
                    }
                    KeyState::Release => {
                        for action in actions.iter().rev() {
                            match *action {
                                KeyAction::Release(key) => {
                                    device_manager.emit_key_release(key)?;
                                    self.virtual_pressed.remove(&key);
                                }
                                KeyAction::Tap(key) => {
                                    device_manager.emit_key_release(key)?;
                                    self.virtual_pressed.remove(&key);
                                }
                                KeyAction::Press(_) => {}
                            }
                        }
                    }
                    KeyState::Repeat => {}
                }
            }
        }

        Ok(())
    }

    fn handle_caps_event(
        &mut self,
        ev: crate::event::Event,
        device_manager: &mut DeviceManager,
    ) -> Result<(), VilandError> {
        let now = Instant::now();

        match (ev.key_state, self.caps_state) {
            (KeyState::Press, CapsState::Idle) => {
                if let Some(last_release) = self.last_caps_release {
                    if (now.duration_since(last_release).as_millis() as u64) < DOUBLE_TAP_TIMEOUT_MS {
                        self.mode = Mode::Normal;
                        self.caps_state = CapsState::Idle;
                        debug!("Double tap: entered Normal mode");
                        return Ok(());
                    }
                }
                self.last_caps_press = Some(now);
                self.caps_state = CapsState::PendingTap;
            }
            (KeyState::Press, CapsState::PendingTap) => {}
            (KeyState::Release, CapsState::PendingTap) => {
                device_manager.emit_key_press(KEY_ESC)?;
                device_manager.emit_key_release(KEY_ESC)?;
                self.caps_state = CapsState::Idle;
                self.last_caps_release = Some(now);
            }
            (KeyState::Release, CapsState::HeldCtrl) => {
                if self.virtual_pressed.remove(&KEY_LEFTCTRL) {
                    device_manager.emit_key_release(KEY_LEFTCTRL)?;
                }
                self.caps_state = CapsState::Idle;
                self.last_caps_release = Some(now);
            }
            _ => {}
        }

        Ok(())
    }

    fn is_emergency_exit(&self, ev: &crate::event::Event) -> bool {
        if !ev.is_backspace() {
            return false;
        }
        if ev.key_state != KeyState::Press {
            return false;
        }
        self.physical_pressed.contains(&KEY_LEFTCTRL)
            && self.physical_pressed.contains(&KEY_LEFTALT)
    }

    fn track_physical_key(&mut self, key: u16, state: KeyState) {
        match state {
            KeyState::Press => {
                self.physical_pressed.insert(key);
            }
            KeyState::Release => {
                self.physical_pressed.remove(&key);
            }
            KeyState::Repeat => {}
        }
    }

    pub fn release_all_virtual(&self, device_manager: &mut DeviceManager) {
        device_manager.release_all_keys(&self.virtual_pressed);
    }
}

impl Default for State {
    fn default() -> Self {
        Self::new()
    }
}