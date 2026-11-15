"""ClipForge AI: a small, self-hosted, rights-respecting Shorts clipper.
Highlight selection is an audio/transcript heuristic, NOT a predictive viral AI model.
"""
import audioop
import hmac
import html
import json
import math
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, jsonify, request, send_file

HERE = Path(__file__).resolve().parent
STORE = Path("/tmp/clipforge-jobs")
STORE.mkdir(parents=True, exist_ok=True)
app = Flask(__name__, static_folder=".", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 180 * 1024 * 1024
PASSWORD = os.getenv("AGENT_PASSWORD", "")
JOBS = {}
LOCK = threading.Lock()
POOL = ThreadPoolExecutor(max_workers=1)
TTL = 4 * 3600
MAX_DURATION = 1800


@app.get("/")
def home():
    return send_file(HERE / "index.html")


@app.get("/api/health")
def health():
    return jsonify(ok=True, protected=bool(PASSWORD), version="1.0")


def authenticate():
    provided = request.headers.get("X-Agent-Password", "")
    return bool(PASSWORD) and hmac.compare_digest(PASSWORD, provided)


def clean_old():
    cutoff = time.time() - TTL
    with LOCK:
        old = [k for k, v in JOBS.items()
               if v.get("created", 0) < cutoff and v.get("status") not in ("processing", "queued")]
        for key in old:
            JOBS.pop(key, None)
            shutil.rmtree(STORE / key, ignore_errors=True)


def update(job, **changes):
    with LOCK:
        if job in JOBS:
            JOBS[job].update(changes)


def safe_youtube_url(raw):
    try:
        u = urlparse(raw.strip())
        host = (u.hostname or "").lower()
        return (u.scheme == "https"
                and host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
                and bool(u.path.strip("/"))
                and not u.username and not u.password)
    except Exception:
        return False


@app.post("/api/jobs")
def submit():
    if not PASSWORD:
        return jsonify(error="Agent password is not configured on the server."), 503
    if not authenticate():
        return jsonify(error="Incorrect agent password."), 401
    if request.form.get("rights") != "yes":
        return jsonify(error="Confirm that you own the footage or have permission to clip it."), 400
    clean_old()
    upload = request.files.get("video")
    url = request.form.get("youtube_url", "").strip()
    if not (upload and upload.filename) and not url:
        return jsonify(error="Upload a video or paste an authorized YouTube link."), 400
    if url and not safe_youtube_url(url):
        return jsonify(error="Only secure YouTube or youtu.be URLs are supported."), 400

    try:
        clip_length = int(request.form.get("length", "30"))
        count = int(request.form.get("count", "3"))
    except ValueError:
        return jsonify(error="Invalid clip settings."), 400
    if clip_length not in (15, 30, 45, 60) or count not in (1, 3, 5, 10):
        return jsonify(error="Unsupported clip length or count."), 400

    job = uuid.uuid4().hex
    directory = STORE / job
    directory.mkdir(parents=True, exist_ok=True)
    source = None
    if upload and upload.filename:
        ext = Path(upload.filename).suffix.lower()
        if ext not in {".mp4", ".mov", ".mkv", ".webm", ".m4v"}:
            shutil.rmtree(directory, ignore_errors=True)
            return jsonify(error="Upload MP4, MOV, MKV or WebM video."), 400
        source = directory / ("source" + ext)
        upload.save(source)
        if source.stat().st_size > 170 * 1024 * 1024:
            shutil.rmtree(directory, ignore_errors=True)
            return jsonify(error="Video exceeds the 170MB free-hosting limit."), 413

    captions = request.files.get("captions")
    caption_path = None
    if captions and captions.filename:
        suffix = Path(captions.filename).suffix.lower()
        if suffix not in {".srt", ".vtt"}:
            shutil.rmtree(directory, ignore_errors=True)
            return jsonify(error="Caption files must be SRT or VTT."), 400
        caption_path = directory / ("captions" + suffix)
        captions.save(caption_path)
        if caption_path.stat().st_size > 2 * 1024 * 1024:
            shutil.rmtree(directory, ignore_errors=True)
            return jsonify(error="Caption file is too large."), 413

    with LOCK:
        JOBS[job] = {"status": "queued", "progress": 0, "created": time.time(), "clips": []}
    POOL.submit(process_job, job, str(source) if source else None, url,
                str(caption_path) if caption_path else None, clip_length, count)
    return jsonify(job_id=job, status="queued"), 202


@app.get("/api/jobs/<job>")
def status(job):
    with LOCK:
        entry = JOBS.get(job)
        if not entry:
            return jsonify(error="Job not found or expired."), 404
        return jsonify({k: v for k, v in entry.items() if k != "created"})


@app.get("/api/jobs/<job>/clip/<int:num>")
def download(job, num):
    if not re.fullmatch(r"[0-9a-f]{32}", job) or not 1 <= num <= 10:
        return jsonify(error="Invalid download path."), 400
    with LOCK:
        entry = JOBS.get(job)
    path = STORE / job / ("short_%02d.mp4" % num)
    if not entry or not path.is_file():
        return jsonify(error="Clip not ready or expired."), 404
    return send_file(path, as_attachment=True, download_name="clipforge_short_%02d.mp4" % num,
                     mimetype="video/mp4")


def command(args, timeout=240):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def duration_seconds(source):
    p = command(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=nokey=1:noprint_wrappers=1", str(source)], timeout=25)
    try:
        value = float(p.stdout.strip())
        if not math.isfinite(value) or value <= 0:
            raise ValueError()
        return value
    except (ValueError, TypeError):
        raise RuntimeError("Cannot read video duration. Try a regular MP4.")


def get_audio_energy(source, duration):
    """Stream 8 kHz PCM, calculate one RMS value per second (bounded memory)."""
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-i", str(source),
           "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "pipe:1"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    energies = []
    try:
        while len(energies) <= math.ceil(duration):
            chunk = proc.stdout.read(16000)
            if not chunk:
                break
            energies.append(audioop.rms(chunk[:len(chunk) - len(chunk) % 2], 2) if len(chunk) >= 2 else 0)
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=10)
        if proc.stdout:
            proc.stdout.close()
    if not energies:
        return [0] * (math.ceil(duration) + 1)
    return energies


def timecode(value):
    parts = value.replace(",", ".").split(":")
    try:
        if len(parts) == 3:
            h, m, s = parts
            return int(h)*3600 + int(m)*60 + float(s)
        if len(parts) == 2:
            m, s = parts
            return int(m)*60 + float(s)
    except ValueError:
        pass
    return 0.0


def read_cues(path):
    if not path or not Path(path).exists():
        return []
    raw = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    cues = []
    for block in re.split(r"\n\s*\n", raw):
        lines = block.strip().splitlines()
        timing = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing is None:
            continue
        match = re.search(r"(\d{1,2}:\d{2}(?::\d{2})?[.,]\d+)\s*-->\s*(\d{1,2}:\d{2}(?::\d{2})?[.,]\d+)", lines[timing])
        if not match:
            continue
        start, end = timecode(match.group(1)), timecode(match.group(2))
        words = " ".join(lines[timing+1:])
        words = html.unescape(re.sub(r"<[^>]*>", "", words))
        words = re.sub(r"\s+", " ", words).strip()
        if end > start and words and (not cues or (cues[-1][2] != words or start - cues[-1][0] > 4)):
            cues.append((start, end, words[:180]))
    return cues


def yt_download(url, folder):
    # Only for videos the user owns or has explicit permission to use.
    template = str(folder / "source.%(ext)s")
    cmd = ["yt-dlp", "--js-runtimes", "node", "--remote-components", "ejs:github", "--no-playlist", "--no-progress", "--restrict-filenames",
           "--socket-timeout", "20", "--retries", "2",
           "--format", "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
           "--merge-output-format", "mp4",
           "--write-subs", "--write-auto-subs", "--sub-langs", "en.*,hi.*",
           "--sub-format", "vtt",
           "--max-filesize", "170M",
           "-o", template, url]
    p = command(cmd, timeout=240)
    candidates = [f for f in folder.glob("source.*")
                  if f.suffix.lower() in {".mp4", ".webm", ".mkv"}]
    if p.returncode or not candidates:
        details = (p.stderr or p.stdout or "").lower()
        if "403" in details or "forbidden" in details or "sign in" in details or "bot" in details:
            raise RuntimeError("YouTube refused this server's download request (HTTP 403 or access restriction). This can happen on cloud hosting even with the JavaScript runtime installed. Try uploading your own video file instead.")
        if "javascript" in details or "js runtime" in details or "ejs" in details:
            raise RuntimeError("YouTube extractor needs its JavaScript runtime or solver. Please contact the app administrator.")
        raise RuntimeError("YouTube could not import this video. Try uploading a file you own instead.")
    captions = sorted(folder.glob("*.vtt"), key=lambda x: ("en" not in x.name, x.name))
    return candidates[0], (captions[0] if captions else None)


def choose_clips(duration, length, count, energies, cues):
    length = min(length, max(1, int(duration)))
    last_start = max(0, duration - length)
    step = max(4, length // 4)
    starts = [float(n) for n in range(0, max(1, int(last_start)+1), step)]
    if not starts:
        starts = [0.0]
    if starts[-1] < last_start - 1:
        starts.append(last_start)
    peak = max(energies or [0]) or 1
    hooks = ("wait", "how", "why", "secret", "best", "crazy", "amazing", "never",
             "biggest", "first", "finally", "listen", "important", "because",
             "लेकिन", "कैसे", "क्यों", "देखो", "सच")
    ranked = []
    for start in starts:
        readings = energies[int(start):int(start+length)] or [0]
        avg = sum(readings) / len(readings) / peak
        swings = (max(readings) - min(readings)) / peak
        speech = [line for a, b, line in cues if b > start and a < start+length]
        transcript_bonus = min(0.20, len(speech) * 0.011)
        interest = 0.15 if any(word in " ".join(speech).lower() for word in hooks) else 0
        # Evenly spread interesting moments, rather than merely choosing the intro.
        score = (0.50 * avg + 0.20 * swings + transcript_bonus + interest)
        ranked.append((score, start))
    ranked.sort(key=lambda item: item[0], reverse=True)
    chosen = []
    for score, start in ranked:
        if any(abs(start - other[1]) < length * 0.87 for other in chosen):
            continue
        chosen.append((score, start))
        if len(chosen) == count:
            break
    if not chosen:
        chosen = [(0.0, 0.0)]
    values = [score for score, _ in ranked]
    lo, hi = min(values), max(values)
    results = []
    for i, (score, start) in enumerate(chosen, 1):
        label = next((text for a, b, text in cues if a >= start and a < start+length and len(text) > 8), "")
        if not label:
            label = "Highlight %02d" % i
        relative = int(round(50 + 50 * ((score - lo)/(hi-lo)))) if hi > lo else 75
        results.append({"id": i, "start": round(start, 1), "end": round(min(duration, start+length), 1),
                        "duration": round(min(duration-start, length), 1),
                        "title": label[:90], "score": relative})
    return results


def srt_stamp(n):
    millis = max(0, int(n * 1000))
    h, rem = divmod(millis, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def create_segment_srt(folder, clip, cues):
    selected = []
    for a, b, words in cues:
        left = max(0, a - clip["start"])
        right = min(clip["duration"], b - clip["start"])
        if right - left >= 0.12:
            selected.append((left, right, words))
    if not selected:
        return None
    target = folder / ("subtitle_%02d.srt" % clip["id"])
    target.write_text("\n\n".join(
        "%d\n%s --> %s\n%s" % (i, srt_stamp(a), srt_stamp(b), words)
        for i, (a, b, words) in enumerate(selected, 1)), encoding="utf-8")
    return target


def export_clip(folder, source, clip, cues):
    subtitle = create_segment_srt(folder, clip, cues)
    vf = ("scale=720:1280:force_original_aspect_ratio=increase,"
          "crop=720:1280,"
          "drawbox=x=0:y=0:w=iw:h=72:color=black@0.55:t=fill,"
          "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
          "text='CLIPFORGE  |  SHORT %02d':fontsize=23:fontcolor=white:x=26:y=23" % clip["id"])
    if subtitle:
        vf += (",subtitles=" + str(subtitle) +
               ":force_style='FontName=DejaVu Sans,FontSize=22,"
               "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
               "BorderStyle=1,Outline=3,Shadow=1,Alignment=2,MarginV=180'")
    target = folder / ("short_%02d.mp4" % clip["id"])
    cmd = ["ffmpeg", "-y", "-nostdin", "-v", "error", "-ss", str(clip["start"]),
           "-i", str(source), "-t", str(clip["duration"]),
           "-vf", vf, "-r", "30", "-c:v", "libx264", "-preset", "ultrafast",
           "-crf", "27", "-threads", "2", "-c:a", "aac", "-b:a", "96k",
           "-movflags", "+faststart", str(target)]
    p = command(cmd, timeout=420)
    if p.returncode or not target.exists() or target.stat().st_size < 1000:
        raise RuntimeError("Video export failed: " + (p.stderr or "")[-550:])


def process_job(job, source, youtube_url, captions_file, length, count):
    directory = STORE / job
    try:
        update(job, status="processing", progress=4, stage="Preparing source video")
        if not source:
            src, auto_captions = yt_download(youtube_url, directory)
            source = str(src)
            captions_file = captions_file or (str(auto_captions) if auto_captions else None)
        dur = duration_seconds(source)
        if dur > MAX_DURATION:
            raise RuntimeError("This free version supports videos up to 30 minutes.")
        update(job, progress=20, stage="Checking audio and subtitles")
        cues = read_cues(captions_file)
        energies = get_audio_energy(source, dur)
        update(job, progress=40, stage="Ranking candidate highlights")
        clips = choose_clips(dur, length, count, energies, cues)
        for index, clip in enumerate(clips):
            update(job, progress=int(42 + 55 * index / len(clips)),
                   stage="Rendering vertical Short %d of %d" % (index+1, len(clips)))
            export_clip(directory, source, clip, cues)
            update(job, clips=clips[:index+1])
        update(job, status="completed", progress=100,
               stage="Finished — download your MP4 Shorts", clips=clips,
               has_captions=bool(cues), source_duration=round(dur, 1))
    except Exception as exc:
        update(job, status="failed", error=str(exc)[:900], stage="Failed")
    finally:
        # Source footage is deleted after processing; rendered clips stay for 4h or until restart.
        for p in directory.glob("source.*"):
            try:
                p.unlink()
            except OSError:
                pass


@app.errorhandler(413)
def too_big(_):
    return jsonify(error="Upload too large (180MB total maximum)."), 413


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")), threaded=True)
