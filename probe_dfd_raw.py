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
params = {"hashid": HASHID, "query": "steelite", "page": 1, "rpp": 100}
r = requests.get(base, params=params, headers=headers, timeout=15)
print("Status:", r.status_code)
print("Response headers:", dict(r.headers))
text = r.text
print("Response len:", len(text))
print("First 1000 chars:", text[:1000])
