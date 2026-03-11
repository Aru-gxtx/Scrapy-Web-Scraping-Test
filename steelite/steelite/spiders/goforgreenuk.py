import json
import re
from urllib.parse import urlencode

import scrapy


class GoforgreenukSpider(scrapy.Spider):
    name = "goforgreenuk"
    allowed_domains = ["www.goforgreenuk.com", "eu1-search.doofinder.com"]

    # Doofinder search API — discovered from the site's JS search widget.
    _DOOFINDER_API = "https://eu1-search.doofinder.com/5/search"
    _DOOFINDER_HASHID = "baeda13069f4a0d7caf0dfdaf0aa8752"

    _PRICE_RANGES = [
        (None, None),
        (0, 5),
        (5, 15),
        (15, 30),
        (30, 50),
        (50, 80),
        (80, 120),
        (120, 200),
        (200, 400),
        (400, 3000),
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
        "CONCURRENT_REQUESTS_PER_DOMAIN": 4,
        "DOWNLOAD_DELAY": 0.5,
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
        primary_sources = (name, url)
        secondary_sources = (body_text,)

        for source in primary_sources:
            if not source:
                continue
            match = re.search(r"\b(VV\d{3,}[A-Z0-9]*)\b", str(source).upper())
            if match:
                return match.group(1)

        for source in primary_sources:
            if not source:
                continue
            match = re.search(r"\b(V\d{4,}[A-Z0-9]*)\b", str(source).upper())
            if match:
                return match.group(1)

        for source in secondary_sources:
            if not source:
                continue
            match = re.search(r"\b(VV\d{3,}[A-Z0-9]*)\b", str(source).upper())
            if match:
                return match.group(1)

        for source in secondary_sources:
            if not source:
                continue
            match = re.search(r"\b(V\d{4,}[A-Z0-9]*)\b", str(source).upper())
            if match:
                return match.group(1)

        for source in (name, url, body_text):
            if not source:
                continue
            src_upper = str(source).upper()
            match = re.search(r"\b([A-Z]{2,}\d{3,}[A-Z0-9]*)\b", src_upper)
            if match:
                val = match.group(1)
                if re.fullmatch(r"\d+MM", val) or re.fullmatch(r"\d+X\d+MM", val):
                    continue
                return val
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
    def _api_scalar(value):
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, (int, float, bool)):
            return str(value).strip()
        if isinstance(value, list):
            parts = [GoforgreenukSpider._api_scalar(part) for part in value]
            return " ".join(part for part in parts if part).strip()
        if isinstance(value, dict):
            for key in ("value", "text", "label", "name", "id"):
                candidate = value.get(key)
                if candidate not in (None, ""):
                    return GoforgreenukSpider._api_scalar(candidate)
            parts = [GoforgreenukSpider._api_scalar(part) for part in value.values()]
            return " ".join(part for part in parts if part).strip()
        return str(value).strip()


    def _api_url(self, page, price_lo=None, price_hi=None):
        params = {
            "hashid": self._DOOFINDER_HASHID,
            "query": "steelite",
            "page": page,
            "rpp": 100,
        }
        if price_lo is not None:
            params["filter[best_price][gte]"] = price_lo
            params["filter[best_price][lt]"] = price_hi
        return f"{self._DOOFINDER_API}?{urlencode(params)}"

    def _initial_requests(self):
        api_headers = {
            "Accept": "application/json",
            "Referer": "https://www.goforgreenuk.com/",
            "Origin": "https://www.goforgreenuk.com",
        }
        for lo, hi in self._PRICE_RANGES:
            url = self._api_url(1, lo, hi)
            yield scrapy.Request(
                url=url,
                callback=self.parse_api_page,
                errback=self.errback_request,
                meta={"price_lo": lo, "price_hi": hi, "api_page": 1},
                dont_filter=True,
                headers=api_headers,
            )

    async def start(self):
        for request in self._initial_requests():
            yield request

    def parse_api_page(self, response):
        try:
            data = json.loads(response.text)
        except Exception as exc:
            self.logger.error("Failed to parse Doofinder API response from %s: %s", response.url, exc)
            return

        results = data.get("results", [])
        price_lo = response.meta.get("price_lo")
        price_hi = response.meta.get("price_hi")
        api_page = response.meta.get("api_page", 1)
        self.logger.info(
            "API page=%s price=%s-%s → %s results (total_found=%s)",
            api_page, price_lo, price_hi, len(results), data.get("total_found"),
        )

        for item in results:
            link = self._api_scalar(item.get("link"))
            if not link:
                continue
            if link.startswith("http"):
                product_url = link
            else:
                product_url = f"https://www.goforgreenuk.com{link}"

            if product_url in self._seen_product_urls:
                continue
            self._seen_product_urls.add(product_url)

            yield scrapy.Request(
                url=product_url,
                callback=self.parse_product,
                errback=self.errback_request,
                meta={
                    "listing_title": self._api_scalar(item.get("title")),
                    "listing_desc": self._api_scalar(item.get("description")),
                    "listing_price": self._api_scalar(item.get("price") or item.get("best_price")),
                    "listing_image": self._api_scalar(item.get("image_link")),
                    "listing_sku": self._api_scalar(item.get("c:sku") or item.get("mpn")),
                    "listing_gtin": self._api_scalar(item.get("gtin")),
                    "listing_color": self._api_scalar(item.get("g:color")),
                    "listing_material": self._api_scalar(item.get("g:material")),
                    "listing_pattern": self._api_scalar(item.get("g:pattern")),
                    "search_url": response.url,
                },
            )

        # Paginate within this price bucket.  The Doofinder API hard-caps at page 10 (1000 items).
        total_found = data.get("total_found", 0)
        if api_page * 100 < min(total_found, 1000):
            next_page = api_page + 1
            next_url = self._api_url(next_page, price_lo, price_hi)
            yield scrapy.Request(
                url=next_url,
                callback=self.parse_api_page,
                errback=self.errback_request,
                meta={"price_lo": price_lo, "price_hi": price_hi, "api_page": next_page},
                dont_filter=True,
                headers={
                    "Accept": "application/json",
                    "Referer": "https://www.goforgreenuk.com/",
                    "Origin": "https://www.goforgreenuk.com",
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
        listing_sku = response.meta.get("listing_sku", "")
        listing_gtin = response.meta.get("listing_gtin", "")
        listing_color = response.meta.get("listing_color", "")
        listing_material = response.meta.get("listing_material", "")
        listing_pattern = response.meta.get("listing_pattern", "")

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

        # Extract MPN and GTIN from the structured code block (highest priority, page-level)
        mpn = ""
        gtin_from_page = ""
        for span_text in response.css("span.gfg-add-code::text").getall():
            text = span_text.strip()
            upper = text.upper()
            if upper.startswith("MPN:"):
                mpn = text[4:].strip()
            elif upper.startswith("GTIN:"):
                gtin_from_page = text[5:].strip()
        if not mpn and listing_sku:
            mpn = listing_sku

        ean_code = self._extract_first(specs, ["ean", "ean code", "gtin", "upc"])
        barcode = self._extract_first(specs, ["barcode", "upc", "gtin", "ean"])

        if not ean_code and gtin_from_page:
            ean_code = gtin_from_page
        if not ean_code:
            ean_code = self._extract_from_text(r"\b(?:GTIN|EAN)\s*:\s*([0-9]{8,14})\b", details_blob)
        if not ean_code and listing_gtin:
            ean_code = listing_gtin

        if not barcode:
            barcode = self._extract_from_text(r"\b(?:Barcode|UPC|MPN|Code)\s*:\s*([A-Z0-9\-]+)\b", details_blob)
        if not barcode and listing_sku:
            barcode = listing_sku

        if not color and listing_color:
            color = listing_color
        if not material and listing_material:
            material = listing_material
        if not pattern and listing_pattern:
            pattern = listing_pattern

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
        if not catalog_number and listing_sku:
            catalog_number = listing_sku

        yield {
            "catalog_number": catalog_number,
            "mpn": mpn,
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
