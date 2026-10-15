# Hospital Data Enrichment Plan

## Goal
Enrich the 618-hospital HDFC Ergo + Care Supreme network dataset with verified, structured fields beyond what the source Google Sheet provides.

## Current Schema (per hospital)
`name, insurance, area, specialty, contact_number[], rating, distance_km, travel_time_min, hdfc_final_score, is_recommended`

## Target Schema (enriched)
| Field | Source | Phase |
|---|---|---|
| `address` (street + landmark) | Google Maps | 1 |
| `website` | Google Maps / web search | 1 |
| `phone_reception` (primary) | Google Maps | 1 |
| `phone_emergency` (if listed) | Google Maps / website | 2 |
| `hours` (OPD timing, 24/7 flag) | Google Maps | 1 |
| `lat` / `lng` (Google Maps coords) | Google Maps | 1 |
| `full_specialties[]` (department list) | Hospital website | 2 |
| `bed_count` / `icu_beds` | Hospital website | 2 |
| `accreditation[]` (NABH, NABL) | Hospital website / nabh.co.in | 2 |
| `doctor_count` (if listed) | Hospital website | 2 |

## Phase 1: Google Maps Enrichment (all ~618 hospitals)

### What
Scrape address, phone(s), website URL, hours, lat/lng from Google Maps for every hospital.

### Why first
- Highest signal-to-noise ratio — these fields are reliable and consistently available
- Fully automatable with no per-site selector work
- Covers ~80% of missing data in one pass

### Method (IMPLEMENTED)
1. Use Termux Browser Pilot (TBP) on Android device (`u0_a221@100.70.18.84:8022`)
2. Script runs ON TERMUX (not via SSH) to avoid quoting issues with complex hospital names
3. For each hospital name, search Google Maps: `site:hospitals near <area>` or direct `"hospital_name" hospital mehdipatnam`
4. Extract structured fields from rendered page text (token-efficient, avoids brittle selectors)
5. Write results to `enriched_hospitals.json` alongside existing data

### Rate Limiting
- 5–10 second delay between requests (Google Maps throttles aggressively)
- Batch of ~60 hospitals/hour → full dataset in ~10 hours (overnight feasible)
- Retry with exponential backoff on 429 / CAPTCHA pages

### Validation
- Cross-check extracted phone against existing `contact_number[]` (fuzzy match)
- Flag hospitals where Google Maps returns zero results for manual review
- Expected: 50–70 hospitals may have no Maps listing (small/newer facilities)

### Output
New file: `enriched_hospitals.json` — original fields preserved, enriched fields appended.
No changes to `hospitals.json` until Phase 1 is validated against a sample batch.

### Lessons Learned (2026-10-15)
- **SSH quoting breaks complex names**: Hospital names with `()`, `&`, etc. break when passed through SSH single-quote wrapping. Solution: run script ON TERMUX, not via SSH.
- **Google Maps text structure varies**: Detail pages have navigation bar ("Restaurants", "Hotels", "Things to do") that must be skipped. Name extraction requires looking for lines containing "Hospital"/"Clinic" or followed by rating pattern.
- **Address format varies**: Can be "Fl no-303, 12-2, ... Hyderabad" or "12-2-831/87, Asif Nagar Rd, ...". Regex must handle both.
- **Phone format varies**: "040 2351 3743" (area code + space + number) or "079979 96030" (no area code). Regex must match both.
- **Hours format varies**: "Open 24 hours" or "Open · Closes 7:30 pm" (middle dot separator). Regex must handle both.
- **Wrong match risk**: Google Maps may return a different hospital's detail page (e.g., searching "Mythri Hospital" returned "Yashoda Hospitals"). Need to verify name match and retry if mismatch.

## Phase 2: Website Deep-Dive (multispecialty + top-rated subset, ~50–80 hospitals)

### What
Visit each hospital's website to extract full specialty list, bed/ICU counts, accreditation, doctor count.

### Why second
- Per-site DOM structure varies wildly — requires selector work per hospital or group
- Only ~50–80 hospitals have websites worth scraping (many small clinics don't)
- Higher effort, lower automation yield

### Method
1. Filter to hospitals with `website` field populated AND `specialty` = multispeciality OR rating ≥ 4.0
2. For each site, navigate via TBP and extract:
   - Departments/specialties page → `full_specialties[]`
   - About/Infrastructure page → bed count, ICU beds
   - Footer or accreditation section → NABH/NABL status
3. Store raw extracted text per hospital for auditability

### Fallback Strategy
- If website extraction fails (paywall, anti-bot, no departments page), mark fields as `null` and continue
- Do NOT block the pipeline on a single hospital failure

## Phase 3: Data Quality & Integration (post-Phase 2)

### What
Merge enriched data back into the canonical dataset, validate, and update the CLI.

### Steps
1. Run deduplication: if Google Maps phone differs from sheet phone, prefer Maps (more likely current)
2. Flag inconsistencies: hospital listed as "multispeciality" but website shows single specialty → mark for review
3. Update `hospital_search.py` to support new fields (`--sort beds`, `--accreditation nabh`, etc.)
4. Write a migration script that merges enriched fields into `hospitals.json` (preserves original data)

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Google Maps CAPTCHA/throttle | Phase 1 stalls | Rate limit, retry with backoff, skip and return later |
| Hospital names don't match Maps listings | Missing data for some hospitals | Fuzzy name matching, manual fallback list |
| Website anti-bot (Cloudflare, etc.) | Phase 2 incomplete for some hospitals | TBP stealth mode, accept nulls gracefully |
| Stale Maps data (closed hospitals) | Wrong phone/address | Cross-check with existing contact list; flag discrepancies |
| Termux device offline during run | Pipeline halts | Design for resumability — checkpoint after each batch of 50 |

## Resumability
- Write progress to `enrichment_progress.json` (hospital index, last successful entry)
- Restart script picks up from checkpoint — no re-scraping completed hospitals
- Phase 1 and Phase 2 each have independent checkpoints

## Estimated Timeline
| Phase | Scope | Time (Termux, sequential) |
|---|---|---|
| Phase 1 build + test | 5-hospital sample | 2 hours (dev) |
| Phase 1 full run | 618 hospitals | ~10 hours (overnight) |
| Phase 2 build + test | 5-hospital sample | 3 hours (dev, selector work) |
| Phase 2 full run | ~60 hospitals | ~5 hours |
| Phase 3 integration | Merge + CLI update | 2 hours (dev) |

## Success Criteria
- [ ] Phase 1: ≥80% of hospitals have `address`, `phone_reception`, `lat`/`lng` populated
- [ ] Phase 2: ≥60% of target subset has ≥3 of {full_specialties, bed_count, accreditation}
- [ ] No data loss: original `hospitals.json` fields fully preserved in enriched output
- [ ] CLI supports querying new fields without breaking existing queries
