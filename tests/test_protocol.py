"""Pi <-> ESP32 protocol: the same vectors are checked by the C++ host tests."""
import random
import struct

from chotu_core import protocol as P


def test_crc16_ccitt_false_check_value():
    assert P.crc16_ccitt(b"123456789") == 0x29B1


def test_cobs_round_trip_random():
    rng = random.Random(1)
    for n in (0, 1, 2, 10, 253, 254, 255, 300):
        data = bytes(rng.choice([0, 0, 1, 7, 255]) for _ in range(n))
        enc = P.cobs_encode(data)
        assert 0 not in enc
        assert P.cobs_decode(enc) == data


def test_cobs_known_vector():
    assert P.cobs_encode(b"\x11\x22\x00\x33") == b"\x03\x11\x22\x02\x33"


def test_cmd_vel_frame_matches_firmware_vector():
    frame = P.Encoder().cmd_vel(0.25, -1.0)
    # payload = 01 00 | FA 00 | 18 FC  (+ CRC) - asserted identically in test_host
    payload = P.unframe(frame[:-1])
    assert payload == bytes([0x01, 0x00, 0xFA, 0x00, 0x18, 0xFC])
    assert P.parse_payload(payload)[2] == (0.25, -1.0)


def test_telemetry_round_trip_and_stream_decoding():
    t = P.Telemetry(123456, 1500, -42, 0.123, 0.5, 1.2, 0.03, 0.8, P.FLAG_BUMP, 11.95)
    stream = b"\x07garbage" + b"\x00" + P.encode_telemetry(t, seq=9) + P.Encoder().heartbeat()
    payloads = list(P.StreamDecoder().feed(stream))
    assert len(payloads) == 2
    msg_id, seq, tel = P.parse_payload(payloads[0])
    assert msg_id == P.MSG_TELEMETRY and seq == 9
    assert tel.ticks_left == 1500 and tel.ticks_right == -42
    assert abs(tel.gyro_z - 0.123) < 1e-3 and tel.bump and not tel.cliff
    assert abs(tel.battery_v - 11.95) < 1e-3


def test_corrupted_frame_is_rejected():
    f = bytearray(P.Encoder().actuators(0.55, 1.0))
    f[2] ^= 0x40
    dec = P.StreamDecoder()
    assert list(dec.feed(bytes(f))) == []
    assert dec.crc_errors == 1


def test_telemetry_struct_size():
    assert P.TELEMETRY_SIZE == struct.calcsize("<IiihHHHHBH") == 25
