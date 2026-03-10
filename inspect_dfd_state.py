import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('https://www.goforgreenuk.com/search/products?keywords=steelite', timeout=90000)
    time.sleep(4)
    for _ in range(6):
        page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        time.sleep(2)

    keys = page.evaluate("""
        () => Object.keys(window).filter(k => /df|doo|search|layer/i.test(k)).slice(0, 200)
    """)
    print('window keys count:', len(keys))
    for k in keys[:80]:
        print(k)

    snippets = page.evaluate("""
        () => {
          const out = [];
          const candidates = ['doofinder', 'Doofinder', 'dfLayer', 'DFLayer', 'dfd', '_df'];
          for (const c of candidates) {
            try {
              if (window[c]) {
                const val = window[c];
                const type = typeof val;
                let info = '';
                if (type === 'object') {
                  const ks = Object.keys(val).slice(0, 40).join(',');
                  info = ` keys=${ks}`;
                }
                out.push(`${c}: type=${type}${info}`);
              }
            } catch (e) {}
          }
          return out;
        }
    """)
    print('\nCandidates:')
    for s in snippets:
        print(s)

    # Try to extract all URLs from scripts in DOM
    urls = page.evaluate("""
      () => {
        const txt = document.documentElement.innerHTML || '';
        const m = txt.match(/https?:\\/\\/www\\.goforgreenuk\\.com\\/[a-z0-9\\-/]+/gi) || [];
        return Array.from(new Set(m)).slice(0, 500);
      }
    """)
    print('\nExtracted absolute URLs from HTML:', len(urls))
    for u in urls[:30]:
        print(u)

    browser.close()
