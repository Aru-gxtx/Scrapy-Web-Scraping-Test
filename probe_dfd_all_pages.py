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

# Page 1 to get total_found and check structure
params = {"hashid": HASHID, "query": "steelite", "page": 1, "rpp": 100}
r = requests.get(base, params=params, headers=headers, timeout=30)
data = r.json()
print(f"total: {data.get('total')} | total_found: {data.get('total_found')} | results: {len(data.get('results', []))}")

# Collect all URLs
all_urls = []
total = data.get("total", 0)
rpp = 100
max_page = (total + rpp - 1) // rpp
print(f"max_page: {max_page}")

for item in data.get("results", []):
    all_urls.append(item.get("link", ""))

# Get remaining pages
for page in range(2, max_page + 1):
    params["page"] = page
    r2 = requests.get(base, params=params, headers=headers, timeout=30)
    d2 = r2.json()
    results = d2.get("results", [])
    print(f"  page {page}: {len(results)} results")
    for item in results:
        all_urls.append(item.get("link", ""))

print(f"\nTotal URLs collected: {len(all_urls)}")
steelite_urls = [u for u in all_urls if u and "steelite" in u.lower()]
print(f"Steelite-specific URLs: {len(steelite_urls)}")
print("\nSample (first 10):")
for u in steelite_urls[:10]:
    print(" ", u)
