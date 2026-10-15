#!/usr/bin/env python3
"""Quick test: run enrichment on first 5 hospitals from the dataset."""

import json
from pathlib import Path
from enrich_google_maps import search_hospital, goto, get_text

DATA_DIR = Path(__file__).parent
with open(DATA_DIR / "hospitals.json") as f:
    hospitals = json.load(f)

test_hospitals = hospitals[:5]
print(f"Testing on {len(test_hospitals)} hospitals:\n")

results = []
for i, h in enumerate(test_hospitals):
    name = h.get("hospital_name", "")
    area = h.get("area", "")
    print(f"[{i+1}/{len(test_hospitals)}] {name} ({area})... ", end="", flush=True)
    
    try:
        extracted = search_hospital(name, area)
        
        if extracted and extracted["maps_name"]:
            print(f"OK")
            results.append({
                "original": h,
                "extracted": extracted,
            })
        else:
            print("NO RESULTS")
    except Exception as e:
        print(f"ERROR: {e}")

# Save test results
with open(DATA_DIR / "enrich_test_results.json", "w") as f:
    json.dump(results, f, indent=2)

print(f"\nTest complete. {len(results)} successful extractions.")
print("Results saved to enrich_test_results.json")
