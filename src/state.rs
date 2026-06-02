use std::collections::{HashMap, HashSet};

use crate::device::DeviceManager;
use crate::event::{
    KeyState, KEY_ESC, KEY_LEFTCTRL, KEY_LEFTALT, KEY_RIGHTCTRL, KEY_RIGHTALT,
    KEY_LEFTSHIFT, KEY_RIGHTSHIFT, KEY_HOME, KEY_END,
    KEY_Q, KEY_V, KEY_D, KEY_Y, KEY_P, KEY_C,
    KEY_O, KEY_UP, KEY_ENTER,
    KEY_A, KEY_I, KEY_G, KEY_N, KEY_S, KEY_X,
    KEY_BACKSPACE, KEY_F3, KEY_DELETE,
};
use crate::keymap::{Action, KeyAction, Keymap, Mode, Motion, Operator};
use crate::VilandError;
use tracing::{debug, info};

fn is_modifier_key(key: u16) -> bool {
    matches!(key,
        KEY_LEFTSHIFT | KEY_RIGHTSHIFT |
        KEY_LEFTCTRL  | KEY_RIGHTCTRL  |
        KEY_LEFTALT   | KEY_RIGHTALT
    )
}

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
    alt_pending: bool,
    physical_pressed: HashSet<u16>,
    virtual_pressed: HashSet<u16>,
    exit_requested: bool,
    pending_operator: Option<Operator>,
    consumed_motion_key: Option<u16>,
    // Macro recording
    recording_register: Option<u16>,
    current_recording: Vec<(u16, KeyState)>,
    registers: HashMap<u16, Vec<(u16, KeyState)>>,
    pending_register_select: bool,
    skip_release_of: Option<u16>,
    // Macro playback
    pending_playback: bool,
    replaying: bool,
}

impl State {
    pub fn new() -> Self {
        Self {
            mode: Mode::Normal,
            keymap: Keymap::new(),
            caps_state: CapsState::Idle,
            alt_pending: false,
            physical_pressed: HashSet::new(),
            virtual_pressed: HashSet::new(),
            exit_requested: false,
            pending_operator: None,
            consumed_motion_key: None,
            recording_register: None,
            current_recording: Vec::new(),
            registers: HashMap::new(),
            pending_register_select: false,
            skip_release_of: None,
            pending_playback: false,
            replaying: false,
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

        // Record physical events into the active register buffer
        if self.recording_register.is_some() && !self.replaying {
            let is_skip = ev.key_state == KeyState::Release
                && Some(ev.key_code) == self.skip_release_of;
            if is_skip {
                self.skip_release_of = None;
            } else if ev.key_code != KEY_Q {
                self.current_recording.push((ev.key_code, ev.key_state));
            }
        }

        if self.is_emergency_exit(&ev) {
            self.exit_requested = true;
            return Ok(());
        }

        self.dispatch(ev, device_manager)
    }

    fn dispatch(
        &mut self,
        ev: crate::event::Event,
        device_manager: &mut DeviceManager,
    ) -> Result<(), VilandError> {
        match self.mode {
            Mode::Insert => self.handle_insert_mode(ev, device_manager),
            Mode::Normal => self.handle_normal_mode(ev, device_manager),
            Mode::Visual => self.handle_visual_mode(ev, device_manager),
        }
    }

    fn switch_mode(&mut self, new_mode: Mode, device_manager: &mut DeviceManager) {
        if self.mode != new_mode {
            info!("Switching from {:?} to {:?}", self.mode, new_mode);
            let _ = std::process::Command::new("notify-send")
                .args(["-t", "800", "-h", "string:x-canonical-private-synchronous:viland", "Viland", &format!("Mode: {:?}", new_mode)])
                .spawn();
            self.release_all_virtual(device_manager);
            self.virtual_pressed.clear();
            self.alt_pending = false;
            self.pending_register_select = false;
            self.pending_playback = false;
            self.mode = new_mode;
        }
    }

    fn execute_operator_motion(
        &mut self,
        op: Operator,
        motion: Motion,
        dm: &mut DeviceManager,
    ) -> Result<(), VilandError> {
        let mods = motion.modifiers();
        let base = motion.base_key();
        let (opt_mod, action_key) = op.action_keys();

        dm.emit_key_press(KEY_LEFTSHIFT)?;
        for &m in &mods {
            dm.emit_key_press(m)?;
        }
        dm.emit_key_press(base)?;
        dm.emit_key_release(base)?;
        for &m in mods.iter().rev() {
            dm.emit_key_release(m)?;
        }
        dm.emit_key_release(KEY_LEFTSHIFT)?;

        if let Some(m) = opt_mod {
            dm.emit_key_press(m)?;
        }
        dm.emit_key_press(action_key)?;
        dm.emit_key_release(action_key)?;
        if let Some(m) = opt_mod {
            dm.emit_key_release(m)?;
        }

        if op.enters_insert() {
            self.switch_mode(Mode::Insert, dm);
        }

        Ok(())
    }

    fn execute_visual_operator(
        &mut self,
        op: Operator,
        dm: &mut DeviceManager,
    ) -> Result<(), VilandError> {
        if self.virtual_pressed.remove(&KEY_LEFTSHIFT) {
            dm.emit_key_release(KEY_LEFTSHIFT)?;
        }

        let (opt_mod, action_key) = op.action_keys();
        if let Some(m) = opt_mod {
            dm.emit_key_press(m)?;
        }
        dm.emit_key_press(action_key)?;
        dm.emit_key_release(action_key)?;
        if let Some(m) = opt_mod {
            dm.emit_key_release(m)?;
        }

        let after = if op.enters_insert() { Mode::Insert } else { Mode::Normal };
        self.switch_mode(after, dm);
        Ok(())
    }

    fn playback_register(
        &mut self,
        reg: u16,
        dm: &mut DeviceManager,
    ) -> Result<(), VilandError> {
        let events = match self.registers.get(&reg).cloned() {
            Some(e) if !e.is_empty() => e,
            _ => return Ok(()),
        };

        info!("Playing back register {} ({} events)", reg, events.len());

        // Snapshot and clear physical_pressed so held modifiers don't contaminate replay
        let saved_physical = std::mem::take(&mut self.physical_pressed);
        self.replaying = true;

        for (key_code, key_state) in events {
            let ev = crate::event::Event::new(0, key_code, key_state, 0);
            let _ = self.dispatch(ev, dm);
        }

        self.replaying = false;
        self.physical_pressed = saved_physical;
        Ok(())
    }

    fn handle_visual_mode(
        &mut self,
        ev: crate::event::Event,
        device_manager: &mut DeviceManager,
    ) -> Result<(), VilandError> {
        if ev.key_state == KeyState::Release && self.virtual_pressed.contains(&ev.key_code) {
            device_manager.emit_key_release(ev.key_code)?;
            self.virtual_pressed.remove(&ev.key_code);
            return Ok(());
        }

        if ev.key_state == KeyState::Press {
            match ev.key_code {
                KEY_V | KEY_ESC => {
                    self.switch_mode(Mode::Normal, device_manager);
                    return Ok(());
                }
                KEY_D => {
                    self.execute_visual_operator(Operator::Delete, device_manager)?;
                    return Ok(());
                }
                KEY_Y => {
                    self.execute_visual_operator(Operator::Yank, device_manager)?;
                    return Ok(());
                }
                KEY_P => {
                    self.execute_visual_operator(Operator::Paste, device_manager)?;
                    return Ok(());
                }
                KEY_C => {
                    self.execute_visual_operator(Operator::Change, device_manager)?;
                    return Ok(());
                }
                _ => {}
            }
        }

        self.handle_normal_mode(ev, device_manager)
    }

    fn handle_insert_mode(
        &mut self,
        ev: crate::event::Event,
        device_manager: &mut DeviceManager,
    ) -> Result<(), VilandError> {
        if ev.is_capslock() {
            return self.handle_caps_event(ev, device_manager);
        }

        if ev.key_code == KEY_LEFTALT {
            return self.handle_alt_event(ev, device_manager);
        }

        // Another key pressed while Alt is held: commit Alt as a real modifier
        if self.alt_pending && ev.key_state == KeyState::Press {
            device_manager.emit_key_press(KEY_LEFTALT)?;
            self.virtual_pressed.insert(KEY_LEFTALT);
            self.alt_pending = false;
        }

        if self.caps_state == CapsState::PendingTap && !ev.is_capslock() {
            device_manager.emit_key_press(KEY_LEFTCTRL)?;
            self.virtual_pressed.insert(KEY_LEFTCTRL);
            self.caps_state = CapsState::HeldCtrl;
            debug!("caps + key: ctrl activated");
        }

        if self.caps_state == CapsState::HeldCtrl && !ev.is_capslock() {
            match ev.key_state {
                KeyState::Press => {
                    device_manager.emit_key(ev.key_code, KeyState::Press)?;
                    self.virtual_pressed.insert(ev.key_code);
                }
                KeyState::Release => {
                    if self.virtual_pressed.remove(&ev.key_code) {
                        device_manager.emit_key(ev.key_code, KeyState::Release)?;
                    }
                }
                KeyState::Repeat => {
                    if self.virtual_pressed.contains(&ev.key_code) {
                        device_manager.emit_key(ev.key_code, KeyState::Repeat)?;
                    }
                }
            }
            return Ok(());
        }

        match ev.key_state {
            KeyState::Press => {
                device_manager.emit_key_press(ev.key_code)?;
                self.virtual_pressed.insert(ev.key_code);
            }
            KeyState::Release => {
                if self.virtual_pressed.remove(&ev.key_code) {
                    device_manager.emit_key_release(ev.key_code)?;
                }
            }
            KeyState::Repeat => {
                if self.virtual_pressed.contains(&ev.key_code) {
                    device_manager.emit_key(ev.key_code, KeyState::Repeat)?;
                }
            }
        }

        Ok(())
    }

    fn handle_alt_event(
        &mut self,
        ev: crate::event::Event,
        device_manager: &mut DeviceManager,
    ) -> Result<(), VilandError> {
        match ev.key_state {
            KeyState::Press => {
                self.alt_pending = true;
            }
            KeyState::Release => {
                if self.alt_pending {
                    self.alt_pending = false;
                    self.switch_mode(Mode::Normal, device_manager);
                } else if self.virtual_pressed.remove(&KEY_LEFTALT) {
                    device_manager.emit_key_release(KEY_LEFTALT)?;
                }
            }
            KeyState::Repeat => {
                if self.alt_pending {
                    device_manager.emit_key_press(KEY_LEFTALT)?;
                    self.virtual_pressed.insert(KEY_LEFTALT);
                    self.alt_pending = false;
                }
                device_manager.emit_key(KEY_LEFTALT, KeyState::Repeat)?;
            }
        }
        Ok(())
    }

    fn handle_caps_event(
        &mut self,
        ev: crate::event::Event,
        device_manager: &mut DeviceManager,
    ) -> Result<(), VilandError> {
        match (ev.key_state, self.caps_state) {
            (KeyState::Press, CapsState::Idle) => {
                self.caps_state = CapsState::PendingTap;
            }
            (KeyState::Press, CapsState::PendingTap) => {}
            (KeyState::Release, CapsState::PendingTap) => {
                device_manager.emit_key_press(KEY_ESC)?;
                device_manager.emit_key_release(KEY_ESC)?;
                self.caps_state = CapsState::Idle;
            }
            (KeyState::Release, CapsState::HeldCtrl) => {
                if self.virtual_pressed.remove(&KEY_LEFTCTRL) {
                    device_manager.emit_key_release(KEY_LEFTCTRL)?;
                }
                self.caps_state = CapsState::Idle;
            }
            _ => {}
        }
        Ok(())
    }

    fn handle_normal_mode(
        &mut self,
        ev: crate::event::Event,
        device_manager: &mut DeviceManager,
    ) -> Result<(), VilandError> {
        // Swallow Repeat and Release for a key consumed by an operator or select trigger
        if Some(ev.key_code) == self.consumed_motion_key {
            if ev.key_state == KeyState::Release {
                self.consumed_motion_key = None;
            }
            return Ok(());
        }

        // Allow release of virtually pressed keys
        if ev.key_state == KeyState::Release && self.virtual_pressed.contains(&ev.key_code) {
            device_manager.emit_key_release(ev.key_code)?;
            self.virtual_pressed.remove(&ev.key_code);
            return Ok(());
        }

        // Pending register selection for recording start/stop
        if self.pending_register_select {
            if ev.key_state == KeyState::Press {
                self.pending_register_select = false;
                let reg = ev.key_code;
                if let Some(active_reg) = self.recording_register {
                    if active_reg == reg {
                        // Same register: stop recording
                        let buf = std::mem::take(&mut self.current_recording);
                        self.registers.insert(reg, buf);
                        self.recording_register = None;
                        info!("Recording stopped for register {}", reg);
                        let _ = std::process::Command::new("notify-send")
                            .args(["-t", "800", "-h", "string:x-canonical-private-synchronous:viland",
                                   "Viland", "Recording stopped"])
                            .spawn();
                    } else {
                        // Different register: stop current, start new
                        let buf = std::mem::take(&mut self.current_recording);
                        self.registers.insert(active_reg, buf);
                        self.recording_register = Some(reg);
                        self.skip_release_of = Some(reg);
                        self.consumed_motion_key = Some(reg);
                        info!("Recording to register {}", reg);
                        let _ = std::process::Command::new("notify-send")
                            .args(["-t", "800", "-h", "string:x-canonical-private-synchronous:viland",
                                   "Viland", "Recording..."])
                            .spawn();
                    }
                } else {
                    // Start recording to new register
                    self.current_recording.clear();
                    self.recording_register = Some(reg);
                    self.skip_release_of = Some(reg);
                    self.consumed_motion_key = Some(reg);
                    info!("Recording to register {}", reg);
                    let _ = std::process::Command::new("notify-send")
                        .args(["-t", "800", "-h", "string:x-canonical-private-synchronous:viland",
                               "Viland", "Recording..."])
                        .spawn();
                }
            }
            return Ok(());
        }

        // Pending playback register selection
        if self.pending_playback {
            if ev.key_state == KeyState::Press {
                self.pending_playback = false;
                let reg = ev.key_code;
                self.consumed_motion_key = Some(reg);
                if !self.replaying {
                    self.playback_register(reg, device_manager)?;
                }
            }
            return Ok(());
        }

        // Pending operator: consume next key as motion or cancel
        if self.pending_operator.is_some() {
            if ev.key_state == KeyState::Press {
                if is_modifier_key(ev.key_code) {
                    // Let Shift/Ctrl/Alt presses fall through so d$ / d^ work
                    return Ok(());
                }
                if let Some(motion) = Motion::from_key_shifted(ev.key_code, self.is_shift_pressed()) {
                    let op = self.pending_operator.take().unwrap();
                    self.execute_operator_motion(op, motion, device_manager)?;
                    self.consumed_motion_key = Some(ev.key_code);
                } else {
                    self.pending_operator = None;
                }
            }
            return Ok(());
        }

        let mut action = self.keymap.get_action(ev.key_code, self.mode);

        if (ev.key_code == crate::event::KEY_4 || ev.key_code == crate::event::KEY_6) && self.is_shift_pressed() {
            action = if ev.key_code == crate::event::KEY_4 {
                Action::Emit(KEY_END)
            } else {
                Action::Emit(KEY_HOME)
            };
        }

        // O (Shift+O): open line above
        if ev.key_code == KEY_O && self.is_shift_pressed() {
            action = Action::Sequence(vec![
                KeyAction::Tap(KEY_HOME),
                KeyAction::Tap(KEY_ENTER),
                KeyAction::Tap(KEY_UP),
                KeyAction::SwitchMode(Mode::Insert),
            ]);
        }

        if self.is_shift_pressed() {
            match ev.key_code {
                // A: append at end of line
                KEY_A => action = Action::Sequence(vec![
                    KeyAction::Tap(KEY_END),
                    KeyAction::SwitchMode(Mode::Insert),
                ]),
                // I: insert at beginning of line
                KEY_I => action = Action::Sequence(vec![
                    KeyAction::Tap(KEY_HOME),
                    KeyAction::SwitchMode(Mode::Insert),
                ]),
                // X: delete backward (backspace)
                KEY_X => action = Action::Emit(KEY_BACKSPACE),
                // N: find previous (Shift+F3)
                KEY_N => {
                    if ev.key_state == KeyState::Press {
                        device_manager.emit_key_press(KEY_LEFTSHIFT)?;
                        device_manager.emit_key_press(KEY_F3)?;
                        device_manager.emit_key_release(KEY_F3)?;
                        device_manager.emit_key_release(KEY_LEFTSHIFT)?;
                    }
                    return Ok(());
                }
                // C: change to end of line (Shift+End to select, Delete, Insert)
                KEY_C => {
                    if ev.key_state == KeyState::Press {
                        device_manager.emit_key_press(KEY_LEFTSHIFT)?;
                        device_manager.emit_key_press(KEY_END)?;
                        device_manager.emit_key_release(KEY_END)?;
                        device_manager.emit_key_release(KEY_LEFTSHIFT)?;
                        device_manager.emit_key_press(KEY_DELETE)?;
                        device_manager.emit_key_release(KEY_DELETE)?;
                        self.switch_mode(Mode::Insert, device_manager);
                    }
                    return Ok(());
                }
                // S: substitute line (Home, Shift+End to select, Delete, Insert)
                KEY_S => {
                    if ev.key_state == KeyState::Press {
                        device_manager.emit_key_press(KEY_HOME)?;
                        device_manager.emit_key_release(KEY_HOME)?;
                        device_manager.emit_key_press(KEY_LEFTSHIFT)?;
                        device_manager.emit_key_press(KEY_END)?;
                        device_manager.emit_key_release(KEY_END)?;
                        device_manager.emit_key_release(KEY_LEFTSHIFT)?;
                        device_manager.emit_key_press(KEY_DELETE)?;
                        device_manager.emit_key_release(KEY_DELETE)?;
                        self.switch_mode(Mode::Insert, device_manager);
                    }
                    return Ok(());
                }
                // G: end of file (Ctrl+End)
                KEY_G => {
                    if ev.key_state == KeyState::Press {
                        device_manager.emit_key_press(KEY_LEFTCTRL)?;
                        device_manager.emit_key_press(KEY_END)?;
                        device_manager.emit_key_release(KEY_END)?;
                        device_manager.emit_key_release(KEY_LEFTCTRL)?;
                    }
                    return Ok(());
                }
                _ => {}
            }
        }

        // @ (Shift+2): arm macro playback
        if ev.key_code == crate::event::KEY_2 && self.is_shift_pressed() {
            if ev.key_state == KeyState::Press && !self.replaying {
                self.pending_playback = true;
                self.consumed_motion_key = Some(crate::event::KEY_2);
            }
            return Ok(());
        }

        match action {
            Action::PassThrough => {
                tracing::warn!("PassThrough action in Normal mode for key {}, ignoring", ev.key_code);
            }
            Action::Ignore => {}
            Action::SwitchMode(new_mode) => {
                if ev.key_state == KeyState::Press {
                    self.switch_mode(new_mode, device_manager);
                    if new_mode == Mode::Visual {
                        device_manager.emit_key_press(KEY_LEFTSHIFT)?;
                        self.virtual_pressed.insert(KEY_LEFTSHIFT);
                    }
                }
            }
            Action::PendingOperator(op) => {
                if ev.key_state == KeyState::Press {
                    self.pending_operator = Some(op);
                }
            }
            Action::ToggleRecording => {
                if ev.key_state == KeyState::Press {
                    if let Some(reg) = self.recording_register.take() {
                        // Stop recording
                        let buf = std::mem::take(&mut self.current_recording);
                        self.registers.insert(reg, buf);
                        info!("Macro recording stopped for register {}", reg);
                        let _ = std::process::Command::new("notify-send")
                            .args(["-t", "800", "-h", "string:x-canonical-private-synchronous:viland",
                                   "Viland", "Recording stopped"])
                            .spawn();
                    } else {
                        // Arm register selection
                        self.pending_register_select = true;
                    }
                }
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
                            match action {
                                KeyAction::Press(key) => {
                                    device_manager.emit_key_press(key)?;
                                    self.virtual_pressed.insert(key);
                                }
                                KeyAction::SwitchMode(new_mode) => {
                                    self.switch_mode(new_mode, device_manager);
                                }
                                KeyAction::Tap(key) => {
                                    device_manager.emit_key_press(key)?;
                                    self.virtual_pressed.insert(key);
                                    device_manager.emit_key_release(key)?;
                                    self.virtual_pressed.remove(&key);
                                }
                            }
                        }
                    }
                    KeyState::Release => {
                        for action in actions.iter().rev() {
                            if let KeyAction::Press(key) = *action {
                                // Only release if we actually pressed it
                                if self.virtual_pressed.remove(&key) {
                                    device_manager.emit_key_release(key)?;
                                }
                            }
                        }
                    }
                    KeyState::Repeat => {
                        if let Some(&KeyAction::Press(key)) = actions.iter().rev().find(|a| matches!(a, KeyAction::Press(_))) {
                            device_manager.emit_key(key, KeyState::Repeat)?;
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
                                    device_manager.emit_key_release(key)?;
                                    self.virtual_pressed.remove(&key);
                                }
                                KeyAction::SwitchMode(new_mode) => {
                                    self.switch_mode(new_mode, device_manager);
                                }
                            }
                        }
                    }
                    KeyState::Release => {
                        for action in actions.iter().rev() {
                            if let KeyAction::Press(key) = *action {
                                if self.virtual_pressed.remove(&key) {
                                    device_manager.emit_key_release(key)?;
                                }
                            }
                        }
                    }
                    KeyState::Repeat => {}
                }
            }
        }

        Ok(())
    }

    fn is_emergency_exit(&self, ev: &crate::event::Event) -> bool {
        if !ev.is_backspace() || ev.key_state != KeyState::Press {
            return false;
        }

        let ctrl = self.physical_pressed.contains(&KEY_LEFTCTRL)
                || self.physical_pressed.contains(&KEY_RIGHTCTRL);
        let alt = self.physical_pressed.contains(&KEY_LEFTALT)
               || self.physical_pressed.contains(&KEY_RIGHTALT);

        ctrl && alt
    }

    fn is_shift_pressed(&self) -> bool {
        self.physical_pressed.contains(&KEY_LEFTSHIFT)
            || self.physical_pressed.contains(&KEY_RIGHTSHIFT)
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
