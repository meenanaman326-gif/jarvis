FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg git libglib2.0-0 libgl1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN pip install --no-cache-dir "fastapi>=0.115,<1" "uvicorn>=0.30,<1" "python-multipart>=0.0.9" "numpy>=1.26,<3" "opencv-python-headless>=4.9,<5" "pillow>=10.3,<12"
RUN git clone https://github.com/Vibha-Ramprakash/claude-video-effects.git /app/engine && cd /app/engine && git checkout 60840acc7e126a5e34068276a23e912ec4c8c34c
COPY . /app/
RUN python /app/patch_engine.py
EXPOSE 10000
CMD ["sh","-c","uvicorn server:app --host 0.0.0.0 --port ${PORT:-10000}"]
