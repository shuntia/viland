import evdev
import subprocess
import time
import logging
import sys
import os
import signal
import atexit
from typing import Optional, Set, List
from .state_machine import StateMachine, Mode
from .input_handler import InputHandler
from .config import load_config, get_action_codes


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
    'left': [105],
    'right': [106],
    'up': [103],
    'down': [108],
}
HOME = [102]
END = [107]
ENTER = [28]
BACKSPACE = [14]
ESC = [1]

CAPSLOCK = 58
ESC_KEY = 1
LEFTCTRL = 29


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
            time.sleep(0.01)
            self.emit_key(code, False)
            time.sleep(0.01)

    def emit_action(self, action: str):
        codes = get_action_codes(action)
        for code in codes:
            self.emit_key(code, True)
            time.sleep(0.01)
            self.emit_key(code, False)
            time.sleep(0.01)


class VilandDaemon:
    def __init__(self, config_path: str = None):
        self.config = load_config(config_path)
        self.state_machine = StateMachine(self.config['double_tap_timeout'])
        self.input_handler = InputHandler()
        self.keyboard = YdotoolKeyboard()
        self.pressed_keys: Set[int] = set()
        self.last_key_time = 0.0
        self.grabbed = False
        self.caps2esc = self.config.get('caps2esc', True)
        self.ctrl_pressed = False
        self.alt_pressed = False
        self._write_pid()
        self._start_tray()

    def _write_pid(self):
        pid_file = os.path.expanduser('~/.config/viland/viland.pid')
        os.makedirs(os.path.dirname(pid_file), exist_ok=True)
        with open(pid_file, 'w') as f:
            f.write(str(os.getpid()))

    def _start_tray(self):
        if not self.config.get('tray', True):
            return
        try:
            from .tray import start_tray
            start_tray()
            logger.info("System tray started")
        except Exception as e:
            logger.warning(f"Failed to start tray: {e}")

    def _check_exit_override(self, code: int, pressed: bool) -> bool:
        if code == evdev.ecodes.KEY_LEFTCTRL or code == evdev.ecodes.KEY_RIGHTCTRL:
            self.ctrl_pressed = pressed
        if code == evdev.ecodes.KEY_LEFTALT or code == evdev.ecodes.KEY_RIGHTALT:
            self.alt_pressed = pressed

        # Ctrl+Alt+Q or Ctrl+Alt+Delete to exit
        if pressed and self.ctrl_pressed and self.alt_pressed:
            if code == evdev.ecodes.KEY_Q or code == evdev.ecodes.KEY_DELETE:
                logger.info("Exit override triggered")
                self._cleanup()
                sys.exit(0)
        return False

    def show_notification(self, message: str):
        if self.config.get('notification') == 'notify':
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

    def _emit_action(self, action: str):
        self.keyboard.emit_action(action)

    def _get_key_action(self, code: int) -> Optional[str]:
        key_map = {
            evdev.ecodes.KEY_H: 'h',
            evdev.ecodes.KEY_J: 'j',
            evdev.ecodes.KEY_K: 'k',
            evdev.ecodes.KEY_L: 'l',
            evdev.ecodes.KEY_W: 'w',
            evdev.ecodes.KEY_B: 'b',
            evdev.ecodes.KEY_E: 'e',
            evdev.ecodes.KEY_Q: 'q',
            evdev.ecodes.KEY_I: 'i',
            evdev.ecodes.KEY_A: 'a',
            evdev.ecodes.KEY_O: 'o',
            evdev.ecodes.KEY_S: 's',
            evdev.ecodes.KEY_X: 'x',
            evdev.ecodes.KEY_0: '0',
            evdev.ecodes.KEY_G: 'g',
            evdev.ecodes.KEY_N: 'n',
            evdev.ecodes.KEY_U: 'u',
            evdev.ecodes.KEY_R: 'r',
            evdev.ecodes.KEY_P: 'p',
            evdev.ecodes.KEY_SLASH: '/',
            evdev.ecodes.KEY_ESC: 'escape',
        }
        key = key_map.get(code)
        if key:
            return self.config.get('keys', {}).get(key)
        return None

    def handle_event(self, event: evdev.InputEvent):
        if event.type != evdev.ecodes.EV_KEY:
            return

        code = event.code
        pressed = event.value == 1

        # Check for exit override (Ctrl+Alt+Q or Ctrl+Alt+Delete)
        self._check_exit_override(code, pressed)

        # Caps2esc: capslock as escape on tap, ctrl on hold
        if self.caps2esc and code == CAPSLOCK and pressed:
            if self.state_machine.is_normal_mode():
                self.state_machine.exit_normal_mode()
                self._ungrab_devices()
                self.show_notification("Insert Mode")
                return
            else:
                now = time.time()
                if now - self.last_key_time < self.state_machine.double_tap_timeout:
                    self.state_machine.mode = Mode.NORMAL
                    self._grab_devices()
                    self.show_notification("Normal Mode")
                self.last_key_time = now
            return

        # Caps2esc: escape as capslock
        if self.caps2esc and code == ESC_KEY and pressed:
            now = time.time()
            if now - self.last_key_time < 0.3:
                pass  # Double escape
            self.last_key_time = now

        if not self.state_machine.is_normal_mode():
            return

        if pressed:
            self.last_key_time = time.time()

        if code in MODIFIER_KEYS:
            return

        if not pressed:
            return

        action = self._get_key_action(code)
        if action:
            self._emit_action(action)
        else:
            pass

    def _cleanup(self):
        self._ungrab_devices()
        pid_file = os.path.expanduser('~/.config/viland/viland.pid')
        if os.path.exists(pid_file):
            os.remove(pid_file)

    def run(self):
        atexit.register(self._cleanup)

        if not self.keyboard.available:
            logger.warning("ydotool not available, key injection will not work")

        logger.info(f"Viland daemon started (caps2esc={self.caps2esc})")
        logger.info("Double-tap caps lock to enter normal mode")
        logger.info("Ctrl+Alt+Q to exit daemon")

        try:
            while True:
                event = self.input_handler.read_event(timeout=0.5)
                if event:
                    self.handle_event(event)
        except KeyboardInterrupt:
            logger.info("Viland daemon stopped")
        finally:
            self._cleanup()


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', help='Config file path')
    args = parser.parse_args()

    daemon = VilandDaemon(config_path=args.config)
    daemon.run()


if __name__ == "__main__":
    main()