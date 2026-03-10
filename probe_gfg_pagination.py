import re
import requests

base = "https://www.goforgreenuk.com/search/products?keywords=steelite"
urls = [
    base,
    base + "&page=2",
    base + "&p=2",
    base + "&pg=2",
    base + "&start=20",
    base + "&offset=20",
]

for u in urls:
    r = requests.get(u, timeout=30)
    t = r.text.lower()
    links = set(re.findall(r'href="([^"]+)"', t))
    prods = [
        x for x in links
        if ("-v" in x or "/steelite-" in x)
        and "/search" not in x
        and not x.endswith((".jpg", ".png", ".svg", ".webp"))
    ]
    print(f"{u} status={r.status_code} len={len(t)} prods={len(prods)}")
