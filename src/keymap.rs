use crate::event::{KEY_LEFTCTRL, KEY_LEFT, KEY_RIGHT, KEY_DOWN, KEY_UP, KEY_LEFTMETA, KEY_Y, KEY_P, KEY_U, KEY_SLASH, KEY_F, KEY_C, KEY_V, KEY_Z, KEY_CAPSLOCK, KEY_ESC};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Mode {
    Insert,
    Normal,
}

#[derive(Debug, Clone, Copy)]
pub enum KeyAction {
    Press(u16),
    Tap(u16),
    SwitchMode(Mode),
}

#[derive(Debug, Clone)]
pub enum Action {
    PassThrough,
    Emit(u16),
    EmitChord(Vec<KeyAction>),
    Sequence(Vec<KeyAction>),
    Ignore,
    SwitchMode(Mode),
}

pub struct Keymap {
    normal_mode_keys: std::collections::HashMap<u16, Action>,
}

impl Keymap {
    pub fn new() -> Self {
        let mut normal_mode_keys = std::collections::HashMap::new();

        normal_mode_keys.insert(crate::event::KEY_W, Action::EmitChord(vec![
            KeyAction::Press(KEY_LEFTCTRL),
            KeyAction::Press(KEY_RIGHT),
        ]));
        normal_mode_keys.insert(crate::event::KEY_B, Action::EmitChord(vec![
            KeyAction::Press(KEY_LEFTCTRL),
            KeyAction::Press(KEY_LEFT),
        ]));

        normal_mode_keys.insert(crate::event::KEY_I, Action::SwitchMode(Mode::Insert));
        normal_mode_keys.insert(crate::event::KEY_A, Action::Sequence(vec![
            KeyAction::Tap(KEY_RIGHT),
            KeyAction::SwitchMode(Mode::Insert),
        ]));

        normal_mode_keys.insert(crate::event::KEY_H, Action::Emit(KEY_LEFT));
        normal_mode_keys.insert(crate::event::KEY_J, Action::Emit(KEY_DOWN));
        normal_mode_keys.insert(crate::event::KEY_K, Action::Emit(KEY_UP));
        normal_mode_keys.insert(crate::event::KEY_L, Action::Emit(KEY_RIGHT));
        normal_mode_keys.insert(KEY_ESC, Action::Emit(KEY_CAPSLOCK));
        
        normal_mode_keys.insert(KEY_Y, Action::EmitChord(vec![
            KeyAction::Press(KEY_LEFTCTRL),
            KeyAction::Tap(KEY_C),
        ]));
        normal_mode_keys.insert(KEY_P, Action::EmitChord(vec![
            KeyAction::Press(KEY_LEFTCTRL),
            KeyAction::Tap(KEY_V),
        ]));
        normal_mode_keys.insert(KEY_U, Action::EmitChord(vec![
            KeyAction::Press(KEY_LEFTCTRL),
            KeyAction::Tap(KEY_Z),
        ]));
        normal_mode_keys.insert(KEY_SLASH, Action::EmitChord(vec![
            KeyAction::Press(KEY_LEFTCTRL),
            KeyAction::Tap(KEY_F),
        ]));

        normal_mode_keys.insert(crate::event::KEY_1, Action::EmitChord(vec![
            KeyAction::Press(KEY_LEFTMETA),
            KeyAction::Tap(crate::event::KEY_1),
        ]));
        normal_mode_keys.insert(crate::event::KEY_2, Action::EmitChord(vec![
            KeyAction::Press(KEY_LEFTMETA),
            KeyAction::Tap(crate::event::KEY_2),
        ]));
        normal_mode_keys.insert(crate::event::KEY_3, Action::EmitChord(vec![
            KeyAction::Press(KEY_LEFTMETA),
            KeyAction::Tap(crate::event::KEY_3),
        ]));
        normal_mode_keys.insert(crate::event::KEY_4, Action::EmitChord(vec![
            KeyAction::Press(KEY_LEFTMETA),
            KeyAction::Tap(crate::event::KEY_4),
        ]));
        normal_mode_keys.insert(crate::event::KEY_5, Action::EmitChord(vec![
            KeyAction::Press(KEY_LEFTMETA),
            KeyAction::Tap(crate::event::KEY_5),
        ]));
        normal_mode_keys.insert(crate::event::KEY_6, Action::EmitChord(vec![
            KeyAction::Press(KEY_LEFTMETA),
            KeyAction::Tap(crate::event::KEY_6),
        ]));
        normal_mode_keys.insert(crate::event::KEY_7, Action::EmitChord(vec![
            KeyAction::Press(KEY_LEFTMETA),
            KeyAction::Tap(crate::event::KEY_7),
        ]));
        normal_mode_keys.insert(crate::event::KEY_8, Action::EmitChord(vec![
            KeyAction::Press(KEY_LEFTMETA),
            KeyAction::Tap(crate::event::KEY_8),
        ]));
        normal_mode_keys.insert(crate::event::KEY_9, Action::EmitChord(vec![
            KeyAction::Press(KEY_LEFTMETA),
            KeyAction::Tap(crate::event::KEY_9),
        ]));
        normal_mode_keys.insert(crate::event::KEY_0, Action::EmitChord(vec![
            KeyAction::Press(KEY_LEFTMETA),
            KeyAction::Tap(crate::event::KEY_0),
        ]));

        Self { normal_mode_keys }
    }

    pub fn get_action(&self, key_code: u16, mode: Mode) -> Action {
        if mode == Mode::Normal {
            self.normal_mode_keys
                .get(&key_code)
                .cloned()
                .unwrap_or(Action::Ignore)
        } else {
            Action::PassThrough
        }
    }
}

impl Default for Keymap {
    fn default() -> Self {
        Self::new()
    }
}