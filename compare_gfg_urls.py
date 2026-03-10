import re
import json
import requests
from pathlib import Path

base = "https://www.goforgreenuk.com/search/products?keywords=steelite"
html = requests.get(base, timeout=30).text.lower()
links = set(re.findall(r'href="([^"]+)"', html))
all_urls = set()
for x in links:
    if not x:
        continue
    full = x if x.startswith("http") else "https://www.goforgreenuk.com" + (x if x.startswith("/") else "/" + x)
    l = full.lower()
    if "/search" in l or l.endswith((".jpg", ".png", ".svg", ".webp")):
        continue
    if "goforgreenuk.com" in l and ("-v" in l or "/steelite-" in l):
        all_urls.add(full)

json_path = Path(r"c:\Users\admin\Documents\GitHub\Scrapy Web Scraping Test\steelite\goforgreenuk.json")
data = json.loads(json_path.read_text(encoding="utf-8"))
scraped = {item.get("product_url", "") for item in data if item.get("product_url")}

missing = sorted(u for u in all_urls if u not in scraped)
print(f"all_urls={len(all_urls)} scraped={len(scraped)} missing={len(missing)}")
for u in missing[:80]:
    print(u)
