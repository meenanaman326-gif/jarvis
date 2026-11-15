"""ShortsFX: phone-first front end for the original 51 Python video effects.
The upstream renderer is included in ./vendor. Rendering happens on this server,
not in the browser. Smart clips use transparent audio/motion heuristics, not an LLM.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv('STUDIO_DATA_DIR', str(Path(tempfile.gettempdir()) / 'shortsfx_jobs')))
DATA_DIR.mkdir(parents=True, exist_ok=True)
MAX_MB = int(os.getenv('MAX_UPLOAD_MB', '150'))
KEEP_SECONDS = 3 * 3600
ALLOWED = {'.mp4', '.mov', '.m4v', '.webm', '.mkv'}
EFFECTS = json.loads((ROOT / 'effects.json').read_text())
EFFECT_IDS = {v['id'] for v in EFFECTS}
JOBS: dict[str, dict[str, Any]] = {}
LOCK = threading.Lock()
EXECUTOR = ThreadPoolExecutor(max_workers=1)
app = FastAPI(title='ShortsFX Studio', version='1.0')


def cleanup() -> None:
    now = time.time()
    with LOCK:
        old = [k for k, v in JOBS.items() if now - v.get('updated', now) > KEEP_SECONDS]
        for k in old:
            JOBS.pop(k, None)
    for folder in DATA_DIR.iterdir():
        if folder.is_dir() and now - folder.stat().st_mtime > KEEP_SECONDS:
            shutil.rmtree(folder, ignore_errors=True)


def media_path(media_id: str) -> Path:
    if not re.fullmatch(r'[0-9a-f]{32}', media_id):
        raise HTTPException(404, 'Video not found')
    folder = DATA_DIR / media_id
    if not folder.is_dir():
        raise HTTPException(404, 'Video expired or not found')
    return folder


def probe(path: Path) -> dict[str, Any]:
    try:
        p = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                            'format=duration,size:stream=codec_type,width,height',
                            '-of', 'json', str(path)], capture_output=True,
                           text=True, timeout=20, check=True)
        val = json.loads(p.stdout)
        vs = next(v for v in val.get('streams', []) if v.get('codec_type') == 'video')
        duration = float(val['format'].get('duration', 0))
        if duration < 0.1 or duration > 600:
            raise ValueError('Video must be between 0.1 seconds and 10 minutes')
        return {'duration': round(duration, 2), 'width': vs.get('width'),
                'height': vs.get('height'), 'bytes': path.stat().st_size}
    except (OSError, ValueError, IndexError, StopIteration, subprocess.SubprocessError, KeyError) as exc:
        raise HTTPException(400, 'Unsupported or damaged video, or video longer than 10 minutes') from exc


def run_cmd(args: list[str], timeout: int = 240, log: Path | None = None):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if log:
        log.write_text((result.stdout + '\n' + result.stderr)[-50000:], encoding='utf-8')
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout)[-650:] or f'Command failed ({result.returncode})')
    return result


@app.get('/api/health')
def health():
    return {'ok': True, 'render_engine': (ROOT / 'vendor/scripts/fx.py').exists(),
            'effects': len(EFFECTS)}


@app.get('/api/effects')
def effects():
    return {'effects': EFFECTS}


@app.post('/api/upload')
async def upload(video: UploadFile = File(...)):
    cleanup()
    suffix = Path(video.filename or '').suffix.lower()
    if suffix not in ALLOWED:
        raise HTTPException(400, 'Choose an MP4, MOV, WEBM, M4V or MKV video')
    media_id = uuid.uuid4().hex
    folder = DATA_DIR / media_id
    folder.mkdir()
    path = folder / ('source' + suffix)
    size = 0
    try:
        with path.open('wb') as out:
            while chunk := await video.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_MB * 1024 * 1024:
                    raise HTTPException(413, f'Max upload size: {MAX_MB} MB')
                out.write(chunk)
        info = probe(path)
        (folder / 'metadata.json').write_text(json.dumps({'source': path.name, **info}))
        return {'id': media_id, 'url': f'/api/video/{media_id}', **info}
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    finally:
        await video.close()


def source_for(media_id: str) -> tuple[Path, dict]:
    folder = media_path(media_id)
    try:
        info = json.loads((folder / 'metadata.json').read_text())
        source = folder / info['source']
        if not source.exists():
            raise FileNotFoundError
        return source, info
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as exc:
        raise HTTPException(404, 'Video no longer available') from exc


@app.get('/api/video/{media_id}')
def video(media_id: str):
    source, _ = source_for(media_id)
    return FileResponse(source)


class SuggestBody(BaseModel):
    length: int = Field(20, ge=8, le=45)


def smart_segments(source: Path, duration: float, length: int):
    """Rank high-audio-energy and visually changing windows; no claim of semantic AI.
    Scores represent *heuristics* and are not probabilities of virality.
    """
    if duration <= length + 2:
        return [{'start': 0.0, 'end': round(duration, 1), 'score': 100,
                 'reason': 'Complete short video'}]
    sample_rate, hop = 8000, 8000 // 2
    audio = np.zeros(0, dtype=np.float32)
    try:
        p = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(source), '-vn', '-ac', '1',
                            '-ar', str(sample_rate), '-f', 'f32le', '-'],
                           capture_output=True, timeout=60, check=True)
        audio = np.frombuffer(p.stdout, dtype='<f4')
    except (subprocess.SubprocessError, ValueError):
        pass
    n = max(1, int(np.ceil(duration * 2)))
    energy = np.zeros(n, dtype=np.float32)
    if audio.size:
        for i in range(n):
            seg = audio[i * hop:min((i+1)*hop, len(audio))]
            if seg.size:
                energy[i] = float(np.sqrt(np.mean(seg.astype(np.float64) ** 2)))
        energy = np.log1p(60 * energy)
        lo, hi = np.quantile(energy, [0.15, 0.95])
        energy = np.clip((energy - lo) / (hi - lo + 1e-6), 0, 1)
    motion = np.zeros(n, dtype=np.float32)
    try:
        p = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(source),
                            '-vf', 'fps=1,scale=96:54,format=gray', '-an', '-f', 'rawvideo', '-'],
                           capture_output=True, timeout=90, check=True)
        frames = np.frombuffer(p.stdout, dtype=np.uint8)
        frames = frames[:len(frames) // (96 * 54) * (96 * 54)].reshape(-1, 54, 96)
        if len(frames) > 1:
            delta = np.mean(np.abs(frames[1:].astype(np.int16) - frames[:-1].astype(np.int16)), axis=(1, 2))
            delta = np.clip(delta / 35.0, 0, 1)
            for i, d in enumerate(delta, start=1):
                motion[min(2 * i, n - 1)] = d
                if 2*i + 1 < n: motion[2*i+1] = d
    except (subprocess.SubprocessError, ValueError):
        pass
    signals = 0.7 * energy + 0.3 * motion if audio.size else motion
    win = min(int(length * 2), n)
    starts = np.arange(0, max(1, n - win + 1), 2)
    proposals = []
    for start in starts:
        end = min(start + win, n)
        window = signals[start:end]
        score = float(window.mean() + 0.1 * np.quantile(window, 0.9))
        proposals.append((score, start / 2, min(duration, end / 2)))
    proposals.sort(reverse=True)
    selected = []
    for score, start, end in proposals:
        if any(max(0, min(end, item['end']) - max(start, item['start'])) > length * 0.25 for item in selected):
            continue
        selected.append({'start': round(start, 1), 'end': round(end, 1),
                         'score': round(min(99, max(15, 45 + score * 52))),
                         'reason': 'Active audio + scene changes' if audio.size else 'Visual action and movement'})
        if len(selected) == 3: break
    return selected or [{'start': 0, 'end': round(min(duration, length), 1), 'score': 50,
                         'reason': 'First section'}]


@app.post('/api/suggest/{media_id}')
def suggest(media_id: str, body: SuggestBody):
    source, info = source_for(media_id)
    return {'clips': smart_segments(source, info['duration'], body.length),
            'method': 'Audio energy and visual motion (no transcript understanding)'}


class RenderBody(BaseModel):
    effect: str
    start: float = Field(0, ge=0)
    end: float = Field(20, gt=0)
    text: str = Field('', max_length=120)
    width: int = Field(360)
    crop: str = Field('fill')


def update(job_id, **fields):
    with LOCK:
        if job_id in JOBS:
            JOBS[job_id].update(fields, updated=time.time())


def render_work(job_id: str, media_id: str, spec: RenderBody):
    folder = DATA_DIR / media_id
    log = folder / f'{job_id}.log'
    clip = folder / f'{job_id}_clip.mp4'
    final = folder / f'{job_id}_final.mp4'
    try:
        source, info = source_for(media_id)
        update(job_id, state='processing', stage='Preparing vertical clip…')
        d = spec.end - spec.start
        if spec.crop == 'fit':
            vf = 'fps=15,scale=360:640:force_original_aspect_ratio=decrease,pad=360:640:(ow-iw)/2:(oh-ih)/2,setsar=1'
        else:
            vf = 'fps=15,scale=360:640:force_original_aspect_ratio=increase,crop=360:640,setsar=1'
        run_cmd(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-ss', str(spec.start), '-i', str(source),
                 '-t', str(d), '-vf', vf, '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '25',
                 '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '96k', '-movflags', '+faststart', str(clip)],
                timeout=180, log=log)
        update(job_id, stage='Tracking subject and applying original effect…')
        end = probe(clip)['duration']
        cmd = ['python', '-u', str(ROOT / 'vendor/scripts/fx.py'), spec.effect, str(clip),
               str(final), '--start', '0', '--end', str(end), '--width', str(spec.width)]
        if spec.text.strip(): cmd += ['--text', spec.text.strip()]
        with log.open('a', encoding='utf-8') as out:
            out.write('\n\nRunning: original effects renderer\n'); out.flush()
            proc = subprocess.run(cmd, stdout=out, stderr=subprocess.STDOUT, timeout=900)
        if proc.returncode or not final.exists() or final.stat().st_size < 5000:
            raise RuntimeError('Renderer failed. See server logs for details.')
        probe(final)
        clip.unlink(missing_ok=True)
        update(job_id, state='done', stage='Finished!', download=f'/api/download/{media_id}/{job_id}',
               preview=f'/api/preview/{media_id}/{job_id}')
    except subprocess.TimeoutExpired:
        update(job_id, state='error', stage='Rendering exceeded the server limit. Try a shorter clip.')
    except Exception as exc:
        update(job_id, state='error', stage=str(exc)[:240])
    finally:
        clip.unlink(missing_ok=True)


@app.post('/api/render/{media_id}')
def render(media_id: str, body: RenderBody):
    source, info = source_for(media_id)
    if body.effect not in EFFECT_IDS:
        raise HTTPException(400, 'Select one of the 51 available effects')
    if body.crop not in ('fill', 'fit') or body.width not in (360, 540):
        raise HTTPException(400, 'Invalid video setting')
    if body.start >= info['duration'] or body.end > info['duration'] + .02 or body.end <= body.start:
        raise HTTPException(400, 'Start and end must be inside the uploaded video')
    if body.end - body.start > 45:
        raise HTTPException(400, 'Maximum clip length is 45 seconds')
    job_id = uuid.uuid4().hex
    update_val = {'state': 'queued', 'stage': 'Waiting for renderer…',
                  'media_id': media_id, 'created': time.time(), 'updated': time.time()}
    with LOCK: JOBS[job_id] = update_val
    EXECUTOR.submit(render_work, job_id, media_id, body)
    return {'job_id': job_id, 'state': 'queued'}


@app.get('/api/job/{job_id}')
def job(job_id: str):
    with LOCK: value = JOBS.get(job_id)
    if not value: raise HTTPException(404, 'Job expired or not found')
    return value


def output_file(media_id: str, job_id: str):
    folder = media_path(media_id)
    with LOCK: status = JOBS.get(job_id)
    if not status or status['media_id'] != media_id or status['state'] != 'done':
        raise HTTPException(404, 'Rendered video not ready')
    path = folder / f'{job_id}_final.mp4'
    if not path.exists(): raise HTTPException(404, 'Video expired')
    return path


@app.get('/api/preview/{media_id}/{job_id}')
def preview(media_id: str, job_id: str):
    return FileResponse(output_file(media_id, job_id), media_type='video/mp4')


@app.get('/api/download/{media_id}/{job_id}')
def download(media_id: str, job_id: str):
    return FileResponse(output_file(media_id, job_id), media_type='video/mp4',
                        filename='shortsfx_' + job_id[:8] + '.mp4')


app.mount('/', StaticFiles(directory=ROOT / 'static', html=True), name='static')