"""CHOTU fleet backend: REST + WebSocket API over mission history, schedules,
no-go zones, alerts and live robot telemetry.

The robot itself never needs this service (rosbridge on the Pi is the robot API);
the backend adds what a single robot cannot keep: multi-robot history, schedules
that survive a re-flash, and one endpoint for the app when away from home WiFi.
"""
__version__ = "1.0.0"
