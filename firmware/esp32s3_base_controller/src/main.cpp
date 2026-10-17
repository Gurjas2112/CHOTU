// CHOTU base controller - ESP32-S3 real-time layer.
//
// Responsibilities (hard real-time, 50 Hz):
//   * receive cmd_vel / actuator / e-stop frames from the Raspberry Pi 4
//   * closed-loop wheel speed control (encoders + PID) on the L298N
//   * read 3 x HC-SR04, VL53L0X ToF, MPU6050 gyro, SW-420 bump, 2 x IR cliff
//   * enforce the safety layer (watchdog, bump/cliff/front-distance stop)
//     even if the Pi / ROS 2 stack crashes
//   * drive the vacuum + brush MOSFETs, stream telemetry back to the Pi
//
// Build:  pio run -e esp32s3      Flash: pio run -e esp32s3 -t upload
#include <Arduino.h>
#include <VL53L0X.h>
#include <Wire.h>
#include <esp_arduino_version.h>

#include "chotu_logic.h"
#include "config.h"
#include "pins.h"

using namespace chotu;

// ------------------------------------------------------------------ PWM shim
// Arduino-ESP32 3.x replaced ledcSetup/ledcAttachPin with ledcAttach(pin,...).
#if ESP_ARDUINO_VERSION_MAJOR >= 3
static void pwmAttach(uint8_t pin, uint8_t, uint32_t freq, uint8_t bits) { ledcAttach(pin, freq, bits); }
static void pwmWrite(uint8_t pin, uint8_t, uint32_t duty) { ledcWrite(pin, duty); }
#else
static void pwmAttach(uint8_t pin, uint8_t ch, uint32_t freq, uint8_t bits) {
  ledcSetup(ch, freq, bits);
  ledcAttachPin(pin, ch);
}
static void pwmWrite(uint8_t, uint8_t ch, uint32_t duty) { ledcWrite(ch, duty); }
#endif

// ------------------------------------------------------------------ state
static volatile uint32_t g_enc_count[2] = {0, 0};
static int32_t g_ticks[2] = {0, 0};          // signed odometry ticks sent to the Pi
static uint32_t g_enc_prev[2] = {0, 0};
static int8_t g_dir[2] = {1, 1};             // single-channel encoders: sign from command

struct UltrasonicChannel {
  uint8_t trig, echo;
  volatile uint32_t rise_us;
  volatile uint32_t width_us;
  volatile bool fresh;
  uint16_t mm;
};
static UltrasonicChannel g_us[3] = {
    {PIN_US_L_TRIG, PIN_US_L_ECHO, 0, 0, false, US_MAX_MM},
    {PIN_US_C_TRIG, PIN_US_C_ECHO, 0, 0, false, US_MAX_MM},
    {PIN_US_R_TRIG, PIN_US_R_ECHO, 0, 0, false, US_MAX_MM},
};
static uint8_t g_us_next = 0;
static uint32_t g_us_fired_us = 0;

static VL53L0X g_tof;
static bool g_tof_ok = false;
static uint16_t g_tof_mm = TOF_MAX_MM;

static bool g_imu_ok = false;
static float g_gyro_bias = 0.0f;             // rad/s
static float g_gyro_z = 0.0f;                // rad/s

static FrameDecoder g_decoder;
static SafetySupervisor g_safety(WATCHDOG_MS, STOP_DISTANCE_MM);
static Command g_cmd;                        // latest cmd_vel
static uint8_t g_suction_pct = 0, g_brush_pct = 0;
static Pid g_pid[2] = {Pid(PID_KP, PID_KI, PID_KD, -PWM_MAX, PWM_MAX),
                       Pid(PID_KP, PID_KI, PID_KD, -PWM_MAX, PWM_MAX)};
static uint8_t g_tx_seq = 0;
static volatile bool g_bump_latch = false;

// ------------------------------------------------------------------ ISRs
static void IRAM_ATTR isrEncL() { g_enc_count[0]++; }
static void IRAM_ATTR isrEncR() { g_enc_count[1]++; }
static void IRAM_ATTR isrBump() { g_bump_latch = true; }

static inline void IRAM_ATTR echoEdge(UltrasonicChannel& ch) {
  uint32_t now = micros();
  if (digitalRead(ch.echo)) {
    ch.rise_us = now;
  } else if (ch.rise_us) {
    ch.width_us = now - ch.rise_us;
    ch.rise_us = 0;
    ch.fresh = true;
  }
}
static void IRAM_ATTR isrEchoL() { echoEdge(g_us[0]); }
static void IRAM_ATTR isrEchoC() { echoEdge(g_us[1]); }
static void IRAM_ATTR isrEchoR() { echoEdge(g_us[2]); }

// ------------------------------------------------------------------ motors
static void setMotor(int side, int pwm) {
  const uint8_t en = side == 0 ? PIN_MOTOR_L_EN : PIN_MOTOR_R_EN;
  const uint8_t ch = side == 0 ? LEDC_CH_L : LEDC_CH_R;
  const uint8_t in_a = side == 0 ? PIN_MOTOR_L_IN1 : PIN_MOTOR_R_IN3;
  const uint8_t in_b = side == 0 ? PIN_MOTOR_L_IN2 : PIN_MOTOR_R_IN4;
  pwm = constrain(pwm, -PWM_MAX, PWM_MAX);
  if (pwm == 0) {                       // active brake
    digitalWrite(in_a, HIGH);
    digitalWrite(in_b, HIGH);
    pwmWrite(en, ch, 0);
    return;
  }
  digitalWrite(in_a, pwm > 0 ? HIGH : LOW);
  digitalWrite(in_b, pwm > 0 ? LOW : HIGH);
  pwmWrite(en, ch, static_cast<uint32_t>(abs(pwm)));
}

static void setActuators(uint8_t suction_pct, uint8_t brush_pct) {
  pwmWrite(PIN_VACUUM_PWM, LEDC_CH_VAC, (uint32_t)suction_pct * PWM_MAX / 100);
  pwmWrite(PIN_BRUSH_PWM, LEDC_CH_BRUSH, (uint32_t)brush_pct * PWM_MAX / 100);
}

// ------------------------------------------------------------------ sensors
static bool mpuWrite(uint8_t reg, uint8_t val) {
  Wire.beginTransmission(0x68);
  Wire.write(reg);
  Wire.write(val);
  return Wire.endTransmission() == 0;
}

static bool mpuReadGyroZ(float& rad_s) {
  Wire.beginTransmission(0x68);
  Wire.write(0x47);                     // GYRO_ZOUT_H
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(0x68, 2) != 2) return false;
  int16_t raw = (int16_t)((Wire.read() << 8) | Wire.read());
  rad_s = (raw / 65.5f) * (PI / 180.0f); // FS_SEL=1 (+-500 dps)
  return true;
}

static void setupImu() {
  g_imu_ok = mpuWrite(0x6B, 0x00)       // wake up
             && mpuWrite(0x1A, 0x03)    // DLPF 44 Hz
             && mpuWrite(0x1B, 0x08);   // +-500 dps
  if (!g_imu_ok) return;
  float sum = 0, v = 0;
  for (int i = 0; i < GYRO_CAL_SAMPLES; ++i) {   // robot must be still on the dock
    if (mpuReadGyroZ(v)) sum += v;
    delay(2);
  }
  g_gyro_bias = sum / GYRO_CAL_SAMPLES;
}

static void setupTof() {
  pinMode(PIN_TOF_XSHUT, OUTPUT);
  digitalWrite(PIN_TOF_XSHUT, LOW);
  delay(10);
  digitalWrite(PIN_TOF_XSHUT, HIGH);
  delay(10);
  g_tof.setTimeout(30);
  g_tof_ok = g_tof.init();
  if (g_tof_ok) {
    g_tof.setMeasurementTimingBudget(20000);
    g_tof.startContinuous(0);
  }
}

static void serviceUltrasonic(uint32_t now_us) {
  // collect finished echoes
  for (auto& ch : g_us) {
    if (ch.fresh) {
      ch.fresh = false;
      uint32_t mm = ch.width_us * 343 / 2000;      // speed of sound 343 m/s
      ch.mm = (uint16_t)min<uint32_t>(mm, US_MAX_MM);
    }
  }
  // fire the next sensor once the previous one had time to echo (no crosstalk)
  if (now_us - g_us_fired_us >= US_TIMEOUT_US) {
    UltrasonicChannel& prev = g_us[(g_us_next + 2) % 3];   // the one fired last
    if (prev.width_us == 0) prev.mm = US_MAX_MM;            // no echo -> nothing in range
    prev.rise_us = 0;
    UltrasonicChannel& ch = g_us[g_us_next];
    ch.width_us = 0;
    digitalWrite(ch.trig, LOW);
    delayMicroseconds(2);
    digitalWrite(ch.trig, HIGH);
    delayMicroseconds(10);
    digitalWrite(ch.trig, LOW);
    g_us_fired_us = now_us;
    g_us_next = (g_us_next + 1) % 3;
  }
}

static uint16_t readBatteryMv() {
  return (uint16_t)(analogReadMilliVolts(PIN_BATT_SENSE) * BATT_DIVIDER_RATIO);
}

// ------------------------------------------------------------------ link
static void serviceLink(uint32_t now_ms) {
  while (Serial.available()) {
    Command c;
    if (!g_decoder.feed((uint8_t)Serial.read(), c)) continue;
    g_safety.on_command(now_ms);
    switch (c.id) {
      case MSG_CMD_VEL: g_cmd = c; break;
      case MSG_ACTUATORS: g_suction_pct = c.suction_pct; g_brush_pct = c.brush_pct; break;
      case MSG_ESTOP: g_safety.set_estop(c.estop != 0); break;
      default: break;  // heartbeat only refreshes the watchdog
    }
  }
}

// ------------------------------------------------------------------ control
static void controlStep(uint32_t now_ms, float dt) {
  // --- sensors
  if (g_tof_ok) {
    uint16_t mm = g_tof.readRangeContinuousMillimeters();
    g_tof_mm = (g_tof.timeoutOccurred() || mm > TOF_MAX_MM) ? TOF_MAX_MM : mm;
  }
  float gz = 0;
  if (g_imu_ok && mpuReadGyroZ(gz)) g_gyro_z = gz - g_gyro_bias;
  const bool cliff_l = digitalRead(PIN_CLIFF_L) == HIGH;  // no floor reflection
  const bool cliff_r = digitalRead(PIN_CLIFF_R) == HIGH;
  const bool bump = g_bump_latch;
  g_bump_latch = false;

  // --- safety
  uint8_t flags = 0;
  if (bump) flags |= FLAG_BUMP;
  if (cliff_l) flags |= FLAG_CLIFF_L;
  if (cliff_r) flags |= FLAG_CLIFF_R;
  const uint16_t front = min(g_us[1].mm, g_tof_mm);
  int16_t w = g_cmd.w_mrad_s;
  const int16_t v = g_safety.limit(g_cmd.v_mm_s, w, now_ms, front, bump, cliff_l || cliff_r, flags);

  // --- wheel PID
  float target[2];
  twist_to_wheels(v, w, WHEEL_BASE_MM, target[0], target[1]);
  for (int s = 0; s < 2; ++s) {
    target[s] = constrain(target[s], -MAX_WHEEL_MM_S, MAX_WHEEL_MM_S);
    noInterrupts();
    uint32_t cnt = g_enc_count[s];
    interrupts();
    const int32_t d = (int32_t)(cnt - g_enc_prev[s]);
    g_enc_prev[s] = cnt;
    if (fabsf(target[s]) > 1.0f) g_dir[s] = target[s] > 0 ? 1 : -1;
    g_ticks[s] += g_dir[s] * d;
    const float measured = g_dir[s] * d * MM_PER_TICK / dt;
    if (fabsf(target[s]) < 1.0f) {
      g_pid[s].reset();
      setMotor(s, 0);
      continue;
    }
    float u = FEEDFORWARD_PWM_PER_MM_S * target[s] + g_pid[s].update(target[s] - measured, dt);
    if (fabsf(u) < MIN_MOVE_PWM) u = (u > 0 ? 1 : -1) * MIN_MOVE_PWM;
    setMotor(s, (int)u);
  }

  // --- actuators (off when e-stopped or the Pi is gone)
  if (flags & (FLAG_ESTOP | FLAG_WATCHDOG)) setActuators(0, 0);
  else setActuators(g_suction_pct, g_brush_pct);

  // --- telemetry
  Telemetry t{};
  t.t_ms = now_ms;
  t.ticks_l = g_ticks[0];
  t.ticks_r = g_ticks[1];
  t.gyro_z_mrad_s = (int16_t)constrain(g_gyro_z * 1000.0f, -32768.0f, 32767.0f);
  t.us_l_mm = g_us[0].mm;
  t.us_c_mm = g_us[1].mm;
  t.us_r_mm = g_us[2].mm;
  t.tof_mm = g_tof_mm;
  t.flags = flags;
  t.batt_mv = readBatteryMv();
  uint8_t frame[MAX_FRAME];
  const size_t n = encode_telemetry(t, g_tx_seq++, frame);
  Serial.write(frame, n);
}

// ------------------------------------------------------------------ Arduino
void setup() {
  Serial.begin(LINK_BAUD);
  pinMode(PIN_MOTOR_L_IN1, OUTPUT);
  pinMode(PIN_MOTOR_L_IN2, OUTPUT);
  pinMode(PIN_MOTOR_R_IN3, OUTPUT);
  pinMode(PIN_MOTOR_R_IN4, OUTPUT);
  pwmAttach(PIN_MOTOR_L_EN, LEDC_CH_L, MOTOR_PWM_FREQ, MOTOR_PWM_BITS);
  pwmAttach(PIN_MOTOR_R_EN, LEDC_CH_R, MOTOR_PWM_FREQ, MOTOR_PWM_BITS);
  pwmAttach(PIN_VACUUM_PWM, LEDC_CH_VAC, ACT_PWM_FREQ, MOTOR_PWM_BITS);
  pwmAttach(PIN_BRUSH_PWM, LEDC_CH_BRUSH, ACT_PWM_FREQ, MOTOR_PWM_BITS);
  setMotor(0, 0);
  setMotor(1, 0);
  setActuators(0, 0);

  pinMode(PIN_ENC_L, INPUT_PULLUP);
  pinMode(PIN_ENC_R, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_ENC_L), isrEncL, RISING);
  attachInterrupt(digitalPinToInterrupt(PIN_ENC_R), isrEncR, RISING);

  for (auto& ch : g_us) {
    pinMode(ch.trig, OUTPUT);
    digitalWrite(ch.trig, LOW);
    pinMode(ch.echo, INPUT);
  }
  attachInterrupt(digitalPinToInterrupt(PIN_US_L_ECHO), isrEchoL, CHANGE);
  attachInterrupt(digitalPinToInterrupt(PIN_US_C_ECHO), isrEchoC, CHANGE);
  attachInterrupt(digitalPinToInterrupt(PIN_US_R_ECHO), isrEchoR, CHANGE);

  pinMode(PIN_SW420, INPUT);
  attachInterrupt(digitalPinToInterrupt(PIN_SW420), isrBump, RISING);
  pinMode(PIN_CLIFF_L, INPUT);
  pinMode(PIN_CLIFF_R, INPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  analogReadResolution(12);

  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, 400000);
  setupTof();
  setupImu();

  // two short beeps = ready (IMU calibrated, waiting for the Pi)
  for (int i = 0; i < 2; ++i) {
    digitalWrite(PIN_BUZZER, HIGH);
    delay(60);
    digitalWrite(PIN_BUZZER, LOW);
    delay(80);
  }
}

void loop() {
  static uint32_t last_ctrl_us = micros();
  const uint32_t now_us = micros();
  serviceLink(millis());
  serviceUltrasonic(now_us);
  const uint32_t period_us = 1000000UL / CONTROL_HZ;
  if (now_us - last_ctrl_us >= period_us) {
    const float dt = (now_us - last_ctrl_us) / 1e6f;
    last_ctrl_us = now_us;
    controlStep(millis(), dt);
  }
}
