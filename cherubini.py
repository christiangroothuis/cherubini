#!/usr/bin/env python3
import sys
import time
import pigpio

from leekoq import LeeKoq

TICK_US = 200
PREAMBLE_TICKS = 46
PREAMBLE_GAP_TICKS = 20
TAIL_GAP_TICKS = 75
TOTAL_BITS = 66
REPEATS = 2

command_map = {
    "UP": 0x50,
    "STOP": 0xA0,
    "DOWN": 0x10,
}


def build_payload(serial_id: int, counter: int, button: int, key: int) -> bytes:
    plaintext = (
        (counter & 0xFFFF)
        | (((serial_id << 6) & 0xFF) << 16)
        | ((((button & 0xF0) | ((serial_id >> 2) & 0x03)) & 0xFF) << 24)
    )

    cipher = LeeKoq.encrypt(plaintext, key)

    payload = bytearray()
    payload += cipher.to_bytes(4, "little")
    payload += serial_id.to_bytes(3, "little")
    payload += button.to_bytes(1, "little")
    payload += b"\x00"

    return payload


class CherubiniRemoteDriver:
    def __init__(self, serial_id, key, tx_pin=None, addr=None, port=None):
        self.serial_id = serial_id
        self.key = key
        self.tx_pin = tx_pin
        self.pi = pigpio.pi(addr, port) if addr else pigpio.pi()

        if not self.pi.connected:
            print("ERROR: could not connect to pigpio daemon", file=sys.stderr)
            sys.exit(1)

        self.pi.set_mode(self.tx_pin, pigpio.OUTPUT)
        self.pi.write(self.tx_pin, 0)

    def _build_sequence(self, payload: bytes) -> list:
        sequence = []

        def _append(level: int, ticks: int):
            sequence.append((level, ticks * TICK_US))

        # Preamble
        level = 0

        for _ in range(PREAMBLE_TICKS):
            _append(level, 1)
            level ^= 1

        # Header gap
        _append(0, PREAMBLE_GAP_TICKS)

        # Payload
        bit_count = 0

        for byte in payload:
            for i in range(8):
                if bit_count >= TOTAL_BITS:
                    break

                bit = (byte >> i) & 1

                _append(1, 4 if bit == 0 else 2)
                _append(0, 2 if bit == 0 else 4)

                bit_count += 1

            if bit_count >= TOTAL_BITS:
                break

        # Tail gap
        _append(0, TAIL_GAP_TICKS)

        return sequence

    def _pulses_from_seq(self, sequence: list) -> list:
        pulses = []

        for level, duration in sequence:
            pulses.append(pigpio.pulse(1 << self.tx_pin if level else 0, 0 if level else 1 << self.tx_pin, duration))

        return pulses

    def _send_wave(self, sequence: list, repeat=None):
        if repeat is None:
            repeat = REPEATS

        while self.pi.wave_tx_busy():
            time.sleep(0.005)

        self.pi.wave_clear()
        self.pi.wave_add_generic(self._pulses_from_seq(sequence))
        wid = self.pi.wave_create()

        try:
            for _ in range(max(1, repeat)):
                self.pi.wave_send_once(wid)

                while self.pi.wave_tx_busy():
                    time.sleep(0.002)
        finally:
            self.pi.wave_delete(wid)
            self.pi.write(self.tx_pin, 0)

    def stop_now(self):
        if self.pi.wave_tx_busy():
            self.pi.wave_tx_stop()
        self.pi.write(self.tx_pin, 0)

    def command(self, command: str, counter: int):
        button = command_map.get(command.upper())
        payload = build_payload(
            serial_id=self.serial_id,
            counter=counter,
            button=button,
            key=self.key,
        )

        sequence = self._build_sequence(payload)

        self._send_wave(sequence)

    def close(self):
        self.stop_now()
        self.pi.stop()
