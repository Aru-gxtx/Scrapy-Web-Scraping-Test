import requests, json

HASHID = "baeda13069f4a0d7caf0dfdaf0aa8752"
ZONE = "eu1"

# Try the standard Doofinder v5 search endpoint
base = f"https://{ZONE}-search.doofinder.com/5/search"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.goforgreenuk.com/",
    "Origin": "https://www.goforgreenuk.com",
}
params = {
    "hashid": HASHID,
    "query": "steelite",
    "page": 1,
    "rpp": 20,
    "type": "product",
}

r = requests.get(base, params=params, headers=headers, timeout=30)
print("Status:", r.status_code)
print("Content-Type:", r.headers.get("content-type", ""))
print("Body (first 2000):", r.text[:2000])

if r.status_code == 200:
    try:
        data = r.json()
        results = data.get("results", [])
        print(f"\nTotal: {data.get('total', '?')} | Results on page: {len(results)}")
        for item in results[:5]:
            print(" -", item.get("title", ""), "|", item.get("link", ""))
    except Exception as e:
        print("JSON parse error:", e)
