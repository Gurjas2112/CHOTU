// chotu_logic.h - hardware-independent logic of the CHOTU base controller.
//
// Everything in this header compiles with plain g++ (host unit tests in
// ../../../test_host) and with the ESP32-S3 Arduino toolchain.  The wire
// format is byte-for-byte identical to chotu_core/protocol.py.
//
//   Frame on the wire:  COBS( payload || CRC16-CCITT(payload) ) || 0x00
//   Payload:            msg_id:u8  seq:u8  body (little-endian)
#pragma once

#include <stddef.h>
#include <stdint.h>
#include <string.h>

namespace chotu {

// --------------------------------------------------------------- messages
enum MsgId : uint8_t {
  MSG_CMD_VEL = 0x01,    // i16 v_mm_s, i16 w_mrad_s
  MSG_ACTUATORS = 0x02,  // u8 suction_pct, u8 brush_pct
  MSG_HEARTBEAT = 0x03,  // (empty)
  MSG_ESTOP = 0x04,      // u8 engage
  MSG_TELEMETRY = 0x81,  // see Telemetry
  MSG_ACK = 0x82,
};

enum Flags : uint8_t {
  FLAG_BUMP = 1 << 0,
  FLAG_CLIFF_L = 1 << 1,
  FLAG_CLIFF_R = 1 << 2,
  FLAG_ESTOP = 1 << 3,
  FLAG_WATCHDOG = 1 << 4,
};

struct Telemetry {
  uint32_t t_ms;
  int32_t ticks_l;
  int32_t ticks_r;
  int16_t gyro_z_mrad_s;
  uint16_t us_l_mm, us_c_mm, us_r_mm, tof_mm;
  uint8_t flags;
  uint16_t batt_mv;
};
static const size_t TELEMETRY_SIZE = 25;
static const size_t MAX_FRAME = 64;

struct Command {
  uint8_t id = 0;
  uint8_t seq = 0;
  int16_t v_mm_s = 0;
  int16_t w_mrad_s = 0;
  uint8_t suction_pct = 0;
  uint8_t brush_pct = 0;
  uint8_t estop = 0;
};

// --------------------------------------------------------------- CRC / COBS
inline uint16_t crc16_ccitt(const uint8_t* data, size_t n, uint16_t crc = 0xFFFF) {
  for (size_t i = 0; i < n; ++i) {
    crc ^= static_cast<uint16_t>(data[i]) << 8;
    for (int b = 0; b < 8; ++b) {
      crc = (crc & 0x8000) ? static_cast<uint16_t>((crc << 1) ^ 0x1021) : static_cast<uint16_t>(crc << 1);
    }
  }
  return crc;
}

// Returns encoded length (no trailing zero). ``out`` needs n + n/254 + 1 bytes.
inline size_t cobs_encode(const uint8_t* in, size_t n, uint8_t* out) {
  size_t code_idx = 0, w = 1;
  uint8_t code = 1;
  for (size_t i = 0; i < n; ++i) {
    if (in[i] == 0) {
      out[code_idx] = code;
      code_idx = w++;
      code = 1;
    } else {
      out[w++] = in[i];
      if (++code == 0xFF) {
        out[code_idx] = code;
        code_idx = w++;
        code = 1;
      }
    }
  }
  out[code_idx] = code;
  return w;
}

// Returns decoded length, or 0 on malformed input.
inline size_t cobs_decode(const uint8_t* in, size_t n, uint8_t* out) {
  size_t r = 0, w = 0;
  while (r < n) {
    uint8_t code = in[r];
    if (code == 0 || r + code > n) return 0;  // zero inside frame / truncated
    ++r;
    for (uint8_t i = 1; i < code; ++i) out[w++] = in[r++];
    if (code < 0xFF && r < n) out[w++] = 0;
  }
  return w;
}

// --------------------------------------------------------------- framing
inline void put_u16(uint8_t* b, uint16_t v) { b[0] = v & 0xFF; b[1] = v >> 8; }
inline void put_u32(uint8_t* b, uint32_t v) { for (int i = 0; i < 4; ++i) b[i] = (v >> (8 * i)) & 0xFF; }
inline uint16_t get_u16(const uint8_t* b) { return static_cast<uint16_t>(b[0] | (b[1] << 8)); }

// payload -> COBS frame incl. trailing 0x00. Returns frame length.
inline size_t build_frame(const uint8_t* payload, size_t n, uint8_t* out) {
  uint8_t raw[MAX_FRAME];
  if (n + 2 > sizeof(raw)) return 0;
  memcpy(raw, payload, n);
  put_u16(raw + n, crc16_ccitt(payload, n));
  size_t len = cobs_encode(raw, n + 2, out);
  out[len++] = 0x00;
  return len;
}

inline size_t encode_telemetry(const Telemetry& t, uint8_t seq, uint8_t* out) {
  uint8_t p[2 + TELEMETRY_SIZE];
  p[0] = MSG_TELEMETRY;
  p[1] = seq;
  uint8_t* b = p + 2;
  put_u32(b, t.t_ms);
  put_u32(b + 4, static_cast<uint32_t>(t.ticks_l));
  put_u32(b + 8, static_cast<uint32_t>(t.ticks_r));
  put_u16(b + 12, static_cast<uint16_t>(t.gyro_z_mrad_s));
  put_u16(b + 14, t.us_l_mm);
  put_u16(b + 16, t.us_c_mm);
  put_u16(b + 18, t.us_r_mm);
  put_u16(b + 20, t.tof_mm);
  b[22] = t.flags;
  put_u16(b + 23, t.batt_mv);
  return build_frame(p, sizeof(p), out);
}

inline bool parse_payload(const uint8_t* p, size_t n, Command& c) {
  if (n < 2) return false;
  c.id = p[0];
  c.seq = p[1];
  switch (c.id) {
    case MSG_CMD_VEL:
      if (n != 6) return false;
      c.v_mm_s = static_cast<int16_t>(get_u16(p + 2));
      c.w_mrad_s = static_cast<int16_t>(get_u16(p + 4));
      return true;
    case MSG_ACTUATORS:
      if (n != 4) return false;
      c.suction_pct = p[2] > 100 ? 100 : p[2];
      c.brush_pct = p[3] > 100 ? 100 : p[3];
      return true;
    case MSG_HEARTBEAT:
      return n == 2;
    case MSG_ESTOP:
      if (n != 3) return false;
      c.estop = p[2];
      return true;
    default:
      return false;
  }
}

// Byte-wise stream decoder: feed() returns true when ``out`` holds a valid command.
class FrameDecoder {
 public:
  bool feed(uint8_t byte, Command& out) {
    if (byte != 0) {
      if (len_ < sizeof(buf_)) buf_[len_++] = byte;
      else overflow_ = true;  // drop the rest of this frame
      return false;
    }
    size_t n = len_;
    bool overflow = overflow_;
    len_ = 0;
    overflow_ = false;
    if (n == 0) return false;
    if (overflow) { ++errors; return false; }
    uint8_t raw[MAX_FRAME];
    size_t m = cobs_decode(buf_, n, raw);
    if (m < 4) { ++errors; return false; }
    uint16_t crc = get_u16(raw + m - 2);
    if (crc16_ccitt(raw, m - 2) != crc) { ++errors; return false; }
    return parse_payload(raw, m - 2, out);
  }
  uint32_t errors = 0;

 private:
  uint8_t buf_[MAX_FRAME];
  size_t len_ = 0;
  bool overflow_ = false;
};

// --------------------------------------------------------------- control
struct Pid {
  float kp, ki, kd, out_min, out_max;
  float integ = 0, prev_err = 0;
  Pid(float p, float i, float d, float lo, float hi) : kp(p), ki(i), kd(d), out_min(lo), out_max(hi) {}
  float update(float err, float dt) {
    integ += err * dt;
    float i_lim = (ki > 0) ? out_max / ki : 0;
    if (integ > i_lim) integ = i_lim;
    if (integ < -i_lim) integ = -i_lim;
    float d = dt > 0 ? (err - prev_err) / dt : 0;
    prev_err = err;
    float u = kp * err + ki * integ + kd * d;
    return u < out_min ? out_min : (u > out_max ? out_max : u);
  }
  void reset() { integ = 0; prev_err = 0; }
};

// cmd_vel -> wheel linear speeds (mm/s)
inline void twist_to_wheels(int16_t v_mm_s, int16_t w_mrad_s, float wheel_base_mm,
                            float& left_mm_s, float& right_mm_s) {
  float w = w_mrad_s / 1000.0f;
  left_mm_s = v_mm_s - w * wheel_base_mm / 2.0f;
  right_mm_s = v_mm_s + w * wheel_base_mm / 2.0f;
}

// --------------------------------------------------------------- safety
// Firmware-level mirror of chotu_core.obstacle_avoidance: it can only make a
// command safer, and it stops the robot if the Raspberry Pi goes silent.
class SafetySupervisor {
 public:
  explicit SafetySupervisor(uint32_t watchdog_ms = 300, uint16_t stop_mm = 50)
      : watchdog_ms_(watchdog_ms), stop_mm_(stop_mm) {}

  void on_command(uint32_t now_ms) { last_cmd_ms_ = now_ms; }
  void set_estop(bool e) { estop_ = e; }
  bool estop() const { return estop_; }
  bool watchdog_tripped(uint32_t now_ms) const { return now_ms - last_cmd_ms_ > watchdog_ms_; }

  // Returns the (possibly reduced) forward speed and sets status flags.
  int16_t limit(int16_t v_mm_s, int16_t& w_mrad_s, uint32_t now_ms, uint16_t front_mm,
                bool bump, bool cliff, uint8_t& flags) const {
    if (estop_) {
      flags |= FLAG_ESTOP;
      w_mrad_s = 0;
      return 0;
    }
    if (watchdog_tripped(now_ms)) {
      flags |= FLAG_WATCHDOG;
      w_mrad_s = 0;
      return 0;
    }
    if (v_mm_s > 0 && (bump || cliff || front_mm < stop_mm_)) return 0;
    return v_mm_s;
  }

 private:
  uint32_t watchdog_ms_;
  uint16_t stop_mm_;
  uint32_t last_cmd_ms_ = 0;
  bool estop_ = false;
};

}  // namespace chotu
