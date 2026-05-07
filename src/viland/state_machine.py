import time
from enum import Enum, auto


class Mode(Enum):
    IDLE = auto()
    NORMAL = auto()


class StateMachine:
    def __init__(self, double_tap_timeout: float = 0.5):
        self.mode = Mode.IDLE
        self.last_caps_lock_time = 0.0
        self.double_tap_timeout = double_tap_timeout

    def handle_caps_lock(self) -> bool:
        now = time.time()
        time_since_last = now - self.last_caps_lock_time

        self.last_caps_lock_time = now

        if self.mode == Mode.IDLE:
            if time_since_last < self.double_tap_timeout:
                self.mode = Mode.NORMAL
                return True
        elif self.mode == Mode.NORMAL:
            if time_since_last < self.double_tap_timeout:
                self.mode = Mode.IDLE
                return True

        return False

    def is_normal_mode(self) -> bool:
        return self.mode == Mode.NORMAL

    def exit_normal_mode(self):
        self.mode = Mode.IDLE