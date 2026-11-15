# ClipForge AI (free self-hosted beta)

An original lightweight Shorts generator with a responsive web interface. It is not affiliated with Kixy.ai.

## Features
- Upload original/licensed video footage (MP4/MOV/MKV/WebM); max 170 MB, 30 minutes.
- Optional YouTube source URL (download can fail depending on access and provider restrictions).
- Select 1, 3, 5 or 10 shorts at 15, 30, 45 or 60 seconds.
- Audio energy and supplied subtitle keyword heuristics for candidate highlight ranking.
- 720x1280 center-cropped vertical MP4 with optional burned-in subtitles.
- Per-clip downloads. Results are ephemeral (4h or server restart).

This is a **heuristic clipper**, not an actual trained AI virality prediction engine. No speech-to-text, speaker tracking, face-aware reframe, or dubbing in this version.

## Local development
Install FFmpeg with ffprobe and libass subtitles support and Python 3.11.

```bash
cd clipforge
pip install -r requirements.txt
export AGENT_PASSWORD='choose-a-long-private-password'
python app.py
```

Visit http://localhost:10000.

## Hosting
Render Docker web service:
- Git repo: this repository.
- Branch: `clipforge-ai`
- Docker context: `clipforge`
- Dockerfile: `clipforge/Dockerfile`
- Environment secret: `AGENT_PASSWORD` (choose private strong value).
- Render's free instance may run slowly, sleep when idle, restart, or fail on heavy videos. No free unlimited guarantee.

Only process material that you own or have legal permission to reuse. YouTube access can fail due to availability, terms, geo restrictions, or anti-bot protections. No login/cookie bypass implemented.
