#!/usr/bin/env python3
"""
Batch scraper: runs enrich_google_maps_termux.py for each hospital.

Usage:
    python3 batch_scrape_wrapper.py --input hospitals.json --output hospitals_enriched.json
    
Or incremental (skip already enriched):
    python3 batch_scrape_wrapper.py --input hospitals.json \
        --existing hospitals_enriched.json \
        --output hospitals_enriched.json
        
Or test mode (first 5):
    python3 batch_scrape_wrapper.py --test 5
    
Or resume from checkpoint:
    python3 batch_scrape_wrapper.py --resume
"""

import json
import subprocess
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


def run_termux_script(hospital_name: str, hospital_area: str = "") -> dict | None:
    """Run the enrichment script on Termux for a single hospital."""
    # Write a temporary Python script on Termux to avoid SSH quoting issues
    tmp_script = f"""
import json
import sys
sys.path.insert(0, '/data/data/com.termux/files/home/hospital-search-hdfc-care')
from enrich_google_maps_termux import search_hospital

name = sys.argv[1]
area = sys.argv[2] if len(sys.argv) > 2 else ''

result = search_hospital(name, area)
if result:
    print(json.dumps(result))
else:
    print(json.dumps({{"error": "No data extracted"}}))
"""
    
    # Write the script to a temp file on Termux
    tmp_path = '/tmp/scrape_one.py'
    
    ssh_cmd = get_termux_ssh()
    
    # Write script
    subprocess.run(
        ssh_cmd + ['bash', '-c', f'cat > {tmp_path} << \'SCRIPT_EOF\'\n{tmp_script}\nSCRIPT_EOF'],
        capture_output=True,
        timeout=10
    )
    
    # Run the script
    try:
        result = subprocess.run(
            ssh_cmd + ['python3', tmp_path, hospital_name, hospital_area],
            capture_output=True,
            text=True,
            timeout=90
        )
        
        if result.returncode == 0:
            # Parse the JSON output
            try:
                return json.loads(result.stdout.strip())
            except json.JSONDecodeError:
                print(f"  ✗ Invalid JSON output: {result.stdout[:200]}")
                return None
        else:
            print(f"  ✗ Script failed: {result.stderr[:200]}")
            return None
            
    except subprocess.TimeoutExpired:
        print(f"  ✗ Timeout after 90s")
        return None
    except Exception as e:
        print(f"  ✗ Error: {e}")
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
    parser.add_argument('--test', type=int, default=0, help='Test mode: scrape first N hospitals')
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
    
    # Test mode
    if args.test > 0:
        needs_scraping = needs_scraping[:args.test]
        print(f"\nTest mode: scraping first {args.test} hospitals")
    
    # Check for checkpoint
    checkpoint_file = Path(args.output).parent / '.scrape_checkpoint.json'
    start_index = 0
    
    if args.resume and checkpoint_file.exists():
        with open(checkpoint_file) as f:
            checkpoint = json.load(f)
            start_index = checkpoint.get('last_index', 0)
            print(f"\nResuming from index {start_index}")
    
    # Scrape hospitals
    total = len(needs_scraping)
    success_count = 0
    fail_count = 0
    
    for i, hospital in enumerate(needs_scraping[start_index:], start=start_index):
        name = hospital['hospital_name']
        area = hospital.get('area', '')
        print(f"\n[{i+1}/{total}] Scraping: {name}")
        
        try:
            data = run_termux_script(name, area)
            
            if data and 'error' not in data:
                # Merge with original hospital data
                enriched_hospital = {**hospital, **data}
                enriched_map[name] = enriched_hospital
                success_count += 1
            else:
                fail_count += 1
                
        except Exception as e:
            print(f"  ✗ Error: {e}")
            fail_count += 1
        
        # Checkpoint every 5 hospitals
        if (i + 1) % 5 == 0:
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
        time.sleep(2)
    
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
