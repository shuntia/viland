import os
import toml
from typing import Dict, Any, List

# Input key codes (from evdev)
KEY_CODES = {
    'h': 35, 'j': 36, 'k': 37, 'l': 38,
    'w': 17, 'b': 48, 'e': 18, 'q': 16,
    'i': 23, 'a': 30, 'o': 24, 's': 31,
    'x': 45, 'g': 34, 'n': 49, 'u': 22,
    'r': 19, 'p': 25, 'z': 44, 'v': 47,
    '0': 11, 'dollar': 21,  # $ uses 21 (KEY_4)
    'escape': 1, 'tab': 15, 'enter': 28,
    'backspace': 14, 'delete': 111,
    'left': 105, 'right': 106, 'up': 103, 'down': 108,
    'home': 102, 'end': 107,
    'leftctrl': 29, 'rightctrl': 97,
    'leftalt': 56, 'rightalt': 100,
    'leftshift': 42, 'rightshift': 54,
    'leftmeta': 125, 'rightmeta': 126,
    '/': 53,  # KEY_SLASH
    ';': 39,  # KEY_SEMICOLON
    'escape': 1,
}

# Output key codes (for ydotool - same as evdev)
OUTPUT_KEYS = {
    'left': 105,
    'right': 106,
    'up': 103,
    'down': 108,
    'home': 102,
    'end': 107,
    'escape': 1,
    'tab': 15,
    'enter': 28,
    'backspace': 14,
    'delete': 111,
    'C-right': (106, 29),   # Ctrl+Right
    'C-left': (105, 29),    # Ctrl+Left
    'C-z': (44, 29),        # Ctrl+Z
    'C-y': (21, 29),        # Ctrl+Y
    'C-v': (47, 29),        # Ctrl+V
    'C-f': (33, 29),        # Ctrl+F
}

# Reverse lookup for input
INPUT_KEY_TO_NAME = {v: k for k, v in KEY_CODES.items()}


DEFAULT_CONFIG = {
    'double_tap_timeout': 0.5,
    'caps2esc': True,
    'notification': 'notify',
    'tray': False,
    'keys': {
        'h': 'left',
        'j': 'down',
        'k': 'up',
        'l': 'right',
        'w': 'C-right',
        'b': 'C-left',
        'e': 'end',
        '0': 'home',
        'dollar': 'end',
        'g': 'home',
        'i': 'exit-insert',
        'a': 'exit-insert-right',
        'o': 'end-enter-up',
        's': 'backspace',
        'x': 'backspace',
        '/': 'C-f',
        'n': 'right',
        'u': 'C-z',
        'r': 'C-y',
        'p': 'C-v',
        'escape': 'escape',
        'tab': 'tab',
    }
}


def load_config(config_path: str = None) -> Dict[str, Any]:
    if config_path is None:
        config_path = os.environ.get('VILAND_CONFIG', '')
        if not config_path:
            xdg_config = os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
            config_path = os.path.join(xdg_config, 'viland', 'config.toml')

    if os.path.exists(config_path):
        try:
            user_config = toml.load(config_path)
            config = DEFAULT_CONFIG.copy()
            if 'keys' in user_config:
                config['keys'] = {**DEFAULT_CONFIG['keys'], **user_config['keys']}
            config.update(user_config)
            return config
        except Exception as e:
            print(f"Failed to load config: {e}", file=__import__('sys').stderr)

    return DEFAULT_CONFIG


def get_output_codes(action: str) -> List[int]:
    """Convert action to list of key codes for ydotool."""
    result = OUTPUT_KEYS.get(action, [])
    if isinstance(result, tuple):
        return list(result)
    return [result] if result else []