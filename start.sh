#!/bin/bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Load env
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

# Setup venv if needed
if [ ! -d venv ]; then
  echo "Creating venv..."
  python3 -m venv venv
fi

source venv/bin/activate

# Install deps
pip install -q -r requirements.txt

# Start uvicorn in background
echo "Starting download service on port 8001..."
uvicorn main:app --host 0.0.0.0 --port 8001 &
UVICORN_PID=$!

# Start cloudflare tunnel
echo "Starting Cloudflare tunnel..."
if ! command -v cloudflared &> /dev/null; then
  echo "Installing cloudflared..."
  brew install cloudflare/cloudflare/cloudflared
fi

# Tunnel and capture the URL
cloudflared tunnel --url http://localhost:8001 2>&1 | tee /tmp/tunnel.log &
TUNNEL_PID=$!

# Wait for tunnel URL
echo "Waiting for tunnel URL..."
sleep 5
TUNNEL_URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /tmp/tunnel.log | head -1)
echo ""
echo "============================================"
echo "Download service running!"
echo "Public URL: $TUNNEL_URL"
echo ""
echo "Set this on Railway:"
echo "  DOWNLOAD_SERVICE_URL=$TUNNEL_URL"
echo "  DOWNLOAD_SERVICE_SECRET=${DOWNLOAD_SERVICE_SECRET:-changeme}"
echo "============================================"
echo ""
echo "Press Ctrl+C to stop"

trap "kill $UVICORN_PID $TUNNEL_PID 2>/dev/null" EXIT
wait
