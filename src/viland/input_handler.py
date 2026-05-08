import evdev
from typing import List, Optional
import selectors
import logging

logger = logging.getLogger(__name__)


class InputHandler:
    def __init__(self):
        self.keyboard_devices: List[evdev.InputDevice] = []
        self.selector = selectors.DefaultSelector()
        self._discover_keyboards()
        self._setup_selector()

    def _discover_keyboards(self):
        all_devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
        for device in all_devices:
            try:
                if 'ydotoold' in device.name.lower():
                    continue
                capabilities = device.capabilities()
                if evdev.ecodes.EV_KEY in capabilities:
                    keys = capabilities[evdev.ecodes.EV_KEY]
                    if any(k in keys for k in [evdev.ecodes.KEY_A, evdev.ecodes.KEY_SPACE, evdev.ecodes.KEY_Q]):
                        self.keyboard_devices.append(device)
                        logger.info(f"Found keyboard: {device.name} ({device.path})")
            except Exception as e:
                logger.warning(f"Error checking device {device.path}: {e}")

    def _setup_selector(self):
        for device in self.keyboard_devices:
            self.selector.register(device.fd, selectors.EVENT_READ, device)

    def get_keyboard_fds(self) -> List[int]:
        return [d.fd for d in self.keyboard_devices]

    def read_event(self, timeout: float = 0.01) -> Optional[evdev.InputEvent]:
        try:
            events = self.selector.select(timeout=timeout)
            if not events:
                return None

            for key, _ in events:
                device = key.data
                try:
                    for event in device.read():
                        if event.type == evdev.ecodes.EV_KEY:
                            return event
                except BlockingIOError:
                    continue
                except Exception as e:
                    logger.debug(f"Read error from {device.name}: {e}")
        except Exception as e:
            logger.warning(f"Selector error: {e}")
        return None

    def grab_all_devices(self):
        for device in self.keyboard_devices:
            try:
                device.grab()
                logger.info(f"Grabbed device: {device.name}")
            except OSError as e:
                logger.error(f"Failed to grab {device.name}: {e}")
            except Exception as e:
                logger.error(f"Error grabbing {device.name}: {e}")

    def ungrab_all_devices(self):
        for device in self.keyboard_devices:
            try:
                device.ungrab()
                logger.info(f"Ungrabbed device: {device.name}")
            except Exception as e:
                logger.error(f"Error ungrabbing {device.name}: {e}")