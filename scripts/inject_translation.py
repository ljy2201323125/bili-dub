#!/usr/bin/env python3
"""Validate agent-filled batch files and merge English back into timeline.

Reads translate/batch_*.json, enforces:
  - every line keeps a valid integer id that exists in segments.json
  - every 'en' is non-empty
  - duplicate ids across files agree
Then writes segments.json and en.srt. The script owns timestamps/order.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir")
    args = ap.parse_args(argv)

    wd = common.resolve_workdir(args.workdir)
    segs = common.load_json(wd / "segments.json")
    by_id = {s["id"]: s for s in segs}

    tdir = wd / "translate"
    batches = sorted(tdir.glob("batch_*.json"))
    if not batches:
        raise SystemExit("no translate/batch_*.json; run export_lines first")

    filled, errors = {}, []
    for bf in batches:
        data = common.load_json(bf)
        for ln in data.get("lines", []):
            lid = ln.get("id")
            en = (ln.get("en") or "").strip()
            if not isinstance(lid, int) or lid not in by_id:
                errors.append(f"{bf.name}: unknown/missing id {lid!r}")
                continue
            if not en:
                errors.append(f"{bf.name}: id {lid} has empty 'en'")
                continue
            if lid in filled and filled[lid] != en:
                errors.append(f"id {lid} translated inconsistently in "
                              f"{bf.name}")
            filled[lid] = en

    if errors:
        print("VALIDATION FAILED:\n- " + "\n- ".join(errors[:50]),
              file=sys.stderr)
        if len(errors) > 50:
            print(f"... and {len(errors) - 50} more", file=sys.stderr)
        raise SystemExit(1)

    for lid, en in filled.items():
        by_id[lid]["en"] = en

    missing = [s["id"] for s in segs if not s.get("en", "").strip()]
    common.save_json(wd / "segments.json", segs)
    common.write_srt(segs, wd / "en.srt", text_key="en")
    common.emit({"merged": len(filled),
                 "still_untranslated": len(missing),
                 "missing_ids": missing[:20],
                 "srt": str(wd / "en.srt")})


if __name__ == "__main__":
    main()
