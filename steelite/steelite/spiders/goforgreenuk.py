import re

import scrapy
from scrapy_playwright.page import PageMethod


class GoforgreenukSpider(scrapy.Spider):
    name = "goforgreenuk"
    allowed_domains = ["www.goforgreenuk.com"]
    start_urls = [
        "https://www.goforgreenuk.com/search/products?keywords=steelite",
        "https://www.goforgreenuk.com/search/products?keywords=steelite&search=products",
    ]
    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "HTTPERROR_ALLOWED_CODES": [403, 404, 429],
        "PLAYWRIGHT_BROWSER_TYPE": "chromium",
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 60_000,
        "DOWNLOAD_HANDLERS": {
            "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
            "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        },
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "DOWNLOAD_DELAY": 1.0,
        "DEFAULT_REQUEST_HEADERS": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        },
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._seen_product_urls = set()
        self._seen_listing_urls = set()

    @staticmethod
    def _clean_text(value):
        if value is None:
            return ""
        text = str(value)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def _normalize_key(value):
        text = GoforgreenukSpider._clean_text(value).lower()
        text = text.replace("\xa0", " ")
        text = re.sub(r"\s+", " ", text)
        return text.strip(" :")

    @staticmethod
    def _extract_first(specs, keys):
        for key in keys:
            value = specs.get(key, "")
            if value:
                return value
        return ""

    @staticmethod
    def _extract_from_text(pattern, text):
        match = re.search(pattern, text or "", flags=re.IGNORECASE)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _extract_catalog_number(name, url, body_text):
        for source in (name, url, body_text):
            if not source:
                continue
            match = re.search(r"\b([A-Z]{0,3}\d{3,}[A-Z0-9]*)\b", str(source).upper())
            if match:
                return match.group(1)
        return ""

    @staticmethod
    def _clean_image(url):
        raw = (url or "").strip()
        if not raw:
            return ""
        if raw.startswith("//"):
            return f"https:{raw}"
        return raw

    @staticmethod
    def _looks_like_product_url(url):
        if not url:
            return False
        lower = url.lower()
        if any(token in lower for token in ["/account", "/blog", "/contact", "/wishlist", "/checkout", "/search", "/shop-by-brand"]):
            return False
        if lower.endswith(".jpg") or lower.endswith(".png") or lower.endswith(".svg"):
            return False
        # Typical product URL pattern on this site includes a sku token at the end, e.g. -vv469 or -v0163.
        if re.search(r"-[a-z]{0,2}v\d{2,}[a-z0-9-]*$", lower):
            return True
        return "/steelite-" in lower and lower.count("-") >= 2

    def start_requests(self):
        for url in self.start_urls:
            self._seen_listing_urls.add(url)
            yield scrapy.Request(
                url=url,
                callback=self.parse_search,
                errback=self.errback_request,
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_page_methods": [
                        PageMethod("wait_for_timeout", 3000),
                        PageMethod("evaluate", "window.scrollTo(0, document.body.scrollHeight)"),
                        PageMethod("wait_for_timeout", 2000),
                        PageMethod("evaluate", "window.scrollTo(0, document.body.scrollHeight)"),
                        PageMethod("wait_for_timeout", 2000),
                        PageMethod("evaluate", "window.scrollTo(0, document.body.scrollHeight)"),
                        PageMethod("wait_for_timeout", 2000),
                        PageMethod("evaluate", "window.scrollTo(0, document.body.scrollHeight)"),
                        PageMethod("wait_for_timeout", 2000),
                        PageMethod("evaluate", "window.scrollTo(0, document.body.scrollHeight)"),
                        PageMethod("wait_for_timeout", 2000),
                    ],
                },
                dont_filter=True,
            )

    async def parse_search(self, response):
        page = response.meta.get("playwright_page")
        page_anchor_urls = set()
        if page:
            try:
                # Doofinder may render links in dynamic frames not visible in response.css.
                for frame in page.frames:
                    try:
                        hrefs = await frame.eval_on_selector_all(
                            "a[href]",
                            "elements => elements.map(e => e.href || e.getAttribute('href') || '').filter(Boolean)",
                        )
                    except Exception:
                        hrefs = []
                    for href in hrefs or []:
                        page_anchor_urls.add(response.urljoin((href or "").strip()))
            finally:
                await page.close()

        cards = response.css(
            "div[id^='df-result-products-'], div.dfd-card, div.dfd-card-live, div[data-dfd-role='card']"
        )
        discovered = 0

        if not cards:
            self.logger.warning("No listing cards found at %s; using anchor fallback", response.url)

        for card in cards:
            product_url = (
                card.css("a.dfd-card-link::attr(href)").get(default="").strip()
                or card.css("::attr(dfd-value-link)").get(default="").strip()
                or card.css("a[href*='goforgreenuk.com']::attr(href)").get(default="").strip()
            )

            if not product_url:
                continue

            product_url = response.urljoin(product_url)
            if product_url in self._seen_product_urls:
                continue
            self._seen_product_urls.add(product_url)
            discovered += 1

            listing_title = self._clean_text(" ".join(card.css(".dfd-card-title *::text").getall()))
            listing_desc = self._clean_text(" ".join(card.css(".dfd-card-description *::text").getall()))
            listing_price = self._clean_text(" ".join(card.css(".dfd-card-price *::text").getall()))
            listing_image = self._clean_image(
                card.css(".dfd-card-thumbnail img::attr(src), img::attr(src)").get(default="")
            )
            if listing_image:
                listing_image = response.urljoin(listing_image)

            yield scrapy.Request(
                url=product_url,
                callback=self.parse_product,
                errback=self.errback_request,
                meta={
                    "listing_title": listing_title,
                    "listing_desc": listing_desc,
                    "listing_price": listing_price,
                    "listing_image": listing_image,
                    "search_url": response.url,
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_page_methods": [
                        PageMethod("wait_for_timeout", 1200),
                    ],
                },
            )

        # Fallback: result pages may expose additional products via generic anchors and JS blobs.
        for anchor in response.css("a[href]"):
            href = (anchor.attrib.get("href") or "").strip()
            if not href:
                continue
            product_url = response.urljoin(href)
            if not self._looks_like_product_url(product_url):
                continue
            if product_url in self._seen_product_urls:
                continue

            self._seen_product_urls.add(product_url)
            discovered += 1

            listing_title = self._clean_text(" ".join(anchor.css("::text").getall()))
            if not listing_title:
                listing_title = self._clean_text(anchor.attrib.get("title", ""))

            yield scrapy.Request(
                url=product_url,
                callback=self.parse_product,
                errback=self.errback_request,
                meta={
                    "listing_title": listing_title,
                    "listing_desc": "",
                    "listing_price": "",
                    "listing_image": "",
                    "search_url": response.url,
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_page_methods": [
                        PageMethod("wait_for_timeout", 1200),
                    ],
                },
            )

        # Playwright frame-aware extraction catches links that do not end up in response.css.
        for product_url in page_anchor_urls:
            if not self._looks_like_product_url(product_url):
                continue
            if product_url in self._seen_product_urls:
                continue

            self._seen_product_urls.add(product_url)
            discovered += 1

            yield scrapy.Request(
                url=product_url,
                callback=self.parse_product,
                errback=self.errback_request,
                meta={
                    "listing_title": "",
                    "listing_desc": "",
                    "listing_price": "",
                    "listing_image": "",
                    "search_url": response.url,
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_page_methods": [
                        PageMethod("wait_for_timeout", 1200),
                    ],
                },
            )

        # Some product URLs are present in JS payloads but not rendered as anchor tags.
        regex_urls = set(
            re.findall(
                r"https?://www\.goforgreenuk\.com/[a-z0-9\-/]+",
                response.text.lower(),
            )
        )
        for product_url in regex_urls:
            product_url = response.urljoin(product_url)
            if product_url in self._seen_product_urls:
                continue
            if not self._looks_like_product_url(product_url):
                continue

            self._seen_product_urls.add(product_url)
            discovered += 1

            yield scrapy.Request(
                url=product_url,
                callback=self.parse_product,
                errback=self.errback_request,
                meta={
                    "listing_title": "",
                    "listing_desc": "",
                    "listing_price": "",
                    "listing_image": "",
                    "search_url": response.url,
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_page_methods": [
                        PageMethod("wait_for_timeout", 1200),
                    ],
                },
            )

        self.logger.info("Discovered %s product URLs from %s", discovered, response.url)

        next_links = response.css(
            "a[rel='next']::attr(href), a.next::attr(href), .pagination a[aria-label*='Next']::attr(href)"
        ).getall()
        for href in next_links:
            next_url = response.urljoin((href or "").strip())
            if not next_url or next_url in self._seen_listing_urls:
                continue
            self._seen_listing_urls.add(next_url)
            yield scrapy.Request(
                url=next_url,
                callback=self.parse_search,
                errback=self.errback_request,
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_page_methods": [
                        PageMethod("wait_for_timeout", 1500),
                        PageMethod("evaluate", "window.scrollTo(0, document.body.scrollHeight)"),
                        PageMethod("wait_for_timeout", 1200),
                    ],
                },
            )

    async def parse_product(self, response):
        page = response.meta.get("playwright_page")
        if page:
            await page.close()

        listing_title = response.meta.get("listing_title", "")
        listing_desc = response.meta.get("listing_desc", "")
        listing_price = response.meta.get("listing_price", "")
        listing_image = response.meta.get("listing_image", "")
        search_url = response.meta.get("search_url", "")

        product_name = self._clean_text(" ".join(response.css("h1 *::text").getall()))
        if not product_name:
            product_name = listing_title

        image_candidates = [
            self._clean_image(src)
            for src in response.css(
                ".fotorama img::attr(src), .image img::attr(src), meta[property='og:image']::attr(content), img::attr(src)"
            ).getall()
            if src and str(src).strip()
        ]
        image_candidates = [response.urljoin(img) for img in image_candidates if img]
        image_link = ""
        for candidate in image_candidates:
            lower = candidate.lower()
            if "logo" in lower or "icon" in lower or "sprite" in lower:
                continue
            image_link = candidate
            break
        if not image_link and listing_image:
            image_link = listing_image

        overview = self._clean_text(
            " ".join(
                response.css(
                    "#top-description *::text, .tab-pane#description *::text, .description *::text, meta[name='description']::attr(content)"
                ).getall()
            )
        )
        if not overview:
            overview = listing_desc

        specs = {}
        for row in response.css("table.gfg_product_specs tr, .details-content table tr, table tr"):
            key = self._normalize_key(" ".join(row.css("td:first-child *::text, th:first-child *::text").getall()))
            value = self._clean_text(" ".join(row.css("td:last-child *::text, th:last-child *::text").getall()))
            if key and value:
                specs[key] = value

        details_blob = self._clean_text(" ".join(response.css(".product_info *::text, body *::text").getall()))

        length = self._extract_first(specs, ["length", "each length", "len", "size length"])
        width = self._extract_first(specs, ["width", "each width", "size width"])
        height = self._extract_first(specs, ["height", "each height", "size height"])
        volume = self._extract_first(specs, ["volume", "capacity", "volume capacity"])
        diameter = self._extract_first(specs, ["diameter", "each diameter"])
        color = self._extract_first(specs, ["color", "colour"])
        material = self._extract_first(specs, ["material", "prod material", "product material"])
        pattern = self._extract_first(specs, ["pattern", "range", "collection"])

        ean_code = self._extract_first(specs, ["ean", "ean code", "gtin", "upc"])
        barcode = self._extract_first(specs, ["barcode", "upc", "gtin", "ean"])

        if not ean_code:
            ean_code = self._extract_from_text(r"\b(?:GTIN|EAN)\s*:\s*([0-9]{8,14})\b", details_blob)
        if not barcode:
            barcode = self._extract_from_text(r"\b(?:Barcode|UPC|MPN|Code)\s*:\s*([A-Z0-9\-]+)\b", details_blob)

        combined = f"{product_name} {overview}"
        if not diameter:
            diameter = self._extract_from_text(r"\b(\d+(?:\.\d+)?)\s*(?:mm|cm)\s*(?:dia|diameter)?\b", combined)
        if not volume:
            volume = self._extract_from_text(r"\b(\d+(?:\.\d+)?)\s*(ml|l|cl|oz)\b", combined)
            if volume:
                unit = self._extract_from_text(r"\b\d+(?:\.\d+)?\s*(ml|l|cl|oz)\b", combined)
                if unit:
                    volume = f"{volume} {unit}"

        catalog_number = self._extract_catalog_number(product_name, response.url, details_blob)

        yield {
            "catalog_number": catalog_number,
            "product_name": product_name,
            "product_url": response.url,
            "search_url": search_url,
            "price": listing_price,
            "Image Link": image_link,
            "Overview": overview,
            "Length": length,
            "Width": width,
            "Height": height,
            "Volume": volume,
            "Diameter": diameter,
            "Color": color,
            "Material": material,
            "EAN Code": ean_code,
            "Pattern": pattern,
            "Barcode": barcode,
            "found": True,
            "blocked": False,
        }

    async def errback_request(self, failure):
        request = failure.request
        page = request.meta.get("playwright_page")
        if page:
            try:
                await page.close()
            except Exception:
                pass

        error_text = str(failure.value or "request failed")
        error_lower = error_text.lower()
        blocked = (
            "403" in error_text
            or "429" in error_text
            or "timeout" in error_lower
            or "connection" in error_lower
        )

        yield {
            "product_url": request.url,
            "search_url": request.meta.get("search_url", ""),
            "found": False,
            "blocked": blocked,
            "error": error_text[:220],
        }
