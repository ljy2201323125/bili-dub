#!/usr/bin/env python3
"""Obtain a timestamped Chinese transcript.

Priority:
  1. A built-in CC subtitle yt-dlp downloaded (source*.srt, ai-zh / zh).
  2. Local transcription with faster-whisper.

Writes segments.json: [{id,start,end,zh,speaker,en}] and zh.srt.
Also guarantees a 16k mono audio.wav for the diarization/TTS stages.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402


def ensure_wav(workdir):
    srcs = list(workdir.glob("source.*"))
    src = next((p for p in srcs if p.suffix in (".mp4", ".mkv", ".flv", ".ts")),
               None)
    if src is None:
        raise SystemExit("no source media found")
    wav = workdir / "audio.wav"
    if not wav.exists():
        common.run([common.FFMPEG, "-y", "-i", str(src), "-vn",
                    "-ac", "1", "-ar", "16000", "-f", "wav", str(wav)])
    return wav


def find_cc_srt(workdir):
    srts = sorted(workdir.glob("source*.srt"))
    if not srts:
        return None
    # prefer a chinese-tagged one if multiple
    zh = [p for p in srts if any(k in p.name.lower()
                                 for k in ("zh", "ai"))]
    return (zh[0] if zh else srts[0])


def from_cc(workdir):
    srt = find_cc_srt(workdir)
    if not srt:
        return None
    raw = common.parse_srt(srt)
    segs = []
    for r in raw:
        text = r["text"].strip()
        if not text:
            continue
        segs.append({"start": round(r["start"], 3), "end": round(r["end"], 3),
                     "zh": text})
    return segs


def from_whisper(wav, model_size):
    from faster_whisper import WhisperModel
    print(f"[whisper] loading model '{model_size}' (first run downloads it)",
          file=sys.stderr)
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        str(wav), language="zh", vad_filter=True, beam_size=5,
        vad_parameters=dict(min_silence_duration_ms=500),
    )
    out = []
    for s in segments:
        text = (s.text or "").strip()
        if not text:
            continue
        out.append({"start": round(s.start, 3), "end": round(s.end, 3),
                    "zh": text})
    print(f"[whisper] detected language={info.language} "
          f"segments={len(out)}", file=sys.stderr)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir")
    ap.add_argument("--model", default="medium",
                    help="faster-whisper size: tiny/base/small/medium/large-v3")
    ap.add_argument("--force", action="store_true",
                    help="re-run even if segments.json exists")
    args = ap.parse_args(argv)

    wd = common.resolve_workdir(args.workdir)
    seg_path = wd / "segments.json"
    if seg_path.exists() and not args.force:
        print(f"[transcribe] reuse {seg_path}", file=sys.stderr)
        segs = common.load_json(seg_path)
    else:
        wav = ensure_wav(wd)
        segs = from_cc(wd)
        source = "cc"
        if segs is None:
            source = "whisper"
            segs = from_whisper(wav, args.model)
        for i, s in enumerate(segs):
            s["id"] = i
            s.setdefault("speaker", None)
            s.setdefault("en", "")
        common.save_json(seg_path, segs)
        meta = common.load_json(wd / "info.json", {})
        meta["transcript_source"] = source
        common.save_json(wd / "info.json", meta)

    common.write_srt(segs, wd / "zh.srt", text_key="zh")
    common.emit({"segments": len(segs),
                 "duration_last": segs[-1]["end"] if segs else 0,
                 "source": common.load_json(wd / "info.json", {})
                     .get("transcript_source")})


if __name__ == "__main__":
    main()
