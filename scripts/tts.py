#!/usr/bin/env python3
"""Synthesize English speech per segment with edge-tts.

Reads speakers.json for the speaker->voice map, writes tts/<id>.mp3 and a
manifest with each clip's natural duration. Alignment happens in mixaudio.
Re-running only synthesizes clips that are missing unless --force.
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402


async def synth_one(text, voice, out_path, retries=3):
    import edge_tts
    last = None
    for attempt in range(retries):
        try:
            comm = edge_tts.Communicate(text, voice, rate="+0%")
            await comm.save(str(out_path))
            if out_path.exists() and out_path.stat().st_size > 0:
                return
        except Exception as e:  # endpoint can be flaky
            last = e
            await asyncio.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"edge-tts failed for {out_path.name}: {last}")


# edge-tts pads clips with trailing silence; strip both ends (two-pass via
# reverse) without touching interior pauses, and normalize to 48k stereo.
TRIM = ("silenceremove=start_periods=1:start_threshold=-40dB:"
        "start_silence=0.03,areverse,"
        "silenceremove=start_periods=1:start_threshold=-40dB:"
        "start_silence=0.08,areverse,"
        "aresample=48000,aformat=channel_layouts=stereo")


async def run(segs, voice_map, tdir, force):
    manifest = common.load_json(tdir / "manifest.json", {})
    for s in segs:
        sid = s["id"]
        voice = voice_map.get(s.get("speaker")) or voice_map.get("__default__")
        key = str(sid)
        wav = tdir / f"{sid}.wav"
        if not force and wav.exists() and manifest.get(key, {}).get(
                "voice") == voice:
            continue
        mp3 = tdir / f"{sid}.mp3"
        await synth_one(s["en"], voice, mp3)
        common.run([common.FFMPEG, "-y", "-loglevel", "error", "-i", str(mp3),
                    "-af", TRIM, "-c:a", "pcm_s16le", str(wav)])
        dur = common.ffprobe_duration(wav)
        manifest[key] = {"file": wav.name, "raw": mp3.name, "voice": voice,
                         "dur": round(dur, 3),
                         "start": s["start"], "end": s["end"]}
        common.save_json(tdir / "manifest.json", manifest)
        print(f"[tts] {sid}: {voice} speech {dur:.2f}s "
              f"(slot {s['end']-s['start']:.2f}s)", file=sys.stderr)
    return manifest


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    wd = common.resolve_workdir(args.workdir)
    segs = common.load_json(wd / "segments.json")
    todo = [s for s in segs if s.get("en", "").strip()]
    if not todo:
        raise SystemExit("no English text; run inject_translation first")

    speakers = common.load_json(wd / "speakers.json", [])
    voice_map = {sp["id"]: sp["voice"] for sp in speakers}
    voice_map["__default__"] = (speakers[0]["voice"] if speakers
                                else "en-US-AndrewNeural")

    tdir = wd / "tts"
    tdir.mkdir(exist_ok=True)
    manifest = asyncio.run(run(todo, voice_map, tdir, args.force))

    over = [k for k, m in manifest.items()
            if m["dur"] > (m["end"] - m["start"]) + 0.05]
    common.emit({"synthesized": len(manifest),
                 "clips_longer_than_slot": len(over),
                 "note": "mixaudio will fit clips into slots"})


if __name__ == "__main__":
    main()
