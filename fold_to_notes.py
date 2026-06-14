#!/usr/bin/env python3
"""
Fold a Keeper export's trailing custom-field columns into the Notes column.

Keeper CSV layout: 0 Folder, 1 Title, 2 Login, 3 Password, 4 Website, 5 Notes,
then a variable number of custom-field columns (6+). Those extra columns make
the file ragged and don't map cleanly on import. This script appends every
non-empty custom field into Notes, producing a clean, fixed 6-column file.

It verifies losslessly: every non-empty input cell must survive somewhere in the
corresponding output row.

Usage:
    python3 fold_to_notes.py INPUT.csv OUTPUT.csv
"""

from __future__ import annotations

import argparse
import csv
import os


def fold(infile: str, outfile: str) -> tuple[list[list[str]], list[list[str]]]:
    rows = list(csv.reader(open(infile, newline="", encoding="utf-8")))
    out = []
    for r in rows:
        base = (r + [""] * 6)[:6]
        extras = [c.strip() for c in r[6:] if c.strip()]
        notes = base[5]
        if extras:
            notes = (notes + ("\n\n" if notes else "") +
                     "Keeper custom fields:\n" + "\n".join(extras))
        out.append([base[0], base[1], base[2], base[3], base[4], notes])
    with open(outfile, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(out)
    return rows, out


def main() -> None:
    parser = argparse.ArgumentParser(description="Fold Keeper custom fields into Notes.")
    parser.add_argument("input", help="Keeper export CSV")
    parser.add_argument("output", help="Output CSV (6 columns)")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        raise SystemExit(f"Input file not found: {args.input}")
    if os.path.abspath(args.input) == os.path.abspath(args.output):
        raise SystemExit("Refusing to overwrite the input file.")

    rows, out = fold(args.input, args.output)

    lost = 0
    for r, o in zip(rows, out):
        blob = "\n".join(o)
        for c in r:
            if c.strip() and c.strip() not in blob:
                lost += 1
    print(f"{len(rows)} rows -> {args.output} (6 cols) | non-empty cells lost: {lost}")
    if lost:
        raise SystemExit("Verification failed: some non-empty cells were dropped.")


if __name__ == "__main__":
    main()
