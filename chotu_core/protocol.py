"""Pi <-> ESP32-S3 serial protocol (Python side).

Byte-for-byte mirror of ``firmware/esp32s3_base_controller/lib/chotu_logic``.
Frame on the wire:  COBS( payload || CRC16-CCITT(payload) ) || 0x00
Payload:            msg_id:u8  seq:u8  body (little-endian)

Pi -> ESP32                         ESP32 -> Pi
  0x01 CMD_VEL   i16 v_mm_s,          0x81 TELEMETRY (see TELEMETRY_FMT)
                 i16 w_mrad_s         0x82 ACK  u8 acked_msg_id, u8 seq
  0x02 ACTUATORS u8 suction_pct,
                 u8 brush_pct
  0x03 HEARTBEAT (empty)
  0x04 ESTOP     u8 engage
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Iterator, List, Optional, Tuple

MSG_CMD_VEL = 0x01
MSG_ACTUATORS = 0x02
MSG_HEARTBEAT = 0x03
MSG_ESTOP = 0x04
MSG_TELEMETRY = 0x81
MSG_ACK = 0x82

# t_ms, ticks_l, ticks_r, gyro_z_mrad_s, us_l, us_c, us_r, tof (mm), flags, batt_mv
TELEMETRY_FMT = "<IiihHHHHBH"
TELEMETRY_SIZE = struct.calcsize(TELEMETRY_FMT)  # 25 bytes

FLAG_BUMP = 1 << 0
FLAG_CLIFF_L = 1 << 1
FLAG_CLIFF_R = 1 << 2
FLAG_ESTOP = 1 << 3
FLAG_WATCHDOG = 1 << 4


def crc16_ccitt(data: bytes, crc: int = 0xFFFF) -> int:
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF). crc('123456789') == 0x29B1."""
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return crc


def cobs_encode(data: bytes) -> bytes:
    out = bytearray([0])
    code_idx, code = 0, 1
    for b in data:
        if b == 0:
            out[code_idx] = code
            code_idx, code = len(out), 1
            out.append(0)
        else:
            out.append(b)
            code += 1
            if code == 0xFF:
                out[code_idx] = code
                code_idx, code = len(out), 1
                out.append(0)
    out[code_idx] = code
    return bytes(out)


def cobs_decode(data: bytes) -> bytes:
    out = bytearray()
    i = 0
    while i < len(data):
        code = data[i]
        if code == 0:
            raise ValueError("zero byte inside COBS frame")
        i += 1
        end = i + code - 1
        if end > len(data):
            raise ValueError("truncated COBS frame")
        out += data[i:end]
        i = end
        if code < 0xFF and i < len(data):
            out.append(0)
    return bytes(out)


def frame(payload: bytes) -> bytes:
    crc = crc16_ccitt(payload)
    return cobs_encode(payload + struct.pack("<H", crc)) + b"\x00"


def unframe(encoded: bytes) -> Optional[bytes]:
    """Decode one frame (without the trailing 0x00). Returns payload or None."""
    try:
        raw = cobs_decode(encoded)
    except ValueError:
        return None
    if len(raw) < 4:
        return None
    payload, crc = raw[:-2], struct.unpack("<H", raw[-2:])[0]
    return payload if crc16_ccitt(payload) == crc else None


@dataclass
class Telemetry:
    t_ms: int
    ticks_left: int
    ticks_right: int
    gyro_z: float          # rad/s
    us_left: float         # m
    us_centre: float
    us_right: float
    tof: float
    flags: int
    battery_v: float

    @property
    def bump(self) -> bool:
        return bool(self.flags & FLAG_BUMP)

    @property
    def cliff(self) -> bool:
        return bool(self.flags & (FLAG_CLIFF_L | FLAG_CLIFF_R))


class Encoder:
    def __init__(self) -> None:
        self.seq = 0

    def _payload(self, msg_id: int, body: bytes = b"") -> bytes:
        p = bytes([msg_id, self.seq]) + body
        self.seq = (self.seq + 1) & 0xFF
        return frame(p)

    def cmd_vel(self, v: float, w: float) -> bytes:
        v_mm = max(-32768, min(32767, int(round(v * 1000))))
        w_mrad = max(-32768, min(32767, int(round(w * 1000))))
        return self._payload(MSG_CMD_VEL, struct.pack("<hh", v_mm, w_mrad))

    def actuators(self, suction: float, brush: float) -> bytes:
        s = max(0, min(100, int(round(suction * 100))))
        b = max(0, min(100, int(round(brush * 100))))
        return self._payload(MSG_ACTUATORS, struct.pack("<BB", s, b))

    def heartbeat(self) -> bytes:
        return self._payload(MSG_HEARTBEAT)

    def estop(self, engage: bool) -> bytes:
        return self._payload(MSG_ESTOP, struct.pack("<B", 1 if engage else 0))


def encode_telemetry(t: Telemetry, seq: int = 0) -> bytes:
    body = struct.pack(TELEMETRY_FMT, t.t_ms, t.ticks_left, t.ticks_right,
                       int(round(t.gyro_z * 1000)),
                       int(t.us_left * 1000), int(t.us_centre * 1000),
                       int(t.us_right * 1000), int(t.tof * 1000), t.flags,
                       int(t.battery_v * 1000))
    return frame(bytes([MSG_TELEMETRY, seq & 0xFF]) + body)


def parse_payload(payload: bytes) -> Tuple[int, int, object]:
    msg_id, seq, body = payload[0], payload[1], payload[2:]
    if msg_id == MSG_TELEMETRY and len(body) == TELEMETRY_SIZE:
        f = struct.unpack(TELEMETRY_FMT, body)
        return msg_id, seq, Telemetry(f[0], f[1], f[2], f[3] / 1000.0, f[4] / 1000.0,
                                      f[5] / 1000.0, f[6] / 1000.0, f[7] / 1000.0,
                                      f[8], f[9] / 1000.0)
    if msg_id == MSG_CMD_VEL and len(body) == 4:
        v, w = struct.unpack("<hh", body)
        return msg_id, seq, (v / 1000.0, w / 1000.0)
    if msg_id == MSG_ACTUATORS and len(body) == 2:
        return msg_id, seq, tuple(body)
    if msg_id == MSG_ACK and len(body) == 2:
        return msg_id, seq, tuple(body)
    return msg_id, seq, body


class StreamDecoder:
    """Accumulates serial bytes and yields valid payloads."""

    def __init__(self, max_frame: int = 128) -> None:
        self.buf = bytearray()
        self.max_frame = max_frame
        self.crc_errors = 0

    def feed(self, data: bytes) -> Iterator[bytes]:
        for b in data:
            if b == 0:
                if self.buf:
                    p = unframe(bytes(self.buf))
                    if p is None:
                        self.crc_errors += 1
                    else:
                        yield p
                self.buf.clear()
            else:
                self.buf.append(b)
                if len(self.buf) > self.max_frame:
                    self.buf.clear()


def decode_stream(data: bytes) -> List[bytes]:
    return list(StreamDecoder().feed(data))
