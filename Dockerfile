FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --upgrade pip && \
    python -m pip install -r requirements.txt

COPY . .

RUN useradd --uid 10001 --create-home aquafeed && \
    mkdir -p /app/instance && \
    chown -R aquafeed:aquafeed /app
USER aquafeed

EXPOSE 5000

# One process runs both Flask and the feeder scheduler.
CMD ["python", "app.py"]
