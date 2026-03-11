import requests, json

HASHID = "baeda13069f4a0d7caf0dfdaf0aa8752"
ZONE = "eu1"
base = f"https://{ZONE}-search.doofinder.com/5/search"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.goforgreenuk.com/",
}

def search(query="steelite", filters=None, rpp=1, page=1):
    params = {"hashid": HASHID, "query": query, "page": page, "rpp": rpp}
    if filters:
        params.update(filters)
    r = requests.get(base, params=params, headers=headers, timeout=15)
    return r.json() if r.status_code == 200 else {}

# Get all categories
d = search(rpp=1)
cats = d.get("facets", {}).get("categories", {}).get("terms", {}).get("buckets", [])
print(f"All category buckets ({len(cats)}):")
for c in cats:
    print(f"  {c['key']:50s} count={c['doc_count']}")

print()
# Get all brands
brands = d.get("facets", {}).get("brand", {}).get("terms", {}).get("buckets", [])
print(f"All brand buckets ({len(brands)}):")
for b in brands:
    print(f"  {b['key']:40s} count={b['doc_count']}")
