#!/usr/bin/env python3
"""
Convert a Keeper CSV export into a CSV that 1Password can import cleanly.

Why this exists
---------------
1Password's Keeper import guide (https://support.1password.com/import-keeper/)
says that one-time-password (TOTP) secrets are exported by Keeper as
`otpauth://...` URLs sitting inside an ordinary field. To import them as real
2FA codes you must move every `otpauth://` URL into its own dedicated column and
label that column "one-time password" during import.

This script does that automatically and safely:

  * It never overwrites the input file (output must be a different path).
  * Keeper exports have NO header row, so the OTP column index would otherwise
    differ from row to row. We pad every row to the same width and put the
    otpauth URL in a single, consistent final column.
  * The otpauth URL is removed from wherever it was found so it doesn't get
    imported twice (once as plain text, once as a real OTP).
  * A header row is written so the 1Password import wizard is easy to map.
  * A verification pass re-reads the output and asserts the conversion is sound.

Usage
-----
    python3 keeper_to_1password.py                       # keeper_export.csv -> 1password_import.csv
    python3 keeper_to_1password.py IN.csv OUT.csv         # explicit paths
    python3 keeper_to_1password.py --verify-only OUT.csv  # just verify an existing output

Keeper's default export column order (no header) is:
    Folder, Title, Login, Password, Website Address, Notes, [custom field pairs...]
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys

# Matches a full otpauth URL. Handles both `otpauth://totp?secret=...` and
# `otpauth://totp/Label?secret=...`. Stops at whitespace (a cell value from the
# csv module is already unquoted, so the URL is the rest of the token).
OTP_REGEX = re.compile(r"otpauth://[^\s]+", re.IGNORECASE)

# The fixed leading columns Keeper exports, in order. Anything after these is a
# variable number of custom-field name/value pairs.
BASE_HEADERS = ["Folder", "Title", "Login", "Password", "Website Address", "Notes"]

DEFAULT_INPUT = "keeper_export.csv"
DEFAULT_OUTPUT = "1password_import.csv"

OTP_COLUMN_NAME = "one-time password"


def extract_otp(row: list[str]) -> tuple[list[str], str]:
    """Return (cleaned_row, otp_url). Removes the first otpauth URL found from
    whichever cell contained it; returns "" if there is none."""
    otp_url = ""
    for i, cell in enumerate(row):
        match = OTP_REGEX.search(cell)
        if match:
            otp_url = match.group(0).strip()
            # Strip the URL out of the original cell so it isn't imported twice.
            row[i] = cell.replace(match.group(0), "").strip()
            break
    return row, otp_url


def convert(input_path: str, output_path: str) -> dict:
    if os.path.abspath(input_path) == os.path.abspath(output_path):
        raise SystemExit("Refusing to run: input and output paths are the same file.")
    if not os.path.exists(input_path):
        raise SystemExit(f"Input file not found: {input_path}")

    with open(input_path, newline="", encoding="utf-8") as infile:
        rows = list(csv.reader(infile))

    if not rows:
        raise SystemExit(f"Input file is empty: {input_path}")

    # Pull OTPs out and find the widest row so every output row lines up.
    cleaned: list[list[str]] = []
    otps: list[str] = []
    for row in rows:
        row, otp = extract_otp(row)
        cleaned.append(row)
        otps.append(otp)

    max_width = max(len(r) for r in cleaned)

    # Build a header that covers the base columns plus any extra custom-field
    # columns, then the dedicated OTP column as the final field.
    header = list(BASE_HEADERS)
    for n in range(len(BASE_HEADERS), max_width):
        header.append(f"Custom Field {n - len(BASE_HEADERS) + 1}")
    header.append(OTP_COLUMN_NAME)

    with open(output_path, "w", newline="", encoding="utf-8") as outfile:
        writer = csv.writer(outfile)
        writer.writerow(header)
        for row, otp in zip(cleaned, otps):
            padded = row + [""] * (max_width - len(row))
            padded.append(otp)
            writer.writerow(padded)

    otp_count = sum(1 for o in otps if o)
    return {
        "input_rows": len(rows),
        "output_data_rows": len(cleaned),
        "otp_extracted": otp_count,
        "total_columns": max_width + 1,
        "output_path": output_path,
    }


def verify(output_path: str, expected_data_rows: int | None = None) -> dict:
    """Re-read the output and assert the conversion is internally consistent.
    Raises SystemExit on any failure."""
    with open(output_path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    if not rows:
        raise SystemExit("Verification failed: output file is empty.")

    header, data = rows[0], rows[1:]
    problems: list[str] = []

    # 1. The OTP column must exist and be the final column.
    if header[-1] != OTP_COLUMN_NAME:
        problems.append(f"Last column is {header[-1]!r}, expected {OTP_COLUMN_NAME!r}.")
    otp_idx = len(header) - 1

    # 2. Every row must have the same width as the header.
    width = len(header)
    ragged = [i for i, r in enumerate(data, start=2) if len(r) != width]
    if ragged:
        problems.append(f"{len(ragged)} row(s) have a different column count (e.g. line {ragged[0]}).")

    # 3. No otpauth URL may remain in any column other than the OTP column.
    leaked = []
    for i, r in enumerate(data, start=2):
        for j, cell in enumerate(r):
            if j == otp_idx:
                continue
            if OTP_REGEX.search(cell):
                leaked.append((i, j))
    if leaked:
        problems.append(f"otpauth URL leaked into a non-OTP column at {len(leaked)} place(s) (e.g. line {leaked[0][0]}).")

    # 4. Every value in the OTP column must be empty or a valid otpauth URL with a secret.
    otp_values = [r[otp_idx] for r in data if len(r) > otp_idx]
    bad_otp = []
    otp_present = 0
    for i, val in enumerate(otp_values, start=2):
        if not val:
            continue
        otp_present += 1
        if not val.lower().startswith("otpauth://") or "secret=" not in val.lower():
            bad_otp.append(i)
    if bad_otp:
        problems.append(f"{len(bad_otp)} OTP value(s) are malformed (missing scheme or secret=).")

    # 5. Row count should match what we converted, if known.
    if expected_data_rows is not None and len(data) != expected_data_rows:
        problems.append(f"Row count mismatch: output has {len(data)} data rows, expected {expected_data_rows}.")

    if problems:
        print("VERIFICATION FAILED:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        raise SystemExit(1)

    return {"data_rows": len(data), "otp_present": otp_present, "columns": width}


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert a Keeper CSV export to a 1Password-importable CSV.")
    parser.add_argument("input", nargs="?", default=DEFAULT_INPUT, help=f"Keeper export CSV (default: {DEFAULT_INPUT})")
    parser.add_argument("output", nargs="?", default=DEFAULT_OUTPUT, help=f"Output CSV (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--verify-only", action="store_true", help="Skip conversion; only verify the given file (pass it as the first positional argument).")
    args = parser.parse_args()

    if args.verify_only:
        target = args.input
        result = verify(target)
        print(f"Verification passed: {target}")
        print(f"  data rows : {result['data_rows']}")
        print(f"  with OTP  : {result['otp_present']}")
        print(f"  columns   : {result['columns']}")
        return

    stats = convert(args.input, args.output)
    vresult = verify(stats["output_path"], expected_data_rows=stats["output_data_rows"])

    print(f"Conversion complete: {args.input} -> {stats['output_path']}")
    print(f"  rows converted   : {stats['output_data_rows']}")
    print(f"  OTP secrets moved: {stats['otp_extracted']}")
    print(f"  columns (incl. OTP): {stats['total_columns']}")
    print("Verification passed.")
    print()
    print("Next: import 1password_import.csv at 1Password.com -> your name -> Import data -> CSV File,")
    print(f'confirm items as "Login", and label the final column "{OTP_COLUMN_NAME}".')


if __name__ == "__main__":
    main()
