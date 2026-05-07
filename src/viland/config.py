import os
import toml
from typing import Dict, Any


DEFAULT_CONFIG = {
    'double_tap_timeout': 0.5,
    'caps2esc': True,
    'notification': 'notify',
    'keys': {
        'h': 'left',
        'j': 'down',
        'k': 'up',
        'l': 'right',
        'w': 'C-right',
        'b': 'C-left',
        'e': 'end',
        '0': 'home',
        '$': 'end',
        'g': 'home',
        'i': 'escape',
        'a': 'escape-right',
        'o': 'end-enter-up',
        's': 'backspace',
        'escape': 'escape',
        'x': 'backspace',
        '/': 'C-f',
        'n': 'right',
        'u': 'C-z',
        'r': 'C-y',
        'p': 'C-v',
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
            config.update(user_config)
            return config
        except Exception as e:
            print(f"Failed to load config: {e}", file=__import__('sys').stderr)

    return DEFAULT_CONFIG


def get_action_codes(action: str) -> list:
    """Convert action string to list of key codes."""
    actions = {
        'left': [105],
        'right': [106],
        'up': [103],
        'down': [108],
        'home': [102],
        'end': [107],
        'escape': [1],
        'tab': [15],
        'enter': [28],
        'backspace': [14],
        'delete': [110],
        'C-left': [105, 29],
        'C-right': [106, 29],
        'C-z': [44, 29],
        'C-y': [21, 29],
        'C-v': [47, 29],
        'C-f': [33, 29],
        'escape-right': [1, 106],
        'end-enter-up': [107, 28, 103],
    }
    return actions.get(action, [])