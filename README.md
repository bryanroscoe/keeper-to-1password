# keeper-to-1password

A small, dependency-free Python script that converts a **Keeper** CSV export into a
CSV that **1Password** can import cleanly — with special handling for one-time
password (TOTP) secrets, and a built-in verification pass.

Based on 1Password's official guide:
<https://support.1password.com/import-keeper/>

## Why this is needed

Keeper exports two-factor secrets as `otpauth://...` URLs sitting inside an
ordinary field. To have 1Password import them as real, working 2FA codes, every
`otpauth://` URL has to be moved into its own dedicated column labeled
**`one-time password`** during import. Keeper exports also have **no header row**
and a **variable number of trailing custom-field columns**, which means a naive
"append OTP to the end" approach puts the OTP in a different column position on
every row — and 1Password can't map it.

This script handles all of that:

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

## Usage

Requires only Python 3 (standard library — no `pip install`).

```bash
# Defaults: keeper_export.csv -> 1password_import.csv
python3 keeper_to_1password.py

# Explicit input/output paths
python3 keeper_to_1password.py my-keeper-export.csv 1password_import.csv

# Verify an already-generated output file
python3 keeper_to_1password.py --verify-only 1password_import.csv
```

## Importing into 1Password

1. Run the script to produce `1password_import.csv`.
2. Go to <https://1password.com>, sign in, select your name (top right) →
   **Import data** → **CSV File**.
3. Confirm all items as **Login**.
4. Label the final column **`one-time password`** so TOTP secrets import as real
   2FA codes. Optionally label a folder column as **`tag`**.
5. After import, recategorize any non-login items (credit cards, identities) by
   hand — Keeper exports them as text fields inside Login items.

## ⚠️ Security

**These CSV files contain your live passwords and 2FA secrets in plaintext.**

- All `*.csv` files are git-ignored by this repo — they will not be committed.
- Delete both the Keeper export and the generated `1password_import.csv` as soon
  as the import succeeds:
  ```bash
  rm keeper_export.csv 1password_import.csv      # or use: shred -u <file>
  ```
- Do not email, sync, or upload these files anywhere.

## License

MIT
