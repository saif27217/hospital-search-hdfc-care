#!/usr/bin/env python3
"""Phase 1: Google Maps enrichment for hospital dataset.

Runs on Termux via TBP daemon. Extracts address, phone, website, hours,
rating from Google Maps search results for each hospital.

Usage:
    python3 enrich_google_maps.py [--batch-size N] [--delay SECONDS]

Checkpoint: writes enrichment_progress.json after every 50 hospitals.
Resume: picks up from last checkpoint automatically.

Output: enriched_hospitals.json (original fields preserved + new fields appended)
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# ── Config ───────────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).parent  # VPS: hospital-search-hdfc-care/
HOSPITALS_JSON = DATA_DIR / "hospitals.json"
ENRICHED_JSON = DATA_DIR / "enriched_hospitals.json"
PROGRESS_FILE = DATA_DIR / "enrichment_progress.json"

# TBP daemon SSH connection (Termux device)
SSH_HOST = "u0_a221@100.70.18.84"
SSH_PORT = 8022
SSH_KEY = "/home/sak/.ssh/id_ed25519"

TBP_DIR = "~/termux-browser-pilot"
SSH_CMD = f"ssh -o StrictHostKeyChecking=no -o BatchMode=yes -i {SSH_KEY} -p {SSH_PORT} {SSH_HOST}"

# ── Helpers ──────────────────────────────────────────────────────────────

def run_tbp(command: str, timeout: int = 30) -> str:
    """Run a TBP CLI command via SSH and return stdout."""
    full_cmd = f"{SSH_CMD} 'cd {TBP_DIR} && python3 cli.py {command}'"
    result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"TBP command failed: {result.stderr.strip()}")
    return result.stdout.strip()

def goto(url: str) -> dict:
    """Navigate to URL and return {url, title}."""
    raw = run_tbp(f'goto "{url}" --json', timeout=30)
    return json.loads(raw)

def get_text() -> str:
    """Get rendered page text."""
    return run_tbp("text", timeout=30)

def extract_fields(text: str, hospital_name: str) -> dict:
    """Extract structured fields from Google Maps text output.

    Returns dict with keys: maps_name, rating, review_count, type,
    address, hours, website_url, phone, plus raw_text for audit.
    """
    result: dict[str, str | float | int | None] = {
        "maps_name": None,
        "rating": None,
        "review_count": None,
        "type": None,
        "address": None,
        "hours": None,
        "website_url": None,
        "phone": None,
    }

    lines = text.split("\n")
    
    # ── Name: first meaningful line after navigation noise ──
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        # Skip navigation UI elements (icons, "Saved", "Recents", etc.)
        noise = {"Saved", "Recents", "Get app", "Directions", "Share",
                 "Save", "Nearby", "Send to phone", "Suggest an edit",
                 "See photos", "Write a review", "More reviews"}
        if stripped in noise or len(stripped) < 3:
            continue
        # First substantial line is likely the name
        result["maps_name"] = stripped
        break

    # ── Rating: pattern like "4.6(3,605)" or just "4.4" ──
    rating_match = re.search(r'(\d\.\d)\(([\d,]+)\)', text)
    if rating_match:
        result["rating"] = float(rating_match.group(1))
        result["review_count"] = int(rating_match.group(2).replace(",", ""))
    else:
        # Rating without review count
        rating_match = re.search(r'^(\d\.\d)\s*$', text, re.MULTILINE)
        if rating_match:
            result["rating"] = float(rating_match.group(1))

    # ── Type: line like "Hospital ·", "Private hospital·" (note the special dot) ──
    type_match = re.search(r'Hospital(?:\s+department)?·|Private\s+hospital', text, re.IGNORECASE)
    if type_match:
        result["type"] = type_match.group(0).replace("·", "").strip()

    # ── Address: line containing postal code pattern or "Rd"/"Road"/"Main" ──
    # Look for lines with Hyderabad/Telangana/500xxx pattern
    addr_patterns = [
        r'[\d]+-[A-Z]?[\d]+,\s*[^,]+(?:Hyderabad|Telangana)',  # flat number pattern
        r'Opp\.?\s+Pillar',  # landmark pattern
        r'(?:Khader Bagh|Padmanabha Nagar|Nanal Nagar)',  # area names
        r'[\d]+-[A-Z]?[\d]+,\s*[^,]+Hyderabad',  # simpler flat number
    ]
    for line in lines:
        stripped = line.strip()
        if any(re.search(p, stripped) for p in addr_patterns):
            # Clean up the address line (remove navigation icons)
            cleaned = re.sub(r'[\s]+$', '', stripped).strip()
            if len(cleaned) > 10:  # Skip short noise lines
                result["address"] = cleaned
                break

    # ── Hours: "Open 24 hours" or specific timing ──
    hours_match = re.search(r'(Open\s+24\s+hours|Open\s+\d{1,2}:\d{2}\s+-\s+Close\s+\d{1,2}:\d{2})', text, re.IGNORECASE)
    if hours_match:
        result["hours"] = hours_match.group(1).strip()

    # ── Website: line that looks like a domain ──
    for line in lines:
        stripped = line.strip()
        if re.match(r'^[a-zA-Z0-9][-a-zA-Z0-9]*\.(in|com|org|net)', stripped):
            result["website_url"] = "https://" + stripped
            break

    # ── Phone: pattern like "040 2353 3810" or "079979 96030" ──
    phone_match = re.search(r'(\d{5}\s+\d{5}|\d{4}\s+\d{3}\s+\d{4})', text)
    if phone_match:
        result["phone"] = phone_match.group(1).strip()

    return result


def search_hospital(name: str, area: str = "") -> dict | None:
    """Search Google Maps for a hospital and extract fields.

    Returns extracted dict or None if no results found.
    """
    from urllib.parse import quote_plus

    # Build search query
    if area:
        query = f"{name} hospital {area} Hyderabad"
    else:
        query = f"{name} hospital Hyderabad"

    # URL-encode properly (handles &, (), etc.)
    encoded = quote_plus(query)
    url = f"https://www.google.com/maps/search/{encoded}"

    try:
        goto(url)
        time.sleep(5)  # Wait for JS render
        text = get_text()

        # Check if we got meaningful results (not just navigation noise)
        if "You've reached the end of the list" not in text and len(text) > 100:
            return extract_fields(text, name)

        # Try a more specific search if first attempt failed
        encoded2 = quote_plus(name)
        url2 = f"https://www.google.com/maps/search/{encoded2}+hospital"
        goto(url2)
        time.sleep(5)
        text2 = get_text()
        if "You've reached the end of the list" not in text2 and len(text2) > 100:
            return extract_fields(text2, name)

        return None  # No results found

    except (RuntimeError, subprocess.TimeoutExpired):
        return None


def load_progress() -> int:
    """Load checkpoint index. Returns 0 if no progress file."""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            data = json.load(f)
        return data.get("last_index", 0)
    return 0

def save_progress(index: int, hospital_name: str):
    """Save checkpoint after processing a batch."""
    with open(PROGRESS_FILE, "w") as f:
        json.dump({"last_index": index, "last_name": hospital_name}, f)


def main():
    batch_size = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 50
    delay = float(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].replace(".","").isdigit() else 7

    # Load hospitals
    print(f"Loading {HOSPITALS_JSON}...")
    with open(HOSPITALS_JSON) as f:
        hospitals = json.load(f)

    # Load existing enriched data (if resuming)
    enriched = {}
    if ENRICHED_JSON.exists():
        with open(ENRICHED_JSON) as f:
            enriched_list = json.load(f)
            for h in enriched_list:
                enriched[h.get("name", "")] = h

    # Load progress checkpoint
    start_idx = load_progress()
    print(f"Resuming from index {start_idx} ({len(hospitals)} total hospitals)")

    results = list(enriched.values())  # Start with already-enriched data
    skipped = []

    for i, hospital in enumerate(hospitals[start_idx:], start=start_idx):
        name = hospital.get("hospital_name", "")
        area = hospital.get("area", "")

        if i % batch_size == 0 and i > start_idx:
            print(f"Checkpoint: saved {len(results)} enriched, last={name}")
            save_progress(i - 1, name)

        print(f"[{i+1}/{len(hospitals)}] {name} ({area})... ", end="", flush=True)

        try:
            extracted = search_hospital(name, area)

            if extracted and extracted["maps_name"]:
                # Merge with original hospital data
                enriched_hospital = dict(hospital)
                enriched_hospital.update({
                    "maps_name": extracted["maps_name"],
                    "maps_rating": extracted["rating"],
                    "maps_review_count": extracted["review_count"],
                    "maps_type": extracted["type"],
                    "maps_address": extracted["address"],
                    "maps_hours": extracted["hours"],
                    "website_url": extracted["website_url"],
                    "maps_phone": extracted["phone"],
                })

                # Cross-check phone against existing contact numbers
                existing_phones = hospital.get("contact_number", [])
                if extracted["phone"] and existing_phones:
                    # Check if extracted phone matches any existing number (fuzzy)
                    cleaned_extracted = re.sub(r'[\s-]', '', extracted["phone"])
                    for ep in existing_phones:
                        cleaned_existing = re.sub(r'[\s-]', '', str(ep))
                        if cleaned_extracted in cleaned_existing or cleaned_existing in cleaned_extracted:
                            enriched_hospital["phone_verified"] = True
                            break

                results.append(enriched_hospital)
                print(f"OK (rating={extracted['rating']}, phone={extracted['phone']})")
            else:
                skipped.append({"index": i, "name": name, "area": area})
                print("NO RESULTS")

        except Exception as e:
            skipped.append({"index": i, "name": name, "area": area, "error": str(e)})
            print(f"ERROR: {e}")

        # Rate limiting
        if i < len(hospitals) - 1:
            time.sleep(delay)

    # Final save
    with open(ENRICHED_JSON, "w") as f:
        json.dump(results, f, indent=2)

    # Save final progress
    save_progress(len(hospitals) - 1, "COMPLETE")

    # Summary
    print(f"\n{'='*60}")
    print(f"Enrichment complete!")
    print(f"  Enriched: {len(results)} hospitals")
    print(f"  Skipped/Failed: {len(skipped)} hospitals")
    if skipped:
        print(f"\nSkipped list:")
        for s in skipped[:10]:  # Show first 10
            print(f"  [{s['index']}] {s['name']} ({s.get('area','')})")
        if len(skipped) > 10:
            print(f"  ... and {len(skipped)-10} more")

    # Save skipped list for manual review
    with open(DATA_DIR / "enrichment_skipped.json", "w") as f:
        json.dump(skipped, f, indent=2)

    print(f"\nOutput: {ENRICHED_JSON}")
    print(f"Skipped: {DATA_DIR / 'enrichment_skipped.json'}")


if __name__ == "__main__":
    main()
