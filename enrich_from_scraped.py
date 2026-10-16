#!/usr/bin/env python3
"""
Enrich hospitals.json with scraped Google Maps data.

Matches existing hospitals to scraped entries by:
1. Exact name match (case-insensitive, ignoring parentheses)
2. Area/city validation with fuzzy name matching
3. Fallback to best match if no better option

Only merges fields that don't already exist in the original record.
"""

import json
import re
from difflib import SequenceMatcher
from pathlib import Path


# Generic titles to exclude from matching (scraping artifacts)
GENERIC_TITLES = {
    'hospital', 'hospitals', 'clinic', 'clinics', 'centre', 'centers',
    'healthcare', 'health care', 'medical', 'hospital & research centre',
}


def normalize_name(name: str) -> str:
    """Normalize hospital name for matching."""
    if not name:
        return ""
    # Lowercase, remove punctuation and special chars (keep letters and numbers)
    name = name.lower().strip()
    # Remove parenthetical content for matching
    name = re.sub(r'\([^)]*\)', '', name)
    # Remove punctuation
    name = re.sub(r'[^\w\s]', '', name)
    # Collapse whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def is_generic_title(title: str) -> bool:
    """Check if a title is too generic to be useful."""
    normalized = normalize_name(title)
    return normalized in GENERIC_TITLES or len(normalized.split()) <= 1


def extract_keywords(name: str) -> set:
    """Extract meaningful keywords from a name."""
    if not name:
        return set()
    
    # Common stop words to remove
    stops = {'hospital', 'hospitals', 'clinic', 'centre', 'center', 
             'and', 'the', 'a', 'an', 'pvt', 'private', 'limited',
             'india', 'hyderabad', 'secunderabad', 'telangana',
             'division', 'surya', 'prakash', 'diagnostics'}
    
    words = normalize_name(name).split()
    return {w for w in words if w not in stops and len(w) > 2}


def validate_area_match(existing_area: str, scraped_city: str, scraped_neighborhood: str) -> bool:
    """
    Validate that the scraped hospital is in the same area as the original.

    Returns True if areas match, False otherwise.
    """
    if not existing_area:
        # No area info in original, skip this check
        return True

    area_norm = normalize_name(existing_area)

    # Check scraped neighborhood first (more specific)
    if scraped_neighborhood:
        neigh_norm = normalize_name(scraped_neighborhood)
        # Area should be contained in neighborhood OR neighborhood in area
        if area_norm in neigh_norm or neigh_norm in area_norm:
            return True

    # Check scraped city (less specific, but still useful)
    if scraped_city:
        city_norm = normalize_name(scraped_city)
        # For Hyderabad area hospitals, city should be Hyderabad or Secunderabad
        if 'hyderabad' in area_norm and 'hyderabad' in city_norm:
            return True
        if 'secunderabad' in area_norm and 'secunderabad' in city_norm:
            return True

    # If we got here, areas don't match
    return False


def calculate_keyword_overlap(existing_name: str, scraped_name: str) -> float:
    """
    Calculate keyword overlap between two names.

    Returns 0.0 to 1.0, where 1.0 is perfect keyword match.
    """
    keywords1 = extract_keywords(existing_name)
    keywords2 = extract_keywords(scraped_name)

    if not keywords1 or not keywords2:
        return 0.0

    # Use min to avoid penalizing scraped names with extra keywords
    overlap = len(keywords1 & keywords2) / min(len(keywords1), len(keywords2))
    return overlap


def calculate_match_score(existing_name: str, scraped_name: str,
                          existing_area: str = None, scraped_city: str = None,
                          scraped_neighborhood: str = None) -> tuple[float, bool]:
    """
    Calculate match score between existing and scraped hospital names.

    Returns: (score, area_valid) where area_valid indicates if areas match.
    Uses keyword overlap as primary signal, area validation as secondary.
    """
    # Skip generic titles
    if is_generic_title(scraped_name):
        return 0.0, False

    n1 = normalize_name(existing_name)
    n2 = normalize_name(scraped_name)

    # Perfect match
    if n1 == n2:
        area_valid = validate_area_match(existing_area, scraped_city, scraped_neighborhood)
        return 1.0, area_valid

    # Check if one contains the other (with minimum length requirement)
    if len(n1) > 5 and n1 in n2:
        base_score = 0.9
    elif len(n2) > 5 and n2 in n1:
        base_score = 0.85
    else:
        # Fuzzy match
        base_score = SequenceMatcher(None, n1, n2).ratio()

    # Keyword overlap is the PRIMARY signal
    keyword_overlap = calculate_keyword_overlap(existing_name, scraped_name)

    # If keywords match well, accept even if area is uncertain
    if keyword_overlap >= 0.7:
        # Strong keyword match - accept with high confidence
        area_valid = validate_area_match(existing_area, scraped_city, scraped_neighborhood)
        # Bonus for area match, but not required
        if area_valid:
            base_score = min(base_score + 0.1, 1.0)
        return max(base_score, 0.85), area_valid

    # If keywords don't match well, use area validation as fallback
    area_valid = validate_area_match(existing_area, scraped_city, scraped_neighborhood)

    # Combine keyword and area signals
    if area_valid:
        base_score = base_score * 0.6 + keyword_overlap * 0.4
    else:
        # No area match and weak keywords - low confidence
        base_score *= 0.5

    return min(base_score, 1.0), area_valid


def extract_hours(opening_hours: list) -> str | None:
    """Extract hours from opening_hours array."""
    if not opening_hours:
        return None
    
    # Check for 24/7
    all_24 = all(
        'open 24 hours' in h.get('hours', '').lower() 
        for h in opening_hours
    )
    if all_24:
        return "Open 24 hours"
    
    # Get first entry's hours
    if opening_hours:
        return opening_hours[0].get('hours')
    
    return None


def match_hospital(existing: dict, scraped_list: list) -> tuple[dict | None, float]:
    """
    Find best match for an existing hospital in scraped data.

    Returns: (scraped_entry, similarity_score) or (None, 0.0)
    Uses keyword overlap as primary signal, area validation as secondary.
    """
    best_match = None
    best_score = 0.0

    existing_name = existing.get('hospital_name', '')
    existing_area = existing.get('area', '')

    for scraped in scraped_list:
        # Skip generic titles
        if is_generic_title(scraped.get('title', '')):
            continue

        scraped_name = scraped.get('title', '')
        scraped_city = scraped.get('city') or ''
        scraped_neighborhood = scraped.get('neighborhood') or ''

        score, area_valid = calculate_match_score(
            existing_name, scraped_name,
            existing_area, scraped_city, scraped_neighborhood
        )

        # Accept matches with score >= 0.7 (lower threshold due to keyword focus)
        if score > best_score:
            best_score = score
            best_match = scraped

    # Only return match if score is high enough (0.7 threshold)
    if best_score >= 0.7:
        return best_match, best_score

    return None, 0.0


def enrich_hospital(existing: dict, scraped: dict) -> dict:
    """Merge scraped data into existing hospital record.

    ONLY adds fields that don't already exist in the original.
    Original data is the source of truth.
    """
    enriched = existing.copy()

    # Add scraped fields (only if not already present in original)
    if 'address' not in existing or not existing.get('address'):
        enriched['address'] = scraped.get('address')

    if 'phone' not in existing or not existing.get('phone'):
        phone = scraped.get('phone')
        if phone:
            enriched['phone'] = phone

    if 'website' not in existing or not existing.get('website'):
        enriched['website'] = scraped.get('url')

    if 'rating' not in existing or not existing.get('rating'):
        score = scraped.get('totalScore')
        if score:
            enriched['rating'] = str(score)

    if 'review_count' not in existing:
        reviews = scraped.get('reviewsCount')
        if reviews:
            enriched['review_count'] = reviews

    # Add hours (only if not already present)
    opening_hours = scraped.get('openingHours', [])
    if opening_hours and 'hours' not in existing:
        hours = extract_hours(opening_hours)
        if hours:
            enriched['hours'] = hours

    # Add location (only if not already present)
    location = scraped.get('location', {})
    if location and 'lat' not in existing:
        enriched['lat'] = location.get('lat')
        enriched['lng'] = location.get('lng')

    # Add categories/specialty if missing
    if 'specialty' not in existing or not existing.get('specialty'):
        categories = scraped.get('categories', [])
        if categories:
            enriched['specialty'] = ', '.join(categories)

    # Add source info for tracking
    enriched['scraped_source'] = 'google_maps'
    enriched['scraped_at'] = scraped.get('scrapedAt')
    enriched['match_score'] = 1.0  # Will be updated by caller

    return enriched


def main():
    # Load data
    with open('/home/sak/hospital-search-hdfc-care/hospitals.json') as f:
        hospitals = json.load(f)
    
    with open('/home/sak/.hermes/cache/scratch/drive_file.xlsx') as f:
        scraped = json.load(f)
    
    print(f"Loaded {len(hospitals)} existing hospitals")
    print(f"Loaded {len(scraped)} scraped entries")
    
    # Filter out generic entries from scraping
    valid_scraped = [s for s in scraped if not is_generic_title(s.get('title', ''))]
    print(f"Valid scraped entries (after filtering): {len(valid_scraped)}")
    
    # Match and enrich (with deduplication)
    matched = 0
    high_confidence = 0
    enriched_hospitals = []
    used_scraped_ids = set()  # Track which scraped entries have been used

    for hospital in hospitals:
        scraped_match, score = match_hospital(hospital, valid_scraped)

        if scraped_match:
            # Check if this scraped entry is already used
            scraped_id = scraped_match.get('placeId') or id(scraped_match)

            if scraped_id in used_scraped_ids:
                # This scraped entry is already matched to another hospital
                # Skip this match to avoid duplicate addresses
                enriched_hospitals.append(hospital)
            else:
                matched += 1
                enriched = enrich_hospital(hospital, scraped_match)
                enriched['match_score'] = score  # Override the placeholder
                used_scraped_ids.add(scraped_id)

                if score >= 0.85:
                    high_confidence += 1

                enriched_hospitals.append(enriched)
        else:
            # No match found, keep original unchanged
            enriched_hospitals.append(hospital)
    
    print(f"\nMatching results:")
    print(f"  Matched: {matched}/{len(hospitals)} ({100*matched/len(hospitals):.1f}%)")
    print(f"  High confidence (>=0.85): {high_confidence}")
    
    # Check for duplicates
    from collections import Counter
    addresses = []
    for h in enriched_hospitals:
        addr = h.get('address', '')
        if addr and 'scraped_source' in h:
            addresses.append(addr[:50])
    
    addr_counts = Counter(addresses)
    duplicates = {k: v for k, v in addr_counts.items() if v > 1}
    print(f"  Duplicate addresses: {len(duplicates)}")
    
    # Save enriched data
    output_path = Path('/home/sak/hospital-search-hdfc-care/hospitals_enriched.json')
    with open(output_path, 'w') as f:
        json.dump(enriched_hospitals, f, indent=2)
    
    print(f"\nSaved enriched data to {output_path}")
    
    # Show sample matches with scores
    print("\nSample matches:")
    for i, hospital in enumerate(hospitals[:20]):
        scraped_match, score = match_hospital(hospital, valid_scraped)
        status = "✓" if scraped_match else "✗"
        print(f"\n  {i+1}. {status} {hospital['hospital_name']}")
        if scraped_match:
            print(f"     Matched to: {scraped_match['title']}")
            print(f"     Score: {score:.2f}")
            if scraped_match.get('address'):
                print(f"     Address: {scraped_match['address'][:60]}...")
            if scraped_match.get('phone'):
                print(f"     Phone: {scraped_match['phone']}")


if __name__ == '__main__':
    main()
