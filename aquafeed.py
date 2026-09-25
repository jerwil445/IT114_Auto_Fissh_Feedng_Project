"""Persistent schedules, feeding execution, and observed hardware telemetry."""
import copy
import json
import math
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from database import Database
from serial_protocol import EMPTY_DISTANCE_CM, feed_percentage, parse_distance



DEFAULTS = {
    "automation": False,
    "angle": 90,
    "duration": 3,
    "full_distance": 3,
    "empty_distance": EMPTY_DISTANCE_CM,
    "calibrated": True,
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
        self.raw_send = send
        self.alarm_lock = threading.RLock()
        self.alarm_active = False
        self.alarm_confirmed = None
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
        self.calibration_sent = None
        self.calibration_sent_at = 0
        self.low = False
        self.empty = False
        self.lcd_idle_command = None
        self.lcd_idle_sent = 0
        self.lcd_idle_error = False
        self.test_cancel = threading.Event()
        self.diagnostics = {"running": False, "results": {}, "current": None}
        self.store = Database(self.database)
        self.store.initialize(DEFAULTS)

    def db(self):
        return self.store.connect()

    def now(self):
        return datetime.now(self.zone)

    def settings(self):
        with self.db() as db:
            settings = json.loads(db.execute("SELECT value FROM settings WHERE id=1").fetchone()['value'])
        settings.setdefault("empty_distance", EMPTY_DISTANCE_CM)
        settings["calibrated"] = True
        if not 0 <= settings["full_distance"] < settings["empty_distance"]:
            settings["full_distance"] = DEFAULTS["full_distance"]
        return settings

    def log(self, kind, status, message, trigger=None, portion=None):
        with self.db() as db:
            db.execute("INSERT INTO events(timestamp,kind,trigger,portion,status,message) VALUES(?,?,?,?,?,?)", (self.now().isoformat(), kind, trigger, portion, status, message))

    def history(self, before=None, limit=15, kind=None):
        with self.db() as db:
            rows = db.execute("SELECT * FROM events WHERE (CAST(? AS BIGINT) IS NULL OR id < ?) AND (CAST(? AS TEXT) IS NULL OR kind = ?) ORDER BY id DESC LIMIT ?", (before, before, kind, kind, limit + 1)).fetchall()
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
        cleaned["calibrated"] = True
        slots = data.get("slots")
        if not isinstance(slots, list) or len(slots) > 12:
            raise ValueError("Use up to 12 feeding times.")
        current = self.settings()
        current_slots_by_id = {s.get("id"): s for s in current.get("slots", []) if isinstance(s, dict)}
        current_slots_by_name = {s.get("name"): s for s in current.get("slots", []) if isinstance(s, dict)}
        rescheduled_slot_ids = set()
        rescheduled_new_times = set()
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
            old_slot = current_slots_by_id.get(slot["id"])
            if old_slot is None:
                old_slot = current_slots_by_name.get(slot["name"])
            if old_slot and old_slot.get("time") != slot["time"]:
                rescheduled_slot_ids.add(slot["id"])
                if old_slot.get("id"):
                    rescheduled_slot_ids.add(old_slot["id"])
                rescheduled_new_times.add(slot["time"])

        today = self.now().strftime("%Y-%m-%d")
        with self.db() as db:
            db.execute("UPDATE settings SET value=? WHERE id=1", (json.dumps(cleaned),))
            for slot_id in rescheduled_slot_ids:
                db.execute("DELETE FROM executions WHERE key = ? OR key LIKE ?", (f"completed:{today}:{slot_id}", f"completed:%:{slot_id}"))
            for new_time in rescheduled_new_times:
                db.execute("DELETE FROM executions WHERE key = ?", (f"{today}:{new_time}",))
        self.log("system", "Info", "Schedule and hardware settings saved.")
        return cleaned

    def snapshot(self):
        settings = self.settings()
        now = self.now()
        prefix = 'completed:' + now.strftime('%Y-%m-%d') + ':'
        with self.db() as db:
            completed = {row['key'][len(prefix):] for row in db.execute('SELECT key FROM executions WHERE key LIKE ?', (prefix + '%',)).fetchall()}
        for slot in settings['slots']:
            slot['completed_today'] = slot['id'] in completed
            if slot['completed_today']:
                slot['status'] = 'Completed'
            elif not settings['automation'] or not slot['enabled']:
                slot['status'] = 'Paused'
            else:
                slot['status'] = 'Automatic'
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

    def lcd_message(self, command):
        try:
            response = self.send(command)
            if not response:
                response = self.send(command)
            return response == 'LCD_OK'
        except Exception:
            return False

    @staticmethod
    def lcd_label(name):
        return ''.join(c for c in name.upper() if c.isascii() and (c.isalnum() or c == ' '))[:10] or 'FEED'

    def idle_lcd_command(self):
        data = self.snapshot()
        upcoming = data['next']
        if not upcoming:
            return 'LCD_IDLE:FEEDER READY|AUTO PAUSED' if not data['settings']['automation'] else 'LCD_IDLE:FEEDER READY|NO SCHEDULE'
        at = datetime.fromisoformat(upcoming['at'])
        clock = at.strftime('%I:%M %p')
        enabled = [slot for slot in data['settings']['slots'] if slot['enabled']]
        if enabled and all(slot['completed_today'] for slot in enabled):
            return 'LCD_IDLE:ALL FEEDS DONE|NEXT: TOM ' + clock.replace(' ', '')
        label = self.lcd_label(upcoming['name'])
        tomorrow = at.date() > self.now().date()
        return f"LCD_IDLE:NEXT: {label}|{'TOM ' if tomorrow else 'AT '}{clock}"

    def apply_alarm(self, distance):
        """Reassert empty warnings; only a valid refill reading clears them."""
        with self.alarm_lock:
            if distance is not None:
                empty = distance >= self.settings()["empty_distance"]
            else:
                empty = self.alarm_active
            if empty:
                commands = ("RED_ON", "BUZZER_ON")
            elif self.alarm_active:
                commands = ("RED_OFF", "BUZZER_OFF")
            else:
                return
            confirmed = True
            for command in commands:
                try:
                    confirmed = self.acknowledged(self.raw_send(command)) and confirmed
                except Exception:
                    confirmed = False
            # Retry unconfirmed alarm clear on the next valid reading.
            self.alarm_active = empty or not confirmed
            self.alarm_confirmed = confirmed

    def send(self, command):
        with self.alarm_lock:
            if command in ("RED_OFF", "BUZZER_OFF", "ALL_LED_OFF", "LCD_TEST"):
                distance = parse_distance(self.raw_send("DISTANCE"))
                self.apply_alarm(distance)
                if distance is None or distance >= self.settings()["empty_distance"] or self.alarm_active:
                    if command == "ALL_LED_OFF":
                        for led in ("MORNING_OFF", "AFTERNOON_OFF", "NIGHT_OFF"):
                            self.raw_send(led)
                    return "ALARM_PROTECTED"
            response = self.raw_send(command)
            if command == 'LCD_TEST':
                self.lcd_idle_command = None
            if command == "DISTANCE":
                self.apply_alarm(parse_distance(response))
            return response

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
        slot = settings.get('_feeding_slot')
        if slot:
            self.lcd_message('LCD_ACTIVE:' + self.lcd_label(slot['name']))
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
                if slot:
                    if not error:
                        with self.db() as db:
                            db.execute('INSERT INTO executions(key) VALUES(?) ON CONFLICT (key) DO NOTHING', (f"completed:{settings['_feeding_day']}:{slot['id']}",))
                    command = ('LCD_DONE:' if not error else 'LCD_FAIL:') + self.lcd_label(slot['name'])
                    if not self.lcd_message(command):
                        self.log('system', 'Warning', 'LCD update was not confirmed. Upload the current arduino_code.c++ sketch; feeding was not retried.')
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
                cleanup_response = None
                try:
                    response = self.send(command)
                    if not self.acknowledged(response):
                        raise ValueError(response or "No acknowledgement from controller.")
                    if component == "sensor":
                        if not response.startswith("DISTANCE:"):
                            raise ValueError("Unexpected sensor response: " + response)
                        value = parse_distance(response)
                        if value is None:
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
                            cleanup_response = self.send(stop)
                            stopped = self.acknowledged(cleanup_response)
                        except Exception:
                            stopped = False
                        if component == "servo":
                            with self.state_lock:
                                self.state["valve"] = "Closed (commanded)" if stopped else "Unknown"
                        if not stopped:
                            error = (error + " " if error else "") + "Stop/off not confirmed. Check the hardware."
                protected = "ALARM_PROTECTED" in (response, cleanup_response)
                result = {"status": "Failed" if error else "Cancelled" if self.test_cancel.is_set() else "Protected" if protected else "Acknowledged", "message": error or ("Automatic warning preserved; refill the hopper before testing alarm outputs or LCD." if protected else response)}
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
                        claimed = db.execute("INSERT INTO executions VALUES(?) ON CONFLICT (key) DO NOTHING", (key,)).rowcount
                    feeding_settings = {**settings, '_feeding_slot': dict(slot), '_feeding_day': now.strftime('%Y-%m-%d')}
                    if claimed and not self.begin_feed("Automatic", slot["portion"], feeding_settings):
                        self.log("feeding", "Failed", "Skipped because another feeding was in progress.", "Automatic", slot["portion"])
        connection = self.connection()
        connected = connection["connected"]
        if connected != self.last_connection:
            self.log("system", "Info" if connected else "Warning", "Arduino connected." if connected else "Arduino disconnected. Check USB and power.")
            self.last_connection = connected
        distance = None
        calibration = (settings['full_distance'], settings['empty_distance'])
        if not connected:
            self.calibration_sent = None
            with self.state_lock:
                self.state['calibration_synced'] = False
        if connected:
            if calibration != self.calibration_sent or time.monotonic() - self.calibration_sent_at >= 30:
                reply = self.send(f"CALIBRATE:{calibration[0]:g},{calibration[1]:g}")
                self.calibration_sent = calibration
                self.calibration_sent_at = time.monotonic()
                with self.state_lock:
                    self.state['calibration_synced'] = reply == 'CALIBRATION_OK'
            response = self.send("DISTANCE")
            distance = parse_distance(response)
        level = feed_percentage(distance, settings["full_distance"], settings["empty_distance"])
        empty = distance >= self.settings()["empty_distance"] if distance is not None else None
        if level is not None:
            if empty and not self.empty:
                self.log("system", "Warning", f"FEED EMPTY — PLEASE REFILL. Hopper distance is {settings['empty_distance']:g} cm or more.")
            elif not empty and self.empty:
                self.log("system", "Info", f"Hopper refilled. Feed level is {level:g}%.")
            elif level < 20 and not self.low:
                self.log("system", "Warning", f"Low feed: hopper is at {level}%. Refill soon.")
            self.low = level < 20
            self.empty = empty
        with self.state_lock:
            self.state.update({**connection, "distance": distance, "level": level, "hopper_empty": empty, "alarm_active": self.alarm_active, "alarm_confirmed": self.alarm_confirmed if connected else None, "updated_at": self.now().isoformat()})
            if not connected:
                self.lcd_idle_command = None
                self.state["valve"] = "Unknown"
        if connected and not self.feed_lock.locked():
            command = self.idle_lcd_command()
            if command != self.lcd_idle_command or time.monotonic() - self.lcd_idle_sent >= 10:
                confirmed = self.lcd_message(command)
                with self.state_lock:
                    self.state['lcd_schedule_confirmed'] = confirmed
                if not confirmed and not self.lcd_idle_error:
                    self.log('system', 'Warning', 'Next-feeding LCD screen was not acknowledged. Upload the current arduino_code.c++ sketch and restart Python; LCD_TEST alone does not display the schedule.')
                self.lcd_idle_error = not confirmed
                self.lcd_idle_command = command
                self.lcd_idle_sent = time.monotonic()

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
                        self.state.update(connected=False, distance=None, level=None, hopper_empty=None, valve="Unknown")
                time.sleep(0.5)
        self.worker = threading.Thread(target=run, daemon=True)
        self.worker.start()


def setup_aquafeed(app, send, connection):
    from pages import dashboard, control, history, hardware

    database = os.getenv("AQUAFEED_DB") or os.getenv("DATABASE_URL", "postgresql://postgres@localhost:5432/aquafeed")
    feeder = Feeder(send, connection, database)
    for page in (dashboard, control, history, hardware):
        app.register_blueprint(page.create_blueprint(feeder))
    return feeder
