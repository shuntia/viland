use std::fmt;

pub const KEY_ESC: u16 = 1;
pub const KEY_BACKSPACE: u16 = 14;

pub const KEY_LEFTCTRL: u16 = 29;
pub const KEY_LEFTALT: u16 = 56;
pub const KEY_LEFTMETA: u16 = 125;
pub const KEY_LEFTSHIFT: u16 = 42;
pub const KEY_RIGHTSHIFT: u16 = 54;
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
pub const KEY_Y: u16 = 21;
pub const KEY_U: u16 = 22;
pub const KEY_P: u16 = 25;
pub const KEY_SLASH: u16 = 53;
pub const KEY_F: u16 = 33;
pub const KEY_C: u16 = 46;
pub const KEY_V: u16 = 47;
pub const KEY_Z: u16 = 44;

pub const KEY_1: u16 = 2;
pub const KEY_2: u16 = 3;
pub const KEY_3: u16 = 4;
pub const KEY_4: u16 = 5;
pub const KEY_5: u16 = 6;
pub const KEY_6: u16 = 7;
pub const KEY_7: u16 = 8;
pub const KEY_8: u16 = 9;
pub const KEY_9: u16 = 10;
pub const KEY_0: u16 = 11;

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