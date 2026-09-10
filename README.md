# AquaFeed Pro

Run `python -m pip install -r requirements.txt`, then `python app.py` and open http://127.0.0.1:5000.

- `/`: monitoring dashboard, upcoming feeding, hopper capacity, distance, valve command state, and alerts.
- `/control`: manual feeding, saved automation schedule, duration, angle preference, and hopper calibration.
- `/history`: persisted feeding and system events, filters, pagination, and a supply checklist.
- `/hardware-test`: individual component tests, Test All Hardware, live results, and cancellation. Tests send off/stop commands on the server and record results in history. A failed test stops the sequence. The servo test may dispense food. Feeding and diagnostics cannot run simultaneously; scheduled attempts during diagnostics are skipped and logged.

Settings and logs are stored in PostgreSQL. The default connection is `postgresql://postgres@localhost:5432/aquafeed`; set `DATABASE_URL` to use your own database and user. Your existing `aquafeed.sqlite3` is preserved for import. Automation defaults to off. Save settings to apply edits. Run one Flask process and keep it running for automatic feeding. Times default to Asia/Manila; `FEEDER_TIMEZONE` can select another IANA timezone with `tzdata` installed. Missed feeding times are not replayed. Scheduled attempts are recorded before dispatch to prevent repeated feeding during the same minute, including after restart.

The existing serial interface supports `SERVO_ROTATE`, `SERVO_STOP`, and `DISTANCE`. Feeding sends rotate, waits the saved duration, and sends stop, including when the start acknowledgement is missing. An empty or error response is a failed attempt. A successful event means the controller acknowledged the commands; it does not prove that food was delivered. Valve state reflects commands, not a physical position sensor.

Servo angle is stored but cannot be applied through the existing rotate/stop interface. If your firmware supports an angle-setting command, set `SERVO_ANGLE_COMMAND` to that exact command with an `{angle}` placeholder. Confirm the firmware protocol before enabling this option. Portion names describe feedings; the app does not select separate flake or pellet dispensers.

Hopper capacity uses `clamp((20 - distance) / (20 - full_distance) * 100, 0, 100)`, displayed to one decimal place. The empty threshold is fixed at 20 cm, including previously saved configurations. Full distance defaults to 3 cm to match the supplied Arduino sketch; set it to the measured full distance in both Feeder Control and the Arduino IDE. The gauge is enabled automatically, and invalid sensor readings display as unavailable. Distance responses with or without a CM suffix are supported; unsolicited feed telemetry is skipped while waiting for other command replies.

Automatic warnings have priority over diagnostics. Python monitors every 500 ms (plus serial response time), including during feeding and tests, and reasserts RED_ON/BUZZER_ON at distances of 20 cm or more. Before RED_OFF, BUZZER_OFF, ALL_LED_OFF, or LCD_TEST, it obtains a fresh distance. Empty or invalid readings protect alarm outputs and the LCD; ALL_LED_OFF still turns off the three feeding indicators. Valid refill readings clear the alarm, with retries if commands are unacknowledged. Invalid readings never clear an active warning. The dashboard distinguishes alarm acknowledgement from unconfirmed commands.

Immediate device-local detection, exact LCD text, and immunity to off commands from any serial client require the alarm-priority firmware changes supplied in the conversation. Python cannot change LCD text through the existing LCD_TEST-only protocol or upload the sketch. Apply those changes in Arduino IDE; no C++ file is maintained here.

Set `ARDUINO_PORT` / `ARDUINO_PORTS` for serial ports, and `DATABASE_URL` for the PostgreSQL connection. `AQUAFEED_DB` is an explicit legacy SQLite/test override; unset it when using PostgreSQL. The interface uses local fallback fonts and does not require a remote font stylesheet.

## Page files

| Page | HTML | CSS | JavaScript | Python routes |
| --- | --- | --- | --- | --- |
| Dashboard | `templates/dashboard.html` | `static/css/dashboard.css` | `static/js/dashboard.js` | `pages/dashboard.py` |
| Feeder Control | `templates/control.html` | `static/css/control.css` | `static/js/control.js` | `pages/control.py` |
| Feeding History | `templates/history.html` | `static/css/history.css` | `static/js/history.js` | `pages/history.py` |
| Hardware Tests | `templates/hardware.html` | `static/css/hardware.css` | `static/js/hardware.js` | `pages/hardware.py` |

`templates/base.html` supplies navigation and the shared layout. `static/css/common.css` supplies shared styles; `static/js/common.js` supplies API helpers and connection polling. Each page script handles its own rendering and controls through `onMonitor` and `onMonitorError` callbacks. `aquafeed.py` contains the shared hardware, scheduler, and persistence service. `app.py` remains the application entry point and serial connection module. Python page modules are Flask blueprints registered by the shared setup function; run the app with `python app.py` as before.

Validation: `python -m unittest -v test_aquafeed` and `node --check` for each file in `static/js/`. Tests use simulated hardware and temporary databases.


## PostgreSQL setup (Windows)

1. Install the updated dependencies: `python -m pip install -r requirements.txt`.
2. Configure PostgreSQL authentication locally. For the default account, create `%APPDATA%\postgresql\pgpass.conf` with `localhost:5432:*:postgres:YOUR_PASSWORD` (replace the placeholder with your real password). Do not commit this file or credentials to the project.
3. If using a different database/user, set `$env:DATABASE_URL = 'postgresql://YOUR_USER@localhost:5432/aquafeed'` in PowerShell and update the matching pgpass entry.
4. Stop the Flask app before importing existing data. Run `python setup_database.py --create --import-sqlite aquafeed.sqlite3`. To start with an empty database, run `python setup_database.py --create` instead. Database creation requires a PostgreSQL role with CREATEDB permission; otherwise create the database with your administrator and omit `--create`.
5. Start the app with `python app.py`.

`schema.sql` defines the PostgreSQL tables. The importer preserves event IDs and execution records, resets the event ID sequence, refuses populated targets, and never modifies the SQLite source. `timestamp` remains ISO 8601 text (including timezone) and settings remain JSON text so the existing API responses are unchanged. The schema is initialized automatically but the PostgreSQL database itself must already exist when the web app starts.


LCD schedule screens: copy arduino_code.c++ into Arduino IDE and upload. Python sends the next enabled feeding and time, dispensing state, and successful completion state. Arduino displays completion for 5 seconds without blocking sensor monitoring, then returns to the next schedule. After all enabled slots succeed, it displays ALL FEEDS DONE and tomorrow's first time. Completion markers are date-scoped, so they reset at local midnight without deleting history. Keep Python running for schedule updates. Empty-hopper and sensor alerts override schedule screens. LCD communication failures do not retry feeding.
