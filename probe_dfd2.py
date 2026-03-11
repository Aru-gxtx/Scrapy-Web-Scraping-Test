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

# Try without type parameter
configs = [
    {"hashid": HASHID, "query": "steelite", "page": 1, "rpp": 10},
    {"hashid": HASHID, "query": "steelite", "page": 1, "rpp": 10, "type": "product,page"},
    {"hashid": HASHID, "query": "steelite", "page": 1, "rpp": 10, "type[]": "product"},
    {"hashid": HASHID, "q": "steelite", "page": 1, "rpp": 10},
]

for i, params in enumerate(configs):
    r = requests.get(base, params=params, headers=headers, timeout=15)
    print(f"Config {i}: status={r.status_code} body={r.text[:300]}")
    print()
