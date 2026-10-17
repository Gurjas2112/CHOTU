// pins.h - ESP32-S3-DevKitC-1 (N8R8 / N16R8) pin map for the CHOTU base controller.
//
// Avoided on purpose: GPIO0/45/46 (strapping; GPIO3 is used only as an input, see
// PIN_DOCK_IR), 19/20 (USB D-/D+),
// 26-37 (flash / octal PSRAM), 43/44 (UART0 to the USB-UART bridge = link to Pi).
// HC-SR04 ECHO and the IR cliff/encoder outputs are 5 V -> use a 1k/2k divider
// or the 4-channel logic level shifter listed in HARDWARE_SOFTWARE_REQUIREMENTS.md.
#pragma once

// ---- TB6612FNG dual H-bridge (drive motors, 2 x 200 RPM BO gear motors)
// Replaces the v1 L298N: ~0.5 V drop instead of ~2 V, standby pin, same
// IN1/IN2 + PWM scheme (IN1 = IN2 = HIGH is short-brake on both chips).
#define PIN_MOTOR_L_EN 4    // PWMA
#define PIN_MOTOR_L_IN1 5   // AIN1
#define PIN_MOTOR_L_IN2 6   // AIN2
#define PIN_MOTOR_R_EN 7    // PWMB
#define PIN_MOTOR_R_IN3 15  // BIN1
#define PIN_MOTOR_R_IN4 16  // BIN2
#define PIN_MOTOR_STBY 2    // STBY: LOW = both channels off (safety stop)

// ---- Wheel encoders (20-slot disc + LM393 slot sensor, single channel)
#define PIN_ENC_L 17
#define PIN_ENC_R 18

// ---- I2C bus: VL53L0X ToF (0x29) + MPU6050 IMU (0x68)
#define PIN_I2C_SDA 8
#define PIN_I2C_SCL 9
#define PIN_TOF_XSHUT 47

// ---- 3 x HC-SR04 ultrasonic (left 35 deg / centre / right -35 deg)
#define PIN_US_L_TRIG 10
#define PIN_US_L_ECHO 13
#define PIN_US_C_TRIG 11
#define PIN_US_C_ECHO 14
#define PIN_US_R_TRIG 12
#define PIN_US_R_ECHO 21

// ---- Safety inputs
#define PIN_SW420 38        // vibration / bump switch (DO, active HIGH on impact)
#define PIN_CLIFF_L 39      // TCRT5000 IR, LOW = floor present
#define PIN_CLIFF_R 40
#define PIN_DOCK_IR 3       // TSOP38238 38 kHz receiver, LOW = dock beacon seen
                            // (GPIO3 strap only matters if the JTAG-sel eFuse is burned)

// ---- Cleaning actuators through IRLZ44N logic-level MOSFETs (+ 1N5822 flyback)
// The v1 IRF520 module is NOT used: Vgs(th) 2-4 V cannot switch 5 A at 3.3 V.
#define PIN_VACUUM_PWM 41   // Bergmann MGA Tornado BAV-60, 12 V / 60 W
#define PIN_BRUSH_PWM 42    // 2 x side-brush DC motors

// ---- Misc
#define PIN_BATT_SENSE 1    // ADC1_CH0, 100k / 22k divider from the 11.1 V pack
#define PIN_STATUS_LED 48   // on-board RGB (WS2812) on DevKitC-1 v1.0
