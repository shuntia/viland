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

ARROWS = {'left': 105, 'right': 106, 'up': 103, 'down': 108}
HOME = 102
END = 107

DOUBLE_TAP_TIMEOUT = 0.5
DOUBLE_ESC_TIMEOUT = 0.3


class VilandFilter:
    def __init__(self):
        self.mode = 'insert'
        self.enabled = True
        self.last_caps_time = 0.0
        self.last_esc_time = 0.0

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

            if code == ESC and value == 1:
                if now - self.last_esc_time < DOUBLE_ESC_TIMEOUT:
                    self.enabled = not self.enabled
                    if self.enabled:
                        sys.stderr.write("Viland: Enabled\n")
                    else:
                        sys.stderr.write("Viland: Disabled\n")
                        self.mode = 'insert'
                self.last_esc_time = now

            if not self.enabled:
                self.write_event(type, code, value)
                continue

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

            if code == 23:  # i
                self.mode = 'insert'
                sys.stderr.write("Viland: Insert Mode\n")
                self.emit_key(ESC, 1)
                self.emit_key(ESC, 0)
                continue

            if code == 30:  # a
                self.mode = 'insert'
                self.emit_key(ESC, 1)
                self.emit_key(ESC, 0)
                self.emit_key(ARROWS['right'], 1)
                self.emit_key(ARROWS['right'], 0)
                sys.stderr.write("Viland: Insert Mode\n")
                continue

            if code == 24:  # o
                self.mode = 'insert'
                self.emit_key(END, 1)
                self.emit_key(END, 0)
                time.sleep(0.01)
                self.emit_key(28, 1)  # enter
                self.emit_key(28, 0)
                time.sleep(0.01)
                self.emit_key(ARROWS['up'], 1)
                self.emit_key(ARROWS['up'], 0)
                sys.stderr.write("Viland: Insert Mode\n")
                continue

            if code == 31:  # s
                self.mode = 'insert'
                self.emit_key(14, 1)  # backspace
                self.emit_key(14, 0)
                sys.stderr.write("Viland: Insert Mode\n")
                continue

            if code == 45:  # x
                self.emit_key(14, 1)
                self.emit_key(14, 0)
                continue

            mapped = {
                35: ARROWS['left'],   # h
                36: ARROWS['down'],   # j
                37: ARROWS['up'],     # k
                38: ARROWS['right'],  # l
                17: ARROWS['right'],  # w
                48: ARROWS['left'],   # b
                18: END,              # e
                16: ARROWS['left'],   # q
                11: HOME,             # 0
                21: END,              # $
                34: HOME,             # g
                39: 106,              # n (next search = right)
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