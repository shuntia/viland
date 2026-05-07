import evdev
from typing import List, Optional
import select


class InputHandler:
    def __init__(self):
        self.devices: List[evdev.InputDevice] = []
        self.keyboard_devices: List[evdev.InputDevice] = []
        self._discover_keyboards()

    def _discover_keyboards(self):
        all_devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
        for device in all_devices:
            try:
                capabilities = device.capabilities()
                if evdev.ecodes.EV_KEY in capabilities:
                    keys = capabilities[evdev.ecodes.EV_KEY]
                    if any(k in keys for k in [evdev.ecodes.KEY_A, evdev.ecodes.KEY_SPACE, evdev.ecodes.KEY_Q]):
                        self.keyboard_devices.append(device)
            except Exception:
                continue

    def get_keyboard_fds(self) -> List[int]:
        return [d.fd for d in self.keyboard_devices]

    def read_event(self, timeout: float = 0.1) -> Optional[evdev.InputEvent]:
        fds = self.get_keyboard_fds()
        if not fds:
            return None

        r, _, _ = select.select(fds, [], [], timeout)
        for fd in r:
            for device in self.keyboard_devices:
                if device.fd == fd:
                    try:
                        for event in device.read():
                            return event
                    except Exception:
                        continue
        return None