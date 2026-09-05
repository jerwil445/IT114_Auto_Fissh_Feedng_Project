"""Persistent schedules, feeding execution, and observed hardware telemetry."""
import copy
import json
import math
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError



DEFAULTS = {
    "automation": False,
    "angle": 90,
    "duration": 3,
    "full_distance": 3,
    "empty_distance": 25,
    "calibrated": False,
    "slots": [
        {"id": "morning", "name": "Morning", "time": "08:00", "portion": "Morning Flakes", "enabled": True},
        {"id": "afternoon", "name": "Afternoon", "time": "13:00", "portion": "Afternoon Flakes", "enabled": True},
        {"id": "evening", "name": "Evening", "time": "18:00", "portion": "Evening Pellets", "enabled": True},
    ],
}


HARDWARE_TESTS = {
    "connection": ("PING", None, 0),
    "morning": ("MORNING_ON", "MORNING_OFF", 1),
    "afternoon": ("AFTERNOON_ON", "AFTERNOON_OFF", 1),
    "night": ("NIGHT_ON", "NIGHT_OFF", 1),
    "red": ("RED_ON", "RED_OFF", 1),
    "buzzer": ("BUZZER_ON", "BUZZER_OFF", 0.5),
    "servo": ("SERVO_ROTATE", "SERVO_STOP", 3),
    "sensor": ("DISTANCE", None, 0),
    "lcd": ("LCD_TEST", None, 0),
    "leds": ("ALL_LED_ON", "ALL_LED_OFF", 1),
}


class Feeder:
    def __init__(self, send, connection, database):
        self.send = send
        self.connection = connection
        self.database = str(database)
        zone_name = os.getenv("FEEDER_TIMEZONE", "Asia/Manila")
        try:
            self.zone = ZoneInfo(zone_name)
        except ZoneInfoNotFoundError:
            if zone_name != "Asia/Manila":
                raise
            # Windows Python may not include the IANA database. Manila uses UTC+8.
            self.zone = timezone(timedelta(hours=8), name="Asia/Manila")
        self.angle_command = os.getenv("SERVO_ANGLE_COMMAND", "")
        self.feed_lock = threading.Lock()
        self.state_lock = threading.RLock()
        self.worker = None
        self.state = {"connected": False, "port": None, "operation": "Ready", "valve": "Unknown", "distance": None, "level": None, "updated_at": None}
        self.last_connection = None
        self.low = False
        self.test_cancel = threading.Event()
        self.diagnostics = {"running": False, "results": {}, "current": None}
        with self.db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, kind TEXT NOT NULL, trigger TEXT, portion TEXT, status TEXT NOT NULL, message TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS executions (key TEXT PRIMARY KEY)")
            db.execute("INSERT OR IGNORE INTO settings VALUES (1, ?)", (json.dumps(DEFAULTS),))

    @contextmanager
    def db(self):
        connection = sqlite3.connect(self.database, timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def now(self):
        return datetime.now(self.zone)

    def settings(self):
        with self.db() as db:
            return json.loads(db.execute("SELECT value FROM settings WHERE id=1").fetchone()[0])

    def log(self, kind, status, message, trigger=None, portion=None):
        with self.db() as db:
            db.execute("INSERT INTO events(timestamp,kind,trigger,portion,status,message) VALUES(?,?,?,?,?,?)", (self.now().isoformat(), kind, trigger, portion, status, message))

    def history(self, before=None, limit=15, kind=None):
        with self.db() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("SELECT * FROM events WHERE (? IS NULL OR id < ?) AND (? IS NULL OR kind = ?) ORDER BY id DESC LIMIT ?", (before, before, kind, kind, limit + 1)).fetchall()
        return {"events": [dict(row) for row in rows[:limit]], "has_more": len(rows) > limit}

    def save(self, data):
        if not isinstance(data, dict):
            raise ValueError("Invalid settings.")
        cleaned = copy.deepcopy(DEFAULTS)
        for key in ("automation", "calibrated"):
            if not isinstance(data.get(key), bool):
                raise ValueError("Automation and calibration must be on or off.")
            cleaned[key] = data[key]
        for key, minimum, maximum in (("angle", 45, 180), ("duration", 0.1, 60), ("full_distance", 0, 500), ("empty_distance", 0.1, 500)):
            value = data.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not minimum <= value <= maximum:
                raise ValueError(f"{key.replace('_', ' ').title()} must be between {minimum} and {maximum}.")
            cleaned[key] = value
        if cleaned["full_distance"] >= cleaned["empty_distance"]:
            raise ValueError("Empty distance must be greater than full distance.")
        slots = data.get("slots")
        if not isinstance(slots, list) or len(slots) > 12:
            raise ValueError("Use up to 12 feeding times.")
        ids, times = set(), set()
        cleaned["slots"] = []
        for slot in slots:
            if not isinstance(slot, dict):
                raise ValueError("Invalid feeding time.")
            for key in ("id", "name", "time", "portion"):
                if not isinstance(slot.get(key), str) or not 1 <= len(slot[key].strip()) <= 80:
                    raise ValueError("Every feeding needs a name, time, and portion description.")
            try:
                parsed = datetime.strptime(slot["time"], "%H:%M")
                if parsed.strftime("%H:%M") != slot["time"]:
                    raise ValueError()
            except ValueError:
                raise ValueError("Use a valid feeding time (HH:MM).")
            if slot["id"] in ids or slot["time"] in times:
                raise ValueError("Each feeding must have a unique time and ID.")
            if not isinstance(slot.get("enabled"), bool):
                raise ValueError("Invalid feeding toggle.")
            ids.add(slot["id"])
            times.add(slot["time"])
            cleaned["slots"].append({key: slot[key] for key in ("id", "name", "time", "portion", "enabled")})
        with self.db() as db:
            db.execute("UPDATE settings SET value=? WHERE id=1", (json.dumps(cleaned),))
        self.log("system", "Info", "Schedule and hardware settings saved.")
        return cleaned

    def snapshot(self):
        settings = self.settings()
        now = self.now()
        upcoming = []
        if settings["automation"]:
            for slot in settings["slots"]:
                if slot["enabled"]:
                    hour, minute = map(int, slot["time"].split(":"))
                    at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    if at <= now:
                        at += timedelta(days=1)
                    upcoming.append({**slot, "at": at.isoformat()})
        with self.state_lock:
            state = dict(self.state)
            state["diagnostics"] = copy.deepcopy(self.diagnostics)
        return {**state, "settings": settings, "next": min(upcoming, key=lambda x: x["at"]) if upcoming else None, "timezone": str(self.zone), "angle_supported": bool(self.angle_command), "alerts": self.history(limit=5, kind="system")["events"]}

    @staticmethod
    def acknowledged(response):
        return bool(response and response.strip()) and not any(word in response.upper() for word in ("ERROR", "FAIL", "UNKNOWN", "INVALID", "EMPTY", "UNSUPPORTED"))

    def begin_feed(self, trigger="Manual", portion="Manual portion", settings=None):
        if not self.feed_lock.acquire(blocking=False):
            return False
        settings = settings or self.settings()
        with self.state_lock:
            self.state["operation"] = "Dispensing"
        threading.Thread(target=self.dispense, args=(trigger, portion, settings), daemon=True).start()
        return True

    def dispense(self, trigger, portion, settings):
        started = False
        error = None
        try:
            if self.angle_command:
                response = self.send(self.angle_command.format(angle=settings["angle"]))
                if not self.acknowledged(response):
                    raise RuntimeError("Servo angle was not acknowledged.")
            # Mark before writing so a timed-out acknowledgement still triggers STOP.
            started = True
            response = self.send("SERVO_ROTATE")
            if not self.acknowledged(response):
                raise RuntimeError(response or "Device did not acknowledge dispensing.")
            with self.state_lock:
                self.state["valve"] = "Open (commanded)"
            time.sleep(settings["duration"])
        except Exception as exc:
            error = str(exc)
        finally:
            if started:
                try:
                    closed = self.acknowledged(self.send("SERVO_STOP"))
                except Exception:
                    closed = False
                with self.state_lock:
                    self.state["valve"] = "Closed (commanded)" if closed else "Unknown"
                if not closed:
                    error = "Valve stop not confirmed. Check the feeder." if error is None else error + " Valve stop not confirmed."
            with self.state_lock:
                self.state["operation"] = "Failed" if error else "Completed"
            try:
                self.log("feeding", "Failed" if error else "Successful", error or "Dispense and stop acknowledged by controller; food delivery is not independently measured.", trigger, portion)
            finally:
                self.feed_lock.release()

    def begin_test(self, component):
        if component != "all" and component not in HARDWARE_TESTS:
            raise ValueError("Unknown hardware test.")
        if not self.feed_lock.acquire(blocking=False):
            return False
        selected = list(HARDWARE_TESTS) if component == "all" else [component]
        self.test_cancel.clear()
        with self.state_lock:
            self.diagnostics = {"running": True, "results": {key: {"status": "Queued", "message": "Waiting to test"} for key in selected}, "current": None}
            self.state["operation"] = "Testing hardware"
        threading.Thread(target=self.run_tests, args=(selected,), daemon=True).start()
        return True

    def run_tests(self, selected):
        failed = False
        try:
            for component in selected:
                if self.test_cancel.is_set() or failed:
                    with self.state_lock:
                        self.diagnostics["results"][component] = {"status": "Skipped", "message": "Test sequence stopped."}
                    continue
                command, stop, duration = HARDWARE_TESTS[component]
                with self.state_lock:
                    self.diagnostics["current"] = component
                    self.diagnostics["results"][component] = {"status": "Testing", "message": "Waiting for controller response..."}
                error = None
                response = None
                try:
                    response = self.send(command)
                    if not self.acknowledged(response):
                        raise ValueError(response or "No acknowledgement from controller.")
                    if component == "sensor":
                        if not response.startswith("DISTANCE:"):
                            raise ValueError("Unexpected sensor response: " + response)
                        value = float(response.split(":", 1)[1])
                        if not math.isfinite(value) or value < 0:
                            raise ValueError("Sensor returned no valid echo.")
                        response = f"Distance: {value:.1f} cm"
                    if component == "servo":
                        with self.state_lock:
                            self.state["valve"] = "Open (commanded)"
                    self.test_cancel.wait(duration)
                except Exception as exc:
                    error = str(exc)
                finally:
                    if stop:
                        try:
                            stopped = self.acknowledged(self.send(stop))
                        except Exception:
                            stopped = False
                        if component == "servo":
                            with self.state_lock:
                                self.state["valve"] = "Closed (commanded)" if stopped else "Unknown"
                        if not stopped:
                            error = (error + " " if error else "") + "Stop/off not confirmed. Check the hardware."
                result = {"status": "Failed" if error else "Cancelled" if self.test_cancel.is_set() else "Acknowledged", "message": error or response}
                with self.state_lock:
                    self.diagnostics["results"][component] = result
                failed = bool(error)
                self.log("system", "Warning" if error else "Info", f"Hardware test ({component}): {result['status']}. {result['message']}")
        finally:
            with self.state_lock:
                self.diagnostics["running"] = False
                self.diagnostics["current"] = None
                self.state["operation"] = "Failed" if failed else "Ready"
            self.feed_lock.release()

    def tick(self):
        settings = self.settings()
        now = self.now()
        if settings["automation"]:
            for slot in settings["slots"]:
                if slot["enabled"] and slot["time"] == now.strftime("%H:%M"):
                    key = now.strftime("%Y-%m-%d") + ":" + slot["time"]
                    with self.db() as db:
                        claimed = db.execute("INSERT OR IGNORE INTO executions VALUES(?)", (key,)).rowcount
                    if claimed and not self.begin_feed("Automatic", slot["portion"], settings):
                        self.log("feeding", "Failed", "Skipped because another feeding was in progress.", "Automatic", slot["portion"])
        if self.feed_lock.locked():
            return
        connection = self.connection()
        connected = connection["connected"]
        if connected != self.last_connection:
            self.log("system", "Info" if connected else "Warning", "Arduino connected." if connected else "Arduino disconnected. Check USB and power.")
            self.last_connection = connected
        distance = None
        if connected:
            response = self.send("DISTANCE")
            try:
                if response and response.startswith("DISTANCE:"):
                    value = float(response.split(":", 1)[1])
                    if math.isfinite(value) and value >= 0:
                        distance = value
            except ValueError:
                pass
        level = None
        if distance is not None and settings["calibrated"]:
            level = round(max(0, min(100, 100 * (settings["empty_distance"] - distance) / (settings["empty_distance"] - settings["full_distance"]))))
        if level is not None:
            if level < 20 and not self.low:
                self.log("system", "Warning", f"Low feed: hopper is at {level}%. Refill soon.")
            self.low = level < 20
        with self.state_lock:
            self.state.update({**connection, "distance": distance, "level": level, "updated_at": self.now().isoformat()})
            if not connected:
                self.state["valve"] = "Unknown"

    def start(self):
        if self.worker and self.worker.is_alive():
            return
        def run():
            while True:
                try:
                    self.tick()
                except Exception:
                    # Keep monitoring alive after transient serial/database errors.
                    with self.state_lock:
                        self.state.update(connected=False, distance=None, level=None, valve="Unknown")
                time.sleep(2)
        self.worker = threading.Thread(target=run, daemon=True)
        self.worker.start()


def setup_aquafeed(app, send, connection):
    from pages import dashboard, control, history, hardware

    database = os.getenv("AQUAFEED_DB", str(Path(app.root_path) / "aquafeed.sqlite3"))
    feeder = Feeder(send, connection, database)
    for page in (dashboard, control, history, hardware):
        app.register_blueprint(page.create_blueprint(feeder))
    return feeder
