#!/usr/bin/env python3
"""
hospital-search: Instant hospital lookup from HDFC Ergo / Care Supreme network data.

Reads from a cached JSON built from the Google Spreadsheet:
  https://docs.google.com/spreadsheets/d/1X4GX0llipvZpW71nGF3gsytcQmf4AxwP1FxVwKiVvJw

Usage:
  hospital-search --insurance hdfc --area "Mehdipatnam" --specialty "Eye" --sort distance
  hospital-search --insurance care --sort rating --limit 10
  hospital-search --rebuild          # rebuild cache from spreadsheet
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from textwrap import dedent

CACHE_FILE = str(Path(__file__).resolve().parent / "hospitals.json")
SPREADSHEET_ID = "1X4GX0llipvZpW71nGF3gsytcQmf4AxwP1FxVwKiVvJw"
XLSX_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=xlsx&id={SPREADSHEET_ID}"

# Area names used as section headers in the raw sheets
AREA_HEADERS = {
    "mehdipatnam", "nampally", "attapur", "lakdi-ka-pool", "masab tank",
    "banjara hills", "jubilee hills", "tolichowki", "basheer bagh",
    "shaikpet", "somajiguda", "others", "dilsukhnagar", "l.b.nagar",
    "vidya nagar", "ramanthapur", "abids", "uppal", "malkajgiri",
}


def clean_contact(contact_val):
    """Clean a contact number from spreadsheet: strip .0 floats, split multi-numbers."""
    if contact_val is None:
        return []
    s = str(contact_val).strip()
    if not s or s.lower() in ("none", "nan", "n/a", ""):
        return []
    # Handle float-formatted ints like "9160795917.0"
    if re.match(r"^\d+\.\d+$", s):
        s = s.split(".")[0]
    # Split multi-number strings like "7095296666/7993360803" or "040-23090609 Ext. 253"
    numbers = []
    cleaned = re.split(r"[/]+", s)
    for part in cleaned:
        part = part.strip()
        # Remove "Ext. 253" suffixes
        part = re.sub(r"\s+ext\.?\s*\d+", "", part, flags=re.IGNORECASE).strip()
        # Validate: must contain at least 6 digits
        digits = re.sub(r"[^\d]", "", part)
        if len(digits) >= 6:
            numbers.append(part)
    return numbers


def is_area_header(val):
    """Check if a cell value is an area header (like 'Mehdipatnam') vs a hospital name."""
    if val is None:
        return True
    s = str(val).strip().lower()
    if not s:
        return True
    # Area headers are single words or known area names without hospital descriptors
    if s in AREA_HEADERS:
        return True
    # Skip note-style cells
    if s.startswith("(no distinct") or s.startswith("(no hospital"):
        return True
    # Skip repeated header rows (two-row headers in source sheet)
    if s in ("hospital name", "simplified address", "name of hospital"):
        return True
    return False


def parse_hdfc_base(ws):
    """Parse HDFC Ergo base sheet (cols: Hospital Name, Simplified Address, Specialty, Contact)."""
    hospitals = {}
    current_area = ""
    for r in range(2, ws.max_row + 1):
        name = ws.cell(row=r, column=1).value
        addr = ws.cell(row=r, column=2).value
        specialty = ws.cell(row=r, column=3).value
        contact = ws.cell(row=r, column=4).value

        if name is None or str(name).strip() == "":
            continue

        name_str = str(name).strip()
        if is_area_header(name_str):
            current_area = name_str
            continue

        contacts = clean_contact(contact)
        addr_str = str(addr).strip() if addr else current_area

        hospitals[name_str] = {
            "hospital_name": name_str,
            "insurance": "HDFC Ergo",
            "area": addr_str if addr_str else current_area,
            "specialty": str(specialty).strip() if specialty else "",
            "contact_number": contacts,
            "google_rating": None,
            "distance_km": None,
            "travel_time_min": None,
            "proximity_category": None,
            "final_score": None,
            "full_address": None,
            "is_recommended": False,
        }
    return hospitals


def parse_hdfc_proximity(ws):
    """Parse HDFC Ergo proximity/rating sheet (cols A-L + note in M)."""
    enrichment = {}
    for r in range(2, ws.max_row + 1):
        name = ws.cell(row=r, column=1).value
        if not name or not str(name).strip():
            continue
        name_str = str(name).strip()
        # Remove the ", AreaName" suffix to match base sheet
        # e.g., "Aravind Eye Hospital, Mehdipatnam" -> "Aravind Eye Hospital"
        # But base sheet has "Aravind Eye Hospital" without area suffix
        # Keep full name for matching, also try without suffix
        rating = ws.cell(row=r, column=3).value
        num_reviews = ws.cell(row=r, column=4).value
        full_addr = ws.cell(row=r, column=5).value
        prox_cat = ws.cell(row=r, column=6).value
        est_dist_text = ws.cell(row=r, column=7).value
        norm_rating = ws.cell(row=r, column=8).value
        norm_users = ws.cell(row=r, column=9).value
        num_dist = ws.cell(row=r, column=10).value
        norm_dist = ws.cell(row=r, column=11).value
        final_score = ws.cell(row=r, column=12).value

        # Map numerical distance (0-3) to approximate km
        # Based on the data: 0=Very Close (~0.5km), 1=Nearby, 2=Adjacent, 3=Significant
        dist_map = {0: 0.5, 1: 3.0, 2: 7.0, 3: 15.0}
        est_dist_km = dist_map.get(num_dist, None) if isinstance(num_dist, (int, float)) else None

        enrichment[name_str] = {
            "google_rating": float(rating) if isinstance(rating, (int, float)) else None,
            "num_reviews": str(num_reviews) if num_reviews else None,
            "full_address": str(full_addr).strip() if full_addr else None,
            "proximity_category": str(prox_cat).strip() if prox_cat else None,
            "estimated_distance_text": str(est_dist_text).strip() if est_dist_text else None,
            "distance_km": est_dist_km,
            "travel_time_min": None,  # Not available in this sheet
            "final_score": float(final_score) if isinstance(final_score, (int, float)) else None,
        }
    return enrichment


def parse_care_base(ws):
    """Parse Care Supreme proximity/rating sheet (sheet 4) which has ALL data."""
    hospitals = {}
    current_area = ""
    for r in range(2, ws.max_row + 1):
        name = ws.cell(row=r, column=1).value
        addr = ws.cell(row=r, column=2).value
        specialty = ws.cell(row=r, column=3).value
        contact = ws.cell(row=r, column=4).value
        rating = ws.cell(row=r, column=5).value
        dist_km = ws.cell(row=r, column=6).value
        travel_time = ws.cell(row=r, column=7).value

        if name is None or str(name).strip() == "":
            continue

        name_str = str(name).strip()
        if is_area_header(name_str):
            current_area = name_str
            continue

        contacts = clean_contact(contact)
        addr_str = str(addr).strip() if addr else current_area

        hospitals[name_str] = {
            "hospital_name": name_str,
            "insurance": "Care Supreme",
            "area": addr_str if addr_str else current_area,
            "specialty": str(specialty).strip() if specialty else "",
            "contact_number": contacts,
            "google_rating": float(rating) if isinstance(rating, (int, float)) else None,
            "distance_km": float(dist_km) if isinstance(dist_km, (int, float)) else None,
            "travel_time_min": float(travel_time) if isinstance(travel_time, (int, float)) else None,
            "proximity_category": None,
            "final_score": None,
            "full_address": None,
            "is_recommended": False,
        }
    return hospitals


def parse_care_recommended(ws):
    """Parse Care Recommended sheet (5 rows of data in two side-by-side tables)."""
    recommended = set()
    # Table 2: columns A-F (rows 2-35)
    # Table 3: columns H-M (rows 2-26)
    for r in range(3, ws.max_row + 1):
        # Table 2
        name = ws.cell(row=r, column=1).value
        if name and str(name).strip():
            recommended.add(str(name).strip())
        # Table 3
        name = ws.cell(row=r, column=8).value
        if name and str(name).strip():
            recommended.add(str(name).strip())
    return recommended


def normalize_name(name):
    """Normalize hospital name for cross-sheet matching."""
    n = name.lower().strip()
    # Remove common prefixes/suffixes
    n = re.sub(r'\s*\(.*?\)\s*', ' ', n)  # remove parenthetical
    n = re.sub(r'\s+-\s+', ' ', n)  # normalize dashes
    n = re.sub(r'\s+', ' ', n)  # normalize spaces
    n = n.strip()
    return n


def match_hdfc_enrichment(hospitals, enrichment):
    """Join HDFC Ergo base sheet with proximity/rating sheet by name."""
    # Build lookup from normalized name
    enrichment_lookup = {}
    for name, data in enrichment.items():
        key = normalize_name(name)
        # Also try without the ", AreaName" suffix
        parts = key.split(",")
        key_short = parts[0].strip()
        enrichment_lookup[key] = data
        enrichment_lookup[key_short] = data

    for hosp_name, hosp_data in hospitals.items():
        key = normalize_name(hosp_name)
        # Try full match
        if key in enrichment_lookup:
            enrich = enrichment_lookup[key]
        else:
            # Try short match (without area suffix)
            parts = key.split(",")
            key_short = parts[0].strip()
            enrich = enrichment_lookup.get(key_short, None)

        if enrich:
            for field in ["google_rating", "distance_km", "proximity_category",
                          "final_score", "full_address", "num_reviews"]:
                hosp_data[field] = enrich.get(field)
        else:
            hosp_data["num_reviews"] = None


def match_care_recommended(hospitals, recommended_names):
    """Tag Care Supreme hospitals that appear in the Recommended sheet."""
    rec_lookup = {normalize_name(n): True for n in recommended_names}
    for hosp_name, hosp_data in hospitals.items():
        key = normalize_name(hosp_name)
        parts = key.split(",")
        key_short = parts[0].strip()
        if key in rec_lookup or key_short in rec_lookup:
            hosp_data["is_recommended"] = True


def build_cache():
    """Build the JSON cache from the spreadsheet."""
    import openpyxl
    import urllib.request
    import tempfile

    print(f"Downloading spreadsheet from Google...", file=sys.stderr)
    req = urllib.request.Request(XLSX_URL)
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        f.write(urllib.request.urlopen(req, timeout=30).read())
        xlsx_path = f.name

    print(f"Parsing spreadsheet...", file=sys.stderr)
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    all_hospitals = {}

    # HDFC Ergo
    if "HDFC Ergo" in wb.sheetnames:
        hdfc_base = parse_hdfc_base(wb["HDFC Ergo"])
        hdfc_prox = parse_hdfc_proximity(wb["HDFC ergo (proximity and rating"])
        match_hdfc_enrichment(hdfc_base, hdfc_prox)
        all_hospitals.update(hdfc_base)
        h = sum(1 for v in hdfc_base.values() if v["google_rating"] is not None)
        print(f"  HDFC Ergo: {len(hdfc_base)} hospitals, {h} enriched with ratings", file=sys.stderr)

    # Care Supreme
    if "Care Supreme" in wb.sheetnames:
        # Prefer sheet 4 (has all data + ratings)
        if "Care (proximity and rating base" in wb.sheetnames:
            care_base = parse_care_base(wb["Care (proximity and rating base"])
        else:
            care_base = parse_care_base(wb["Care Supreme"])
        all_hospitals.update(care_base)
        h = sum(1 for v in care_base.values() if v["google_rating"] is not None)
        print(f"  Care Supreme: {len(care_base)} hospitals, {h} with ratings", file=sys.stderr)

    # Care Recommended tags
    if "Care (Recommended)" in wb.sheetnames:
        recommended = parse_care_recommended(wb["Care (Recommended)"])
        match_care_recommended(all_hospitals, recommended)
        r = sum(1 for v in all_hospitals.values() if v["is_recommended"])
        print(f"  Tagged {r} recommended hospitals", file=sys.stderr)

    os.unlink(xlsx_path)

    # Deduplicate by (insurance, normalized_name) preserving first occurrence
    seen = set()
    deduped = []
    for h in all_hospitals.values():
        key = (h["insurance"], normalize_name(h["hospital_name"]))
        if key not in seen:
            seen.add(key)
            deduped.append(h)

    print(f"Total unified records: {len(deduped)}", file=sys.stderr)

    # Save cache
    cache_dir = Path(CACHE_FILE).parent
    cache_dir.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(deduped, f, indent=2, ensure_ascii=False)

    print(f"Cache written to {CACHE_FILE}", file=sys.stderr)
    return deduped


def load_cache():
    if not os.path.exists(CACHE_FILE):
        print("Cache not found. Run with --rebuild first.", file=sys.stderr)
        sys.exit(1)
    with open(CACHE_FILE) as f:
        return json.load(f)


def search(hospitals, insurance=None, area=None, specialty=None,
           sort="distance", limit=None, show_contact_only=False):
    """Filter and sort hospitals."""
    results = hospitals

    # Filter by insurance ("hdfc" -> "HDFC Ergo", "care" -> "Care Supreme")
    if insurance:
        results = [h for h in results if insurance.lower() in h["insurance"].lower()]

    # Filter by area (fuzzy match)
    if area:
        area_lower = area.lower()
        results = [h for h in results if area_lower in h.get("area", "").lower()]

    # Filter by specialty (regex, case-insensitive)
    if specialty:
        spec_lower = specialty.lower()
        results = [h for h in results if spec_lower in h.get("specialty", "").lower()]

    # Sort
    if sort == "distance":
        results.sort(key=lambda h: (h.get("distance_km") is None, h.get("distance_km") or 9999))
    elif sort == "rating":
        results.sort(key=lambda h: (h.get("google_rating") is None, -(h.get("google_rating") or 0)))
    elif sort == "score":
        results.sort(key=lambda h: (h.get("final_score") is None, -(h.get("final_score") or 0)))
    elif sort == "name":
        results.sort(key=lambda h: h.get("hospital_name", ""))

    if limit:
        results = results[:limit]

    return results


def format_results(results, show_contact_only=False):
    """Pretty-print results as a table."""
    if not results:
        print("No hospitals found matching your criteria.")
        return

    if show_contact_only:
        print("\n📞 Closest hospital contact:")
        h = results[0]
        contacts = h.get("contact_number", [])
        contact_str = " | ".join(contacts) if contacts else "N/A"
        rating = h.get("google_rating")
        rating_str = f"⭐ {rating}/5" if rating else "No rating"
        dist = h.get("distance_km")
        dist_str = f"📍 {dist} km" if dist else "📍 Distance N/A"
        print(f"  Hospital: {h['hospital_name']}")
        print(f"  Insurance: {h['insurance']}")
        print(f"  Area: {h.get('area', '')}")
        print(f"  Specialty: {h.get('specialty', '')}")
        print(f"  Contact: {contact_str}")
        print(f"  {rating_str}  {dist_str}")
        if h.get("travel_time_min"):
            print(f"  Travel time: {h['travel_time_min']} min")
        if h.get("is_recommended"):
            print(f"  🏆 Recommended")
        return

    # Full table
    print(f"\n{'Hospital':<50} {'Insurance':<12} {'Area':<18} {'Rating':<8} {'Dist(km)':<10} {'Contact'}")
    print("-" * 120)
    for h in results:
        name = h["hospital_name"][:48]
        ins = h["insurance"][:11]
        area = (h.get("area") or "")[:16]
        rating = f"⭐{h['google_rating']:.1f}" if h.get("google_rating") else "  —"
        dist = f"{h['distance_km']:.1f}" if h.get("distance_km") else "—"
        contacts = h.get("contact_number", [])
        contact = contacts[0][:20] if contacts else "N/A"
        recommended = " 🏆" if h.get("is_recommended") else ""
        print(f"{name:<50} {ins:<12} {area:<18} {rating:<8} {dist:<10} {contact}{recommended}")

    print(f"\nShowing {len(results)} result(s).")
    if show_contact_only is False and results:
        print(f"Use --contact flag to get just the top hospital's phone number.")


def main():
    parser = argparse.ArgumentParser(
        description="Search HDFC Ergo / Care Supreme hospital network data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=dedent("""\
            Examples:
              hospital-search --insurance hdfc --area Mehdipatnam --sort distance
              hospital-search --insurance care --specialty "Eye" --sort rating --limit 5
              hospital-search --insurance hdfc --area Banjara --contact
              hospital-search --rebuild
        """)
    )
    parser.add_argument("--insurance", choices=["hdfc", "care"], help="Filter by insurance provider")
    parser.add_argument("--area", type=str, help="Filter by area/neighborhood")
    parser.add_argument("--specialty", type=str, help="Filter by specialty (fuzzy, case-insensitive)")
    parser.add_argument("--sort", choices=["distance", "rating", "score", "name"], default="distance",
                        help="Sort by: distance (closest first), rating (best first), score (HDFC Ergo final score), name")
    parser.add_argument("--limit", type=int, default=20, help="Max results to show")
    parser.add_argument("--contact", action="store_true", help="Show only the single closest/best hospital's contact info")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild the JSON cache from the spreadsheet")
    args = parser.parse_args()

    if args.rebuild:
        build_cache()
        return

    hospitals = load_cache()
    results = search(
        hospitals,
        insurance=args.insurance,
        area=args.area,
        specialty=args.specialty,
        sort=args.sort,
        limit=args.limit,
        show_contact_only=args.contact,
    )
    format_results(results, show_contact_only=args.contact)


if __name__ == "__main__":
    main()
