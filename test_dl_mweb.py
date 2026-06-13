import urllib.request, json as _json
import yt_dlp as ytdlp_lib
import sys

video_id = "lacFcgcHx6I"
url = f"https://www.youtube.com/watch?v={video_id}"

_BGUTIL_URL = "http://127.0.0.1:4416/get_pot"

def _get_po_token(vid: str):
    body = _json.dumps({"content_binding": vid} if vid else {}).encode()
    req = urllib.request.Request(
        _BGUTIL_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return _json.loads(r.read())

try:
    po_token_data = _get_po_token(video_id)
except Exception as e:
    sys.exit(1)

tok = po_token_data["poToken"]
visitor = po_token_data.get("contentBinding", "")

mweb_args = {"youtube": {
    "player_client": ["mweb"],
    "po_token": [f"web.gvs+{tok}", f"mweb.gvs+{tok}"],
}}
if visitor:
    mweb_args["youtube"]["visitor_data"] = [visitor]

ydl_opts = {
    "outtmpl": "test_dl.mp4",
    "format": "bestvideo[height<=720]+bestaudio/best",
    "extractor_args": mweb_args,
    "verbose": True
}

with ytdlp_lib.YoutubeDL(ydl_opts) as ydl:
    try:
        ydl.extract_info(url, download=True)
    except Exception as e:
        print(f"FAILED WITH ERROR: {e}")
