FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=10000
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY clipforge/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY clipforge/ ./
CMD ["gunicorn","--bind","0.0.0.0:10000","--workers","1","--threads","4","--timeout","900","app:app"]
