import evdev
import subprocess
import time
import logging
import sys
import os
import signal
import atexit
import threading
from typing import Optional, Set, List
from .state_machine import StateMachine, Mode
from .input_handler import InputHandler
from .config import load_config, get_output_codes, KEY_CODES, INPUT_KEY_TO_NAME


log_file = os.path.expanduser('~/.config/viland/viland.log')
os.makedirs(os.path.dirname(log_file), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stderr),
        logging.FileHandler(log_file),
    ],
)
logger = logging.getLogger(__name__)


# Only these are true modifiers: leftctrl(29), rightctrl(97), leftshift(42), rightshift(54), leftalt(56), rightalt(100), leftmeta(125), rightmeta(126), capslock(58)
MODIFIER_KEYS = {29, 97, 42, 54, 56, 100, 125, 126, 58}

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
        self.last_injected_time = 0.0

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
        self.last_injected_time = time.time()
        try:
            subprocess.run(
                ['ydotool', 'key', f'{code}:{1 if pressed else 0}'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=0.05,
            )
        except Exception as e:
            logger.debug(f"ydotool key failed: {e}")

    def emit_keys(self, codes: list):
        """Emit multiple keys in sequence"""
        for code in codes:
            self.emit_key(code, True)
            time.sleep(0.01)
            self.emit_key(code, False)
            time.sleep(0.01)

    def is_our_injection(self) -> bool:
        """Check if event came from our injection (within last 50ms)"""
        return time.time() - self.last_injected_time < 0.05

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
        self.caps_lock_time = 0.0
        self.caps_as_ctrl = False
        self.last_trigger_key = 0
        self.caps2esc_timeout = 0.1
        self.command_timeout = 5.0
        self._write_pid()
        self._start_tray()
        # Grab devices at startup - always grab
        self._grab_devices()

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
            self._tray_thread = start_tray()
            logger.info("System tray started (may not work on Wayland)")
        except Exception as e:
            logger.warning(f"Failed to start tray: {e}")

    def _check_exit_override(self, code: int, pressed: bool) -> bool:
        # Check for Ctrl+Alt+Q (leftctrl=29, leftalt=56)
        has_ctrl = 29 in self.pressed_keys or 97 in self.pressed_keys  # leftctrl or rightctrl
        has_alt = 56 in self.pressed_keys or 100 in self.pressed_keys  # leftalt or rightalt
        has_q = 16 in self.pressed_keys  # q key

        if pressed and has_ctrl and has_alt and has_q:
            logger.info("Exit override triggered - quitting")
            self._cleanup()
            os._exit(0)
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
        codes = get_output_codes(action)
        self.keyboard.emit_keys(codes)

    def _emit_key_with_mod(self, code: int):
        """Emit a key after a modifier (like ctrl)"""
        # Get output code - use same as input for simplicity
        self.keyboard.emit_key(code, True)
        self.keyboard.emit_key(code, False)

    def _get_key_action(self, code: int) -> Optional[str]:
        key_name = INPUT_KEY_TO_NAME.get(code)
        if key_name:
            return self.config.get('keys', {}).get(key_name)
        return None

    def _run_command_mode(self):
        """Enter command mode - spawn wofi for command input"""
        self.show_notification("Command mode...")

        def get_command():
            try:
                result = subprocess.run(
                    ['wofi', '--show', 'dmenu', '--prompt', ':'],
                    capture_output=True,
                    text=True,
                    timeout=self.command_timeout,
                )
                return result.stdout.strip()
            except subprocess.TimeoutExpired:
                return None
            except FileNotFoundError:
                try:
                    result = subprocess.run(
                        ['fuzzel', '--dmenu', '--prompt', ':'],
                        capture_output=True,
                        text=True,
                        timeout=self.command_timeout,
                    )
                    return result.stdout.strip()
                except:
                    return None
            except Exception as e:
                logger.warning(f"Command mode error: {e}")
                return None

        cmd = get_command()
        if not cmd:
            return

        logger.info(f"Command: {cmd}")

        # Parse and execute commands
        if cmd.startswith('q'):
            # :q or :quit - close window
            self.keyboard.emit_keys([106, 106, 106])  # Alt+F4
            logger.info("CMD: Quit")
            self.show_notification("Quit")

        elif cmd == 'qa' or cmd == 'qall':
            # :qa - quit all
            self.keyboard.emit_keys([18, 29])  # Ctrl+Q
            logger.info("CMD: Quit All")
            self.show_notification("Quit All")

        elif cmd.startswith('d'):
            # :d or :delete - delete key
            self.keyboard.emit_key(14, True)
            self.keyboard.emit_key(14, False)
            logger.info("CMD: Delete")
            self.show_notification("Delete")

        elif cmd == 'w' or cmd == 'wa' or cmd.startswith('w'):
            # :w or :write - save
            self.keyboard.emit_keys([31, 29])  # Ctrl+S
            logger.info("CMD: Save")
            self.show_notification("Save")

        elif cmd == 'x' or cmd == 'wq':
            # :x - save and quit
            self.keyboard.emit_keys([31, 29])  # Ctrl+S
            time.sleep(0.1)
            self.keyboard.emit_keys([106, 106, 106])  # Alt+F4
            logger.info("CMD: Save & Quit")
            self.show_notification("Save & Quit")

        elif cmd == 'c' or cmd.startswith('close'):
            # :c or :close
            self.keyboard.emit_keys([106, 106, 106])
            logger.info("CMD: Close")
            self.show_notification("Close")

        elif cmd.startswith('tabn') or cmd == 'tn':
            # :tabnext
            self.keyboard.emit_keys([23, 23])  # Ctrl+Tab
            logger.info("CMD: Tab Next")
            self.show_notification("Tab Next")

        elif cmd.startswith('tabp') or cmd == 'tp':
            # :tabprev
            self.keyboard.emit_keys([22, 23])  # Ctrl+Shift+Tab
            logger.info("CMD: Tab Prev")
            self.show_notification("Tab Prev")

        elif cmd.startswith('tab'):
            # :tab - new tab
            self.keyboard.emit_keys([20, 29])  # Ctrl+T
            logger.info("CMD: New Tab")
            self.show_notification("New Tab")

        elif cmd == 'h' or cmd == 'help':
            logger.info("CMD: Help")
            self.show_notification("Cmds: q,qa,d,w,x,c,tab,tn,tp,h")

        elif cmd.startswith('e'):
            # :e - explore/file manager
            self.keyboard.emit_keys([31, 56, 18])  # Alt+E
            logger.info("CMD: Explorer")
            self.show_notification("Explorer")

        elif cmd.startswith('r'):
            # :r - refresh
            self.keyboard.emit_keys([15, 29])  # Ctrl+R
            logger.info("CMD: Refresh")
            self.show_notification("Refresh")

        elif cmd.startswith('y'):
            # :y - yank/copy
            self.keyboard.emit_keys([21, 29])  # Ctrl+C
            logger.info("CMD: Copy")
            self.show_notification("Copy")

        elif cmd.startswith('p'):
            # :p - paste
            self.keyboard.emit_keys([25, 29])  # Ctrl+V
            logger.info("CMD: Paste")
            self.show_notification("Paste")

        elif cmd.startswith('s'):
            # :s - search
            self.keyboard.emit_keys([33, 29])  # Ctrl+F
            logger.info("CMD: Search")
            self.show_notification("Search")

        elif cmd.startswith('z'):
            # :z - undo
            self.keyboard.emit_keys([44, 29])  # Ctrl+Z
            logger.info("CMD: Undo")
            self.show_notification("Undo")

        elif cmd.startswith('m'):
            # :m - minimize
            self.keyboard.emit_keys([58, 107])  # Win+Down (minimize)
            logger.info("CMD: Minimize")
            self.show_notification("Minimize")

        else:
            logger.info(f"CMD: Unknown - {cmd}")
            self.show_notification(f"Unknown: {cmd}")

    def handle_event(self, event: evdev.InputEvent):
        # Ignore our own injected events
        if self.keyboard.is_our_injection():
            return

        if event.type != evdev.ecodes.EV_KEY:
            return

        code = event.code
        pressed = event.value == 1
        released = event.value == 0

        # Track pressed keys
        if pressed:
            self.pressed_keys.add(code)
        elif released:
            self.pressed_keys.discard(code)

        key_name = INPUT_KEY_TO_NAME.get(code, f'unknown-{code}')
        logger.info(f"KEY {'DOWN' if pressed else 'UP'}: {key_name} ({code}) - pressed: {sorted(self.pressed_keys)}")

# Check for exit override (Ctrl+Alt+Q or Ctrl+Alt+Delete)
        self._check_exit_override(code, pressed)

        # Caps2esc: capslock (code 58) - tap = escape, hold + key = ctrl
        if self.caps2esc and code == 58:
            if not self.state_machine.is_normal_mode():
                if pressed:
                    logger.info("MATCH: CapsLock pressed (caps2esc)")
                    self.caps_lock_time = time.time()
                    self.caps_as_ctrl = False
                elif released:
                    if self.caps_as_ctrl:
                        logger.info("MATCH: CapsLock released after ctrl modifier")
                        self.keyboard.emit_key(29, False)  # release ctrl
                        self.caps_as_ctrl = False
                    else:
                        logger.info("MATCH: CapsLock tap -> escape")
                        self.keyboard.emit_key(1, True)
                        time.sleep(0.01)
                        self.keyboard.emit_key(1, False)
            return

        # Escape key (code 1) - acts as CapsLock for double-tap detection
        # In insert mode: pass through as escape (not converted to capslock)
        # In normal mode: double-tap to enter
        if code == 1:
            if pressed:
                logger.info("MATCH: Escape pressed")
                now = time.time()
                
                if self.state_machine.is_normal_mode():
                    # In normal mode, check for double-tap
                    if (now - self.last_key_time < self.state_machine.double_tap_timeout and 
                        self.last_trigger_key in (58, 1)):
                        self.state_machine.mode = Mode.NORMAL
                        self._grab_devices()
                        self.show_notification("Normal Mode")
                        logger.info("MATCH: Double-tap escape - entered Normal Mode, grabbed devices")
                    self.last_key_time = now
                    self.last_trigger_key = 1
                    return
                else:
                    # In insert mode: emit escape and pass through
                    self.keyboard.emit_key(1, True)
                    self.last_key_time = now
                    self.last_trigger_key = 1
                    return
            elif released:
                if not self.state_machine.is_normal_mode():
                    self.keyboard.emit_key(1, False)
                return

        if not self.state_machine.is_normal_mode():
            # Insert mode: always re-emit key to ensure it's captured
            # Skip caps2esc handling since it's done above
            if code != 58:
                self.keyboard.emit_key(code, pressed)
            return

        # Caps2esc: If capslock was pressed recently and this is a key press, treat as ctrl
        if self.caps2esc and pressed and 58 in self.pressed_keys:
            time_since_caps = time.time() - self.caps_lock_time
            if time_since_caps < 0.5:  # Within 500ms
                self.caps_as_ctrl = True
                logger.info(f"MATCH: CapsLock as Ctrl modifier for key {code}")
                # Emit ctrl + the key
                self.keyboard.emit_key(29, True)  # leftctrl
                self._emit_key_with_mod(code)
                self.keyboard.emit_key(29, False)
                return

        # Normal mode: handle vim keys
        if pressed:
            self.last_key_time = time.time()

        if code in MODIFIER_KEYS:
            return

        if not pressed:
            return

        # Special exit keys
        if code == 23:  # KEY_I = 23
            logger.info("MATCH: Exit to insert mode (i)")
            self.state_machine.exit_normal_mode()
            self._ungrab_devices()
            self.show_notification("Insert Mode")
            logger.info("STATE: Exited Normal Mode via i, ungrabbed devices")
            return

        if code == 30:  # KEY_A = 30
            logger.info("MATCH: Exit to insert mode (a)")
            self.state_machine.exit_normal_mode()
            self._ungrab_devices()
            self.show_notification("Insert Mode")
            logger.info("STATE: Exited Normal Mode via a, ungrabbed devices")
            # Move right after exit
            self.keyboard.emit_key(106, True)
            self.keyboard.emit_key(106, False)
            return

        # Command mode - press ; or : (code 39) to get command input
        if code == 39:  # KEY_SEMICOLON = 39
            logger.info("MATCH: Command mode (;)")
            self._run_command_mode()
            return

        # Also support / for command mode
        if code == 53:  # KEY_SLASH = 53
            logger.info("MATCH: Command mode (/)")
            self._run_command_mode()
            return

        action = self._get_key_action(code)
        if action:
            logger.info(f"MATCH: Key {key_name} -> action '{action}'")
            self._emit_action(action)
            return  # Key is consumed

        logger.info(f"NO MATCH: Key {key_name} ({code}) has no action, consuming")
        return  # Consume unmapped keys too

    def _cleanup(self):
        # Release all pressed keys
        for code in list(self.pressed_keys):
            self.keyboard.emit_key(code, False)
            logger.info(f"CLEANUP: Released key {code}")
        
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

    # Check if already running
    pid_file = os.path.expanduser('~/.config/viland/viland.pid')
    if os.path.exists(pid_file):
        try:
            with open(pid_file, 'r') as f:
                old_pid = int(f.read().strip())
            # Check if process exists
            if os.path.exists(f'/proc/{old_pid}'):
                print(f"Viland is already running (PID: {old_pid})")
                sys.exit(1)
        except:
            pass

    daemon = VilandDaemon(config_path=args.config)
    daemon.run()


if __name__ == "__main__":
    main()