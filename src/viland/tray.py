import os
import signal
import threading


def create_icon():
    try:
        from PIL import Image, ImageDraw
        size = 64
        img = Image.new('RGB', (size, size), color='#2d2d2d')
        d = ImageDraw.Draw(img)
        d.polygon([(16, 16), (32, 48), (48, 16)], fill='#50fa7b', outline='#50fa7b')
        return img
    except:
        return None


def run_tray():
    import pystray
    icon = pystray.Icon(
        'viland',
        create_icon(),
        'Viland',
        menu=pystray.Menu(
            pystray.MenuItem('Quit', lambda icon, item: os.kill(os.getpid(), signal.SIGTERM))
        )
    )
    try:
        icon.run()
    except Exception:
        pass


def start_tray():
    tray_thread = threading.Thread(target=run_tray, daemon=True)
    tray_thread.start()
    return tray_thread