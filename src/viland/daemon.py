import evdev
import subprocess
import time
import logging
import sys
import os
from typing import Optional, Set
from .state_machine import StateMachine, Mode
from .key_mapper import KeyMapper
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


class VilandDaemon:
    def __init__(self, double_tap_timeout: float = 0.5):
        self.state_machine = StateMachine(double_tap_timeout)
        self.key_mapper = KeyMapper()
        self.input_handler = InputHandler()
        self.keyboard = YdotoolKeyboard()
        self.pressed_keys: Set[int] = set()
        self.active_modifiers: Set[int] = set()

    def show_notification(self, message: str):
        try:
            subprocess.Popen(
                ["notify-send", "-u", "low", "-t", "500", "Viland", message],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

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
            self.show_notification("Idle Mode")
            return

        if code == evdev.ecodes.KEY_A:
            self.state_machine.exit_normal_mode()
            self.show_notification("Insert Mode")
            return

        mapped_code = self.key_mapper.map_key(code)
        if mapped_code is not None:
            self.keyboard.emit_key(mapped_code, True)
            time.sleep(0.02)
            self.keyboard.emit_key(mapped_code, False)

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