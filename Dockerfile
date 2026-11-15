FROM node:22-slim AS node_runtime
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=10000
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core ca-certificates libstdc++6 && rm -rf /var/lib/apt/lists/*
COPY --from=node_runtime /usr/local/bin/node /usr/local/bin/node
WORKDIR /app
COPY clipforge/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && node --version && yt-dlp --version
COPY clipforge/ ./
CMD ["gunicorn","--bind","0.0.0.0:10000","--workers","1","--threads","4","--timeout","900","app:app"]
