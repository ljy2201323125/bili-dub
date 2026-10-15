#!/usr/bin/env python3
"""bili-dub unified command-line entrypoint.

Subcommands (positional):
  probe <url> [--cookies f] [--sessdata x]
  transcribe <url> [--model s] [--force] [--speakers n] [--cookies f] [--sessdata x]
  dub <url> [--tts edge|skip] [--model s] [--crf N] [--preset p]
            [--no-soft-sub] [--speakers n] [--cookies f] [--sessdata x]
  all = alias for dub (download..mux). Most users just call:
      python scripts/cli.py dub "<url>"
"""
import argparse
import sys

from download import main as download_main
from transcribe import main as transcribe_main
from diarize import main as diarize_main
from export_lines import main as export_main
from inject_translation import main as inject_main
from tts import main as tts_main
from mixaudio import main as mixaudio_main
from mux import main as mux_main


STAGES = {
    "download": download_main,
    "transcribe": transcribe_main,
    "diarize": diarize_main,
    "export": export_main,
    "inject": inject_main,
    "tts": tts_main,
    "mixaudio": mixaudio_main,
    "mux": mux_main,
}


def _forward(parser_fn, argv, drop=()):
    """Run a stage script's argparse main with a reconstructed argv list."""
    return parser_fn(argv)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        print("Available stages: " + ", ".join(STAGES))
        return 0

    stage = argv.pop(0)
    rest = argv

    if stage in ("probe",):
        return download_main(["--limit"] + rest)
    if stage == "transcribe":
        return transcribe_main(rest)
    if stage == "dub" or stage == "all":
        # Full pipeline. Each stage parses its own flags from `rest`; we route
        # the common superset of args through each. Unknown args are ignored by
        # the individual parsers only if we pass them explicitly, so instead we
        # re-invoke each stage's main with the full `rest` -- stages already
        # accept a superset via argparse (they ignore nothing, so we filter).
        return run_full(rest)
    if stage in STAGES:
        return STAGES[stage](rest)
    print(f"Unknown subcommand: {stage}\n{__doc__}", file=sys.stderr)
    return 2


def _keep(rest, *names):
    """Keep only flags whose long/short name is in `names`, with their value."""
    takes_value = {
        "--cookies", "--sessdata", "--model", "--speakers", "--batch-size",
        "--crf", "--preset", "--tts", "--duck-level",
    }
    bool_flags = {"--force", "--no-soft-sub"}
    aliases = {
        "--cookies": ["--cookies"], "--sessdata": ["--sessdata"],
        "--model": ["--model"], "--speakers": ["--speakers"],
        "--batch-size": ["--batch-size"], "--crf": ["--crf"],
        "--preset": ["--preset"], "--tts": ["--tts"],
        "--duck-level": ["--duck-level"],
        "--force": ["--force"], "--no-soft-sub": ["--no-soft-sub"],
    }
    out, i = [], 0
    while i < len(rest):
        tok = rest[i]
        key = tok.split("=")[0]
        if key in takes_value:
            if key not in names:
                i += 1 if "=" in tok else 2
                continue
            out.append(tok)
            if "=" not in tok and i + 1 < len(rest):
                out.append(rest[i + 1])
            i += 1 if "=" in tok else 2
        elif key in bool_flags:
            if key in names:
                out.append(tok)
            i += 1
        else:
            i += 1
    return out


def run_full(rest):
    # 1 download (needs url, cookies/sessdata)
    url = next((a for a in rest if not a.startswith("-")), None)
    if not url:
        print("error: a Bilibili URL is required", file=sys.stderr)
        return 2
    dl = _keep(rest, "--cookies", "--sessdata")
    download_main([url] + dl)
    # 2 transcribe
    transcribe_main([url] + _keep(rest, "--model", "--force", "--speakers",
                                  "--cookies", "--sessdata"))
    # 3 tts (handles translation checkpoint + edge/skip)
    tts_main([url] + _keep(rest, "--model", "--force", "--speakers"))
    # 4 mix
    mixaudio_main([url] + _keep(rest, "--duck-level"))
    # 5 mux
    mux_main([url] + _keep(rest, "--crf", "--preset", "--no-soft-sub"))
    print("\n=== bili-dub pipeline complete ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
