#!/usr/bin/env python3
"""
Example: Query top-rated hospitals by insurance, area, and specialty.

This script demonstrates how to query the enriched hospital dataset
to find top-rated hospitals matching specific criteria.

Usage:
    python3 examples/query_top_hospitals.py
"""

import json
from pathlib import Path


def load_hospitals(data_dir: str = ".") -> list[dict]:
    """Load enriched hospital data."""
    data_path = Path(data_dir) / "hospitals_enriched.json"
    with open(data_path) as f:
        return json.load(f)


def find_top_hospitals_near_area(
    insurance: str,
    reference_area: str,
    max_distance_km: float = 7.0,
    specialty_keywords: list[str] | None = None,
    limit: int = 3,
) -> list[dict]:
    """
    Find top-rated hospitals near a reference area.

    This queries ALL hospitals within max_distance_km, not just those
    in the reference area. Useful for finding nearby options.

    Args:
        insurance: Insurance provider (e.g., "Care Supreme", "HDFC Ergo")
        reference_area: Reference area name (e.g., "Mehdipatnam") - used for display only
        max_distance_km: Maximum distance in km (default: 7.0)
        specialty_keywords: Keywords to match in specialty field
        limit: Number of results to return

    Returns:
        List of hospital dicts sorted by rating (desc) then distance (asc)
    """
    hospitals = load_hospitals()

    # Filter by insurance only (not area - we want nearby hospitals)
    results = [
        h for h in hospitals
        if h.get("insurance") == insurance
    ]

    # Filter by specialty keywords (if provided)
    if specialty_keywords:
        results = [
            h for h in results
            if any(kw in h.get("specialty", "").lower() for kw in specialty_keywords)
        ]

    # Filter by distance (None means no distance data, include it)
    results = [
        h for h in results
        if h.get("distance_km") is None or h.get("distance_km", 999) <= max_distance_km
    ]

    # Sort by rating (descending), then distance (ascending)
    results.sort(
        key=lambda x: (
            x.get("google_rating", 0) or 0,
            -(x.get("distance_km", 999) or 0),
        ),
        reverse=True,
    )

    return results[:limit]


def find_top_hospitals_in_area(
    insurance: str,
    area: str,
    max_distance_km: float = 7.0,
    specialty_keywords: list[str] | None = None,
    limit: int = 3,
) -> list[dict]:
    """
    Find top-rated hospitals in a specific area.

    Args:
        insurance: Insurance provider (e.g., "Care Supreme", "HDFC Ergo")
        area: Area name (e.g., "Mehdipatnam", "Banjara Hills")
        max_distance_km: Maximum distance in km (default: 7.0)
        specialty_keywords: Keywords to match in specialty field
        limit: Number of results to return

    Returns:
        List of hospital dicts sorted by rating (desc) then distance (asc)
    """
    hospitals = load_hospitals()

    # Filter by insurance and area
    results = [
        h for h in hospitals
        if h.get("insurance") == insurance
        and h.get("area") == area
    ]

    # Filter by specialty keywords (if provided)
    if specialty_keywords:
        results = [
            h for h in results
            if any(kw in h.get("specialty", "").lower() for kw in specialty_keywords)
        ]

    # Filter by distance (None means no distance data, include it)
    results = [
        h for h in results
        if h.get("distance_km") is None or h.get("distance_km", 999) <= max_distance_km
    ]

    # Sort by rating (descending), then distance (ascending)
    results.sort(
        key=lambda x: (
            x.get("google_rating", 0) or 0,
            -(x.get("distance_km", 999) or 0),
        ),
        reverse=True,
    )

    return results[:limit]


def format_hospital(h: dict) -> str:
    """Format hospital info for display."""
    phone = h.get("contact_number", ["N/A"])[0] if h.get("contact_number") else "N/A"
    scraped_phone = h.get("phone", "")

    lines = [
        f"{h['hospital_name']}",
        f"   Area: {h.get('area')} | Distance: {h.get('distance_km') or 'N/A'}km",
        f"   Rating: ⭐{h.get('google_rating', 'N/A')}",
        f"   Specialty: {h.get('specialty')}",
        f"   Phone (original): {phone}",
    ]

    if scraped_phone:
        lines.append(f"   Phone (scraped): {scraped_phone}")

    return "\n".join(lines)


def main():
    """Main example: Find top 3 Care Supreme multi-speciality hospitals near Mehdipatnam."""

    print("=" * 60)
    print("Example: Top Hospitals Query")
    print("=" * 60)
    print()

    # Example 1: Top 3 Care Supreme multi-speciality hospitals NEAR Mehdipatnam
    # (within 7km, not just in Mehdipatnam area)
    print("Query: Top 3 Care Supreme multi-speciality hospitals near Mehdipatnam (7km)")
    print("-" * 60)

    results = find_top_hospitals_near_area(
        insurance="Care Supreme",
        reference_area="Mehdipatnam",
        max_distance_km=7.0,
        specialty_keywords=["multi"],  # Multi-speciality hospitals include surgery
        limit=3,
    )

    print(f"Found {len(results)} hospitals matching criteria:\n")

    for i, h in enumerate(results, 1):
        print(f"{i}. {format_hospital(h)}")
        print()

    # Example 2: All Care Supreme hospitals IN Mehdipatnam
    print("-" * 60)
    print("Query: All Care Supreme hospitals IN Mehdipatnam")
    print("-" * 60)

    all_hospitals = load_hospitals()
    mehdipatnam_care = [
        h for h in all_hospitals
        if h.get("area") == "Mehdipatnam" and h.get("insurance") == "Care Supreme"
    ]

    for h in mehdipatnam_care:
        phone = h.get("contact_number", ["N/A"])[0] if h.get("contact_number") else "N/A"
        print(f"  - {h['hospital_name']} | Rating: ⭐{h.get('google_rating', 'N/A')} | Phone: {phone}")

    print()


if __name__ == "__main__":
    main()
