#!/usr/bin/env python3
"""Burn English subtitles into the picture and mux three audio tracks.

Output MP4:
  video  : source video with hard-burned English subtitles (libx264)
  audio 0: Chinese original   (chi, default)
  audio 1: English dub        (eng)
  audio 2: English + ducked Chinese mix (eng)
  subtitle (optional, on by default): switchable English soft track
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402


def safe_name(name, fallback="bili_video"):
    name = re.sub(r'[\\/:*?"<>|\n]+', " ", name or "").strip()
    name = re.sub(r"\s+", " ", name)
    return (name[:80] or fallback)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir")
    ap.add_argument("--crf", type=int, default=20)
    ap.add_argument("--preset", default="medium")
    ap.add_argument("--no-softsub", action="store_true")
    args = ap.parse_args(argv)

    wd = common.resolve_workdir(args.workdir)
    src = next((p for p in wd.glob("source.*")
                if p.suffix in (".mp4", ".mkv", ".flv", ".ts")), None)
    if not src:
        raise SystemExit("no source media")
    for need in ("zh.m4a", "en.m4a", "mix.m4a", "en.srt"):
        if not (wd / need).exists():
            raise SystemExit(f"missing {need}; run earlier stages first")

    info = common.load_json(wd / "info.json", {})
    outdir = common.SKILL_ROOT / "output"
    outdir.mkdir(exist_ok=True)
    out = outdir / f"{safe_name(info.get('title'))}.mp4"

    style = ("FontName=Arial,FontSize=20,PrimaryColour=&H00FFFFFF,"
             "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,"
             "Alignment=2,MarginV=30")
    vf = f"subtitles=en.srt:force_style='{style}'"

    cmd = [common.FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
           "-i", src.name,
           "-i", "zh.m4a", "-i", "en.m4a", "-i", "mix.m4a"]
    idx_sub = None
    if not args.no_softsub:
        cmd += ["-i", "en.srt"]
        idx_sub = 4  # inputs: source=0 zh=1 en=2 mix=3 srt=4
    cmd += ["-vf", vf,
            "-map", "0:v:0",
            "-map", "1:a:0", "-map", "2:a:0", "-map", "3:a:0"]
    if idx_sub is not None:
        cmd += ["-map", f"{idx_sub}:s:0"]
    cmd += [
        "-c:v", "libx264", "-crf", str(args.crf), "-preset", args.preset,
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-metadata:s:a:0", "language=chi",
        "-metadata:s:a:0", "title=Chinese Original",
        "-metadata:s:a:1", "language=eng",
        "-metadata:s:a:1", "title=English Dub",
        "-metadata:s:a:2", "language=eng",
        "-metadata:s:a:2", "title=English Dub + Chinese",
        "-disposition:a:0", "default",
        "-disposition:a:1", "0",
        "-disposition:a:2", "0",
        "-movflags", "+faststart",
    ]
    if idx_sub is not None:
        # soft subtitle defaults to non-default; do not pass an explicit
        # empty disposition (rejected by newer ffmpeg for mov_text)
        cmd += ["-c:s", "mov_text",
                "-metadata:s:s:0", "language=eng",
                "-metadata:s:s:0", "title=English"]
    cmd += [str(out)]

    print(f"[mux] encoding -> {out}", file=sys.stderr)
    common.run(cmd, cwd=str(wd))
    common.emit({"output": str(out),
                 "size_mb": round(out.stat().st_size / 1e6, 1),
                 "duration": round(common.ffprobe_duration(out), 2)})


if __name__ == "__main__":
    main()
