import requests, json

HASHID = "baeda13069f4a0d7caf0dfdaf0aa8752"
ZONE = "eu1"
base = f"https://{ZONE}-search.doofinder.com/5/search"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.goforgreenuk.com/",
    "Origin": "https://www.goforgreenuk.com",
}

def search_total(query="steelite", filters=None):
    params = {"hashid": HASHID, "query": query, "page": 1, "rpp": 1}
    if filters:
        params.update(filters)
    r = requests.get(base, params=params, headers=headers, timeout=15)
    if r.status_code != 200:
        return None, None
    d = r.json()
    return d.get("total"), d.get("total_found")

# First get all categories
params = {"hashid": HASHID, "query": "steelite", "page": 1, "rpp": 100}
r = requests.get(base, params=params, headers=headers, timeout=15)
d = r.json()
facets = d.get("facets", {})
categories = facets.get("categories", {}).get("terms", {}).get("buckets", [])
print("All categories:")
for c in categories:
    print(f"  {c['key']:60s} count={c['doc_count']}")

print()

# Try price range splits
price_ranges = [
    (0, 5), (5, 15), (15, 30), (30, 50), (50, 80), 
    (80, 120), (120, 200), (200, 400), (400, 3000)
]
print("Price range partition counts:")
for lo, hi in price_ranges:
    flt = {"filter[best_price][gte]": lo, "filter[best_price][lt]": hi}
    total, found = search_total(filters=flt)
    print(f"  £{lo:4} - £{hi:5}: total={total}, total_found={found}")

# No-price items
_, found0 = search_total(filters={"filter[best_price][lte]": 0})
print(f"  price=0: total_found={found0}")
