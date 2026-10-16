# AquaFeed Docker setup

These files run this Flask project with Python 3.11 and PostgreSQL 17. The Dockerfile installs requirements.txt and runs `python app.py`, so the existing feeder scheduler starts too. Compose waits until PostgreSQL is healthy before starting the app. Keep one web container; multiple instances would run multiple feeder schedulers.

## 1. Prepare

Open Docker Desktop and wait until its engine is running. Use Linux containers. Open PowerShell in the project folder:

```powershell
cd C:\Users\Jerwil\OneDrive\Documents\IT114_0.2
Copy-Item .env.docker.example .env.docker
notepad .env.docker
```

Replace `replace_with_your_database_password` with your chosen password and save. This config creates a separate PostgreSQL database named `aquafeed`, with username `aquafeed`. It does not import your existing local PostgreSQL settings or feeding history. Port 5433 avoids conflicting with the local PostgreSQL server on 5432. Passwords are supplied separately from the connection URL, so they do not require URL encoding.

## 2. Recommended on Windows with Arduino COM4

Docker Desktop does not directly pass a Windows COM4 device into a Linux container. Run just PostgreSQL in Docker, and Python on Windows for real hardware:

```powershell
docker compose --env-file .env.docker up -d db
python -m pip install -r requirements.txt
$env:DATABASE_URL = "postgresql://aquafeed@localhost:5433/aquafeed"
$env:AQUAFEED_DB = $env:DATABASE_URL
$dockerCredential = Get-Credential -UserName aquafeed -Message "Enter the password you saved in .env.docker"
$env:PGPASSWORD = $dockerCredential.GetNetworkCredential().Password
$env:ARDUINO_PORT = "COM4"
$env:ARDUINO_PORTS = "COM4"
python app.py
```

Close Arduino Serial Monitor/Plotter before starting Python. Open http://localhost:5000 or your computer's LAN address with port 5000. These environment variables affect this terminal session only. If you changed DB_PORT in .env.docker, use that port in DATABASE_URL too.

## 3. Run both website and database in Docker

Stop the Windows Python server first (Ctrl+C) to free port 5000:

```powershell
docker compose --env-file .env.docker up -d --build
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker logs -f web
```

Open http://localhost:5000. On Windows, without separate USB forwarding, the dashboard opens but the Arduino is disconnected and hardware controls cannot operate. Setting ARDUINO_PORT to COM4 inside this Linux container does not grant USB access.

The web container uses `db:5432`, not localhost:5433, to reach the Compose database. Tables are created by the Python app at startup. The app_instance volume persists the session key if account support is enabled in your current version.

## 4. Native Linux with an Arduino

Use the optional override only when the serial device actually exists on the Linux Docker host. Find its group number:

```sh
stat -c '%g' /dev/ttyACM0
```

Add the values to .env.docker (use /dev/ttyUSB0 instead if that is your device):

```ini
ARDUINO_DEVICE=/dev/ttyACM0
ARDUINO_GID=20
```

Use the group number returned by stat, then run:

```sh
docker compose --env-file .env.docker -f compose.yaml -f compose.linux.yaml up -d --build
```

For Docker Desktop USB forwarding, follow its platform-specific USB/IP documentation first: https://docs.docker.com/desktop/features/usbip/

## 5. Common commands

```powershell
# Validate configuration without starting containers:
docker compose --env-file .env.docker config --quiet

# Rebuild after code changes:
docker compose --env-file .env.docker up -d --build web

# Stop the stack (database data remains in its named volume):
docker compose --env-file .env.docker down

# Stop only the containerized website when switching to Windows Python:
docker compose --env-file .env.docker stop web
```

If port 5000 is occupied, stop the other server or change WEB_PORT in .env.docker and visit the new port. Database credentials are initialized only when the postgres_data volume is first created; editing the password in .env.docker later does not change an existing PostgreSQL user's password. Avoid `down -v` unless you intend to delete the Docker database.
