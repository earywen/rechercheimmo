#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
exec .venv/bin/uvicorn src.app:app --host 0.0.0.0 --port 8765
