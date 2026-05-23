#!/usr/bin/env python3
"""Create a Customer File Custom Audience from a CSV of emails/phones.

Hashes email + phone with SHA-256 (lowercased + trimmed for email; digits-only
E.164 without leading '+' for phone) and uploads in 10k-row batches per Meta's
Audience API requirements.

Usage:
  python scripts/create_custom_audience.py --csv path.csv --name "My Audience" --account-id act_X --dry-run
  python scripts/create_custom_audience.py --csv path.csv --name "My Audience" --account-id act_X --confirm

Phone normalization: defaults to Israel (+972), strips leading 0 if present.
Override with --country-code 1 for US, etc. Numbers already in international
format (10+ digits starting with country code) are detected automatically.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
from pathlib import Path

from meta_client import get, normalize_account_id, post, print_json

BATCH_SIZE = 10000


def normalize_email(raw: str) -> str | None:
    if not raw:
        return None
    s = raw.strip().lower()
    if "@" not in s or "." not in s:
        return None
    return s


def normalize_phone(raw: str, default_cc: str = "972") -> str | None:
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None
    # Strip leading 0 (Israeli format like 0509...)
    if digits.startswith("0"):
        digits = digits.lstrip("0")
    # If already starts with country code (>= len(cc) + 7 digits), keep as-is
    if digits.startswith(default_cc) and len(digits) >= len(default_cc) + 7:
        return digits
    # Otherwise prepend default country code
    return default_cc + digits


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def parse_csv(path: Path, country_code: str) -> tuple[list[tuple[str, str]], dict]:
    """Return (records, stats). Each record is (email_hash, phone_hash)."""
    records: list[tuple[str, str]] = []
    stats = {
        "total_rows": 0,
        "email_only": 0,
        "phone_only": 0,
        "both": 0,
        "skipped_empty": 0,
        "invalid_email": 0,
        "invalid_phone": 0,
    }
    with path.open("r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            stats["total_rows"] += 1
            raw_email = (row.get("email") or row.get("Email") or row.get("EMAIL") or "").strip()
            raw_phone = (row.get("phone") or row.get("Phone") or row.get("PHONE") or "").strip()
            if not raw_email and not raw_phone:
                stats["skipped_empty"] += 1
                continue
            email = normalize_email(raw_email)
            phone = normalize_phone(raw_phone, default_cc=country_code)
            if raw_email and not email:
                stats["invalid_email"] += 1
            if raw_phone and not phone:
                stats["invalid_phone"] += 1
            if not email and not phone:
                continue
            email_h = sha256_hex(email) if email else ""
            phone_h = sha256_hex(phone) if phone else ""
            records.append((email_h, phone_h))
            if email and phone:
                stats["both"] += 1
            elif email:
                stats["email_only"] += 1
            else:
                stats["phone_only"] += 1
    return records, stats


def create_audience(account_id: str, name: str, description: str) -> str:
    """POST to create the audience shell. Returns audience ID."""
    resp = post(
        f"{account_id}/customaudiences",
        data={
            "name": name,
            "description": description,
            "subtype": "CUSTOM",
            "customer_file_source": "USER_PROVIDED_ONLY",
        },
    )
    return resp["id"]


def upload_users(audience_id: str, records: list[tuple[str, str]]) -> dict:
    """Upload hashed user records in batches of 10k."""
    schema = ["EMAIL_SHA256", "PHONE_SHA256"]
    total_received = 0
    invalid_entries = 0
    batches = 0
    session_id = int(time.time())
    num_batches = (len(records) + BATCH_SIZE - 1) // BATCH_SIZE
    for batch_idx in range(0, len(records), BATCH_SIZE):
        batch = records[batch_idx : batch_idx + BATCH_SIZE]
        is_last = batch_idx + BATCH_SIZE >= len(records)
        payload = {
            "schema": schema,
            "data": [[e, p] for e, p in batch],
        }
        session = {
            "session_id": session_id,
            "estimated_num_total": len(records),
            "batch_seq": batches + 1,
            "last_batch_flag": is_last,
        }
        resp = post(
            f"{audience_id}/users",
            data={
                "payload": json.dumps(payload),
                "session": json.dumps(session),
            },
        )
        total_received += resp.get("num_received", 0)
        invalid_entries += resp.get("num_invalid_entries", 0)
        batches += 1
        print(
            f"[+] batch {batches}/{num_batches}: received={resp.get('num_received')} invalid={resp.get('num_invalid_entries')}",
            file=sys.stderr,
        )
    return {
        "batches": batches,
        "num_received_total": total_received,
        "num_invalid_total": invalid_entries,
        "session_id": session_id,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="CSV with 'email' and/or 'phone' columns")
    ap.add_argument("--name", required=True, help="Audience name as it will appear in Ads Manager")
    ap.add_argument("--description", default="Customer file uploaded via API", help="Audience description")
    ap.add_argument("--account-id", required=False, help="Ad account ID (uses env default if omitted)")
    ap.add_argument("--country-code", default="972", help="Default country code for phones without one (default: 972 Israel)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--confirm", action="store_true")
    args = ap.parse_args()

    csv_path = Path(args.csv).expanduser()
    if not csv_path.is_absolute():
        csv_path = (Path.cwd() / csv_path).resolve()
    if not csv_path.exists():
        print_json({"ok": False, "error": f"CSV not found: {csv_path}"})
        return 1

    account_id = normalize_account_id(args.account_id)

    print(f"[i] reading {csv_path}", file=sys.stderr)
    records, stats = parse_csv(csv_path, country_code=args.country_code)

    if args.dry_run:
        out = {
            "ok": True,
            "mode": "dry-run",
            "csv": str(csv_path),
            "account_id": account_id,
            "audience_name": args.name,
            "stats": stats,
            "records_to_upload": len(records),
            "sample_hashes": [
                {"email_sha256": e[:12] + "…" if e else None, "phone_sha256": p[:12] + "…" if p else None}
                for e, p in records[:3]
            ],
        }
        print_json(out)
        return 0

    # Confirm path
    if not records:
        print_json({"ok": False, "error": "No valid records to upload."})
        return 1

    print(f"[i] creating audience '{args.name}' on {account_id}", file=sys.stderr)
    audience_id = create_audience(account_id, args.name, args.description)
    print(f"[+] audience: {audience_id}", file=sys.stderr)

    print(f"[i] uploading {len(records)} records in batches of {BATCH_SIZE}", file=sys.stderr)
    upload_summary = upload_users(audience_id, records)

    # Fetch current state
    info = get(audience_id, {"fields": "id,name,subtype,approximate_count_lower_bound,approximate_count_upper_bound,delivery_status,operation_status"})

    print_json(
        {
            "ok": True,
            "mode": "confirm",
            "audience_id": audience_id,
            "audience_name": args.name,
            "upload": upload_summary,
            "audience_info": info,
            "note": "Audience needs ~30 min to several hours to populate fully. Can be referenced in ad sets immediately.",
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
