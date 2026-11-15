# ClipKhoj Auto Highlights
Uploads a video owned/licensed by the user, detects motion and loud audio events and exports up to three 9:16 MP4 short clips. This is a signal-based **automatic highlight extractor**, not a semantic AI that understands jokes/plot/action. Requires no API keys. Does not ingest/download YouTube or Instagram URLs.

Endpoints: /api/health, POST /api/clips (multipart file: video, rights=true, seconds=15/20/30, count=1/2/3), GET /api/status/{job_id}, GET /api/download/{job_id}/highlight_{n}.mp4.

Run: pip install -r requirements.txt; uvicorn app:app --host 0.0.0.0 --port 8000.
Limits: 125 MB, 6 seconds to 15 min duration; ephemeral /tmp output for ~45 min; CPU processing may take time. Suitable for short test videos; long heavy videos may exceed host limits. No cloud file retention guarantee.
