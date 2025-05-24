# Dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir flask yt-dlp waitress

ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["python", "main.py"]