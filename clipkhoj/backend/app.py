"""ClipKhoj Auto Highlights: uploaded video -> ranked vertical short clips.
Scores audio energy + visual motion/scene changes. Does not download YouTube/Instagram.
"""
from __future__ import annotations
import math
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

APP_ROOT = Path(tempfile.gettempdir()) / "clipkhoj_jobs"
APP_ROOT.mkdir(parents=True, exist_ok=True)
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
MAX_BYTES = 125 * 1024 * 1024
MAX_DURATION = 900
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()
RUN_LOCK = threading.Lock()
VALID_EXT = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}
app = FastAPI(title="ClipKhoj Auto Highlights", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://clipkhoj-video-finder-v2.onrender.com",
        "https://clipkhoj-mobile.onrender.com",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def ffmpeg(*args: str, timeout: int = 90, capture: bool = False):
    cmd = [FFMPEG, "-hide_banner", "-nostdin", "-loglevel", "error", *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def duration_of(path: Path) -> float:
    p = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path)],
                       capture_output=True, timeout=15, check=False)
    stderr = p.stderr.decode("utf-8", "ignore")
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", stderr)
    if not match:
        raise ValueError("Video duration read nahi ho paaya; supported MP4/MOV/WebM upload karo.")
    hh, mm, sec = match.groups()
    return int(hh) * 3600 + int(mm) * 60 + float(sec)


def pick_highlights(path: Path, duration: float, length: int, count: int) -> list[tuple[float, float, float]]:
    # Signal analysis: low-res frames every 2s + mono audio at 8kHz.
    limit = min(duration, MAX_DURATION)
    p = ffmpeg("-i", str(path), "-t", str(limit), "-an",
               "-vf", "fps=1/2,scale=96:54,format=gray",
               "-f", "rawvideo", "-", timeout=130, capture=True)
    if p.returncode != 0 and not p.stdout:
        raise ValueError("Video frames extract nahi ho paaye.")
    size = 96 * 54
    n = len(p.stdout) // size
    visual = np.frombuffer(p.stdout[:n * size], dtype=np.uint8)
    frame_scores = np.zeros(max(1, n), dtype=float)
    if n > 1:
        frames = visual.reshape(n, size).astype(np.int16)
        frame_scores[1:] = np.mean(np.abs(np.diff(frames, axis=0)), axis=1) / 255
    frame_scores = np.clip(frame_scores, 0, .6) / .6

    a = ffmpeg("-i", str(path), "-t", str(limit), "-vn", "-ac", "1",
               "-ar", "8000", "-f", "s16le", "-", timeout=120, capture=True)
    audio_raw = np.frombuffer(a.stdout, dtype=np.int16).astype(np.float32) / 32768 if a.stdout else np.zeros(1, dtype=np.float32)
    audio_step = 16000
    audio_scores = []
    for start in range(0, len(audio_raw), audio_step):
        chunk = audio_raw[start:start + audio_step]
        if not len(chunk):
            break
        audio_scores.append(float(np.sqrt(np.mean(chunk * chunk))))
    audio_scores = np.array(audio_scores if audio_scores else [0.], dtype=float)
    if audio_scores.max() > 0:
        audio_scores = np.minimum(1., audio_scores / max(float(np.percentile(audio_scores, 90)), .003))

    length = min(length, int(duration))
    if length <= 0:
        raise ValueError("Video clip ke liye bahut chhota hai.")
    max_start = max(0., duration - length)
    starts = [round(v, 2) for v in np.arange(0, max_start + .1, max(3, length // 5))]
    if not starts or starts[-1] != round(max_start, 2):
        starts.append(round(max_start, 2))

    scored = []
    for start in starts:
        i = max(0, int(start // 2))
        j = max(i + 1, min(n, int(math.ceil((start + length) / 2))))
        frames = frame_scores[i:j]
        snd = audio_scores[i:max(i + 1, min(len(audio_scores), j))]
        # Loud/exciting moments + fast scene changes; small tie break to vary selection.
        motion = float(np.mean(frames)) if frames.size else 0.
        peaks = float(np.mean(frames > .26)) if frames.size else 0.
        loud = float(np.mean(snd)) if snd.size else 0.
        varied = float(np.std(snd)) if snd.size else 0.
        score = (.50 * loud + .32 * motion + .12 * peaks + .06 * varied)
        scored.append((score, start))
    scored.sort(reverse=True)
    chosen = []
    for score, start in scored:
        if all(abs(start - prev[1]) >= length * .83 for prev in chosen):
            chosen.append((score, start))
            if len(chosen) >= count:
                break
    if not chosen:
        chosen = [(0., 0.)]
    return [(start, float(length), round(score, 4)) for score, start in chosen]


def cleanup_old():
    now = time.time()
    with JOBS_LOCK:
        for jobid, item in list(JOBS.items()):
            if item["state"] not in {"queued", "working"} and now - item["created"] > 2700:
                JOBS.pop(jobid, None)
                shutil.rmtree(APP_ROOT / jobid, ignore_errors=True)


def set_state(jobid: str, **update):
    with JOBS_LOCK:
        if jobid in JOBS:
            JOBS[jobid].update(update)


def render_job(jobid: str, path: Path, length: int, count: int):
    with RUN_LOCK:
        try:
            set_state(jobid, state="working", message="Video analyze ho raha hai...")
            duration = duration_of(path)
            if duration < 6 or duration > MAX_DURATION:
                raise ValueError("Supported video duration: 6 seconds se 15 minutes.")
            picks = pick_highlights(path, duration, length, count)
            clips = []
            for k, (start, sec, score) in enumerate(picks, 1):
                set_state(jobid, message=f"Short {k}/{len(picks)} export ho raha hai...")
                name = f"highlight_{k}.mp4"
                output = APP_ROOT / jobid / name
                # Vertical 9:16, fit entire original in frame without cutting subjects.
                filt = ("[0:v]scale=480:854:force_original_aspect_ratio=increase,"
                        "crop=480:854,boxblur=16:2[bg];"
                        "[0:v]scale=480:854:force_original_aspect_ratio=decrease[fg];"
                        "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,format=yuv420p")
                cmd = [
                    "-ss", str(start), "-i", str(path), "-t", str(sec),
                    "-filter_complex", filt,
                    "-map", "[vout]",  # replaced below by named output
                ]
                filt = filt.replace("format=yuv420p", "format=yuv420p[vout]")
                cmd = [
                    "-ss", str(start), "-i", str(path), "-t", str(sec),
                    "-filter_complex", filt, "-map", "[vout]", "-map", "0:a:0?",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "29",
                    "-r", "24", "-threads", "2", "-c:a", "aac", "-b:a", "96k",
                    "-movflags", "+faststart", "-y", str(output),
                ]
                run = ffmpeg(*cmd, timeout=210)
                if run.returncode != 0 or not output.exists() or output.stat().st_size < 1000:
                    raise RuntimeError("Video export fail hua; shorter MP4 try karo.")
                clips.append({
                    "name": name,
                    "start_second": round(start, 1),
                    "length_second": round(sec, 1),
                    "activity_score": score,
                    "download": f"/api/download/{jobid}/{name}",
                })
            set_state(jobid, state="done", clips=clips, message="Shorts ready!")
        except Exception as e:
            set_state(jobid, state="error", message=str(e)[:180])
        finally:
            path.unlink(missing_ok=True)
            cleanup_old()


@app.get("/api/health")
def health():
    return {"ok": True, "feature": "automated scene+audio highlight ranking",
            "supported": "User-uploaded videos only; no platform video downloading"}


@app.post("/api/clips")
async def create_clips(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    seconds: int = Form(20),
    count: int = Form(3),
    rights: bool = Form(False),
):
    if not rights:
        raise HTTPException(400, "Upload only your own or explicitly licensed videos.")
    if seconds not in {15, 20, 30} or count not in {1, 2, 3}:
        raise HTTPException(400, "Choose supported clip settings.")
    suffix = Path(video.filename or "").suffix.lower()
    if suffix not in VALID_EXT:
        raise HTTPException(400, "Upload MP4, MOV, MKV, WebM or M4V.")
    cleanup_old()
    with JOBS_LOCK:
        active = sum(v["state"] in {"queued", "working"} for v in JOBS.values())
    if active >= 2:
        raise HTTPException(429, "Server busy hai. Thodi der baad try karo.")
    jobid = str(uuid.uuid4())
    directory = APP_ROOT / jobid
    directory.mkdir()
    path = directory / f"source{suffix}"
    size = 0
    try:
        with path.open("wb") as output:
            while chunk := await video.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, "Max video size 125 MB hai.")
                output.write(chunk)
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    finally:
        await video.close()
    if size < 1024:
        shutil.rmtree(directory, ignore_errors=True)
        raise HTTPException(400, "Video file empty hai.")
    with JOBS_LOCK:
        JOBS[jobid] = {"created": time.time(), "state": "queued",
                       "message": "Queue mein hai...", "clips": []}
    background_tasks.add_task(render_job, jobid, path, seconds, count)
    return {"job_id": jobid, "state": "queued"}


@app.get("/api/status/{jobid}")
def status(jobid: str):
    if not re.fullmatch(r"[0-9a-f-]{36}", jobid):
        raise HTTPException(404, "Not found")
    with JOBS_LOCK:
        item = JOBS.get(jobid)
        if not item:
            raise HTTPException(404, "Job expired. Please upload again.")
        return {key: value for key, value in item.items() if key != "created"}


@app.get("/api/download/{jobid}/{filename}")
def download(jobid: str, filename: str):
    if not re.fullmatch(r"[0-9a-f-]{36}", jobid) or not re.fullmatch(r"highlight_[1-3]\.mp4", filename):
        raise HTTPException(404, "Not found")
    with JOBS_LOCK:
        item = JOBS.get(jobid)
    if not item or item["state"] != "done":
        raise HTTPException(404, "Clip not ready")
    path = APP_ROOT / jobid / filename
    if not path.is_file():
        raise HTTPException(404, "Clip expired")
    return FileResponse(path, media_type="video/mp4", filename=filename)
