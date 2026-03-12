# Scrapy Web Scraping STEELITE

A Scrapy-based pipeline for scraping Steelite product data from multiple retailer websites and populating a master Excel spreadsheet (`sources/STEELITE.xlsx`).

---

## Project Overview

This project scrapes product details (descriptions, dimensions, pricing, images, materials, etc.) for Steelite/Utopia catalog numbers across several retailer sites, then writes the collected data back into a structured Excel file.

---

## Prerequisites

- Python 3.12 (`C:\Users\admin\AppData\Local\Programs\Python\Python312\python.exe`)
- Scrapy installed under Python 3.12 — run as `python -m scrapy` (not `scrapy` directly)
- `openpyxl`, `pandas`, `requests`, `pdfplumber` (optional, for PDF extraction)

Install dependencies:
```bash
pip install -r requirements.txt
```

---

## Repository Structure

```
.
├── catalog_numbers.json              # All Mfr Catalog Numbers from the Excel sheet
├── incomplete_catalog_numbers_v0.8.json  # Catalog numbers with no data yet (columns E–T blank)
├── sources/
│   └── STEELITE.xlsx                 # Master product spreadsheet
├── steelite/                         # Scrapy project root
│   ├── scrapy.cfg
│   ├── steelite/
│   │   ├── items.py
│   │   ├── pipelines.py
│   │   ├── settings.py
│   │   └── spiders/
│   │       ├── almoroojstore.py
│   │       ├── bgbenton.py
│   │       ├── drinkstuff.py
│   │       ├── goforgreenuk.py
│   │       ├── granbazar_fixed.py    # Use this, not granbazar.py (duplicate name issue)
│   │       ├── kitchenrestock.py
│   │       ├── rillcatering.py
│   │       ├── russoequip.py
│   │       ├── steelite_com.py
│   │       ├── steelite_utopia.py
│   │       ├── tabletopstyle.py
│   │       ├── wasserstrom_v0_1.py
│   │       └── webstaurantstore.py
│   └── *.json                        # Scraped output files per source
├── populate_steelite_from_*.py       # Scripts to write scraped data into the Excel file
├── read_steelite.py                  # Exports all catalog numbers → catalog_numbers.json
├── read_incomplete_steelite.py       # Exports incomplete rows → incomplete_catalog_numbers_v0.8.json
├── filter_unfound.py                 # Summarises found/unfound/blocked items in a JSON output
├── fill_na_steelite.py               # Fills blank cells (E–T) in the Excel with "n/a"
└── fetch_api_data_fixed.py           # Fetches product data directly from the Steelite-Utopia API
```

---

## Running a Spider

All spiders must be run from inside the `steelite/` directory (where `scrapy.cfg` lives):

```bash
cd steelite
C:\Users\admin\AppData\Local\Programs\Python\Python312\python.exe -m scrapy crawl <spider-name> -o output.json
```

| Spider file | Spider name |
|---|---|
| `almoroojstore.py` | `almoroojstore` |
| `bgbenton.py` | `bgbenton` |
| `drinkstuff.py` | `drinkstuff` |
| `goforgreenuk.py` | `goforgreenuk` |
| `granbazar_fixed.py` | `granbazar` |
| `kitchenrestock.py` | `kitchenrestock` |
| `rillcatering.py` | `rillcatering` |
| `russoequip.py` | `russoequip` |
| `steelite_com.py` | `steelite-com` |
| `steelite_utopia.py` | `steelite-utopia` |
| `tabletopstyle.py` | `tabletopstyle` |
| `wasserstrom_v0_1.py` | `wasserstrom` |
| `webstaurantstore.py` | `webstaurantstore` |

Alternatively, use `run_spider.py` from the project root:

```bash
python run_spider.py
```

---

## Spider Architecture

### Search + Product Pattern
Used by Wasserstrom, GranBazar, etc.:
1. `start_requests()` issues search queries
2. `parse_search_results()` paginates and collects product URLs
3. `parse_product()` scrapes each detail page

### Catalog-Lookup Pattern
Used by TableTopStyle, Drinkstuff, etc.:
1. `start_requests()` reads `incomplete_catalog_numbers_v0.8.json`
2. Generates a search request per catalog number
3. `parse_search()` identifies the matching product
4. `parse_product()` fetches the detail page if a URL is available

---

## Output Item Fields

| Field | Description |
|---|---|
| `catalog_number` | Steelite/Utopia Mfr catalog number |
| `product_name` | Product title |
| `product_url` | URL of the scraped product page |
| `overview` | Description / marketing text |
| `price` | Listed price |
| `image_link` | Primary image URL |
| `alternative_image_links` | Additional image URLs |
| `length`, `width`, `height`, `diameter` | Physical dimensions |
| `material`, `color`, `pattern` | Physical attributes |
| `volume` / `capacity` | Capacity (e.g. 12cl) |
| `ean_code`, `barcode`, `item_number` | Identifiers (site-specific) |
| `found` | `true` if product was found, `false` otherwise |
| `blocked` | `true` if the request was blocked (403, CAPTCHA, etc.) |

---

## Utility Scripts

| Script | Purpose |
|---|---|
| `read_steelite.py` | Reads the Excel and exports all catalog numbers to `catalog_numbers.json` |
| `read_incomplete_steelite.py` | Exports rows with no data in columns E–T to `incomplete_catalog_numbers_v0.8.json` |
| `filter_unfound.py` | Analyses a scraped JSON file and reports found/unfound/blocked counts |
| `fill_na_steelite.py` | Fills all blank cells in columns E–T of the Excel with `"n/a"` |
| `fetch_api_data_fixed.py` | Fetches data directly from the Steelite-Utopia product API |
| `populate_steelite_from_<source>.py` | Reads a scraped JSON and writes matched data into the Excel |

---

## Notes

- Do **not** run `granbazar.py` and `granbazar_fixed.py` at the same time — they share the same spider name and Scrapy may pick the wrong one.
- Wasserstrom pagination uses `beginIndex` increments, not `pageNumber`.
- GranBazar product attributes (volume, diameter, height, material, color) are often embedded in the product name and extracted with regex rather than scraped from spec tables.
- Error handling: HTTP 403/404 → item yielded with `found=False`; network errors → item yielded with `blocked=True`.

