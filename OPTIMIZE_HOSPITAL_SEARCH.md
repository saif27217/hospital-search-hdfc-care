# Hospital Search System Optimization Plan

## Current State Analysis

### Data Coverage
| Metric | Value | Status |
|--------|-------|--------|
| Total hospitals | 618 | ✓ Complete |
| Enriched with scraped data | 182 (29%) | ⚠️ 71% incomplete |
| Insurance providers | 2 (HDFC Ergo, Care Supreme) | ⚠️ Limited coverage |
| Unique specialties | 105 | ✓ Good diversity |
| Average rating | 3.98/5 | ✓ Decent |
| Hospitals with distance data | 372 (60%) | ⚠️ Missing for many |

### Data Gaps
- **Phone numbers**: 479 hospitals missing (78%)
- **Websites**: 436 hospitals missing (71%)
- **Operating hours**: 467 hospitals missing (76%)
- **Coordinates**: 436 hospitals missing (71%)

---

## Optimization Opportunities

### Priority 1: Complete Phase 1 Scraping (HIGH IMPACT, LOW EFFORT)

**Goal**: Enrich remaining 436 hospitals with Google Maps data

**What to scrape**:
- Address (full formatted address)
- Phone number(s)
- Website URL
- Operating hours
- Rating & review count
- Latitude/longitude coordinates

**Implementation**:
```bash
# Run on Termux (avoids SSH quoting issues)
python3 enrich_google_maps_termux.py --input hospitals.json --output hospitals_enriched.json

# Or incremental: only scrape unmatched hospitals
python3 enrich_google_maps_termux.py --input hospitals.json \
    --existing hospitals_enriched.json \
    --output hospitals_enriched.json
```

**Estimated time**: 2-3 hours on Termux (TBP daemon)
**Expected outcome**: 95%+ data coverage for all fields

---

### Priority 2: Add More Insurance Providers (HIGH IMPACT, MEDIUM EFFORT)

**Goal**: Expand coverage to 5-10 major health insurance providers

**Target insurers**:
1. Max Bupa Health Insurance
2. ICICI Lombard General Insurance
3. Star Health and Allied Insurance
4. New India Assurance
5. Oriental Insurance
6. HDFC Ergo (already covered)
7. Care Supreme (already covered)

**Implementation**:
1. Obtain hospital network lists for each insurer
2. Merge with existing dataset (dedup by hospital_name + area)
3. Re-run enrichment scraping for new hospitals

**Estimated time**: 1-2 days per insurer (data collection + processing)
**Expected outcome**: 5-7x more hospital coverage

---

### Priority 3: Phase 2 Website Deep-Dive (HIGH IMPACT, HIGH EFFORT)

**Goal**: Extract detailed department and service information from hospital websites

**Target hospitals**: Top 50-80 multispeciality/highest-rated hospitals
- Filter: `specialty` contains "multi" or "general" AND `google_rating` >= 4.0

**What to scrape**:
- Departments (surgery, cardiology, orthopedics, neurology, etc.)
- Doctor listings with specialties
- Services offered (OPD, IPD, emergency, ICU)
- Insurance verification pages
- Appointment booking info

**Implementation**:
```python
# Pseudocode for Phase 2 scraper
for hospital in top_hospitals:
    if 'scraped_source' not in hospital:
        continue
    
    # Scrape website for department info
    dept_data = scrape_website(hospital['website'])
    
    # Extract departments
    departments = extract_departments(dept_data)
    
    # Update hospital record
    hospital['departments'] = departments
    hospital['has_surgery'] = 'surgery' in str(departments).lower()
```

**Estimated time**: 1-2 weeks (manual verification needed)
**Expected outcome**: Ability to query "hospitals with surgery department"

---

### Priority 4: Enhanced Query CLI (MEDIUM IMPACT, LOW EFFORT)

**Goal**: Better search interface with advanced filtering

**Current CLI**:
```bash
hospital-search --insurance hdfc --area mehdipatnam --specialty multispeciality
```

**Proposed enhancements**:
```bash
# Sort options
hospital-search --sort rating|distance|score

# Limit results
hospital-search --limit 10

# Show only recommended hospitals
hospital-search --recommended-only

# Compare hospitals
hospital-search --compare hospital1,hospital2,hospital3

# Export to CSV/JSON
hospital-search --export csv|json
```

**Implementation**:
- Extend `hospital_search.py` with new flags
- Add sorting by rating, distance, final_score
- Add comparison view (side-by-side)
- Add export functionality

**Estimated time**: 1-2 days
**Expected outcome**: More flexible and powerful search interface

---

### Priority 5: Web UI (MEDIUM IMPACT, MEDIUM EFFORT)

**Goal**: Browser-based interface for browsing hospitals

**Features**:
- Search with filters (insurance, area, specialty, rating)
- Map view showing hospital locations
- Hospital detail pages with all info
- Comparison tool
- Export to CSV/JSON

**Implementation**:
```python
# Flask web app
from flask import Flask, render_template, request

app = Flask(__name__)

@app.route('/')
def index():
    # Load hospitals, apply filters
    hospitals = load_hospitals()
    return render_template('index.html', hospitals=hospitals)

@app.route('/hospital/<id>')
def hospital_detail(id):
    # Show single hospital details
    return render_template('hospital.html', hospital=hospital)

@app.route('/compare')
def compare():
    # Side-by-side comparison
    return render_template('compare.html', hospitals=hospitals)
```

**Estimated time**: 3-5 days
**Expected outcome**: User-friendly interface for non-technical users

---

### Priority 6: Comparison Feature (MEDIUM IMPACT, LOW EFFORT)

**Goal**: Compare multiple hospitals side-by-side

**Implementation**:
```python
def compare_hospitals(hospital_ids: list[str]) -> dict:
    """Compare hospitals by key metrics."""
    hospitals = [h for h in hospitals if h['hospital_name'] in hospital_ids]
    
    return {
        'hospitals': hospitals,
        'comparison': {
            'rating': [h.get('google_rating') for h in hospitals],
            'distance': [h.get('distance_km') for h in hospitals],
            'phone': [h.get('contact_number', ['N/A'])[0] for h in hospitals],
            'specialty': [h.get('specialty') for h in hospitals],
        }
    }
```

**CLI usage**:
```bash
hospital-search --compare "Mythri Hospital, Premier Hospital, Olive Hospitals"
```

**Estimated time**: 1 day
**Expected outcome**: Easy comparison for decision-making

---

### Priority 7: Export Features (LOW IMPACT, LOW EFFORT)

**Goal**: Export data for external use

**Formats**:
- CSV (for Excel/spreadsheets)
- JSON (for APIs/programs)
- Google Sheets (via Composio MCP)

**Implementation**:
```python
import csv
import json

def export_csv(hospitals: list[dict], output_path: str):
    """Export hospitals to CSV."""
    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=hospitals[0].keys())
        writer.writeheader()
        writer.writerows(hospitals)

def export_json(hospitals: list[dict], output_path: str):
    """Export hospitals to JSON."""
    with open(output_path, 'w') as f:
        json.dump(hospitals, f, indent=2)
```

**Estimated time**: 0.5 days
**Expected outcome**: Data usable in other tools

---

## Implementation Roadmap

### Phase 1: Quick Wins (Week 1)
- [ ] Complete Phase 1 scraping for remaining 436 hospitals
- [ ] Add export features (CSV, JSON)
- [ ] Add comparison feature

### Phase 2: Enhanced Search (Week 2)
- [ ] Build enhanced query CLI with sorting/filtering
- [ ] Add web UI (basic version)

### Phase 3: Deep Data (Week 3-4)
- [ ] Add more insurance providers (start with Max Bupa)
- [ ] Phase 2 website deep-dive for top 50 hospitals

### Phase 4: Advanced Features (Month 2)
- [ ] Map view with hospital locations
- [ ] Real-time insurance verification
- [ ] Mobile app (optional)

---

## Success Metrics

| Metric | Current | Target | Timeline |
|--------|---------|--------|----------|
| Data coverage | 29% | 95%+ | Week 1 |
| Insurance providers | 2 | 5-7 | Month 1 |
| Query flexibility | Basic | Advanced filters | Week 2 |
| Department data | 0% | 50+ hospitals | Month 1-2 |
| User interface | CLI only | Web UI + CLI | Week 2-3 |

---

## Technical Notes

### TBP Daemon Management
```bash
# Check status
ssh -o StrictHostKeyChecking=no -o BatchMode=yes \
    -i ~/.ssh/id_ed25519 -p 8022 u0_a221@100.70.18.84 \
    'cd ~/termux-browser-pilot && python3 cli.py status'

# Start daemon
ssh ... 'cd ~/termux-browser-pilot && python3 cli.py start --browser firefox'

# Stop daemon
ssh ... 'cd ~/termux-browser-pilot && python3 cli.py stop'
```

### Data Schema
```json
{
  "hospital_name": "Mythri Hospital",
  "insurance": "Care Supreme",
  "area": "Mehdipatnam",
  "specialty": "Multi-speciality",
  "contact_number": ["040-64588805"],
  "google_rating": 4.1,
  "distance_km": 0.8,
  "address": "Opp Pillar No. 81, PVNR Expressway...",
  "phone": "+91 79979 96030",
  "website": "https://...",
  "hours": "9 AM to 9 PM",
  "lat": 17.5044324,
  "lng": 78.5047291,
  "scraped_source": "google_maps",
  "scraped_at": "2026-03-23T15:00:07.720Z",
  "match_score": 1.0
}
```

### File Locations
- Original data: `/home/sak/hospital-search-hdfc-care/hospitals.json`
- Enriched data: `/home/sak/hospital-search-hdfc-care/hospitals_enriched.json`
- Scraping script: `/home/sak/hospital-search-hdfc-care/enrich_google_maps_termux.py`
- Matching script: `/home/sak/hospital-search-hdfc-care/enrich_from_scraped.py`
- Examples: `/home/sak/hospital-search-hdfc-care/examples/`

---

## Next Steps

1. **Immediate**: Complete Phase 1 scraping (Priority 1)
2. **This week**: Add export and comparison features (Priorities 6, 7)
3. **Next week**: Build enhanced CLI and web UI (Priorities 4, 5)
4. **Next month**: Add more insurers and deep-dive scraping (Priorities 2, 3)

---

*Document created: 2026-10-16*
*Last updated: 2026-10-16*
