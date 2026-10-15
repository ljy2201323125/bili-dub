#!/usr/bin/env python3
"""Download a Bilibili video and probe metadata / CC subtitles.

Outputs into work/<id>/:
  source.<ext>   merged media (mp4)
  info.json      id/title/uploader/duration/has_cc/...
  cc.*           any built-in subtitle we could fetch (optional)
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

import time  # noqa: E402
import yt_dlp  # noqa: E402


def browser_headers(args):
    h = {
        "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0 Safari/537.36"),
        "Referer": "https://www.bilibili.com/",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    if args.sessdata:
        h["Cookie"] = f"SESSDATA={args.sessdata}"
    return h


def build_opts(workdir, args):
    opts = {
        "outtmpl": str(workdir / "source.%(ext)s"),
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "ffmpeg_location": str(Path(common.FFMPEG).parent),
        "quiet": False,
        "noplaylist": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "sub_langs": ["all"],
        "sub_format": "srt",
        "ignoreerrors": False,
        "retries": 5,
        "fragment_retries": 5,
        "http_headers": browser_headers(args),
    }
    if args.cookies:
        opts["cookiefile"] = args.cookies
    return opts


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--cookies", help="Netscape cookies.txt")
    ap.add_argument("--sessdata", help="SESSDATA cookie value (for HD/login)")
    ap.add_argument("--limit", action="store_true",
                    help="only probe, do not download")
    args = ap.parse_args(argv)

    # First pass: extract info (no download) to get the id.
    probe_opts = {"quiet": True, "noplaylist": True, "skip_download": True,
                  "http_headers": browser_headers(args)}
    if args.cookies:
        probe_opts["cookiefile"] = args.cookies

    info, last_err = None, None
    for attempt in range(4):
        try:
            with yt_dlp.YoutubeDL(dict(probe_opts)) as ydl:
                info = ydl.extract_info(args.url, download=False)
            break
        except Exception as e:  # transient anti-bot (KeyError 'bvid' / 412)
            last_err = e
            wait = 2 ** attempt
            print(f"[download] extract attempt {attempt+1} failed "
                  f"({type(e).__name__}); retry in {wait}s", file=sys.stderr)
            time.sleep(wait)
    if info is None:
        raise SystemExit(f"[download] failed after retries: {last_err}")

    vid = info.get("id")
    workdir = common.SKILL_ROOT / "work" / vid
    workdir.mkdir(parents=True, exist_ok=True)

    subs = info.get("subtitles") or {}
    autos = info.get("automatic_captions") or {}
    cc_langs = sorted(set(list(subs.keys()) + list(autos.keys())))

    meta = {
        "id": vid,
        "title": info.get("title"),
        "uploader": info.get("uploader") or info.get("channel"),
        "duration": info.get("duration"),
        "url": args.url,
        "ext": info.get("ext"),
        "resolution": info.get("resolution"),
        "has_cc": bool(cc_langs),
        "cc_langs": cc_langs,
        "manual_cc": sorted(subs.keys()),
        "auto_cc": sorted(autos.keys()),
    }
    common.save_json(workdir / "info.json", meta)
    common.emit(meta)

    if args.limit:
        return

    print(f"\n[download] -> {workdir}", file=sys.stderr)
    with yt_dlp.YoutubeDL(build_opts(workdir, args)) as ydl:
        ydl.download([args.url])

    # Report subtitle files that actually landed.
    cc_files = [p.name for p in workdir.glob("cc.*")] + \
               [p.name for p in workdir.glob("source*.srt")]
    print(f"[download] done. cc files: {cc_files}", file=sys.stderr)


if __name__ == "__main__":
    main()
