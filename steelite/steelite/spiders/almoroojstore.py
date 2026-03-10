import re

import scrapy
from scrapy_playwright.page import PageMethod


class AlmoroojstoreSpider(scrapy.Spider):
    name = "almoroojstore"
    allowed_domains = ["www.almoroojstore.com"]
    start_urls = ["https://www.almoroojstore.com/searchResults/steelite"]
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

    @staticmethod
    def _clean_text(value):
        if value is None:
            return ""
        text = str(value)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def _normalize_key(value):
        text = AlmoroojstoreSpider._clean_text(value).lower()
        text = text.replace("\xa0", " ")
        text = re.sub(r"\s+", " ", text)
        return text

    @staticmethod
    def _extract_first(specs, keys):
        for key in keys:
            if key in specs and specs[key]:
                return specs[key]
        return ""

    @staticmethod
    def _extract_from_text(pattern, text):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _normalize_catalog_number(value):
        text = AlmoroojstoreSpider._clean_text(value).upper()
        # Remove common vendor prefixes/suffixes and keep only alphanumerics.
        text = re.sub(r"^STE[-\s]*", "", text)
        text = re.sub(r"\([^)]*PK[^)]*\)", "", text)
        text = re.sub(r"[^A-Z0-9]", "", text)
        return text

    def start_requests(self):
        for url in self.start_urls:
            yield scrapy.Request(
                url=url,
                callback=self.parse_search,
                errback=self.errback_request,
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_page_methods": [
                        PageMethod("wait_for_timeout", 2000),
                        # Trigger lazy-loaded products.
                        PageMethod("evaluate", "window.scrollTo(0, document.body.scrollHeight)"),
                        PageMethod("wait_for_timeout", 1500),
                        PageMethod("evaluate", "window.scrollTo(0, document.body.scrollHeight)"),
                        PageMethod("wait_for_timeout", 1500),
                    ],
                },
                dont_filter=True,
            )

    async def parse_search(self, response):
        page = response.meta.get("playwright_page")
        if page:
            await page.close()

        cards = response.css("div.item")
        if not cards:
            self.logger.warning("No product cards found on search page: %s", response.url)
            return

        seen_urls = set()
        discovered = 0

        for card in cards:
            product_url = card.css("a[href*='/product/']::attr(href)").get(default="").strip()
            if not product_url:
                continue

            product_url = response.urljoin(product_url)
            if product_url in seen_urls:
                continue

            seen_urls.add(product_url)
            discovered += 1

            title = self._clean_text(" ".join(card.css("h4::text").getall()))
            sku = self._clean_text(" ".join(card.css(".sku::text").getall()))
            list_price = self._clean_text(" ".join(card.css(".code::text, .price *::text").getall()))
            image_link = card.css("img::attr(data-src), img::attr(src)").get(default="").strip()
            image_link = response.urljoin(image_link) if image_link else ""

            yield scrapy.Request(
                url=product_url,
                callback=self.parse_product,
                errback=self.errback_request,
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_page_methods": [
                        PageMethod("wait_for_timeout", 1800),
                    ],
                    "listing_title": title,
                    "listing_sku": sku,
                    "listing_price": list_price,
                    "listing_image": image_link,
                },
                dont_filter=True,
            )

        self.logger.info("Discovered %s unique products from %s", discovered, response.url)

    async def parse_product(self, response):
        page = response.meta.get("playwright_page")
        if page:
            await page.close()

        listing_title = response.meta.get("listing_title", "")
        listing_sku = response.meta.get("listing_sku", "")
        listing_price = response.meta.get("listing_price", "")
        listing_image = response.meta.get("listing_image", "")

        product_name = self._clean_text(
            response.css("h1::text, h2::text, h4[name]::attr(name), .product-title-wrapper h4::attr(name)").get(default="")
        )
        if not product_name:
            product_name = listing_title

        raw_catalog_number = self._clean_text(
            response.css("p.text-black-50.defaultFontType::text").get(default="")
        )
        if not raw_catalog_number:
            raw_catalog_number = self._extract_from_text(r"\b(STE[-\s]*[A-Z0-9]+(?:\s*\([^)]*\))?)\b", response.text)

        catalog_number = self._normalize_catalog_number(raw_catalog_number)

        image_link = response.css(
            "img.zoom::attr(src), .pic_he img::attr(src), .img-wrapper img::attr(src), img::attr(src)"
        ).get(default="").strip()
        if not image_link:
            image_link = listing_image
        image_link = response.urljoin(image_link) if image_link else ""

        overview = self._clean_text(
            " ".join(
                response.css(
                    "p.fullDetailsdiv *::text, .q-tab-panel p *::text, .q-tab-panel::text"
                ).getall()
            )
        )

        specs = {}
        for row in response.css("tr.itemProduct__table__tr, table tr"):
            key = self._clean_text(" ".join(row.css("td:first-child *::text").getall()))
            value = self._clean_text(" ".join(row.css("td:last-child *::text").getall()))
            if key and value:
                specs[self._normalize_key(key)] = value

        length = self._extract_first(specs, ["length"])
        width = self._extract_first(specs, ["width"])
        height = self._extract_first(specs, ["height"])
        volume = self._extract_first(specs, ["volume", "capacity"])
        diameter = self._extract_first(specs, ["diameter"])
        color = self._extract_first(specs, ["color", "colour"])
        material = self._extract_first(specs, ["material"])
        pattern = self._extract_first(specs, ["pattern"])

        ean_code = self._extract_first(specs, ["ean code", "ean", "gtin", "upc"])
        barcode = self._extract_first(specs, ["barcode", "upc", "gtin"])

        if not ean_code:
            ean_code = self._extract_from_text(r"\b(?:ean|gtin)\s*[:#-]?\s*([0-9]{8,14})", response.text)
        if not barcode:
            barcode = self._extract_from_text(r"\b(?:barcode|upc)\s*[:#-]?\s*([0-9]{8,14})", response.text)

        if not (ean_code or barcode):
            sku_digits = re.sub(r"[^0-9]", "", listing_sku)
            if len(sku_digits) >= 8:
                barcode = sku_digits

        if not color:
            color = self._extract_from_text(
                r"\b(black|white|brown|green|blue|red|yellow|orange|terracotta|grey|gray|beige)\b",
                f"{product_name} {overview}",
            )

        if not material:
            material = self._extract_from_text(
                r"\b(vitrified|porcelain|ceramic|china|stoneware|glass|melamine|stainless steel|steel|plastic)\b",
                f"{product_name} {overview}",
            )

        yield {
            "catalog_number_raw": raw_catalog_number,
            "catalog_number": catalog_number,
            "product_name": product_name,
            "product_url": response.url,
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
            await page.close()

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
            "found": False,
            "blocked": blocked,
            "error": error_text[:220],
        }
