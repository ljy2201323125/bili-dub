#!/usr/bin/env python3
"""Speaker diarization with pyannote, mapped onto segments.json.

Writes speaker labels into each segment and emits speakers.json, a template
the user reviews/edits to confirm voices:
  [{id, n_segments, voice(edge-tts), note}]

A HuggingFace token (free) is required for pyannote the first time:
  1. create token at https://hf.co/settings/tokens
  2. accept terms at the model page linked on first run
  3. export HF_TOKEN=... or put it in assets/hf_token
Without a token, everything falls back to a single speaker.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

DEFAULT_VOICES = [
    "en-US-AndrewNeural",
    "en-US-AvaNeural",
    "en-US-BrianNeural",
    "en-US-EmmaNeural",
    "en-US-EricNeural",
    "en-US-JennyNeural",
]


def read_hf_token():
    t = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if t:
        return t.strip()
    f = common.SKILL_ROOT / "assets" / "hf_token"
    if f.exists():
        return f.read_text().strip()
    return None


def overlap(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def run_pyannote(wav, num_speakers, min_speakers, max_speakers):
    from pyannote.audio import Pipeline
    token = read_hf_token()
    if not token:
        return None
    try:
        pipe = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1", token=token)
    except Exception as e:
        print(f"[diarize] could not load pyannote pipeline: {e}\n"
              f"Accept the model terms at "
              f"https://hf.co/pyannote/speaker-diarization-3.1 "
              f"and the segmentation model terms.", file=sys.stderr)
        return None

    kw = {}
    if num_speakers:
        kw["num_speakers"] = num_speakers
    else:
        if min_speakers:
            kw["min_speakers"] = min_speakers
        if max_speakers:
            kw["max_speakers"] = max_speakers
    diar = pipe(str(wav), **kw)
    # list of (start,end,label)
    return [(turn.start, turn.end, spk) for turn, _, spk in diar.itertracks(
        yield_label=True)]


def label_segments(segs, tracks):
    """Assign each transcript segment the speaker with most overlap."""
    # stable order of speaker labels
    labels = sorted({sp for _, _, sp in tracks})
    alias = {lab: f"SPK_{i}" for i, lab in enumerate(labels)}
    for s in segs:
        best, best_ov = None, 0.0
        for t0, t1, lab in tracks:
            ov = overlap(s["start"], s["end"], t0, t1)
            if ov > best_ov:
                best_ov, best = ov, lab
        s["speaker"] = alias[best] if best is not None else "SPK_0"
    return [alias[l] for l in labels]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir")
    ap.add_argument("--speakers", type=int, default=None,
                    help="known number of speakers (more accurate)")
    ap.add_argument("--min-speakers", type=int, default=None)
    ap.add_argument("--max-speakers", type=int, default=None)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    wd = common.resolve_workdir(args.workdir)
    segs = common.load_json(wd / "segments.json")
    if not segs:
        raise SystemExit("segments.json missing/empty; run transcribe first")

    spk_path = wd / "speakers.json"
    if spk_path.exists() and not args.force:
        print(f"[diarize] reuse {spk_path} (edit it to change voices)",
              file=sys.stderr)
        common.emit(common.load_json(spk_path))
        return

    wav = wd / "audio.wav"
    if not wav.exists():
        # transcribe normally creates it
        raise SystemExit("audio.wav missing; run transcribe first")

    tracks = run_pyannote(wav, args.speakers, args.min_speakers,
                          args.max_speakers)
    if tracks is None:
        print("[diarize] no HF token / model unavailable -> single speaker "
              "fast path (SPK_0). Set HF_TOKEN for multi-speaker detection.",
              file=sys.stderr)
        for s in segs:
            s["speaker"] = "SPK_0"
        used = ["SPK_0"]
    else:
        used = label_segments(segs, tracks)

    common.save_json(wd / "segments.json", segs)

    counts = {u: 0 for u in used}
    for s in segs:
        counts[s["speaker"]] = counts.get(s["speaker"], 0) + 1
    speakers_meta = []
    for i, u in enumerate(used):
        speakers_meta.append({
            "id": u,
            "n_segments": counts.get(u, 0),
            "voice": DEFAULT_VOICES[i % len(DEFAULT_VOICES)],
            "note": "edit voice/name; edge-tts voices in assets/voices.json",
        })
    common.save_json(spk_path, speakers_meta)
    common.emit({"n_speakers": len(used), "speakers": speakers_meta,
                 "review": str(spk_path)})


if __name__ == "__main__":
    main()
