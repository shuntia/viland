import evdev
import subprocess
import time
import logging
import sys
import os
from typing import Optional, Set, List
from .state_machine import StateMachine, Mode
from .key_mapper import KeyMapper
from .input_handler import InputHandler


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
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

ARROWS = {
    'left': 105,
    'right': 106,
    'up': 103,
    'down': 108,
}
HOME = 102
END = 107
ENTER = 28
BACKSPACE = 14


def notify(msg: str):
    try:
        subprocess.Popen(
            ['notify-send', '-u', 'low', '-t', '800', 'Viland', msg],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


class YdotoolKeyboard:
    def __init__(self):
        self.available = self._check_ydotool()

    def _check_ydotool(self) -> bool:
        try:
            result = subprocess.run(
                ['ydotool', 'click', '0'],
                capture_output=True,
                timeout=2,
            )
            return result.returncode == 0
        except Exception:
            return False

    def emit_key(self, code: int, pressed: bool = True):
        if not self.available:
            return
        try:
            subprocess.run(
                ['ydotool', 'key', f'{code}:{1 if pressed else 0}'],
                capture_output=True,
                timeout=0.5,
            )
        except Exception as e:
            logger.debug(f"ydotool key failed: {e}")

    def emit_sequence(self, codes: List[int]):
        for code in codes:
            self.emit_key(code, True)
            time.sleep(0.015)
            self.emit_key(code, False)
            time.sleep(0.015)


class VilandDaemon:
    def __init__(self, double_tap_timeout: float = 0.5):
        self.state_machine = StateMachine(double_tap_timeout)
        self.input_handler = InputHandler()
        self.keyboard = YdotoolKeyboard()
        self.pressed_keys: Set[int] = set()
        self.active_modifiers: Set[int] = set()
        self.last_key_time = 0.0
        self.grabbed = False

    def show_notification(self, message: str):
        notify(message)

    def _is_double_press(self) -> bool:
        return time.time() - self.last_key_time < 0.3

    def _grab_devices(self):
        if self.grabbed:
            return
        try:
            self.input_handler.grab_all_devices()
            self.grabbed = True
            logger.info("Devices grabbed successfully")
        except Exception as e:
            logger.error(f"Failed to grab devices: {e}")

    def _ungrab_devices(self):
        if not self.grabbed:
            return
        try:
            self.input_handler.ungrab_all_devices()
            self.grabbed = False
            logger.info("Devices ungrabbed successfully")
        except Exception as e:
            logger.error(f"Failed to ungrab devices: {e}")

    def handle_event(self, event: evdev.InputEvent):
        if event.type != evdev.ecodes.EV_KEY:
            return

        code = event.code
        pressed = event.value == 1
        released = event.value == 0

        if code == evdev.ecodes.KEY_CAPSLOCK and pressed:
            now = time.time()
            if now - self.last_key_time < self.state_machine.double_tap_timeout:
                if self.state_machine.is_normal_mode():
                    self.state_machine.exit_normal_mode()
                    self._ungrab_devices()
                    self.show_notification("Insert Mode")
                else:
                    self.state_machine.mode = Mode.NORMAL
                    self._grab_devices()
                    self.show_notification("Normal Mode")
            self.last_key_time = now
            return

        if not self.state_machine.is_normal_mode():
            return

        if pressed:
            self.pressed_keys.add(code)
            self.last_key_time = time.time()
        elif released:
            self.pressed_keys.discard(code)

        if code in MODIFIER_KEYS:
            return

        if not pressed:
            return

        if code == evdev.ecodes.KEY_I:
            self.state_machine.exit_normal_mode()
            self._ungrab_devices()
            self.show_notification("Insert Mode")
            return

        if code == evdev.ecodes.KEY_A:
            self.state_machine.exit_normal_mode()
            self._ungrab_devices()
            self.keyboard.emit_key(ARROWS['right'])
            self.show_notification("Insert Mode")
            return

        if code == evdev.ecodes.KEY_O:
            self.state_machine.exit_normal_mode()
            self._ungrab_devices()
            self.keyboard.emit_key(END)
            time.sleep(0.02)
            self.keyboard.emit_key(ENTER)
            time.sleep(0.02)
            self.keyboard.emit_key(ARROWS['up'])
            self.show_notification("Insert Mode")
            return

        if code == evdev.ecodes.KEY_ESC:
            self.state_machine.exit_normal_mode()
            self._ungrab_devices()
            self.show_notification("Insert Mode")
            return

        if code == evdev.ecodes.KEY_X:
            self.keyboard.emit_key(BACKSPACE)
            return

        mapped = {
            evdev.ecodes.KEY_H: ARROWS['left'],
            evdev.ecodes.KEY_J: ARROWS['down'],
            evdev.ecodes.KEY_K: ARROWS['up'],
            evdev.ecodes.KEY_L: ARROWS['right'],
            evdev.ecodes.KEY_W: ARROWS['right'],
            evdev.ecodes.KEY_B: ARROWS['left'],
            evdev.ecodes.KEY_E: END,
            evdev.ecodes.KEY_Q: ARROWS['left'],
            evdev.ecodes.KEY_0: HOME,
            evdev.ecodes.KEY_G: HOME,
            evdev.ecodes.KEY_N: ARROWS['right'],
        }.get(code)

        if mapped:
            self.keyboard.emit_key(mapped)
        else:
            pass

    def run(self):
        if not self.keyboard.available:
            logger.warning("ydotool not available, key injection will not work")

        logger.info("Viland daemon started")
        logger.info("Double-tap caps lock to enter normal mode")

        try:
            while True:
                event = self.input_handler.read_event(timeout=0.5)
                if event:
                    self.handle_event(event)
        except KeyboardInterrupt:
            logger.info("Viland daemon stopped")
        finally:
            self._ungrab_devices()


def main():
    daemon = VilandDaemon()
    daemon.run()


if __name__ == "__main__":
    main()