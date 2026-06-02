use crate::event::{
    KEY_LEFT, KEY_RIGHT, KEY_DOWN, KEY_UP,
    KEY_LEFTCTRL, KEY_LEFTMETA,
    KEY_Y, KEY_P, KEY_U, KEY_SLASH, KEY_F, KEY_C, KEY_V, KEY_Z,
    KEY_CAPSLOCK, KEY_ESC,
    KEY_H, KEY_J, KEY_K, KEY_L, KEY_W, KEY_B,
    KEY_D, KEY_Q, KEY_S, KEY_X, KEY_N,
    KEY_O, KEY_ENTER, KEY_HOME, KEY_END, KEY_DELETE, KEY_F3,
};
use crate::event::{KEY_4, KEY_6};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Mode {
    Insert,
    Normal,
    Visual,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Operator {
    Delete,
    Yank,
    Paste,
    Change,
}

impl Operator {
    /// Returns (optional modifier to hold, key to tap) for executing after selection.
    pub fn action_keys(&self) -> (Option<u16>, u16) {
        match self {
            Operator::Delete | Operator::Change => (None, KEY_DELETE),
            Operator::Yank  => (Some(KEY_LEFTCTRL), KEY_C),
            Operator::Paste => (Some(KEY_LEFTCTRL), KEY_V),
        }
    }

    /// Whether the operator should switch to Insert mode after executing.
    pub fn enters_insert(self) -> bool {
        matches!(self, Operator::Change)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Motion {
    Left,
    Down,
    Up,
    Right,
    WordForward,
    WordBackward,
    EndOfLine,
    StartOfLine,
}

impl Motion {
    /// Resolve a physical key to a motion, taking the current shift state into account.
    /// `shift` must reflect the physical modifier state at the time the key is pressed.
    pub fn from_key_shifted(key: u16, shift: bool) -> Option<Self> {
        match (key, shift) {
            (KEY_H, _) => Some(Motion::Left),
            (KEY_J, _) => Some(Motion::Down),
            (KEY_K, _) => Some(Motion::Up),
            (KEY_L, _) => Some(Motion::Right),
            (KEY_W, _) => Some(Motion::WordForward),
            (KEY_B, _) => Some(Motion::WordBackward),
            (KEY_4, true) => Some(Motion::EndOfLine),
            (KEY_6, true) => Some(Motion::StartOfLine),
            _ => None,
        }
    }

    pub fn modifiers(&self) -> Vec<u16> {
        match self {
            Motion::WordForward | Motion::WordBackward => vec![KEY_LEFTCTRL],
            _ => vec![],
        }
    }

    pub fn base_key(&self) -> u16 {
        match self {
            Motion::Left | Motion::WordBackward => KEY_LEFT,
            Motion::Down => KEY_DOWN,
            Motion::Up => KEY_UP,
            Motion::Right | Motion::WordForward => KEY_RIGHT,
            Motion::EndOfLine => KEY_END,
            Motion::StartOfLine => KEY_HOME,
        }
    }
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
    PendingOperator(Operator),
    ToggleRecording,
}

pub struct Keymap {
    normal_mode_keys: std::collections::HashMap<u16, Action>,
}

impl Keymap {
    pub fn new() -> Self {
        let mut normal_mode_keys = std::collections::HashMap::new();

        normal_mode_keys.insert(KEY_W, Action::EmitChord(vec![
            KeyAction::Press(KEY_LEFTCTRL),
            KeyAction::Press(KEY_RIGHT),
        ]));
        normal_mode_keys.insert(KEY_B, Action::EmitChord(vec![
            KeyAction::Press(KEY_LEFTCTRL),
            KeyAction::Press(KEY_LEFT),
        ]));

        normal_mode_keys.insert(crate::event::KEY_I, Action::SwitchMode(Mode::Insert));
        normal_mode_keys.insert(crate::event::KEY_A, Action::Sequence(vec![
            KeyAction::Tap(KEY_RIGHT),
            KeyAction::SwitchMode(Mode::Insert),
        ]));

        // o: open line below
        normal_mode_keys.insert(KEY_O, Action::Sequence(vec![
            KeyAction::Tap(KEY_END),
            KeyAction::Tap(KEY_ENTER),
            KeyAction::SwitchMode(Mode::Insert),
        ]));

        normal_mode_keys.insert(KEY_H, Action::Emit(KEY_LEFT));
        normal_mode_keys.insert(KEY_J, Action::Emit(KEY_DOWN));
        normal_mode_keys.insert(KEY_K, Action::Emit(KEY_UP));
        normal_mode_keys.insert(KEY_L, Action::Emit(KEY_RIGHT));
        normal_mode_keys.insert(KEY_ESC, Action::Emit(KEY_CAPSLOCK));

        normal_mode_keys.insert(KEY_U, Action::EmitChord(vec![
            KeyAction::Press(KEY_LEFTCTRL),
            KeyAction::Tap(KEY_Z),
        ]));
        normal_mode_keys.insert(KEY_SLASH, Action::EmitChord(vec![
            KeyAction::Press(KEY_LEFTCTRL),
            KeyAction::Tap(KEY_F),
        ]));

        // Operators
        normal_mode_keys.insert(KEY_D, Action::PendingOperator(Operator::Delete));
        normal_mode_keys.insert(KEY_C, Action::PendingOperator(Operator::Change));
        normal_mode_keys.insert(KEY_Y, Action::PendingOperator(Operator::Yank));
        normal_mode_keys.insert(KEY_P, Action::PendingOperator(Operator::Paste));

        // Single-key actions
        normal_mode_keys.insert(KEY_X, Action::Sequence(vec![KeyAction::Tap(KEY_DELETE)]));
        normal_mode_keys.insert(KEY_S, Action::Sequence(vec![
            KeyAction::Tap(KEY_DELETE),
            KeyAction::SwitchMode(Mode::Insert),
        ]));
        normal_mode_keys.insert(KEY_N, Action::Emit(KEY_F3));

        normal_mode_keys.insert(KEY_V, Action::SwitchMode(Mode::Visual));
        normal_mode_keys.insert(KEY_Q, Action::ToggleRecording);

        for (key_code, num_key) in [
            (crate::event::KEY_1, crate::event::KEY_1),
            (crate::event::KEY_2, crate::event::KEY_2),
            (crate::event::KEY_3, crate::event::KEY_3),
            (crate::event::KEY_4, crate::event::KEY_4),
            (crate::event::KEY_5, crate::event::KEY_5),
            (crate::event::KEY_6, crate::event::KEY_6),
            (crate::event::KEY_7, crate::event::KEY_7),
            (crate::event::KEY_8, crate::event::KEY_8),
            (crate::event::KEY_9, crate::event::KEY_9),
            (crate::event::KEY_0, crate::event::KEY_0),
        ] {
            normal_mode_keys.insert(key_code, Action::EmitChord(vec![
                KeyAction::Press(KEY_LEFTMETA),
                KeyAction::Tap(num_key),
            ]));
        }

        Self { normal_mode_keys }
    }

    pub fn get_action(&self, key_code: u16, mode: Mode) -> Action {
        match mode {
            Mode::Normal | Mode::Visual => {
                self.normal_mode_keys
                    .get(&key_code)
                    .cloned()
                    .unwrap_or(Action::Ignore)
            }
            Mode::Insert => Action::PassThrough,
        }
    }
}

impl Default for Keymap {
    fn default() -> Self {
        Self::new()
    }
}
