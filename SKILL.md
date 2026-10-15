---
name: bili-dub
description: Download a Bilibili video and produce an MP4 with burned-in English subtitles plus three switchable audio tracks (Chinese original, English dub, and an English-led mix). Transcription and TTS run locally/free; the translation is done by you, the loaded agent — no API keys required. Invoke with a Bilibili video URL, e.g. /bili-dub https://www.bilibili.com/video/BVxxxx.
---

# bili-dub — B站视频 → 英文字幕 + 英文配音 (MP4)

Turn a Bilibili link into an MP4 with:

- **hard-burned English subtitles** (always visible)
- **three audio tracks**, switchable in IINA/VLC/Plex/TV:
  1. Chinese original (default)
  2. English dub
  3. English dub + ducked Chinese background
- optional switchable English soft-subtitle track

**Division of labor.** Downloading, transcription, speaker diarization, TTS,
mixing and muxing are deterministic local scripts (free). **You, the agent,
perform the English translation inside this conversation** — so the user's AI
platform/model is reused and no translation API key is needed. You never
hand-write an SRT; you only fill the `en` field in batch JSON files and the
scripts own all timestamps.

## Commands

Run scripts with the skill's Python. `$SKILL` is this skill directory
(`~/.claude/skills/bili-dub`). Every script prints a JSON summary.

```bash
cd ~/.claude/skills/bili-dub
PY=.venv/bin/python
```

If the environment is missing (no `.venv` or `bin/ffenv`), run `./setup.sh`
once first (installs uv, Python deps, and a libass-enabled ffmpeg).

## Workflow

Go stage by stage. Stop at the two checkpoints marked ★ to get user input.

### 1. Download & probe
```bash
$PY scripts/download.py "<URL>"
# add --cookies cookies.txt  or  --sessdata <SESSDATA>  for HD / login-only
```
Probes title/uploader/duration/resolution/CC, then downloads the best media
into `work/<id>/source.mp4`. Report the title, duration, resolution, and
whether CC exists. If yt-dlp is blocked (412/403), retry with `--sessdata`
(the user can export SESSDATA from a logged-in browser), or fall back to
BBDown (see Troubleshooting).

### 2. Transcribe (Chinese, timestamped)
```bash
$PY scripts/transcribe.py <id> --model medium
```
Uses a downloaded CC subtitle when available, otherwise local
faster-whisper (`medium` is a good speed/accuracy balance on Apple Silicon;
use `large-v3` for max accuracy, `small` for a quick pass). Produces
`segments.json` (id/start/end/zh/speaker/en), `zh.srt`, and `audio.wav`.

### 3. Speaker diarization
```bash
$PY scripts/diarize.py <id>          # auto-detect speaker count
#   $PY scripts/diarize.py <id> --speakers 2   when the count is known
```
Needs a free HuggingFace token for multi-speaker detection: put it in
`assets/hf_token` or `HF_TOKEN`, and accept the model terms at
https://hf.co/pyannote/speaker-diarization-3.1 once. **Without a token it
uses the single-speaker fast path** — correct for most narration videos.

★ **CHECKPOINT — confirm voices.** Open `work/<id>/speakers.json`. It lists
each speaker with segment count and a default edge-tts voice. Ask the user to
confirm, or edit voices yourself from `assets/voices.json`. For a 1-speaker
video this is trivial — glance and continue.

### 4. Translate (YOU do this)
```bash
$PY scripts/export_lines.py <id> [--batch-size 60]
```
Writes `work/<id>/translate/batch_001.json`, … each with
`lines: [{id, speaker, zh, en}]`. Then:

1. Read `work/<id>/translate/glossary.json`; add fixed renderings for any
   names/terms (ask the user when unsure) and honor them everywhere.
2. For **each batch file**, fill every `"en"` with natural, concise English
   suited to dubbing:
   - match the speaker's tone; keep it **short** (English is spoken into a
     fixed time slot — prefer tight phrasing over literal length)
   - do **not** change `id`, `speaker`, or `zh`; one entry per id; keep valid
     JSON (escape quotes/newlines; avoid literal newlines in a line)
   - leave numbers, names and brand terms consistent across batches
3. Write the file back, then merge:
```bash
$PY scripts/inject_translation.py <id>
```
The injector validates ids/count/non-empty `en` and refuses on any problem —
fix the reported lines and re-run. It produces `work/<id>/en.srt`. On success
the translation checkpoint is complete.

For very long videos, process batches sequentially; never silently drop a
line. If the user wants unattended batch processing instead, a CLI translator
can be added later (`providers/translate_cli.sh`) — the default needs no key.

### 5. Synthesize English speech
```bash
$PY scripts/tts.py <id>
```
edge-tts renders each segment with its speaker's voice into `work/<id>/tts/`
and records natural durations. Free, network-based, no key. Re-run is
incremental; `--force` re-synthesizes.

### 6. Build the three audio tracks
```bash
$PY scripts/mixaudio.py <id>
```
Places clips on the timeline, gently speeding up (`atempo`, capped 1.15x)
when a clip exceeds its slot, and writes `zh.m4a`, `en.m4a`, and the ducked
`mix.m4a`.

### 7. Burn subtitles & mux MP4
```bash
$PY scripts/mux.py <id>
```
Encodes the video with burned English subtitles and all three audio tracks
(+ a switchable English soft-subs track) into `output/<title>.mp4`. Use
`--crf 18` for higher quality, `--no-softsub` to skip the soft track.

★ Tell the user the final path and how to switch tracks (IINA/VLC audio menu).

## Resume / re-run

Every stage is idempotent and keyed by files in `work/<id>/`. Re-running a
script reuses its outputs; pass `--force` where supported to regenerate. To
re-translate a single line, edit its `en` in `segments.json` (or its batch
file), re-run `inject_translation.py`, then `tts.py` (incremental),
`mixaudio.py`, `mux.py`.

## Troubleshooting

- **412/403 on download or search:** pass `--sessdata`/`--cookies`; avoid the
  search extractor (use direct video URLs). Bilibili anti-bot changes often.
- **BBDown fallback:** for login-only / high-bitrate / special content,
  BBDown (https://github.com/nilaoda/BBDown) often succeeds where yt-dlp
  fails; download its CLI, save media as `work/<id>/source.mp4`, and continue
  from stage 2.
- **pyannote model errors:** confirm HF token and that both model-term pages
  were accepted; otherwise the single-speaker path still works.
- **subtitles filter missing:** the conda ffmpeg has libass; do not swap in a
  minimal ffmpeg. Re-run `./setup.sh`.
- **English clip too long even at cap:** shorten that line's `en` and re-run
  stages 4→7 rather than accepting an unnatural speed-up.

## Scope

Personal learning / authorized use only. DRM, paid-member-only content you
are not entitled to, and interactive videos are out of scope. High-fidelity
voice cloning is a later phase that only replaces the TTS backend in stage 5;
the diarization and timeline stay unchanged.
