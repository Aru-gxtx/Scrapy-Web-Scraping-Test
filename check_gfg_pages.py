import time
from playwright.sync_api import sync_playwright

CANDIDATE_URLS = [
    "https://www.goforgreenuk.com/search/products?keywords=steelite",
    "https://www.goforgreenuk.com/search/products?keywords=steelite&page=2",
    "https://www.goforgreenuk.com/search/products?keywords=steelite&p=2",
    "https://www.goforgreenuk.com/search/products?keywords=steelite&pg=2",
    "https://www.goforgreenuk.com/search/products?keywords=steelite&offset=20",
]


def count_urls(page):
    anchors = page.query_selector_all("a[href]")
    urls = set()
    for a in anchors:
        href = (a.get_attribute("href") or "").strip()
        if not href:
            continue
        if "/" not in href:
            continue
        full = href if href.startswith("http") else f"https://www.goforgreenuk.com{href if href.startswith('/') else '/' + href}"
        lower = full.lower()
        if any(x in lower for x in ["/account", "/contact", "/search", "/checkout", "/wishlist", "/blog"]):
            continue
        if lower.endswith((".jpg", ".png", ".svg", ".webp")):
            continue
        if "goforgreenuk.com" in lower and ("-vv" in lower or "-v" in lower or "/steelite-" in lower):
            urls.add(full)
    return urls


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    for url in CANDIDATE_URLS:
        page.goto(url, timeout=90000)
        time.sleep(4)
        for _ in range(5):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1.5)

        found = count_urls(page)
        print(url)
        print(f"found={len(found)}")
        for s in sorted(list(found))[:5]:
            print(f"  {s}")
        print("-")

    browser.close()
