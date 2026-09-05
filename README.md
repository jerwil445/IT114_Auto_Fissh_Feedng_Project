# AquaFeed Pro

Run `python -m pip install -r requirements.txt`, then `python app.py` and open http://127.0.0.1:5000.

- `/`: monitoring dashboard, upcoming feeding, hopper capacity, distance, valve command state, and alerts.
- `/control`: manual feeding, saved automation schedule, duration, angle preference, and hopper calibration.
- `/history`: persisted feeding and system events, filters, pagination, and a supply checklist.
- `/hardware-test`: individual component tests, Test All Hardware, live results, and cancellation. Tests send off/stop commands on the server and record results in history. A failed test stops the sequence. The servo test may dispense food. Feeding and diagnostics cannot run simultaneously; scheduled attempts during diagnostics are skipped and logged.

Settings and logs are stored in `aquafeed.sqlite3`. Automation defaults to off. Save settings to apply edits. Run one Flask process and keep it running for automatic feeding. Times default to Asia/Manila; `FEEDER_TIMEZONE` can select another IANA timezone with `tzdata` installed. Missed feeding times are not replayed. Scheduled attempts are recorded before dispatch to prevent repeated feeding during the same minute, including after restart.

The existing serial interface supports `SERVO_ROTATE`, `SERVO_STOP`, and `DISTANCE`. Feeding sends rotate, waits the saved duration, and sends stop, including when the start acknowledgement is missing. An empty or error response is a failed attempt. A successful event means the controller acknowledged the commands; it does not prove that food was delivered. Valve state reflects commands, not a physical position sensor.

Servo angle is stored but cannot be applied through the existing rotate/stop interface. If your firmware supports an angle-setting command, set `SERVO_ANGLE_COMMAND` to that exact command with an `{angle}` placeholder. Confirm the firmware protocol before enabling this option. Portion names describe feedings; the app does not select separate flake or pellet dispensers.

Measure full and empty hopper sensor distances in Feeder Control and enable calibration to show estimated capacity and warnings below 20%. No invented sensor measurements or historical feeding events are shown. Wi-Fi, firmware updates, component wiring, and dispenser-empty diagnostics require additional firmware telemetry. Supply ordering currently provides a checklist; no vendor or checkout is configured.

Set `ARDUINO_PORT` / `ARDUINO_PORTS` for serial ports, or `AQUAFEED_DB` for a different database location. The interface uses local fallback fonts and does not require a remote font stylesheet.

## Page files

| Page | HTML | CSS | JavaScript | Python routes |
| --- | --- | --- | --- | --- |
| Dashboard | `templates/dashboard.html` | `static/css/dashboard.css` | `static/js/dashboard.js` | `pages/dashboard.py` |
| Feeder Control | `templates/control.html` | `static/css/control.css` | `static/js/control.js` | `pages/control.py` |
| Feeding History | `templates/history.html` | `static/css/history.css` | `static/js/history.js` | `pages/history.py` |
| Hardware Tests | `templates/hardware.html` | `static/css/hardware.css` | `static/js/hardware.js` | `pages/hardware.py` |

`templates/base.html` supplies navigation and the shared layout. `static/css/common.css` supplies shared styles; `static/js/common.js` supplies API helpers and connection polling. Each page script handles its own rendering and controls through `onMonitor` and `onMonitorError` callbacks. `aquafeed.py` contains the shared hardware, scheduler, and persistence service. `app.py` remains the application entry point and serial connection module. Python page modules are Flask blueprints registered by the shared setup function; run the app with `python app.py` as before.

Validation: `python -m unittest -v test_aquafeed` and `node --check` for each file in `static/js/`. Tests use simulated hardware and temporary databases.
