#!/usr/bin/env python3
"""Export untranslated Chinese lines into batch files for the agent.

Writes translate/batch_001.json ... each shaped:
  {"batch": 1, "lines": [{"id": 0, "speaker": "SPK_0",
                          "zh": "...", "en": ""}, ...]}
The agent fills ONLY the "en" fields, preserving id/speaker/zh, then
inject_translation.py merges them back by id. The agent never edits the SRT.

Also creates a glossary.json template for consistent names/terminology.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir")
    ap.add_argument("--batch-size", type=int, default=60)
    ap.add_argument("--all", action="store_true",
                    help="re-export lines already translated too")
    args = ap.parse_args(argv)

    wd = common.resolve_workdir(args.workdir)
    segs = common.load_json(wd / "segments.json")
    if not segs:
        raise SystemExit("segments.json missing/empty")

    tdir = wd / "translate"
    tdir.mkdir(exist_ok=True)
    gloss = tdir / "glossary.json"
    if not gloss.exists():
        common.save_json(gloss, {"_help": "add fixed translations for names / "
                                          "terms; the agent follows these",
                                 "terms": []})

    todo = [s for s in segs if args.all or not s.get("en", "").strip()]
    batches = []
    for i in range(0, len(todo), args.batch_size):
        chunk = todo[i:i + args.batch_size]
        bn = i // args.batch_size + 1
        bf = tdir / f"batch_{bn:03d}.json"
        payload = {"batch": bn,
                   "instruction": "Fill every 'en' with natural English. "
                                  "Keep id unchanged. Leave one line per id.",
                   "lines": [{"id": s["id"], "speaker": s.get("speaker"),
                              "zh": s["zh"], "en": ""} for s in chunk]}
        common.save_json(bf, payload)
        batches.append({"file": str(bf), "lines": len(chunk)})

    total = len(segs)
    done = total - len(todo)
    common.emit({"total": total, "already_translated": done,
                 "exported": len(todo), "batch_size": args.batch_size,
                 "batches": batches,
                 "glossary": str(gloss),
                 "next": "agent fills 'en' in each batch file, then run "
                         "inject_translation.py"})


if __name__ == "__main__":
    main()
