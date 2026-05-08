use std::fmt;

pub const KEY_ESC: u16 = 1;
pub const KEY_BACKSPACE: u16 = 14;

pub const KEY_LEFTCTRL: u16 = 29;
pub const KEY_LEFTALT: u16 = 56;
pub const KEY_RIGHTCTRL: u16 = 97;
pub const KEY_RIGHTALT: u16 = 100;

pub const KEY_CAPSLOCK: u16 = 58;

pub const KEY_UP: u16 = 103;
pub const KEY_DOWN: u16 = 108;
pub const KEY_LEFT: u16 = 105;
pub const KEY_RIGHT: u16 = 106;

pub const KEY_HOME: u16 = 102;
pub const KEY_END: u16 = 107;

pub const KEY_A: u16 = 30;
pub const KEY_B: u16 = 48;
pub const KEY_H: u16 = 35;
pub const KEY_I: u16 = 23;
pub const KEY_J: u16 = 36;
pub const KEY_K: u16 = 37;
pub const KEY_L: u16 = 38;
pub const KEY_W: u16 = 17;

pub const KEY_0: u16 = 11;
pub const KEY_4: u16 = 5;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum KeyState {
    Press,
    Release,
    Repeat,
}

impl KeyState {
    pub fn from(value: u32) -> Option<Self> {
        match value {
            0 => Some(KeyState::Release),
            1 => Some(KeyState::Press),
            2 => Some(KeyState::Repeat),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Copy)]
pub struct Event {
    pub device_id: u32,
    pub key_code: u16,
    pub key_state: KeyState,
}

impl Event {
    pub fn new(device_id: u32, key_code: u16, key_state: KeyState, _timestamp: u64) -> Self {
        Self {
            device_id,
            key_code,
            key_state,
        }
    }

    pub fn is_capslock(&self) -> bool {
        self.key_code == KEY_CAPSLOCK
    }

    pub fn is_backspace(&self) -> bool {
        self.key_code == KEY_BACKSPACE
    }
}

impl fmt::Display for Event {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "Event(device={}, key={}, state={:?})",
            self.device_id, self.key_code, self.key_state
        )
    }
}