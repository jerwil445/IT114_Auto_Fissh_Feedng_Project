"""Parse the Arduino's distance readings and separate streamed telemetry from replies."""
import math

EMPTY_DISTANCE_CM = 20.0


def parse_distance(response):
    if not isinstance(response, str) or not response.startswith("DISTANCE:"):
        return None
    value = response.split(":", 1)[1].strip().upper()
    if value.endswith("CM"):
        value = value[:-2].strip()
    try:
        distance = float(value)
    except ValueError:
        return None
    return distance if math.isfinite(distance) and distance >= 0 else None


def feed_percentage(distance, full_distance, empty_distance=EMPTY_DISTANCE_CM):
    if distance is None:
        return None
    # Floating-point equivalent of map(distance, full_distance, empty_distance, 100, 0).
    percent = (empty_distance - distance) / (empty_distance - full_distance) * 100
    return round(max(0.0, min(100.0, percent)), 1)


def is_command_reply(command, response):
    if not response or response == "ARDUINO_READY":
        return False
    if response.startswith("DISTANCE:"):
        return command == "DISTANCE"
    if response.startswith("FEED_LEVEL:"):
        return command == "FEED_LEVEL"
    if response.startswith("FEED_STATUS:") or response == "SENSOR_ERROR":
        return False
    if command.startswith('CALIBRATE:'):
        return response == 'CALIBRATION_OK' or response.startswith(('ERROR:', 'UNKNOWN_COMMAND:'))
    if command.startswith(('LCD_IDLE:', 'LCD_ACTIVE:', 'LCD_DONE:', 'LCD_FAIL:')):
        return response == 'LCD_OK' or response.startswith(('UNKNOWN_COMMAND:', 'ERROR:'))
    return True
