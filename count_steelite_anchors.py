import requests
from bs4 import BeautifulSoup

url = "https://www.goforgreenuk.com/search/products?keywords=steelite"
html = requests.get(url, timeout=30).text
soup = BeautifulSoup(html, "html.parser")

urls = set()
for a in soup.select("a[href]"):
    href = (a.get("href") or "").strip()
    text = " ".join(a.stripped_strings).lower()
    if not href:
        continue
    full = href if href.startswith("http") else "https://www.goforgreenuk.com" + (href if href.startswith("/") else "/" + href)
    lower = full.lower()
    if any(x in lower for x in ["/search", "/account", "/contact", "/wishlist", "/checkout", "/blog", "/shop-"]):
        continue
    if lower.endswith((".jpg", ".png", ".svg", ".webp")):
        continue
    if "steelite" in lower or "steelite" in text:
        urls.add(full)

print("count", len(urls))
for u in sorted(urls):
    print(u)
