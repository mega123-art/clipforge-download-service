import urllib.request, json as _json
import yt_dlp as ytdlp_lib
import sys

video_id = "lacFcgcHx6I"
url = f"https://www.youtube.com/watch?v={video_id}"

ios_args = {"youtube": {
    "player_client": ["ios"],
}}

ydl_opts = {
    "outtmpl": "test_dl.mp4",
    "format": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best",
    "extractor_args": ios_args,
    "verbose": True
}

with ytdlp_lib.YoutubeDL(ydl_opts) as ydl:
    try:
        ydl.extract_info(url, download=True)
    except Exception as e:
        print(f"FAILED WITH ERROR: {e}")
