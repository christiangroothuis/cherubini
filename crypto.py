from typing import Union

BytesLike = Union[bytes, bytearray, memoryview]
State = tuple[int, int, int, int]
SerialID = tuple[int, int, int]
Key8 = bytes

MIX_ROUNDS = 66


def _u8(x) -> int:
    return x & 0xFF


def _shift_state_left(state: State, table: Key8) -> State:
    r54, r55, r56, r57 = state
    table_index = 1

    for _ in range(MIX_ROUNDS):
        mix_byte = table[table_index]
        table_index = (table_index - 1) & 7

        for _ in range(8):
            reg57 = r57

            # base mask from r57
            if (reg57 & 0x40) == 0:
                mask = 0x74 if (reg57 & 0x02) == 0 else 0x2E
            else:
                mask = 0x3A if (reg57 & 0x02) == 0 else 0x5C

            if r56 & 0x08:
                mask = _u8(mask << 4)
            if r55 & 0x01:
                mask = _u8(mask << 2)
            if r54 & 0x01:
                mask = _u8(mask << 1)

            # carries
            c54, c55, c56 = (r54 >> 7) & 1, (r55 >> 7) & 1, (r56 >> 7) & 1
            feedback_bit = ((r55 ^ r57 ^ mix_byte ^ mask) >> 7) & 1

            # Shift chain left
            r54 = _u8((r54 << 1) | feedback_bit)
            r55 = _u8((r55 << 1) | c54)
            r56 = _u8((r56 << 1) | c55)
            r57 = _u8((r57 << 1) | c56)

            mix_byte = _u8(mix_byte << 1)

    return r54, r55, r56, r57


def _shift_state_right(state: State, table: Key8) -> State:
    r54, r55, r56, r57 = state
    table_index = 0

    for _ in range(MIX_ROUNDS):
        mix_byte = table[table_index]
        table_index = (table_index + 1) & 7

        for _ in range(8):
            reg57 = r57

            # base mask from r57
            if (reg57 & 0x80) == 0:
                mask = 0x2E if (reg57 & 0x04) == 0 else 0x74
            else:
                mask = 0x5C if (reg57 & 0x04) == 0 else 0x3A

            if r56 & 0x10:
                mask >>= 4
            if r55 & 0x02:
                mask >>= 2
            if r54 & 0x02:
                mask >>= 1
            mask = _u8(mask)

            # lsb's
            lsb_57, lsb_56, lsb_55 = (r57 & 1), (r56 & 1), (r55 & 1)
            feedback_bit = (r56 ^ r54 ^ mix_byte ^ mask) & 1

            r57 = _u8((feedback_bit << 7) | (r57 >> 1))
            r56 = _u8((lsb_57 << 7) | (r56 >> 1))
            r55 = _u8((lsb_56 << 7) | (r55 >> 1))
            r54 = _u8((lsb_55 << 7) | (r54 >> 1))

            mix_byte = _u8(mix_byte >> 1)

    return r54, r55, r56, r57


def _expand_key_table(serial_id: SerialID, key: Key8) -> Key8:
    sid0, sid1, sid2 = serial_id
    first = _shift_state_left((sid0, sid1, sid2, 0x20), key)
    second = _shift_state_left((sid0, sid1, sid2, 0x60), key)

    return bytes([*first, *second])


def encrypt(
    serial_id: int, counter: int, button_state: int, master_key: int
) -> State:
    """Encrypt (counter, button_state) into cipher state
    Args:
        serial_id (int): 28-bit serial ID
    """
    serial_id = serial_id.to_bytes(3, "little")
    master_key = master_key.to_bytes(8, "little")

    key_table = _expand_key_table(serial_id, master_key)

    r54 = _u8(counter)
    r55 = _u8(counter >> 8)
    r56 = _u8(serial_id[0] << 6)
    r57 = _u8((button_state & 0xF0) | ((serial_id[0] & 0x0C) >> 2))

    state =  _shift_state_right((r54, r55, r56, r57), key_table)

    return state[0] | (state[1] << 8) | (state[2] << 16) | (state[3] << 24)


class DecryptionError(Exception):
    pass


def decrypt(
    serial_id: int, cipher: int, master_key: int
) -> tuple[int, int]:
    """Decrypt cipher state and return (counter, button_state)."""
    serial_id = serial_id.to_bytes(3, "little")
    cipher = cipher.to_bytes(4, "little")
    master_key = master_key.to_bytes(8, "little")

    key_table = _expand_key_table(serial_id, bytes(master_key))
    sid0, *_ = serial_id
    d0, d1, d2, d3 = _shift_state_left(cipher, key_table)

    if d2 != _u8((sid0 << 6)) or (d3 & 0x03) != (sid0 & 0x0C) >> 2:
        raise DecryptionError("Decryption failed: serial ID check failed")

    counter = d0 | (d1 << 8)
    button_state = d3 & 0xF0

    return (counter, button_state)
