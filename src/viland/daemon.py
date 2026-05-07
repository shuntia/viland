import evdev
import subprocess
import time
import logging
import sys
import os
from typing import Optional, Set
from .state_machine import StateMachine, Mode
from .key_mapper import KeyMapper, VimOperator
from .input_handler import InputHandler


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s %(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger(__name__)


MODIFIER_KEYS = {
    evdev.ecodes.KEY_LEFTCTRL,
    evdev.ecodes.KEY_RIGHTCTRL,
    evdev.ecodes.KEY_LEFTSHIFT,
    evdev.ecodes.KEY_RIGHTSHIFT,
    evdev.ecodes.KEY_LEFTALT,
    evdev.ecodes.KEY_RIGHTALT,
    evdev.ecodes.KEY_LEFTMETA,
    evdev.ecodes.KEY_RIGHTMETA,
}

KEY_TO_YDOTOOL = {
    evdev.ecodes.KEY_LEFT: "Left",
    evdev.ecodes.KEY_RIGHT: "Right",
    evdev.ecodes.KEY_UP: "Up",
    evdev.ecodes.KEY_DOWN: "Down",
    evdev.ecodes.KEY_HOME: "Home",
    evdev.ecodes.KEY_END: "End",
}


class YdotoolKeyboard:
    def __init__(self):
        self.available = self._check_ydotool()

    def _check_ydotool(self) -> bool:
        try:
            result = subprocess.run(
                ["ydotool", "click", "0"],
                capture_output=True,
                timeout=2,
            )
            return result.returncode == 0
        except Exception:
            return False

    def emit_key(self, code: int, pressed: bool = True):
        if not self.available:
            return

        ykey = KEY_TO_YDOTOOL.get(code)
        if not ykey:
            return

        try:
            subprocess.run(
                ["ydotool", "key", f"KEY_{ykey}:{1 if pressed else 0}"],
                capture_output=True,
                timeout=0.5,
            )
        except Exception as e:
            logger.debug(f"ydotool key failed: {e}")

    def emit_sequence(self, codes: list):
        for code in codes:
            self.emit_key(code, True)
            time.sleep(0.01)
            self.emit_key(code, False)
            time.sleep(0.01)


class VilandDaemon:
    def __init__(self, double_tap_timeout: float = 0.5):
        self.state_machine = StateMachine(double_tap_timeout)
        self.key_mapper = KeyMapper()
        self.input_handler = InputHandler()
        self.keyboard = YdotoolKeyboard()
        self.pressed_keys: Set[int] = set()
        self.active_modifiers: Set[int] = set()
        self.pending_operator: Optional[int] = None
        self.operator_timeout = 0.5
        self.last_key_time = 0.0

    def show_notification(self, message: str):
        try:
            subprocess.Popen(
                ["notify-send", "-u", "low", "-t", "500", "Viland", message],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    def _is_double_press(self) -> bool:
        return time.time() - self.last_key_time < 0.2

    def _handle_operator(self, op_key: int, next_key: int):
        if next_key == evdev.ecodes.KEY_D:
            if op_key == evdev.ecodes.KEY_D:
                self._delete_line()
        elif next_key == evdev.ecodes.KEY_Y:
            if op_key == evdev.ecodes.KEY_Y:
                self._yank_line()
        elif next_key == evdev.ecodes.KEY_W:
            if op_key == evdev.ecodes.KEY_D:
                self._delete_word()
            elif op_key == evdev.ecodes.KEY_Y:
                self._yank_word()
        elif next_key == evdev.ecodes.KEY_C:
            if op_key == evdev.ecodes.KEY_C:
                self._change_line()

    def _delete_line(self):
        self.keyboard.emit_key(evdev.ecodes.KEY_HOME, True)
        time.sleep(0.02)
        self.keyboard.emit_key(evdev.ecodes.KEY_HOME, False)
        time.sleep(0.02)
        self.keyboard.emit_key(evdev.ecodes.KEY_END, True)
        time.sleep(0.02)
        self.keyboard.emit_key(evdev.ecodes.KEY_END, False)
        time.sleep(0.02)
        self._emit_ctrl_shift("KEY_LEFT")
        time.sleep(0.02)
        self.keyboard.emit_key(evdev.ecodes.KEY_DELETE, True)
        time.sleep(0.02)
        self.keyboard.emit_key(evdev.ecodes.KEY_DELETE, False)

    def _yank_line(self):
        self.keyboard.emit_key(evdev.ecodes.KEY_HOME, True)
        time.sleep(0.02)
        self.keyboard.emit_key(evdev.ecodes.KEY_HOME, False)
        time.sleep(0.02)
        self.keyboard.emit_key(evdev.ecodes.KEY_END, True)
        time.sleep(0.02)
        self.keyboard.emit_key(evdev.ecodes.KEY_END, False)
        time.sleep(0.02)
        self._emit_ctrl_shift("KEY_LEFT")
        time.sleep(0.02)
        self.keyboard.emit_key(evdev.ecodes.KEY_LEFTCTRL, True)
        time.sleep(0.02)
        self.keyboard.emit_key(evdev.ecodes.KEY_C, True)
        time.sleep(0.02)
        self.keyboard.emit_key(evdev.ecodes.KEY_C, False)
        time.sleep(0.02)
        self.keyboard.emit_key(evdev.ecodes.KEY_LEFTCTRL, False)

    def _delete_word(self):
        self._emit_ctrl_shift("KEY_RIGHT")
        time.sleep(0.02)
        self.keyboard.emit_key(evdev.ecodes.KEY_DELETE, True)
        time.sleep(0.02)
        self.keyboard.emit_key(evdev.ecodes.KEY_DELETE, False)

    def _yank_word(self):
        self._emit_ctrl_shift("KEY_RIGHT")
        time.sleep(0.02)
        self._emit_ctrl_c()

    def _change_line(self):
        self.keyboard.emit_key(evdev.ecodes.KEY_HOME, True)
        time.sleep(0.02)
        self.keyboard.emit_key(evdev.ecodes.KEY_HOME, False)
        time.sleep(0.02)
        self.keyboard.emit_key(evdev.ecodes.KEY_END, True)
        time.sleep(0.02)
        self.keyboard.emit_key(evdev.ecodes.KEY_END, False)
        time.sleep(0.02)
        self._emit_ctrl_shift("KEY_LEFT")
        time.sleep(0.02)
        self.keyboard.emit_key(evdev.ecodes.KEY_DELETE, True)
        time.sleep(0.02)
        self.keyboard.emit_key(evdev.ecodes.KEY_DELETE, False)

    def _emit_ctrl_shift(self, key: str):
        self.keyboard.emit_key(evdev.ecodes.KEY_LEFTSHIFT, True)
        time.sleep(0.01)
        self.keyboard.emit_key(evdev.ecodes.KEY_LEFTCTRL, True)
        time.sleep(0.01)
        self.keyboard.emit_key(getattr(evdev.ecodes, key), True)
        time.sleep(0.01)
        self.keyboard.emit_key(getattr(evdev.ecodes, key), False)
        time.sleep(0.01)
        self.keyboard.emit_key(evdev.ecodes.KEY_LEFTCTRL, False)
        time.sleep(0.01)
        self.keyboard.emit_key(evdev.ecodes.KEY_LEFTSHIFT, False)

    def _emit_ctrl_c(self):
        self.keyboard.emit_key(evdev.ecodes.KEY_LEFTCTRL, True)
        time.sleep(0.02)
        self.keyboard.emit_key(evdev.ecodes.KEY_C, True)
        time.sleep(0.02)
        self.keyboard.emit_key(evdev.ecodes.KEY_C, False)
        time.sleep(0.02)
        self.keyboard.emit_key(evdev.ecodes.KEY_LEFTCTRL, False)

    def handle_event(self, event: evdev.InputEvent):
        if event.type != evdev.ecodes.EV_KEY:
            return

        code = event.code
        pressed = event.value == 1
        released = event.value == 0

        if code == evdev.ecodes.KEY_CAPSLOCK:
            mode_changed = self.state_machine.handle_caps_lock()
            if mode_changed:
                if self.state_machine.is_normal_mode():
                    self.show_notification("Normal Mode")
                else:
                    self.show_notification("Idle Mode")
            return

        if not self.state_machine.is_normal_mode():
            return

        if pressed:
            self.pressed_keys.add(code)
            self.last_key_time = time.time()
        elif released:
            self.pressed_keys.discard(code)

        if code in MODIFIER_KEYS:
            if pressed:
                self.active_modifiers.add(code)
            else:
                self.active_modifiers.discard(code)
            return

        if not pressed:
            return

        if code == evdev.ecodes.KEY_I:
            self.state_machine.exit_normal_mode()
            self.show_notification("Insert Mode")
            return

        if code == evdev.ecodes.KEY_A:
            self.state_machine.exit_normal_mode()
            self.keyboard.emit_key(evdev.ecodes.KEY_RIGHT, True)
            time.sleep(0.01)
            self.keyboard.emit_key(evdev.ecodes.KEY_RIGHT, False)
            self.show_notification("Insert Mode")
            return

        if code == evdev.ecodes.KEY_O:
            self.state_machine.exit_normal_mode()
            self.keyboard.emit_key(evdev.ecodes.KEY_END, True)
            time.sleep(0.01)
            self.keyboard.emit_key(evdev.ecodes.KEY_END, False)
            time.sleep(0.01)
            self.keyboard.emit_key(evdev.ecodes.KEY_ENTER, True)
            time.sleep(0.01)
            self.keyboard.emit_key(evdev.ecodes.KEY_ENTER, False)
            time.sleep(0.01)
            self.keyboard.emit_key(evdev.ecodes.KEY_UP, True)
            time.sleep(0.01)
            self.keyboard.emit_key(evdev.ecodes.KEY_UP, False)
            self.show_notification("Insert Mode")
            return

        if code == evdev.ecodes.KEY_U:
            self._emit_ctrl_z()
            return

        if code == evdev.ecodes.KEY_R:
            if self._is_double_press():
                self._emit_ctrl_y()
            return

        if code == evdev.ecodes.KEY_P:
            self._emit_ctrl_v()
            return

        if code == evdev.ecodes.KEY_SLASH:
            self._emit_ctrl_f()
            return

        if self.pending_operator:
            self._handle_operator(self.pending_operator, code)
            self.pending_operator = None
            return

        if self.key_mapper.is_prefix_key(code):
            self.pending_operator = code
            return

        mapped_code = self.key_mapper.map_key(code)
        if mapped_code is not None:
            if code == evdev.ecodes.KEY_G:
                if self._is_double_press():
                    self.keyboard.emit_key(evdev.ecodes.KEY_HOME, True)
                    time.sleep(0.01)
                    self.keyboard.emit_key(evdev.ecodes.KEY_HOME, False)
                return

            self.keyboard.emit_key(mapped_code, True)
            time.sleep(0.02)
            self.keyboard.emit_key(mapped_code, False)

    def _emit_ctrl_z(self):
        self.keyboard.emit_key(evdev.ecodes.KEY_LEFTCTRL, True)
        time.sleep(0.02)
        self.keyboard.emit_key(evdev.ecodes.KEY_Z, True)
        time.sleep(0.02)
        self.keyboard.emit_key(evdev.ecodes.KEY_Z, False)
        time.sleep(0.02)
        self.keyboard.emit_key(evdev.ecodes.KEY_LEFTCTRL, False)

    def _emit_ctrl_y(self):
        self.keyboard.emit_key(evdev.ecodes.KEY_LEFTCTRL, True)
        time.sleep(0.02)
        self.keyboard.emit_key(evdev.ecodes.KEY_Y, True)
        time.sleep(0.02)
        self.keyboard.emit_key(evdev.ecodes.KEY_Y, False)
        time.sleep(0.02)
        self.keyboard.emit_key(evdev.ecodes.KEY_LEFTCTRL, False)

    def _emit_ctrl_v(self):
        self.keyboard.emit_key(evdev.ecodes.KEY_LEFTCTRL, True)
        time.sleep(0.02)
        self.keyboard.emit_key(evdev.ecodes.KEY_V, True)
        time.sleep(0.02)
        self.keyboard.emit_key(evdev.ecodes.KEY_V, False)
        time.sleep(0.02)
        self.keyboard.emit_key(evdev.ecodes.KEY_LEFTCTRL, False)

    def _emit_ctrl_f(self):
        self.keyboard.emit_key(evdev.ecodes.KEY_LEFTCTRL, True)
        time.sleep(0.02)
        self.keyboard.emit_key(evdev.ecodes.KEY_F, True)
        time.sleep(0.02)
        self.keyboard.emit_key(evdev.ecodes.KEY_F, False)
        time.sleep(0.02)
        self.keyboard.emit_key(evdev.ecodes.KEY_LEFTCTRL, False)

    def run(self):
        if not self.keyboard.available:
            logger.warning("ydotool not available, key injection will not work")

        logger.info("Viland daemon started")
        logger.info("Double-tap caps lock to enter normal mode")

        while True:
            event = self.input_handler.read_event(timeout=0.5)
            if event:
                self.handle_event(event)


def main():
    daemon = VilandDaemon()
    try:
        daemon.run()
    except KeyboardInterrupt:
        logger.info("Viland daemon stopped")
        sys.exit(0)


if __name__ == "__main__":
    main()