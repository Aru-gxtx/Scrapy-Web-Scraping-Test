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

# First, get page 1 with 100 results per page to understand structure
params = {"hashid": HASHID, "query": "steelite", "page": 1, "rpp": 100}
r = requests.get(base, params=params, headers=headers, timeout=30)
print("Status:", r.status_code)
data = r.json()
print("Keys:", list(data.keys()))

# Check result structure
results = data.get("results", [])
print(f"\nTotal: {data.get('total', '?')} | rpp: {data.get('rpp', '?')} | page: {data.get('page', '?')}")
print(f"Results on this page: {len(results)}")

if results:
    print("\nFirst result keys:", list(results[0].keys()))
    for item in results[:5]:
        print(" -", item.get("title", "?"), "|", item.get("link", item.get("url", item.get("df_url", "?"))))
