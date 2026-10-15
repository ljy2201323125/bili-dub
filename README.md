# bili-dub

Give an AI assistant a Bilibili link, and get back an MP4 with **burned-in
English subtitles** and **three switchable audio tracks**:

1. Chinese original
2. English dub
3. English dub led, with the Chinese audio ducked underneath

Everything deterministic (download, transcription, TTS, mixing, muxing) runs
locally via small scripts. The **translation itself is done by your AI
assistant in the conversation** — so it works on top of whatever model /
platform you already use, and **no translation API key is required**.

## Why it works with (almost) any AI tool

The pipeline is plain Python plus ffmpeg and is driven by a single `SKILL.md`
prompt. Any AI coding assistant that can read a folder and run shell commands
can follow it — Claude Code, Cursor, Windsurf, Cline, a ChatGPT/Codex-style
agent with a terminal, etc. You don't need an account or an API key for the
translation step; the assistant *is* the translator.

## Requirements

- **macOS** (Apple Silicon or Intel) or **Linux**. On **Windows**, use
  **WSL (Ubuntu)** and run `setup.sh` there. (The Python pipeline itself is
  cross-platform; if you already have a libass-enabled ffmpeg on PATH you can
  even run it natively.)
- `bash`, `curl`, `tar` (preinstalled on macOS/Linux/WSL).
- A few GB free for the models and a network connection (first run downloads
  Python packages, ffmpeg, and a Whisper model).

## Install

```bash
# 1. get the skill
git clone https://github.com/<your-username>/bili-dub.git
cd bili-dub

# 2. one-time bootstrap: Python venv + a full ffmpeg (libass)
./setup.sh
```

`setup.sh` is idempotent — re-run it any time. It installs everything **inside
this folder** (a `.venv/` and `bin/ffenv/`); it does not touch your system. If
you already have an ffmpeg with the `subtitles` (libass) filter on PATH, it uses
that and skips the ffmpeg download.

### Optional: multi-speaker voices

By default all speakers share one English voice — correct for narration
videos. To detect and voice multiple speakers, create a free Hugging Face
token, accept the model terms once at
<https://hf.co/pyannote/speaker-diarization-3.1>, and expose the token:

```bash
export HF_TOKEN=hf_xxx          # or: echo hf_xxx > assets/hf_token
```

Without a token the pipeline automatically uses the single-speaker path.

## Use with an AI assistant

### Claude Code

Clone or symlink this folder into your skills directory so it loads as a skill:

```bash
git clone https://github.com/<your-username>/bili-dub.git \
  ~/.claude/skills/bili-dub
~/.claude/skills/bili-dub/setup.sh
```

Then just say, in Claude Code:

```
Use bili-dub on https://www.bilibili.com/video/BVxxxxxxxx
```

### Any other AI tool (Cursor / generic agent / etc.)

1. Open/claude this `bili-dub` folder in the tool (or clone it into your project).
2. Tell the assistant to read `SKILL.md` and run it:

```
Read SKILL.md and follow it to dub this video:
https://www.bilibili.com/video/BVxxxxxxxx
```

The assistant will install deps if needed, then walk the 7 stages, pausing at
the two checkpoints (confirm voices; review/perform the translation).

### Run it yourself without an assistant

The pipeline is also a plain CLI:

```bash
.venv/bin/python scripts/cli.py dub "https://www.bilibili.com/video/BVxxxx"
# optional: --sessdata <SESSDATA> for HD / login-only video
#           --model large-v3 for max transcription accuracy
#           --crf 18 for higher output quality
```

You will still need to supply the English translation at the checkpoint (fill
the `en` fields in `work/<id>/translate/batch_*.json`) — that is the one step an
AI normally does for you.

## Output

A single MP4 in `output/<title>.mp4`:

- hard-burned English subtitles
- 3 audio tracks (Chinese / English dub / ducked mix), switchable in the audio
  menu of IINA, VLC, Plex, a TV, etc.
- an optional switchable English soft-subtitle track

## How it works

| Stage | Script | What it does |
|------|--------|--------------|
| 1 | `download.py` | probe + download best media with yt-dlp |
| 2 | `transcribe.py` | CC if present, else local faster-whisper |
| 3 | `diarize.py` | optional speaker separation (pyannote) |
| 4 | `export_lines.py` / `inject_translation.py` | checkpoint where the **assistant translates** |
| 5 | `tts.py` | edge-tts neural speech, per speaker voice |
| 6 | `mixaudio.py` | place clips, gentle `atempo`, build 3 tracks |
| 7 | `mux.py` | burn subtitles + mux everything to MP4 |

The scripts own all timestamps; the assistant only fills text fields, so it can
never hand-write a broken SRT.

## Troubleshooting

- **412/403 on download:** pass `--sessdata <SESSDATA>` (export it from a
  logged-in browser) or a `--cookies cookies.txt`. Bilibili anti-bot changes
  often; direct video URLs work better than search.
- **BBDown fallback:** for login-only / high-bitrate content,
  [BBDown](https://github.com/nilaoda/BBDown) often succeeds where yt-dlp fails;
  save the media as `work/<id>/source.mp4` and continue from stage 2.
- **`subtitles` filter missing:** you need the full libass ffmpeg, not a minimal
  build — re-run `./setup.sh`.
- **pyannote errors:** confirm the HF token and that the model terms were
  accepted; the single-speaker path still works without it.
- **An English clip is too long:** shorten that line's `en` and re-run stages
  4→7 instead of accepting an unnatural speed-up.

## Scope

Personal learning and authorized use only. DRM, paid-member-only content you
are not entitled to, and interactive videos are out of scope. High-fidelity
voice cloning is a possible later phase that only replaces the TTS backend in
stage 5.

## License

[MIT](LICENSE)
