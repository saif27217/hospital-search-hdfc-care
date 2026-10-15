# hospital-search-hdfc-care

Offline hospital network lookup for **HDFC Ergo** and **Care Supreme** insurance in Hyderabad. Instant CLI search over 618 hospitals with area, specialty, rating, and distance filters — no API calls at query time.

## Data

Built from a curated Google Spreadsheet (5 sheets: base networks, Google ratings, proximity scoring, recommended hospitals). `hospitals.json` is the committed cache; the raw XLSX is fetched only on `--rebuild`.

Per-hospital fields: name, insurance, area, specialty, contact(s), Google rating, distance (km), travel time, HDFC proximity score, recommended flag.

## Requirements

- Python 3.8+ (stdlib only for search)
- `openpyxl` — only for `--rebuild`

## Install

```bash
git clone https://github.com/saif27217/hospital-search-hdfc-care.git
cd hospital-search-hdfc-care
pip install -r requirements.txt        # optional, rebuild only
ln -s "$(pwd)/hospital-search" ~/.local/bin/hospital-search
```

## Usage

```bash
# Closest HDFC Ergo hospitals in Mehdipatnam
hospital-search --insurance hdfc --area Mehdipatnam --sort distance

# Top-rated Care Supreme eye hospitals
hospital-search --insurance care --specialty "Eye" --sort rating --limit 5

# Just the best match's phone number
hospital-search --insurance hdfc --area Banjara --contact

# Rebuild cache from the Google Spreadsheet (network + openpyxl)
hospital-search --rebuild
```

### Flags

| Flag | Values | Default | |
|---|---|---|---|
| `--insurance` | `hdfc` \| `care` | all | Filter by provider |
| `--area` | free text | — | Fuzzy area/neighborhood match |
| `--specialty` | free text | — | Case-insensitive substring match |
| `--sort` | `distance` \| `rating` \| `score` \| `name` | `distance` | `score` = HDFC proximity composite |
| `--limit` | int | `20` | Max rows |
| `--contact` | flag | — | Print single top match's full contact card |
| `--rebuild` | flag | — | Re-download sheet, reparse, rewrite `hospitals.json` |

## Notes

- Distance for HDFC entries is bucket-mapped (0 → 0.5 km, 1 → 3 km, 2 → 7 km, 3 → 15 km) from the sheet's proximity buckets; Care Supreme entries carry measured km.
- Contacts are normalized: float artifacts stripped, multi-numbers split on `/`, extensions removed.
- Cache lives next to the script (`hospitals.json` in the repo); `--rebuild` rewrites it in place.

## Hermes skill

A token-efficient skill lives at `~/.hermes/skills/hospital-search/SKILL.md` for agent-driven queries.
