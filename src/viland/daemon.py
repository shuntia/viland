import evdev
import subprocess
import time
import logging
import sys
import os
from typing import Optional, Set, Callable, List, Any
from enum import Enum, auto
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

NUMBER_KEYS = {
    evdev.ecodes.KEY_1, evdev.ecodes.KEY_2, evdev.ecodes.KEY_3,
    evdev.ecodes.KEY_4, evdev.ecodes.KEY_5, evdev.ecodes.KEY_6,
    evdev.ecodes.KEY_7, evdev.ecodes.KEY_8, evdev.ecodes.KEY_9,
    evdev.ecodes.KEY_0,
}

KEY_TO_YDOTOOL = {
    evdev.ecodes.KEY_LEFT: "Left",
    evdev.ecodes.KEY_RIGHT: "Right",
    evdev.ecodes.KEY_UP: "Up",
    evdev.ecodes.KEY_DOWN: "Down",
    evdev.ecodes.KEY_HOME: "Home",
    evdev.ecodes.KEY_END: "End",
    evdev.ecodes.KEY_PAGEUP: "PageUp",
    evdev.ecodes.KEY_PAGEDOWN: "PageDown",
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


class CommandType(Enum):
    MOTION = auto()
    OPERATOR = auto()
    TEXT_OBJECT = auto()


class VimCommand:
    def __init__(self, cmd_type: CommandType, code: int, count: int = 1):
        self.cmd_type = cmd_type
        self.code = code
        self.count = count


class RegisterManager:
    def __init__(self):
        self.registers: dict[str, List[VimCommand]] = {}
        self.current_recording: Optional[str] = None
        self.last_executed: Optional[List[VimCommand]] = None

    def start_recording(self, name: str):
        self.current_register = name
        self.current_recording = name
        self.registers[name] = []

    def record(self, cmd: VimCommand):
        if self.current_recording and self.current_recording in self.registers:
            self.registers[self.current_recording].append(cmd)

    def stop_recording(self):
        self.current_recording = None
        self.last_executed = None

    def play(self, name: str) -> Optional[List[VimCommand]]:
        if name in self.registers and self.registers[name]:
            self.last_executed = self.registers[name]
            return self.registers[name]
        return None

    def set_last_executed(self, cmds: List[VimCommand]):
        self.last_executed = cmds

    def get_last_executed(self) -> Optional[List[VimCommand]]:
        return self.last_executed


class VilandDaemon:
    def __init__(self, double_tap_timeout: float = 0.5):
        self.state_machine = StateMachine(double_tap_timeout)
        self.key_mapper = KeyMapper()
        self.input_handler = InputHandler()
        self.keyboard = YdotoolKeyboard()
        self.pressed_keys: Set[int] = set()
        self.active_modifiers: Set[int] = set()
        self.pending_operator: Optional[int] = None
        self.last_key_time = 0.0
        self.number_prefix = 0
        self.last_keycode = None
        self.registers = RegisterManager()

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
        return time.time() - self.last_key_time < 0.3

    def _get_count(self) -> int:
        count = max(1, self.number_prefix)
        self.number_prefix = 0
        return count

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

    def _emit_ctrl(self, key: str):
        self.keyboard.emit_key(evdev.ecodes.KEY_LEFTCTRL, True)
        time.sleep(0.01)
        self.keyboard.emit_key(getattr(evdev.ecodes, key), True)
        time.sleep(0.01)
        self.keyboard.emit_key(getattr(evdev.ecodes, key), False)
        time.sleep(0.01)
        self.keyboard.emit_key(evdev.ecodes.KEY_LEFTCTRL, False)

    def _emit_key_with_count(self, code: int, count: int):
        for _ in range(count):
            self.keyboard.emit_key(code, True)
            time.sleep(0.015)
            self.keyboard.emit_key(code, False)
            time.sleep(0.015)

    def _delete_line(self):
        count = self._get_count()
        for _ in range(count):
            self.keyboard.emit_key(evdev.ecodes.KEY_HOME, True)
            time.sleep(0.015)
            self.keyboard.emit_key(evdev.ecodes.KEY_HOME, False)
            time.sleep(0.015)
            self.keyboard.emit_key(evdev.ecodes.KEY_END, True)
            time.sleep(0.015)
            self.keyboard.emit_key(evdev.ecodes.KEY_END, False)
            time.sleep(0.015)
            self._emit_ctrl_shift("KEY_LEFT")
            time.sleep(0.015)
            self.keyboard.emit_key(evdev.ecodes.KEY_DELETE, True)
            time.sleep(0.015)
            self.keyboard.emit_key(evdev.ecodes.KEY_DELETE, False)
            time.sleep(0.015)
            if _ < count - 1:
                self.keyboard.emit_key(evdev.ecodes.KEY_DOWN, True)
                time.sleep(0.015)
                self.keyboard.emit_key(evdev.ecodes.KEY_DOWN, False)
                time.sleep(0.015)

    def _yank_line(self):
        count = self._get_count()
        for _ in range(count):
            self.keyboard.emit_key(evdev.ecodes.KEY_HOME, True)
            time.sleep(0.015)
            self.keyboard.emit_key(evdev.ecodes.KEY_HOME, False)
            time.sleep(0.015)
            self.keyboard.emit_key(evdev.ecodes.KEY_END, True)
            time.sleep(0.015)
            self.keyboard.emit_key(evdev.ecodes.KEY_END, False)
            time.sleep(0.015)
            self._emit_ctrl_shift("KEY_LEFT")
            time.sleep(0.015)
            self._emit_ctrl("KEY_C")
            time.sleep(0.015)
            if _ < count - 1:
                self.keyboard.emit_key(evdev.ecodes.KEY_DOWN, True)
                time.sleep(0.015)
                self.keyboard.emit_key(evdev.ecodes.KEY_DOWN, False)
                time.sleep(0.015)

    def _delete_word(self):
        count = self._get_count()
        for _ in range(count):
            self._emit_ctrl_shift("KEY_RIGHT")
            time.sleep(0.015)
            self.keyboard.emit_key(evdev.ecodes.KEY_DELETE, True)
            time.sleep(0.015)
            self.keyboard.emit_key(evdev.ecodes.KEY_DELETE, False)
            time.sleep(0.015)

    def _yank_word(self):
        count = self._get_count()
        for _ in range(count):
            self._emit_ctrl_shift("KEY_RIGHT")
            time.sleep(0.015)
            self._emit_ctrl("KEY_C")
            time.sleep(0.015)

    def _change_line(self):
        count = self._get_count()
        for _ in range(count):
            self.keyboard.emit_key(evdev.ecodes.KEY_HOME, True)
            time.sleep(0.015)
            self.keyboard.emit_key(evdev.ecodes.KEY_HOME, False)
            time.sleep(0.015)
            self.keyboard.emit_key(evdev.ecodes.KEY_END, True)
            time.sleep(0.015)
            self.keyboard.emit_key(evdev.ecodes.KEY_END, False)
            time.sleep(0.015)
            self._emit_ctrl_shift("KEY_LEFT")
            time.sleep(0.015)
            self.keyboard.emit_key(evdev.ecodes.KEY_DELETE, True)
            time.sleep(0.015)
            self.keyboard.emit_key(evdev.ecodes.KEY_DELETE, False)
            time.sleep(0.015)
            if _ < count - 1:
                self.keyboard.emit_key(evdev.ecodes.KEY_DOWN, True)
                time.sleep(0.015)
                self.keyboard.emit_key(evdev.ecodes.KEY_DOWN, False)
                time.sleep(0.015)

    def _handle_operator(self, op_key: int, next_key: int):
        cmds = []
        count = self._get_count()

        if next_key == evdev.ecodes.KEY_D:
            if op_key == evdev.ecodes.KEY_D:
                cmds = [VimCommand(CommandType.OPERATOR, evdev.ecodes.KEY_D)]
                self._delete_line()
        elif next_key == evdev.ecodes.KEY_Y:
            if op_key == evdev.ecodes.KEY_Y:
                cmds = [VimCommand(CommandType.OPERATOR, evdev.ecodes.KEY_Y)]
                self._yank_line()
        elif next_key == evdev.ecodes.KEY_W:
            if op_key == evdev.ecodes.KEY_D:
                cmds = [VimCommand(CommandType.OPERATOR, evdev.ecodes.KEY_D),
                        VimCommand(CommandType.MOTION, evdev.ecodes.KEY_W)]
                self._delete_word()
            elif op_key == evdev.ecodes.KEY_Y:
                cmds = [VimCommand(CommandType.OPERATOR, evdev.ecodes.KEY_Y),
                        VimCommand(CommandType.MOTION, evdev.ecodes.KEY_W)]
                self._yank_word()
        elif next_key == evdev.ecodes.KEY_C:
            if op_key == evdev.ecodes.KEY_C:
                cmds = [VimCommand(CommandType.OPERATOR, evdev.ecodes.KEY_C)]
                self._change_line()

        if cmds:
            self.registers.set_last_executed(cmds)
        self.pending_operator = None

    def _record_command(self, cmd: VimCommand):
        if self.registers.current_recording:
            self.registers.record(cmd)

    def _handle_number_key(self, code: int) -> bool:
        num_map = {
            evdev.ecodes.KEY_1: 1, evdev.ecodes.KEY_2: 2, evdev.ecodes.KEY_3: 3,
            evdev.ecodes.KEY_4: 4, evdev.ecodes.KEY_5: 5, evdev.ecodes.KEY_6: 6,
            evdev.ecodes.KEY_7: 7, evdev.ecodes.KEY_8: 8, evdev.ecodes.KEY_9: 9,
            evdev.ecodes.KEY_0: 0,
        }
        if code in num_map:
            self.number_prefix = self.number_prefix * 10 + num_map[code]
            return True
        return False

    def handle_event(self, event: evdev.InputEvent):
        if event.type != evdev.ecodes.EV_KEY:
            return

        code = event.code
        pressed = event.value == 1
        released = event.value == 0

        if code == evdev.ecodes.KEY_CAPSLOCK and pressed:
            logger.debug(f"CapsLock: value={event.value}, mode={self.state_machine.mode}")
            mode_changed = self.state_machine.handle_caps_lock()
            logger.debug(f"Mode changed: {mode_changed}, now in {self.state_machine.mode}")
            if mode_changed:
                if self.state_machine.is_normal_mode():
                    self.input_handler.grab_devices()
                    self.show_notification("Normal Mode")
                else:
                    self.input_handler.ungrab_devices()
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

        if self._handle_number_key(code):
            return

        if code == evdev.ecodes.KEY_I:
            count = self._get_count()
            cmd = VimCommand(CommandType.MOTION, code, count)
            self._record_command(cmd)
            self.registers.set_last_executed([cmd])
            self.state_machine.exit_normal_mode()
            self.show_notification("Insert Mode")
            return

        if code == evdev.ecodes.KEY_A:
            count = self._get_count()
            cmd = VimCommand(CommandType.MOTION, code, count)
            self._record_command(cmd)
            self.registers.set_last_executed([cmd])
            self.state_machine.exit_normal_mode()
            for _ in range(count):
                self.keyboard.emit_key(evdev.ecodes.KEY_RIGHT, True)
                time.sleep(0.01)
                self.keyboard.emit_key(evdev.ecodes.KEY_RIGHT, False)
            self.show_notification("Insert Mode")
            return

        if code == evdev.ecodes.KEY_O:
            count = self._get_count()
            cmd = VimCommand(CommandType.MOTION, code, count)
            self._record_command(cmd)
            self.registers.set_last_executed([cmd])
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

        if code == evdev.ecodes.KEY_Q:
            if self.registers.current_recording:
                self.registers.stop_recording()
                self.show_notification("Recording stopped")
            else:
                self.registers.start_recording('"')
                self.show_notification("Recording started (press q to stop)")
            return

        if code == evdev.ecodes.KEY_AT:
            count = self._get_count()
            cmds = self.registers.play('"')
            if cmds:
                for _ in range(count):
                    for cmd in cmds:
                        self._execute_command(cmd)
            return

        if code == evdev.ecodes.KEY_DOT:
            count = self._get_count()
            cmds = self.registers.get_last_executed()
            if cmds:
                for _ in range(count):
                    for cmd in cmds:
                        self._execute_command(cmd)
            return

        if code == evdev.ecodes.KEY_U:
            count = self._get_count()
            cmd = VimCommand(CommandType.MOTION, code, count)
            self._record_command(cmd)
            self.registers.set_last_executed([cmd])
            for _ in range(count):
                self._emit_ctrl("KEY_Z")
            return

        if code == evdev.ecodes.KEY_R:
            count = self._get_count()
            if self._is_double_press():
                for _ in range(count):
                    self._emit_ctrl("KEY_Y")
            return

        if code == evdev.ecodes.KEY_P:
            count = self._get_count()
            cmd = VimCommand(CommandType.MOTION, code, count)
            self._record_command(cmd)
            self.registers.set_last_executed([cmd])
            for _ in range(count):
                self._emit_ctrl("KEY_V")
            return

        if code == evdev.ecodes.KEY_SLASH:
            count = self._get_count()
            cmd = VimCommand(CommandType.MOTION, code, count)
            self._record_command(cmd)
            self.registers.set_last_executed([cmd])
            self._emit_ctrl("KEY_F")
            return

        if code == evdev.ecodes.KEY_N:
            count = self._get_count()
            cmd = VimCommand(CommandType.MOTION, code, count)
            self._record_command(cmd)
            self.registers.set_last_executed([cmd])
            for _ in range(count):
                self._emit_ctrl("KEY_G")
            return

        if code == evdev.ecodes.KEY_S:
            count = self._get_count()
            cmd = VimCommand(CommandType.OPERATOR, code, count)
            self._record_command(cmd)
            self.registers.set_last_executed([cmd])
            self.state_machine.exit_normal_mode()
            for _ in range(count):
                self.keyboard.emit_key(evdev.ecodes.KEY_DELETE, True)
                time.sleep(0.01)
                self.keyboard.emit_key(evdev.ecodes.KEY_DELETE, False)
                time.sleep(0.01)
            self.show_notification("Insert Mode")
            return

        if self.pending_operator:
            self._handle_operator(self.pending_operator, code)
            return

        if self.key_mapper.is_prefix_key(code):
            self.pending_operator = code
            return

        count = self._get_count()
        mapped_code = self.key_mapper.map_key(code)
        if mapped_code is not None:
            if code == evdev.ecodes.KEY_G:
                if self._is_double_press():
                    cmd = VimCommand(CommandType.MOTION, evdev.ecodes.KEY_END, count)
                    self._record_command(cmd)
                    self.registers.set_last_executed([cmd])
                    for _ in range(count):
                        self.keyboard.emit_key(evdev.ecodes.KEY_HOME, True)
                        time.sleep(0.015)
                        self.keyboard.emit_key(evdev.ecodes.KEY_HOME, False)
                        time.sleep(0.015)
                return

            cmd = VimCommand(CommandType.MOTION, code, count)
            self._record_command(cmd)
            self.registers.set_last_executed([cmd])
            self._emit_key_with_count(mapped_code, count)

    def _execute_command(self, cmd: VimCommand):
        if cmd.cmd_type == CommandType.MOTION:
            mapped_code = self.key_mapper.map_key(cmd.code)
            if mapped_code:
                self._emit_key_with_count(mapped_code, cmd.count)
        elif cmd.cmd_type == CommandType.OPERATOR:
            if cmd.code == evdev.ecodes.KEY_D:
                self._delete_line()
            elif cmd.code == evdev.ecodes.KEY_Y:
                self._yank_line()
            elif cmd.code == evdev.ecodes.KEY_C:
                self._change_line()

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