// config.h - tunables for the CHOTU base controller (keep in sync with chotu_core/config.py)
#pragma once

// Serial link to the Raspberry Pi 4 (UART0 via the DevKit's USB-UART port)
#define LINK_BAUD 115200
#define CONTROL_HZ 50                 // PID + telemetry rate
#define WATCHDOG_MS 300               // stop motors if the Pi goes silent

// Geometry
#define WHEEL_BASE_MM 260.0f
#define WHEEL_RADIUS_MM 32.5f
#define ENCODER_TICKS_PER_REV 20
#define MM_PER_TICK (2.0f * 3.14159265f * WHEEL_RADIUS_MM / ENCODER_TICKS_PER_REV)
#define MAX_WHEEL_MM_S 300.0f         // 200 RPM BO motor @ 11.1 V, 65 mm wheel ~ 680 mm/s no-load; capped

// PWM (LEDC)
#define MOTOR_PWM_FREQ 20000
#define MOTOR_PWM_BITS 10             // 0..1023
#define PWM_MAX 1023
#define ACT_PWM_FREQ 20000
#define LEDC_CH_L 0
#define LEDC_CH_R 1
#define LEDC_CH_VAC 2
#define LEDC_CH_BRUSH 3

// Wheel velocity PID (output in PWM counts, feed-forward added separately)
#define PID_KP 1.6f
#define PID_KI 6.0f
#define PID_KD 0.0f
#define FEEDFORWARD_PWM_PER_MM_S 2.6f
#define MIN_MOVE_PWM 330              // BO motors stall below this

// Sensors
#define US_MAX_MM 1500
#define US_TIMEOUT_US 25000
#define TOF_MAX_MM 1200
#define STOP_DISTANCE_MM 50
#define BATT_DIVIDER_RATIO ((100.0f + 22.0f) / 22.0f)
#define GYRO_CAL_SAMPLES 400
