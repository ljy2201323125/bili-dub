#!/usr/bin/env python3
"""Build the three audio tracks.

  zh.m4a   original Chinese audio
  en.m4a   English dub placed on the timeline; clips sped up (atempo, capped
           at 1.15x) when longer than their slot, else laid in with the gaps
  mix.m4a  English dub + original audio ducked whenever English is speaking
           (sidechain compression)

Clips are concatenated in time order with silence gaps, so no huge filter
graphs regardless of video length.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

MAX_TEMPO = 1.15


def source_media(wd):
    for p in wd.glob("source.*"):
        if p.suffix in (".mp4", ".mkv", ".flv", ".ts"):
            return p
    raise SystemExit("no source media")


def ffmpeg(args):
    common.run([common.FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                *args])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir")
    ap.add_argument("--duck-level", type=float, default=0.06,
                    help="original volume under speech (sidechain threshold)")
    args = ap.parse_args(argv)

    wd = common.resolve_workdir(args.workdir)
    src = source_media(wd)
    tdir = wd / "tts"
    manifest = common.load_json(tdir / "manifest.json")
    segs = [s for s in common.load_json(wd / "segments.json")
            if str(s["id"]) in manifest]
    segs.sort(key=lambda s: s["start"])

    tl = tdir / "timeline"
    tl.mkdir(exist_ok=True)
    for old in tl.glob("piece_*.wav"):
        old.unlink()

    pieces = []
    cursor = 0.0

    def add_silence(dur, n):
        if dur <= 0.02:
            return n
        out = tl / f"piece_{n:05d}.wav"
        ffmpeg(["-f", "lavfi", "-i",
                "anullsrc=r=48000:cl=stereo", "-t", f"{dur:.3f}",
                "-c:a", "pcm_s16le", str(out)])
        pieces.append(out)
        return n + 1

    n = 0
    for s in segs:
        m = manifest[str(s["id"])]
        start, end = s["start"], s["end"]
        speech = m["dur"]
        slot = max(0.1, end - start)

        gap = start - cursor
        n = add_silence(gap, n)

        tempo = min(speech / slot, MAX_TEMPO) if speech > slot else 1.0
        out = tl / f"piece_{n:05d}.wav"
        af = f"atempo={tempo:.4f}"
        ffmpeg(["-i", str(tdir / m["file"]), "-af", af,
                "-c:a", "pcm_s16le", str(out)])
        fitted = speech / tempo
        pieces.append(out)
        n += 1
        cursor = start + fitted

    # tail silence to match source duration
    total = common.ffprobe_duration(src)
    n = add_silence(total - cursor, n)

    concat_list = tl / "list.txt"
    concat_list.write_text(
        "\n".join(f"file '{p.name}'" for p in pieces), encoding="utf-8")

    en = wd / "en.m4a"
    ffmpeg(["-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c:a", "aac", "-b:a", "192k", str(en)])

    zh = wd / "zh.m4a"
    ffmpeg(["-i", str(src), "-vn", "-c:a", "aac", "-b:a", "192k", str(zh)])

    # mix: duck original under the dub, then combine at equal weight
    mix = wd / "mix.m4a"
    fc = (
        f"[0:a]aresample=48000,aformat=channel_layouts=stereo[base];"
        f"[1:a]aresample=48000,aformat=channel_layouts=stereo[dub];"
        f"[base][dub]sidechaincompress=threshold={args.duck_level}:ratio=10:"
        f"attack=20:release=350[ducked];"
        f"[ducked][dub]amix=inputs=2:duration=first:normalize=0[out]"
    )
    ffmpeg(["-i", str(src), "-i", str(en), "-filter_complex", fc,
            "-map", "[out]", "-c:a", "aac", "-b:a", "192k", str(mix)])

    common.emit({"zh": str(zh), "en": str(en), "mix": str(mix),
                 "segments": len(segs), "source_duration": round(total, 2)})


if __name__ == "__main__":
    main()
