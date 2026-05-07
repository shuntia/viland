import evdev
from typing import Optional


class KeyMapper:
    def __init__(self):
        self.key_map = {
            evdev.ecodes.KEY_Q: evdev.ecodes.KEY_LEFT,
            evdev.ecodes.KEY_H: evdev.ecodes.KEY_DOWN,
            evdev.ecodes.KEY_J: evdev.ecodes.KEY_LEFT,
            evdev.ecodes.KEY_K: evdev.ecodes.KEY_UP,
            evdev.ecodes.KEY_L: evdev.ecodes.KEY_RIGHT,
            evdev.ecodes.KEY_I: None,
            evdev.ecodes.KEY_A: None,
        }

    def map_key(self, code: int) -> Optional[int]:
        return self.key_map.get(code)

    def is_exit_key(self, code: int) -> bool:
        return code in (evdev.ecodes.KEY_I, evdev.ecodes.KEY_A)

    def should_remap(self, code: int) -> bool:
        return code in self.key_map