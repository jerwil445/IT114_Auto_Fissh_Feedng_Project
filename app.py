import os
import threading
import time

import serial
from flask import Flask, jsonify
from serial_protocol import is_command_reply, parse_distance

app = Flask(__name__)

# ==========================================
# SERIAL CONFIGURATION
# ==========================================

ARDUINO_PORT = os.getenv("ARDUINO_PORT", "COM4")
ARDUINO_PORTS = [
    p.strip()
    for p in os.getenv(
        "ARDUINO_PORTS",
        f"{ARDUINO_PORT},COM4,COM5,/dev/ttyUSB0,/dev/ttyACM0,/dev/ttyUSB1"
    ).split(",")
    if p.strip()
]
BAUD_RATE = 9600

arduino = None
serial_lock = threading.RLock()


# ==========================================
# CONNECT TO ARDUINO
# ==========================================

def connect_arduino(port=None):
    with serial_lock:
        return _connect_arduino(port)


def _connect_arduino(port=None):

    global arduino

    ports_to_try = [port] if port else ARDUINO_PORTS

    for candidate in ports_to_try:
        try:
            if arduino is not None and arduino.is_open:
                arduino.close()

            arduino = serial.Serial(
                port=candidate,
                baudrate=BAUD_RATE,
                timeout=2
            )

            # Arduino resets when serial opens
            time.sleep(2)

            print(f"Arduino connected successfully on {candidate}!")
            return True

        except Exception as e:
            print(f"Arduino connection failed on {candidate}:")
            print(e)
            arduino = None

    return False


connect_arduino()


# ==========================================
# SEND COMMAND
# ==========================================

def send_command(command):
    with serial_lock:
        return _send_command(command)


def _send_command(command):

    if arduino is None or not arduino.is_open:
        if not connect_arduino():
            return None

    try:

        with serial_lock:

            arduino.reset_input_buffer()

            arduino.write(
                (command + "\n").encode("utf-8")
            )

            arduino.flush()

            response = None
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                line = arduino.readline().decode("utf-8", errors="ignore").strip()
                if is_command_reply(command, line):
                    response = line
                    break

            print(
                "Command:",
                command,
                "| Response:",
                response
            )

            return response

    except Exception as e:

        print("Serial communication error:")
        print(e)

        if not connect_arduino():
            return None

        return None


# ==========================================
# HOME PAGE
# ==========================================

@app.route("/status")
def status():
    return jsonify(get_connection())


def get_connection():
    global arduino

    with serial_lock:
        if arduino is not None and arduino.is_open:
            try:
                # Query the driver without consuming data or activating hardware.
                # is_open alone can remain true after the USB cable is removed.
                arduino.in_waiting
            except (serial.SerialException, OSError):
                try:
                    arduino.close()
                except (serial.SerialException, OSError):
                    pass
                arduino = None

        if arduino is None or not arduino.is_open:
            connect_arduino()

        connected = arduino is not None and arduino.is_open
        return {
            "connected": connected,
            "port": arduino.port if connected else None
        }


# ==========================================
# SEND HARDWARE COMMAND
# ==========================================

@app.route("/command/<command>")
def hardware_command(command):

    command = command.upper()

    allowed_commands = [

        "MORNING_ON",
        "MORNING_OFF",

        "AFTERNOON_ON",
        "AFTERNOON_OFF",

        "NIGHT_ON",
        "NIGHT_OFF",

        "RED_ON",
        "RED_OFF",

        "BUZZER_ON",
        "BUZZER_OFF",

        "SERVO_ROTATE",
        "SERVO_STOP",
        "SERVO_TEST",

        "LCD_TEST",

        "ALL_LED_ON",
        "ALL_LED_OFF",

        "PING"
    ]

    if command not in allowed_commands:

        return jsonify({
            "success": False,
            "message": "Invalid command"
        }), 400


    response = feeder.send(command)


    if response is None:

        return jsonify({
            "success": False,
            "message": "Arduino communication failed."
        }), 500


    return jsonify({
        "success": True,
        "command": command,
        "response": response
    })


# ==========================================
# ULTRASONIC SENSOR
# ==========================================

@app.route("/distance")
def distance():

    response = feeder.send(
        "DISTANCE"
    )


    if response is None:

        return jsonify({
            "success": False,
            "message": "Unable to read sensor."
        }), 500


    try:

        if response.startswith(
            "DISTANCE:"
        ):

            value = parse_distance(response)
            if value is None:
                return jsonify(success=False, message="No valid sensor reading.")

            return jsonify({
                "success": True,
                "distance": value
            })

    except Exception:
        pass


    return jsonify({
        "success": False,
        "message": response
    })


# ==========================================
# START SERVER
# ==========================================

from aquafeed import setup_aquafeed

feeder = setup_aquafeed(app, send_command, get_connection)


if __name__ == "__main__":

    print()
    print("==============================")
    print(" SMART FISH FEEDER DASHBOARD")
    print("==============================")
    print()

    feeder.start()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        use_reloader=False
    )
