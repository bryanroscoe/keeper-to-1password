#!/usr/bin/env python3
"""
Split a Keeper CSV export into separate per-owner files.

Useful for a *shared* Keeper vault that holds credentials belonging to more than
one person (e.g. a household or a team), so each owner can import only their own
items into their own 1Password account.

Classification is rule-based and fully transparent. All rules live in an external
JSON config (see ``split_rules.example.json``) so this script contains **no
personal data** and can be shared. The real config typically contains emails,
phone numbers, and sometimes passwords used as login values, so keep your own
``split_rules.json`` private (it is git-ignored by this repo).

Decision order for each row (first match wins):

    1. "other" routing      -> a domain hint that is NOT one of the owner's
                               self-hints (e.g. a coworker on a shared work domain)
    2. Exact-login override -> a hand-mapped owner for a specific login value
                               (use for numeric / gibberish / ambiguous logins)
    3. Device-login exact   -> generic logins like admin/user/root
    4. Substring patterns   -> checked in the order owners are listed in config
    5. Blank login?         -> fall back to Title/Website/Notes and re-check (4)
    6. Default owner

Output files are raw Keeper rows (no header), so each one is itself a valid
Keeper export you can feed straight into keeper_to_1password.py.

Usage:
    python3 split_keeper_vault.py EXPORT.csv --rules split_rules.json
    python3 split_keeper_vault.py EXPORT.csv --rules split_rules.json --prefix run1
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("login_index", 2)
    cfg.setdefault("fallback_indices", [1, 4, 5])  # Title, Website, Notes
    cfg.setdefault("owners", [])
    cfg.setdefault("default_owner", cfg["owners"][0] if cfg["owners"] else "default")
    cfg.setdefault("routing", {})       # {"other": {"domain_hints": [...], "exclude_self_hints": [...]}}
    cfg.setdefault("device_exact", {})  # {"admin": "owner_a", ...}
    cfg.setdefault("exact_overrides", {})
    cfg.setdefault("patterns", {})      # {"owner_a": [...substrings...], ...}

    # Normalize everything we compare against to lowercase.
    cfg["device_exact"] = {k.lower(): v for k, v in cfg["device_exact"].items()}
    cfg["exact_overrides"] = {k.lower(): v for k, v in cfg["exact_overrides"].items()}
    cfg["patterns"] = {o: [p.lower() for p in pats] for o, pats in cfg["patterns"].items()}
    return cfg


def match_patterns(text: str, cfg: dict) -> str | None:
    """Return the first owner (in config order) whose substring patterns hit."""
    for owner in cfg["owners"]:
        if any(p in text for p in cfg["patterns"].get(owner, [])):
            return owner
    return None


def classify(row: list[str], cfg: dict) -> tuple[str, str]:
    """Return (owner, reason)."""
    li = cfg["login_index"]
    login = row[li].strip().lower() if len(row) > li else ""

    # 1. "other" routing (e.g. a coworker on a shared domain).
    other = cfg["routing"].get("other")
    if other:
        hints = [h.lower() for h in other.get("domain_hints", [])]
        self_hints = [h.lower() for h in other.get("exclude_self_hints", [])]
        if any(h in login for h in hints) and not any(h in login for h in self_hints):
            return "other", "other routing"

    # 2. Exact-login override.
    if login in cfg["exact_overrides"]:
        return cfg["exact_overrides"][login], "exact override"

    # 3. Generic device login.
    if login in cfg["device_exact"]:
        return cfg["device_exact"][login], "device login"

    # 4. Substring patterns on the login.
    owner = match_patterns(login, cfg)
    if owner:
        return owner, "login pattern"

    # 5. Blank login -> fall back to Title/Website/Notes.
    if not login:
        text = " ".join(row[i].lower() for i in cfg["fallback_indices"] if len(row) > i)
        owner = match_patterns(text, cfg)
        if owner:
            return owner, "title fallback"

    # 6. Default.
    return cfg["default_owner"], "default"


def main() -> None:
    parser = argparse.ArgumentParser(description="Split a Keeper export into per-owner CSVs.")
    parser.add_argument("input", help="Keeper export CSV")
    parser.add_argument("--rules", required=True, help="JSON rules file (see split_rules.example.json)")
    parser.add_argument("--prefix", default="", help="Optional output filename prefix")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        raise SystemExit(f"Input file not found: {args.input}")
    if not os.path.exists(args.rules):
        raise SystemExit(f"Rules file not found: {args.rules}")

    cfg = load_config(args.rules)
    if not cfg["owners"]:
        raise SystemExit("Config must list at least one owner in 'owners'.")

    rows = list(csv.reader(open(args.input, newline="", encoding="utf-8")))
    if not rows:
        raise SystemExit("Input file is empty.")

    # An "other" bucket exists only if the config routes to it.
    bucket_names = list(cfg["owners"])
    if "other" in cfg["routing"] and "other" not in bucket_names:
        bucket_names.append("other")
    buckets: dict[str, list[list[str]]] = {name: [] for name in bucket_names}

    reasons: Counter = Counter()
    defaulted = []
    for row in rows:
        owner, reason = classify(row, cfg)
        buckets.setdefault(owner, []).append(row)
        reasons[(owner, reason)] += 1
        if reason == "default":
            li = cfg["login_index"]
            login = row[li].strip() if len(row) > li else ""
            title = row[1].strip() if len(row) > 1 else ""
            defaulted.append(login or f"(no login) [{title[:40]}]")

    p = (args.prefix + "_") if args.prefix else ""
    out_paths = {}
    for owner, owner_rows in buckets.items():
        path = f"{p}{owner}_logins.csv"
        if os.path.abspath(path) == os.path.abspath(args.input):
            raise SystemExit("Refusing to overwrite the input file.")
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(owner_rows)
        out_paths[owner] = path

    # --- Verification: every input row landed in exactly one output file -------
    total_out = sum(len(v) for v in buckets.values())
    assert total_out == len(rows), f"Row count mismatch: in={len(rows)} out={total_out}"

    # --- Report ----------------------------------------------------------------
    print(f"Split {len(rows)} rows from {args.input}:")
    for owner in buckets:
        print(f"  {owner:10s}: {len(buckets[owner]):5d}  -> {out_paths[owner]}")
    print(f"  verified: {total_out} out == {len(rows)} in  (no row lost or duplicated)")

    print("\nWhy rows were placed (owner, reason: count):")
    for (owner, reason), n in reasons.most_common():
        print(f"  {owner:10s} {reason:16s} {n}")

    if defaulted:
        print(f"\n{len(defaulted)} row(s) hit the default ('{cfg['default_owner']}') with no explicit match.")
        print("Spot-check these; add a rule if any are misfiled:")
        for login, n in Counter(defaulted).most_common(40):
            print(f"  {n:4d}  {login}")

    print("\nNext, convert each for 1Password (TOTP handling + verification):")
    for owner, path in out_paths.items():
        print(f"  python3 keeper_to_1password.py {path} {owner}_1password.csv")


if __name__ == "__main__":
    main()
