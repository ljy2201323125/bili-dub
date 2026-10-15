#!/usr/bin/env python3
"""Shared helpers for the bili-dub pipeline."""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
# Linux/macOS venv python; Windows venvs put the interpreter in Scripts/.
_VENV_PY = SKILL_ROOT / ".venv" / "bin" / "python"
if not _VENV_PY.exists():
    _alt = SKILL_ROOT / ".venv" / "Scripts" / "python.exe"
    VENVPY = _alt if _alt.exists() else _VENV_PY
else:
    VENVPY = _VENV_PY


def _candidates(name):
    """Possible locations of ffmpeg/ffprobe, in priority order.

    Covers the bundled micromamba env (POSIX + Windows layouts), a binary
    dropped directly into bin/, and finally whatever is on PATH.
    """
    exe = f"{name}.exe" if os.name == "nt" else name
    return [
        SKILL_ROOT / "bin" / "ffenv" / "bin" / exe,
        SKILL_ROOT / "bin" / "ffenv" / "Scripts" / f"{name}.exe",
        SKILL_ROOT / "bin" / exe,
        SKILL_ROOT / "bin" / name,
    ]


def find_exe(name):
    for c in _candidates(name):
        if c.exists():
            return str(c)
    found = shutil.which(name)
    return found or name  # bare name → rely on PATH at call time


FFMPEG = find_exe("ffmpeg")
FFPROBE = find_exe("ffprobe")


def run(cmd, **kw):
    """Run a command, raising with output on failure."""
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       text=True, **kw)
    if p.returncode != 0:
        raise RuntimeError(
            f"command failed ({p.returncode}): {' '.join(map(str, cmd[:6]))}\n"
            f"{p.stderr[-3000:]}"
        )
    return p


def ffprobe_duration(path):
    p = run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
             "-of", "json", str(path)])
    return float(json.loads(p.stdout)["format"]["duration"])


def load_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def srt_time(t):
    if t < 0:
        t = 0
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    if ms == 1000:
        ms = 999
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(segments, out_path, text_key="en"):
    lines = []
    for i, seg in enumerate(segments, 1):
        lines.append(str(i))
        lines.append(f"{srt_time(seg['start'])} --> {srt_time(seg['end'])}")
        lines.append(seg.get(text_key, "").strip())
        lines.append("")
    Path(out_path).write_text("\n".join(lines), encoding="utf-8")


def parse_srt_time(s):
    s = s.strip().replace(",", ".")
    h, m, rest = s.split(":")
    return int(h) * 3600 + int(m) * 60 + float(rest)


def parse_srt(path):
    """Return [{start,end,text}] from an SRT file."""
    raw = Path(path).read_text(encoding="utf-8", errors="ignore")
    blocks = re.split(r"\n\s*\n", raw.strip())
    out = []
    for b in blocks:
        lines = [x for x in b.splitlines() if x.strip()]
        if len(lines) < 2:
            continue
        idx = 0
        if "-->" not in lines[0]:
            idx = 1  # skip numeric id
        try:
            a, bb = lines[idx].split("-->")
        except (ValueError, IndexError):
            continue
        text = " ".join(lines[idx + 1:]).strip()
        if not text:
            continue
        out.append({"start": parse_srt_time(a), "end": parse_srt_time(bb),
                    "text": text})
    return out


def resolve_workdir(arg):
    """Accept either a work dir path or a video id; resolve under work/."""
    p = Path(arg)
    if p.exists() and (p / "info.json").exists():
        return p
    w = SKILL_ROOT / "work" / arg
    if w.exists():
        return w
    # maybe given the work dir directly even without info.json
    if p.exists() and p.is_dir():
        return p
    raise SystemExit(f"cannot find work dir for: {arg} (expected {w})")


def emit(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))
