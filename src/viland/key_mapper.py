import evdev
from typing import Optional, Dict, Set
from enum import Enum, auto


class KeyAction(Enum):
    NONE = auto()
    NORMAL = auto()


class VimOperator(Enum):
    NONE = auto()
    DELETE = auto()
    YANK = auto()
    CHANGE = auto()


class KeyMapper:
    def __init__(self):
        self.key_map: Dict[int, int] = {
            evdev.ecodes.KEY_Q: evdev.ecodes.KEY_LEFT,
            evdev.ecodes.KEY_H: evdev.ecodes.KEY_DOWN,
            evdev.ecodes.KEY_J: evdev.ecodes.KEY_LEFT,
            evdev.ecodes.KEY_K: evdev.ecodes.KEY_UP,
            evdev.ecodes.KEY_L: evdev.ecodes.KEY_RIGHT,
            evdev.ecodes.KEY_W: evdev.ecodes.KEY_RIGHT,
            evdev.ecodes.KEY_B: evdev.ecodes.KEY_LEFT,
            evdev.ecodes.KEY_E: evdev.ecodes.KEY_END,
            evdev.ecodes.KEY_0: evdev.ecodes.KEY_HOME,
            evdev.ecodes.KEY_4: evdev.ecodes.KEY_END,
            evdev.ecodes.KEY_G: evdev.ecodes.KEY_HOME,
        }

        self.prefix_keys: Set[int] = {
            evdev.ecodes.KEY_D,
            evdev.ecodes.KEY_Y,
            evdev.ecodes.KEY_C,
        }

    def map_key(self, code: int) -> Optional[int]:
        return self.key_map.get(code)

    def is_exit_key(self, code: int) -> bool:
        return code in (evdev.ecodes.KEY_I, evdev.ecodes.KEY_A)

    def is_prefix_key(self, code: int) -> bool:
        return code in self.prefix_keys

    def should_remap(self, code: int) -> bool:
        return code in self.key_map