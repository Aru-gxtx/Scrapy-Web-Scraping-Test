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

# Test 1: page=11 with rpp=100 (beyond the 1000 cap)
r = requests.get(base, params={"hashid": HASHID, "query": "steelite", "page": 11, "rpp": 100}, headers=headers, timeout=15)
print(f"page=11 rpp=100: status={r.status_code} len={len(r.json().get('results', []))} total={r.json().get('total')}")

# Test 2: rpp=200
r = requests.get(base, params={"hashid": HASHID, "query": "steelite", "page": 1, "rpp": 200}, headers=headers, timeout=15)
print(f"page=1 rpp=200: status={r.status_code} len={len(r.json().get('results', []))} total={r.json().get('total')}")

# Test 3: rpp=1000
r = requests.get(base, params={"hashid": HASHID, "query": "steelite", "page": 1, "rpp": 1000}, headers=headers, timeout=15)
d = r.json()
print(f"page=1 rpp=1000: status={r.status_code} len={len(d.get('results', []))} total={d.get('total')} results_per_page={d.get('results_per_page')}")

r = requests.get(base, params={"hashid": HASHID, "query": "steelite", "page": 1, "rpp": 1}, headers=headers, timeout=15)
d = r.json()
facets = d.get("facets", {})
print("\nAvailable facets:", list(facets.keys()))
for fname, fdata in list(facets.items())[:3]:
    terms = fdata.get("terms", {}).get("buckets", [])
    if terms:
        print(f"  {fname}: {[t['key'] for t in terms[:5]]}")
