// Host unit tests for lib/chotu_logic (no hardware needed).
//   g++ -std=c++17 -Wall -Wextra -I../lib/chotu_logic/src test_chotu_logic.cpp -o test_chotu_logic
// The expected frames below were produced by chotu_core/protocol.py, so this
// proves the C++ firmware and the Python ROS bridge speak the same bytes.
#include <cmath>
#include <cstdio>
#include <cstring>

#include "chotu_logic.h"

using namespace chotu;

static int g_fail = 0, g_pass = 0;
#define CHECK(cond)                                                     \
  do {                                                                  \
    if (cond) { ++g_pass; }                                             \
    else { ++g_fail; std::printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #cond); } \
  } while (0)

static bool feed_all(FrameDecoder& d, const uint8_t* f, size_t n, Command& c) {
  bool got = false;
  for (size_t i = 0; i < n; ++i) got = d.feed(f[i], c) || got;
  return got;
}

static void test_crc() {
  const char* s = "123456789";
  CHECK(crc16_ccitt(reinterpret_cast<const uint8_t*>(s), 9) == 0x29B1);
}

static void test_cobs() {
  const uint8_t in[] = {0x11, 0x22, 0x00, 0x33};
  uint8_t enc[16], dec[16];
  size_t n = cobs_encode(in, 4, enc);
  const uint8_t expect[] = {0x03, 0x11, 0x22, 0x02, 0x33};
  CHECK(n == 5 && std::memcmp(enc, expect, 5) == 0);
  CHECK(cobs_decode(enc, n, dec) == 4 && std::memcmp(dec, in, 4) == 0);
  uint8_t big[300], benc[310], bdec[310];
  for (int i = 0; i < 300; ++i) big[i] = static_cast<uint8_t>(i % 7 == 0 ? 0 : i);
  size_t bn = cobs_encode(big, 300, benc);
  for (size_t i = 0; i < bn; ++i) CHECK(benc[i] != 0);
  CHECK(cobs_decode(benc, bn, bdec) == 300 && std::memcmp(big, bdec, 300) == 0);
}

static void test_python_vectors() {
  // Encoder().cmd_vel(0.25, -1.0)  (seq 0)
  const uint8_t cmd[] = {0x02, 0x01, 0x02, 0xFA, 0x05, 0x18, 0xFC, 0x1F, 0x18, 0x00};
  // Encoder().actuators(0.55, 1.0)  (seq 1)
  const uint8_t act[] = {0x07, 0x02, 0x01, 0x37, 0x64, 0xB8, 0xEE, 0x00};
  FrameDecoder d;
  Command c;
  CHECK(feed_all(d, cmd, sizeof(cmd), c));
  CHECK(c.id == MSG_CMD_VEL && c.seq == 0 && c.v_mm_s == 250 && c.w_mrad_s == -1000);
  CHECK(feed_all(d, act, sizeof(act), c));
  CHECK(c.id == MSG_ACTUATORS && c.seq == 1 && c.suction_pct == 55 && c.brush_pct == 100);

  // encode_telemetry(Telemetry(123456,1500,-42,0.123,0.5,1.2,0.03,0.8,BUMP,11.95), seq=9)
  const uint8_t tel_py[] = {0x06, 0x81, 0x09, 0x40, 0xE2, 0x01, 0x03, 0xDC, 0x05, 0x01, 0x06, 0xD6,
                            0xFF, 0xFF, 0xFF, 0x7B, 0x06, 0xF4, 0x01, 0xB0, 0x04, 0x1E, 0x08, 0x20,
                            0x03, 0x01, 0xAE, 0x2E, 0xE7, 0x4A, 0x00};
  Telemetry t{123456, 1500, -42, 123, 500, 1200, 30, 800, FLAG_BUMP, 11950};
  uint8_t out[MAX_FRAME];
  size_t n = encode_telemetry(t, 9, out);
  CHECK(n == sizeof(tel_py) && std::memcmp(out, tel_py, n) == 0);
}

static void test_corruption_and_overflow() {
  uint8_t act[] = {0x07, 0x02, 0x01, 0x37, 0x64, 0xB8, 0xEE, 0x00};
  act[3] ^= 0x10;
  FrameDecoder d;
  Command c;
  CHECK(!feed_all(d, act, sizeof(act), c));
  CHECK(d.errors == 1);
  uint8_t junk[200];
  std::memset(junk, 0x55, sizeof(junk));
  junk[199] = 0;
  CHECK(!feed_all(d, junk, sizeof(junk), c));
  const uint8_t hb_payload[] = {MSG_HEARTBEAT, 7};
  uint8_t hb[16];
  size_t n = build_frame(hb_payload, 2, hb);
  CHECK(feed_all(d, hb, n, c) && c.id == MSG_HEARTBEAT && c.seq == 7);
}

static void test_pid_and_kinematics() {
  Pid pid(2.0f, 5.0f, 0.0f, -1023.f, 1023.f);
  float y = 0;
  for (int i = 0; i < 1000; ++i) y += 0.1f * (pid.update(100.0f - y, 0.02f) - y);  // first-order plant
  CHECK(std::fabs(y - 100.0f) < 5.0f);
  float l, r;
  twist_to_wheels(200, 1000, 260.0f, l, r);
  CHECK(std::fabs(l - 70.0f) < 1e-3 && std::fabs(r - 330.0f) < 1e-3);
}

static void test_safety() {
  SafetySupervisor s(300, 50);
  uint8_t flags = 0;
  int16_t w = 500;
  s.on_command(1000);
  CHECK(s.limit(250, w, 1100, 800, false, false, flags) == 250);
  CHECK(s.limit(250, w, 1100, 30, false, false, flags) == 0);     // obstacle ahead
  CHECK(s.limit(-100, w, 1100, 30, false, false, flags) == -100); // reversing allowed
  CHECK(s.limit(250, w, 1100, 800, true, false, flags) == 0);     // bump
  CHECK(s.limit(250, w, 1500, 800, false, false, flags) == 0 && (flags & FLAG_WATCHDOG) && w == 0);
  s.set_estop(true);
  flags = 0;
  w = 100;
  s.on_command(2000);
  CHECK(s.limit(250, w, 2001, 800, false, false, flags) == 0 && (flags & FLAG_ESTOP));
}

int main() {
  test_crc();
  test_cobs();
  test_python_vectors();
  test_corruption_and_overflow();
  test_pid_and_kinematics();
  test_safety();
  std::printf("chotu_logic host tests: %d passed, %d failed\n", g_pass, g_fail);
  return g_fail == 0 ? 0 : 1;
}
