#!/usr/bin/env bash
# Idempotent environment bootstrap for bili-dub. Safe to re-run.
#
# Works on macOS (Apple Silicon + Intel) and Linux (incl. WSL).
# It installs, all inside this skill folder (no global system changes):
#   1. uv + a Python 3.11 venv with the Python dependencies
#   2. a FULL ffmpeg build with libass (the "subtitles" filter), unless a
#      suitable ffmpeg already exists on PATH.
#
# Windows: run this under WSL (Ubuntu) — see README.md. Native Windows/PowerShell
# is not supported by this shell script, but the pipeline itself is pure Python
# and will run there if you provide ffmpeg on PATH yourself.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo "[setup] skill root: $ROOT"

# ---------------------------------------------------------------------------
# 0) If a system ffmpeg already has libass, use it and skip the conda install.
# ---------------------------------------------------------------------------
have_good_ffmpeg() {
  command -v ffmpeg >/dev/null 2>&1 &&
    ffmpeg -hide_banner -filters 2>/dev/null | grep -q -- '--> *subtitles '
}
# older ffmpeg prints ".. subtitles .." without an arrow; accept either.
have_good_ffmpeg() {
  command -v ffmpeg >/dev/null 2>&1 &&
    ffmpeg -hide_banner -filters 2>/dev/null | grep -qw subtitles
}

# ---------------------------------------------------------------------------
# 1) Python venv via uv
# ---------------------------------------------------------------------------
if ! command -v uv >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/uv" ]; then
  echo "[setup] installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
export PATH="$HOME/.local/bin:$PATH"

if [ ! -x ".venv/bin/python" ]; then
  echo "[setup] creating Python 3.11 venv"
  "$UV" venv --python 3.11 .venv
fi
echo "[setup] installing Python packages"
"$UV" pip install --python .venv/bin/python -r requirements.txt

# ---------------------------------------------------------------------------
# 2) ffmpeg with libass
# ---------------------------------------------------------------------------
if [ -x "bin/ffenv/bin/ffmpeg" ] && bin/ffenv/bin/ffmpeg -hide_banner -filters 2>/dev/null | grep -qw subtitles; then
  echo "[setup] bundled ffmpeg already present"
elif have_good_ffmpeg; then
  echo "[setup] using system ffmpeg ($(command -v ffmpeg)) — libass detected"
  echo "[setup] (scripts will find it on PATH; nothing to install)"
else
  echo "[setup] no suitable ffmpeg found — installing a full build via micromamba"
  mkdir -p bin/mm

  # map `uname` to a micromamba release slug
  os="$(uname -s)"
  arch="$(uname -m)"
  case "$os" in
    Darwin) PLATFORM="osx" ;;
    Linux)  PLATFORM="linux" ;;
    *)
      echo "[setup] ERROR: unsupported OS '$os'. Use Linux/WSL or macOS." >&2
      exit 1 ;;
  esac
  case "$arch" in
    arm64|aarch64) MM_ARCH="aarch64" ;;
    x86_64|amd64)  MM_ARCH="64" ;;   # micromamba uses linux-64 / osx-64
    *)
      echo "[setup] ERROR: unsupported CPU architecture '$arch'." >&2
      exit 1 ;;
  esac
  SLUG="${PLATFORM}-${MM_ARCH}"   # osx-arm64 / osx-64 / linux-aarch64 / linux-64

  if [ ! -x "bin/mm/bin/micromamba" ]; then
    echo "[setup] downloading micromamba for $SLUG"
  curl -Ls "https://micro.mamba.pm/api/micromamba/${SLUG}/latest" \
      | tar -xv -C bin/mm bin/micromamba
    chmod +x bin/mm/bin/micromamba
  fi
  MAMBA_ROOT_PREFIX="$ROOT/bin/mmroot" bin/mm/bin/micromamba create -y \
    -p "$ROOT/bin/ffenv" -c conda-forge ffmpeg
fi

# ---------------------------------------------------------------------------
# 3) verify
# ---------------------------------------------------------------------------
ok=1
FF="bin/ffenv/bin/ffmpeg"
[ -x "$FF" ] || FF="$(command -v ffmpeg || true)"
if [ -n "${FF:-}" ] && "$FF" -hide_banner -filters 2>/dev/null | grep -qw subtitles; then
  echo "  ffmpeg libass OK ($FF)"
else
  echo "  ffmpeg libass MISSING — burned subtitles won't work." >&2
  ok=0
fi
if .venv/bin/python -c "import yt_dlp,faster_whisper,edge_tts" 2>/dev/null; then
  echo "  python deps OK"
else
  echo "  python deps import FAILED (pyannote is optional)." >&2
  ok=0
fi
[ "$ok" = 1 ] && echo "[setup] done." || { echo "[setup] finished with warnings." >&2; exit 1; }
