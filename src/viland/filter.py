#!/usr/bin/env python3
import sys
import struct
import time
import subprocess
import os

EV_KEY = 0x01
EV_SYN = 0x00

CAPSLOCK = 58
ESC = 1

ARROWS = {'left': 105, 'right': 106, 'up': 103, 'down': 108}
HOME = 102
END = 107
ENTER = 28
BACKSPACE = 14

DOUBLE_TAP_TIMEOUT = 0.5
DOUBLE_ESC_TIMEOUT = 0.3


def notify(msg):
    try:
        subprocess.Popen(['notify-send', '-u', 'low', '-t', '800', 'Viland', msg],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        pass
    sys.stderr.write(f"Viland: {msg}\n")
    sys.stderr.flush()


class VilandFilter:
    def __init__(self):
        self.mode = 'insert'
        self.enabled = True
        self.last_caps_time = 0.0
        self.last_esc_time = 0.0

    def read_event(self):
        try:
            data = sys.stdin.buffer.read(24)
            if not data:
                return None
            if len(data) != 24:
                return (0, 0, 0)
            sec, usec, tv_sec, tv_usec, type, code, value = struct.unpack('QQHHIii', data)
            return (type, code, value)
        except Exception as e:
            sys.stderr.write(f"Read error: {e}\n")
            return (0, 0, 0)

    def write_event(self, type, code, value):
        try:
            sys.stdout.buffer.write(struct.pack('QQHHIii',
                0, 0, 0, 0, type, code, value))
            sys.stdout.buffer.flush()
        except Exception as e:
            sys.stderr.write(f"Write error: {e}\n")

    def emit_key(self, code, value):
        self.write_event(EV_KEY, code, value)
        self.write_event(EV_SYN, 0, 0)

    def run(self):
        notify("Insert Mode")

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
                        self.mode = 'insert'
                        notify("Enabled (Insert Mode)")
                    else:
                        notify("Disabled")
                self.last_esc_time = now

            if not self.enabled:
                self.write_event(type, code, value)
                continue

            if code == CAPSLOCK and value == 1:
                if now - self.last_caps_time < DOUBLE_TAP_TIMEOUT:
                    if self.mode == 'insert':
                        self.mode = 'normal'
                        notify("Normal Mode")
                    else:
                        self.mode = 'insert'
                        notify("Insert Mode")
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
                notify("Insert Mode")
                self.emit_key(ESC, 1)
                self.emit_key(ESC, 0)
                continue

            if code == 30:  # a
                self.mode = 'insert'
                self.emit_key(ESC, 1)
                self.emit_key(ESC, 0)
                self.emit_key(ARROWS['right'], 1)
                self.emit_key(ARROWS['right'], 0)
                notify("Insert Mode")
                continue

            if code == 24:  # o
                self.mode = 'insert'
                self.emit_key(END, 1)
                self.emit_key(END, 0)
                time.sleep(0.01)
                self.emit_key(ENTER, 1)
                self.emit_key(ENTER, 0)
                time.sleep(0.01)
                self.emit_key(ARROWS['up'], 1)
                self.emit_key(ARROWS['up'], 0)
                notify("Insert Mode")
                continue

            if code == 31:  # s
                self.mode = 'insert'
                self.emit_key(BACKSPACE, 1)
                self.emit_key(BACKSPACE, 0)
                notify("Insert Mode")
                continue

            if code == 45:  # x
                self.emit_key(BACKSPACE, 1)
                self.emit_key(BACKSPACE, 0)
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