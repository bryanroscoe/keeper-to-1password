# keeper-to-1password

A small, dependency-free toolkit for migrating from **Keeper** to **1Password**.
The core script converts a Keeper CSV export into a CSV that 1Password imports
cleanly — with proper handling of one-time-password (TOTP) secrets and a built-in
verification pass. Two optional helpers deal with messier real-world exports
(shared vaults and ragged custom-field columns).

Requires only **Python 3** (standard library — no `pip install`). Based on
1Password's official guide: <https://support.1password.com/import-keeper/>

## What's included

| File | Purpose |
|------|---------|
| `keeper_to_1password.py` | Convert a Keeper CSV export → a 1Password-importable CSV (TOTP-aware, verified). |
| `split_keeper_vault.py` | *(optional)* Split a shared Keeper vault into one raw export per owner. |
| `fold_to_notes.py` | *(optional)* Fold ragged trailing custom-field columns into the Notes column. |
| `split_rules.example.json` | Example config for the splitter (copy to `split_rules.json` and edit). |

## Why the converter is needed

Keeper exports two-factor secrets as `otpauth://...` URLs sitting inside an
ordinary field. To have 1Password import them as real, working 2FA codes, every
`otpauth://` URL has to be moved into its own dedicated column labeled
**`one-time password`** during import. Keeper exports also have **no header row**
and a **variable number of trailing custom-field columns**, which means a naive
"append OTP to the end" approach puts the OTP in a different column position on
every row — and 1Password can't map it.

`keeper_to_1password.py` handles all of that:

- **Never overwrites your input.** Input and output must be different files; it
  refuses to run otherwise.
- **No header-row assumption.** Keeper exports have no header, so it doesn't eat
  your first credential as headers.
- **Consistent OTP column.** Every row is padded to the same width and the
  `otpauth://` URL is placed in a single final column, so the OTP maps cleanly.
- **No double-import.** The OTP URL is removed from wherever it was found so it
  isn't imported both as plain text and as a real OTP.
- **Verification pass.** After writing, it re-reads the output and asserts:
  row count is preserved, all rows are the same width, no `otpauth://` leaked
  into a non-OTP column, and every OTP value is a valid `otpauth://...secret=...`.

## Quick start

```bash
# Defaults: keeper_export.csv -> 1password_import.csv
python3 keeper_to_1password.py

# Explicit input/output paths
python3 keeper_to_1password.py my-keeper-export.csv 1password_import.csv

# Verify an already-generated output file
python3 keeper_to_1password.py --verify-only 1password_import.csv
```

Then [import into 1Password](#importing-into-1password).

## Optional: shared vaults & messy exports

If a single Keeper vault holds credentials for more than one person, or the
export has lots of custom fields, run the helpers **before** the converter:

```bash
# 1. Split a shared vault into one raw Keeper export per owner.
cp split_rules.example.json split_rules.json   # then edit for your owners
python3 split_keeper_vault.py keeper_export.csv --rules split_rules.json
#   -> alice_logins.csv, bob_logins.csv, (other_logins.csv) ...

# 2. (optional) Flatten ragged custom-field columns into Notes.
python3 fold_to_notes.py alice_logins.csv alice_clean.csv

# 3. Convert each person's file for 1Password.
python3 keeper_to_1password.py alice_clean.csv alice_1password.csv
```

### `split_keeper_vault.py` — split a shared vault by owner

Splits the export into one raw Keeper CSV per owner, so each person imports only
their own items. Classification is rule-based and fully transparent — **all rules
live in an external JSON config**, so the script itself contains no personal data.
See `split_rules.example.json` for the format (owners, substring patterns,
exact-login overrides, and an optional "other" route for shared/coworker logins).
Each output file is itself a valid Keeper export. The run prints a per-owner
count, why each row was placed, and a list of rows that hit the default owner so
you can spot-check and refine your rules.

> Your real `split_rules.json` usually contains emails, phone numbers, and
> sometimes passwords used as login values, so it is **git-ignored**. Only
> `split_rules.example.json` (placeholder data) is committed.

### `fold_to_notes.py` — flatten ragged custom-field columns

Keeper exports have a variable number of trailing custom-field columns. This
folds every non-empty custom field into the Notes column, producing a clean,
fixed 6-column file. It verifies losslessly and exits non-zero if any non-empty
cell would be dropped.

```bash
python3 fold_to_notes.py keeper_export.csv keeper_clean.csv
```

## Importing into 1Password

1. Run the converter to produce `1password_import.csv`.
2. Go to <https://1password.com>, sign in, select your name (top right) →
   **Import data** → **CSV File**.
3. Confirm all items as **Login**.
4. Label the final column **`one-time password`** so TOTP secrets import as real
   2FA codes. Optionally label a folder column as **`tag`**.
5. After import, recategorize any non-login items (credit cards, identities) by
   hand — Keeper exports them as text fields inside Login items.

## Limitations (what Keeper exports leave out)

These aren't bugs in this tool — Keeper itself does not include them in exports,
so they can't be converted and must be handled separately:

- **Passkeys can't be file-imported.** Keeper does export passkey records, but
  there is no supported file-based path to load them into 1Password. Passkey
  portability uses the FIDO Credential Exchange standard, which 1Password
  currently supports only as on-device, app-to-app transfer — not a file import.
  Plan to **re-register passkeys per site**. Keep any passkey-only accounts
  (no password backup) accessible in Keeper until you've redone them.
- **Credit cards / payment info are not exported.** Keeper excludes Payment Cards
  and Personal Info from CSV and JSON exports by design. **Re-enter them by hand**
  in 1Password using the Credit Card item type.

## ⚠️ Security

**Keeper exports and the converted CSVs contain your live passwords and 2FA
secrets in plaintext.**

- `*.csv`, `*.json`, and your real `split_rules.json` are **git-ignored** by this
  repo, so they won't be committed. (Only `split_rules.example.json` is tracked.)
- Delete the Keeper export and every generated CSV as soon as the import succeeds:
  ```bash
  rm keeper_export.csv *_1password.csv *_logins.csv *_clean.csv
  ```
  (macOS has no `shred`; the files bypass Trash with `rm`. Note that copies may
  persist in Time Machine / iCloud backups.)
- Do not email, sync, or upload these files anywhere.

## License

MIT
