import requests, json

HASHID = "baeda13069f4a0d7caf0dfdaf0aa8752"
ZONE = "eu1"
base5 = f"https://{ZONE}-search.doofinder.com/5/search"
base6 = f"https://{ZONE}-search.doofinder.com/6/search"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.goforgreenuk.com/",
    "Origin": "https://www.goforgreenuk.com",
}

# Test v6 API
r = requests.get(base6, params={"hashid": HASHID, "query": "steelite", "page": 1, "rpp": 100}, headers=headers, timeout=15)
print(f"v6 page=1: status={r.status_code}")
if r.status_code == 200:
    d = r.json()
    print(f"  total={d.get('total')} total_found={d.get('total_found')} results={len(d.get('results', []))}")

# Test 'from' offset (Elasticsearch-style)
r = requests.get(base5, params={"hashid": HASHID, "query": "steelite", "from": 1000, "rpp": 100}, headers=headers, timeout=15)
print(f"\nv5 from=1000: status={r.status_code}")
if r.status_code == 200:
    d = r.json()
    print(f"  total={d.get('total')} results={len(d.get('results', []))}")

# Test filter by brand
r = requests.get(base5, params={"hashid": HASHID, "query": "steelite", "page": 1, "rpp": 1,
    "filter[brand][]": "Steelite"}, headers=headers, timeout=15)
print(f"\nfilter brand=Steelite: status={r.status_code}")
if r.status_code == 200:
    d = r.json()
    print(f"  total={d.get('total')} total_found={d.get('total_found')}")

# Test filter by category "Steelite"
r = requests.get(base5, params={"hashid": HASHID, "query": "steelite", "page": 1, "rpp": 1,
    "filter[categories][]": "Steelite"}, headers=headers, timeout=15)
print(f"\nfilter categories=Steelite: status={r.status_code}")
if r.status_code == 200:
    d = r.json()
    print(f"  total={d.get('total')} total_found={d.get('total_found')}")

# Test without query (browse all) filtered to Steelite brand
r = requests.get(base5, params={"hashid": HASHID, "query": "", "page": 1, "rpp": 1,
    "filter[brand][]": "Steelite"}, headers=headers, timeout=15)
print(f"\nno query filter brand=Steelite: status={r.status_code}")
if r.status_code == 200:
    d = r.json()
    print(f"  total={d.get('total')} total_found={d.get('total_found')}")

r = requests.get(base5, params={"hashid": HASHID, "query": "steelite", "page": 1, "rpp": 1}, headers=headers, timeout=15)
d = r.json()
price_facet = d.get("facets", {}).get("best_price", {})
print(f"\nPrice range: {price_facet.get('from', '?')} to {price_facet.get('to', '?')}")
price_stats = price_facet.get("range", {}).get("buckets", [{}])[0].get("stats", {})
print(f"  min={price_stats.get('min')} max={price_stats.get('max')} count={price_stats.get('count')}")
