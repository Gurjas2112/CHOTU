"""Loopback test of the serial framing used by serial_bridge_node (no hardware)."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")))

from chotu_core import protocol as P  # noqa: E402


def test_cmd_vel_survives_byte_by_byte_stream():
    frame = P.Encoder().cmd_vel(0.18, 0.5)
    dec = P.StreamDecoder()
    got = []
    for b in frame:
        got += list(dec.feed(bytes([b])))
    assert len(got) == 1
    assert P.parse_payload(got[0])[2] == (0.18, 0.5)
