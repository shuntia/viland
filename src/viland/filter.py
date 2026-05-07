#!/usr/bin/env python3
import sys
import struct
import time
import logging

logging.basicConfig(level=logging.WARNING)

EV_KEY = 0x01
EV_SYN = 0x00

CAPSLOCK = 58
ESC = 1

KEYS = {
    'h': 35, 'j': 36, 'k': 37, 'l': 38,
    'w': 17, 'b': 48, 'e': 18,
    'q': 16, 'i': 23, 'a': 30,
    '0': 11, '$': 21, 'g': 34,
    'd': 32, 'y': 21, 'c': 33,
    'u': 22, 'r': 19, 'p': 25,
    '/': 53, 'o': 24, 's': 31,
    'x': 45, 'v': 47, 'n': 39,
    'z': 44, 'v': 47,
}

ARROWS = {'left': 105, 'right': 106, 'up': 103, 'down': 108}
HOME = 102
END = 107

DOUBLE_TAP_TIMEOUT = 0.5

class VilandFilter:
    def __init__(self):
        self.mode = 'insert'
        self.last_caps_time = 0.0
        self.caps_pressed = False
        self.buffer = []

    def read_event(self):
        try:
            data = sys.stdin.buffer.read(24)
            if len(data) != 24:
                return None
            sec, usec, tv_sec, tv_usec, type, code, value = struct.unpack('QQHHIii', data)
            return (type, code, value)
        except:
            return None

    def write_event(self, type, code, value):
        sys.stdout.buffer.write(struct.pack('QQHHIii',
            0, 0, 0, 0, type, code, value))
        sys.stdout.buffer.flush()

    def emit_key(self, code, value):
        self.write_event(EV_KEY, code, value)
        self.write_event(EV_SYN, 0, 0)

    def run(self):
        while True:
            event = self.read_event()
            if event is None:
                break

            type, code, value = event
            if type != EV_KEY:
                self.write_event(type, code, value)
                continue

            now = time.time()

            if code == CAPSLOCK and value == 1:
                if now - self.last_caps_time < DOUBLE_TAP_TIMEOUT:
                    if self.mode == 'insert':
                        self.mode = 'normal'
                        sys.stderr.write("Viland: Normal Mode\n")
                    else:
                        self.mode = 'insert'
                        sys.stderr.write("Viland: Insert Mode\n")
                self.last_caps_time = now

            if self.mode == 'insert':
                self.write_event(type, code, value)
                continue

            if code == CAPSLOCK:
                self.write_event(type, code, value)
                continue

            if value != 1:
                self.write_event(type, code, value)
                continue

            if code == 23:
                self.mode = 'insert'
                sys.stderr.write("Viland: Insert Mode\n")
                self.emit_key(ESC, 1)
                self.emit_key(ESC, 0)
                continue

            if code == 30:
                self.mode = 'insert'
                self.emit_key(ESC, 1)
                self.emit_key(ESC, 0)
                self.emit_key(ARROWS['right'], 1)
                self.emit_key(ARROWS['right'], 0)
                sys.stderr.write("Viland: Insert Mode\n")
                continue

            mapped = {
                35: ARROWS['left'],
                36: ARROWS['down'],
                37: ARROWS['up'],
                38: ARROWS['right'],
                17: ARROWS['right'],
                48: ARROWS['left'],
                18: 107,
                16: 105,
                11: 102,
                21: 107,
                34: 102,
            }.get(code)

            if mapped:
                self.emit_key(mapped, 1)
                self.emit_key(mapped, 0)
            else:
                self.write_event(type, code, value)


def main():
    VilandFilter().run()

if __name__ == '__main__':
    main()