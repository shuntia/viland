import pystray
from PIL import Image, ImageDraw
import os
import signal
import sys


def create_icon():
    size = 64
    img = Image.new('RGB', (size, size), color='#2d2d2d')
    d = ImageDraw.Draw(img)

    # Draw V shape
    d.polygon([(16, 16), (32, 48), (48, 16)], fill='#50fa7b', outline='#50fa7b')

    return img


def create_menu():
    pass


def run_tray():
    icon = pystray.Icon(
        'viland',
        create_icon(),
        'Viland',
        menu=pystray.Menu(
            pystray.MenuItem('Quit', lambda icon, item: os.kill(os.getpid(), signal.SIGTERM))
        )
    )
    icon.run()


def start_tray():
    import threading
    tray_thread = threading.Thread(target=run_tray, daemon=True)
    tray_thread.start()
    return tray_thread