import os
import uuid
import shutil
import tempfile
import threading
import subprocess
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import boto3
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel

app = FastAPI()

SECRET = os.getenv("DOWNLOAD_SERVICE_SECRET", "changeme")
R2_ENDPOINT = os.getenv("R2_ENDPOINT_URL")
R2_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
R2_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
R2_BUCKET = os.getenv("AWS_S3_BUCKET")

# Use system yt-dlp (2026.x) — newer clients handle YouTube better
YTDLP_BIN = os.getenv("YTDLP_BIN", "/opt/homebrew/bin/yt-dlp")

_jobs: dict = {}


def _r2_client():
    return boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        region_name="auto",
    )


class DownloadRequest(BaseModel):
    url: str
    job_id: str
    quality: str = "720p"   # "720p" | "1080p"
    r2_key: str = ""        # if set, override default R2 destination


def _do_download(task_id: str, url: str, job_id: str, quality: str = "720p", r2_key_override: str = ""):
    tmp = Path(tempfile.mkdtemp())
    try:
        out_template = str(tmp / "original.%(ext)s")

        if quality == "1080p":
            formats = [
                ("bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best", "1080p"),
                ("bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best", "720p"),
                ("18", "360p"),
            ]
        else:
            formats = [
                ("bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best", "720p"),
                ("18", "360p"),
            ]

        for fmt, label in formats:
            print(f"[dl_service] trying {label}", flush=True)
            cmd = [
                YTDLP_BIN,
                "-f", fmt,
                "--merge-output-format", "mp4",
                "--no-playlist",
                "--no-warnings",
                "-o", out_template,
                url,
            ]
            result = subprocess.run(cmd, capture_output=False, timeout=1800)
            files = list(tmp.glob("original.*"))
            if result.returncode == 0 and files:
                video_file = max(files, key=lambda f: f.stat().st_size)
                if video_file.stat().st_size > 100_000:
                    print(f"[dl_service] {label} success: {video_file.stat().st_size // 1024 // 1024}MB", flush=True)
                    break
            # clean up partial files for next attempt
            for f in tmp.glob("original.*"):
                f.unlink(missing_ok=True)
        else:
            raise RuntimeError("All quality attempts failed")

        # Get resolution via ffprobe
        width, height = None, None
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height", "-of", "csv=p=0", str(video_file)],
                capture_output=True, text=True, timeout=15,
            )
            parts = r.stdout.strip().split(",")
            if len(parts) == 2:
                width, height = int(parts[0]), int(parts[1])
        except Exception:
            pass

        # Get duration/title via yt-dlp --dump-json
        title, duration = "video", 0.0
        try:
            r = subprocess.run(
                [YTDLP_BIN, "--dump-json", "--no-playlist", url],
                capture_output=True, text=True, timeout=30,
            )
            import json as _json
            meta = _json.loads(r.stdout.strip())
            title = meta.get("title", "video")
            duration = float(meta.get("duration") or 0)
        except Exception:
            pass

        r2_key = r2_key_override if r2_key_override else f"jobs/{job_id}/original.mp4"
        print(f"[dl_service] uploading {video_file.stat().st_size // 1024 // 1024}MB → R2 {r2_key}", flush=True)
        _r2_client().upload_file(str(video_file), R2_BUCKET, r2_key)
        print(f"[dl_service] upload done", flush=True)

        _jobs[task_id] = {
            "status": "done",
            "r2_key": r2_key,
            "title": title,
            "duration": duration,
            "width": width,
            "height": height,
            "ext": "mp4",
        }
    except Exception as e:
        print(f"[dl_service] error: {e}", flush=True)
        _jobs[task_id] = {"status": "error", "error": str(e)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/download")
def download(req: DownloadRequest, x_secret: str = Header(...)):
    if x_secret != SECRET:
        raise HTTPException(status_code=401, detail="Invalid secret")
    task_id = str(uuid.uuid4())
    _jobs[task_id] = {"status": "downloading"}
    threading.Thread(
        target=_do_download,
        args=(task_id, req.url, req.job_id, req.quality, req.r2_key),
        daemon=True,
    ).start()
    return {"task_id": task_id, "status": "downloading"}


@app.get("/status/{task_id}")
def status(task_id: str, x_secret: str = Header(...)):
    if x_secret != SECRET:
        raise HTTPException(status_code=401, detail="Invalid secret")
    job = _jobs.get(task_id)
    if not job:
        raise HTTPException(status_code=404, detail="Task not found")
    return job
