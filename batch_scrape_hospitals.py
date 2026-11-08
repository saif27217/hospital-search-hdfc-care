#!/usr/bin/env python3
"""
Batch Google Maps scraper for hospital data enrichment.

Usage:
    python3 batch_scrape_hospitals.py --input hospitals.json --output hospitals_enriched.json
    
Or incremental (only scrape unmatched):
    python3 batch_scrape_hospitals.py --input hospitals.json \
        --existing hospitals_enriched.json \
        --output hospitals_enriched.json
        
Or with batch size control:
    python3 batch_scrape_hospitals.py --batch-size 50 --checkpoint-interval 10
"""

import json
import sys
import time
import argparse
from pathlib import Path


def get_termux_ssh():
    """Get SSH command for Termux."""
    return [
        'ssh',
        '-o', 'StrictHostKeyChecking=no',
        '-o', 'BatchMode=yes',
        '-i', str(Path.home() / '.ssh' / 'id_ed25519'),
        '-p', '8022',
        'u0_a221@100.70.18.84'
    ]


def run_termux_command(cmd: str) -> tuple[int, str]:
    """Run a command on Termux via SSH."""
    import subprocess
    
    ssh_cmd = get_termux_ssh()
    full_cmd = f'cd ~/termux-browser-pilot && python3 cli.py {cmd}'
    
    result = subprocess.run(
        ssh_cmd + [full_cmd],
        capture_output=True,
        text=True,
        timeout=120
    )
    
    return result.returncode, result.stdout + result.stderr


def scrape_hospital(hospital: dict) -> dict | None:
    """Scrape Google Maps for a hospital."""
    name = hospital.get('hospital_name', '')
    
    # Build search query
    area = hospital.get('area', 'Hyderabad')
    query = f"{name} {area} Hyderabad"
    
    # Navigate to Google Maps search
    code, output = run_termux_command(
        f'goto "https://www.google.com/maps/search/{query.replace(" ", "+")}"'
    )
    
    if code != 0:
        print(f"  ✗ Navigation failed for {name}")
        return None
    
    # Wait for page load
    time.sleep(3)
    
    # Extract text content
    code, output = run_termux_command('text')
    
    if code != 0:
        print(f"  ✗ Text extraction failed for {name}")
        return None
    
    # Parse the output
    data = parse_google_maps_text(output, hospital)
    
    if data:
        print(f"  ✓ Extracted data for {name}")
    else:
        print(f"  ⚠ No data extracted for {name}")
    
    return data


def parse_google_maps_text(text: str, hospital: dict) -> dict | None:
    """Parse Google Maps text output to extract hospital data."""
    import re
    
    # Check if we got a detail page (not search results)
    has_detail_markers = bool(re.search(
        r'\d+-[A-Z]?\d+.*(?:Hyderabad|Telangana)',
        text,
        re.IGNORECASE
    ))
    
    if not has_detail_markers:
        return None
    
    # Extract name (skip navigation noise)
    lines = text.split('\n')
    name = None
    for i, line in enumerate(lines):
        # Skip navigation categories
        skip_words = ['Restaurants', 'Hotels', 'Things to do', 'Transit', 
                      'Parking', 'Pharmacies', 'ATMs', 'Gas', 'Groceries',
                      'Clothing', 'Electronics', 'Home goods', 'Beauty', 
                      'Food', 'Coffee', 'Saved', 'Recents']
        if any(word in line for word in skip_words):
            continue
        
        # Look for hospital/clinic names
        if any(keyword in line for keyword in ['Hospital', 'Clinic', 'Centre', 'Center']):
            name = line.strip()
            break
        
        # Or look for lines before rating markers
        if i + 1 < len(lines) and '★' in lines[i + 1]:
            name = line.strip()
            break
    
    # Extract rating
    rating_match = re.search(r'(\d+\.\d+)\s*★', text)
    rating = float(rating_match.group(1)) if rating_match else None
    
    # Extract review count
    review_match = re.search(r'(\d+)\s*reviews', text, re.IGNORECASE)
    review_count = int(review_match.group(1)) if review_match else None
    
    # Extract address
    address_match = re.search(r'\d+-[A-Z]?\d+.*?(Hyderabad|Telangana)', text, re.IGNORECASE)
    address = address_match.group(0).strip() if address_match else None
    
    # Extract phone
    phone_patterns = [
        r'(\d{3}\s+\d{4}\s+\d{4})',  # 040 2351 3743
        r'(\d{3,4}\s+\d{6,7})',       # 040-23513743
        r'(\d{5}\s+\d{5})',           # 500001 12345
        r'(\d{4}\s+\d{3}\s+\d{4})',   # 040 235 1374
    ]
    phone = None
    for pattern in phone_patterns:
        match = re.search(pattern, text)
        if match:
            phone = match.group(1)
            break
    
    # Extract website
    website_match = re.search(r'(https?://[^\s]+)', text)
    website = website_match.group(1) if website_match else None
    
    # Extract hours
    hours_match = re.search(r'Open\s+24\s+hours|Open\s+[·\s]+\s*Close(?:s)?\s+\d{1,2}:\d{2}\s*[ap]\.?m', text)
    hours = hours_match.group(0).strip() if hours_match else None
    
    # Extract coordinates
    lat_match = re.search(r'@(-?\d+\.\d+)', text)
    lng_match = re.search(r',(-?\d+\.\d+),', text)
    lat = float(lat_match.group(1)) if lat_match else None
    lng = float(lng_match.group(1)) if lng_match else None
    
    # Build result
    result = {
        'hospital_name': name or hospital.get('hospital_name'),
        'google_rating': rating,
        'review_count': review_count,
        'address': address,
        'phone': phone,
        'website': website,
        'hours': hours,
        'lat': lat,
        'lng': lng,
    }
    
    # Only return if we got at least some data
    if any(result.values()):
        return result
    
    return None


def load_hospitals(filepath: str) -> list[dict]:
    """Load hospital data from JSON file."""
    with open(filepath) as f:
        return json.load(f)


def save_hospitals(hospitals: list[dict], filepath: str):
    """Save hospital data to JSON file."""
    with open(filepath, 'w') as f:
        json.dump(hospitals, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description='Batch scrape hospitals from Google Maps')
    parser.add_argument('--input', required=True, help='Input hospitals JSON file')
    parser.add_argument('--output', required=True, help='Output enriched JSON file')
    parser.add_argument('--existing', help='Existing enriched JSON (for incremental updates)')
    parser.add_argument('--batch-size', type=int, default=50, help='Batch size for scraping')
    parser.add_argument('--checkpoint-interval', type=int, default=10, help='Checkpoint interval')
    parser.add_argument('--resume', action='store_true', help='Resume from last checkpoint')
    
    args = parser.parse_args()
    
    # Load hospitals
    print(f"Loading hospitals from {args.input}...")
    hospitals = load_hospitals(args.input)
    
    # Load existing enriched data if provided
    if args.existing:
        print(f"Loading existing enriched data from {args.existing}...")
        existing = load_hospitals(args.existing)
        enriched_map = {h['hospital_name']: h for h in existing}
    else:
        enriched_map = {}
    
    # Find hospitals that need scraping
    needs_scraping = [
        h for h in hospitals
        if h['hospital_name'] not in enriched_map
    ]
    
    print(f"\nTotal hospitals: {len(hospitals)}")
    print(f"Already enriched: {len(enriched_map)}")
    print(f"Needs scraping: {len(needs_scraping)}")
    
    if not needs_scraping:
        print("\nAll hospitals already enriched. Nothing to do.")
        return
    
    # Check for checkpoint
    checkpoint_file = Path(args.output).parent / '.scrape_checkpoint.json'
    start_index = 0
    
    if args.resume and checkpoint_file.exists():
        with open(checkpoint_file) as f:
            checkpoint = json.load(f)
            start_index = checkpoint.get('last_index', 0)
            print(f"\nResuming from index {start_index}")
    
    # Scrape in batches
    total = len(needs_scraping)
    success_count = 0
    fail_count = 0
    
    for i, hospital in enumerate(needs_scraping[start_index:], start=start_index):
        batch_num = i // args.batch_size
        print(f"\n[{i+1}/{total}] Scraping: {hospital['hospital_name']}")
        
        try:
            data = scrape_hospital(hospital)
            
            if data:
                # Merge with original hospital data
                enriched_hospital = {**hospital, **data}
                enriched_map[hospital['hospital_name']] = enriched_hospital
                success_count += 1
            else:
                fail_count += 1
                
        except Exception as e:
            print(f"  ✗ Error: {e}")
            fail_count += 1
        
        # Checkpoint every N hospitals
        if (i + 1) % args.checkpoint_interval == 0:
            checkpoint = {
                'last_index': i + 1,
                'success_count': success_count,
                'fail_count': fail_count,
                'total_scraped': len(enriched_map),
            }
            with open(checkpoint_file, 'w') as f:
                json.dump(checkpoint, f, indent=2)
            print(f"  ✓ Checkpoint saved ({success_count} success, {fail_count} failed)")
        
        # Small delay between requests
        time.sleep(1)
    
    # Save final results
    print(f"\nSaving enriched data to {args.output}...")
    all_hospitals = list(enriched_map.values())
    save_hospitals(all_hospitals, args.output)
    
    # Clean up checkpoint
    if checkpoint_file.exists():
        checkpoint_file.unlink()
    
    # Summary
    print(f"\n{'='*60}")
    print(f"SCRAPING COMPLETE")
    print(f"{'='*60}")
    print(f"Total hospitals: {len(hospitals)}")
    print(f"Successfully enriched: {success_count}")
    print(f"Failed: {fail_count}")
    print(f"Total enriched now: {len(enriched_map)}")
    print(f"Coverage: {100*len(enriched_map)/len(hospitals):.1f}%")


if __name__ == '__main__':
    main()
