import json
import re
import scrapy
from pathlib import Path
from urllib.parse import quote_plus


class DrinkstuffSpider(scrapy.Spider):
    name = "drinkstuff"
    allowed_domains = ["www.drinkstuff.com"]
    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "USER_AGENT": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "HTTPERROR_ALLOWED_CODES": [403, 404],
        "PLAYWRIGHT_BROWSER_TYPE": "chromium",
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 45_000,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "DOWNLOAD_DELAY": 1.2,
        "DEFAULT_REQUEST_HEADERS": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Referer": "https://www.drinkstuff.com/",
        },
    }

    def __init__(self, catalog_file=None, limit=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        default_catalog_file = Path(__file__).resolve().parents[3] / "incomplete_catalog_numbers_v0.4.json"
        self.catalog_file = Path(catalog_file) if catalog_file else default_catalog_file
        if not self.catalog_file.is_absolute():
            self.catalog_file = (Path.cwd() / self.catalog_file).resolve()

        self.limit = int(limit) if limit else None
        self.catalog_numbers = self._load_catalog_numbers()

        if self.limit is not None and self.limit >= 0:
            self.catalog_numbers = self.catalog_numbers[: self.limit]

        self.logger.info("Loaded %s catalog numbers from %s", len(self.catalog_numbers), self.catalog_file)

    def _load_catalog_numbers(self):
        try:
            with open(self.catalog_file, "r", encoding="utf-8") as file:
                raw_items = json.load(file)
        except FileNotFoundError:
            self.logger.error("Catalog file not found: %s", self.catalog_file)
            return []

        catalog_numbers = []
        for item in raw_items:
            if item is None:
                continue
            catalog = str(item).strip()
            if catalog and catalog.lower() != "nan":
                catalog_numbers.append(catalog)

        return catalog_numbers

    @staticmethod
    def _normalize_catalog(value):
        if value is None:
            return ""

        text = str(value).strip().upper()
        text = re.sub(r"[^A-Z0-9]", "", text)
        return text

    @staticmethod
    def _extract_catalog_from_text(text):
        if not text:
            return ""
        match = re.search(r"\b[A-Z0-9]{5,}\b", text, re.IGNORECASE)
        return match.group(0).upper() if match else ""

    @staticmethod
    def _preferred_image(candidates):
        if not candidates:
            return ""
        
        skip_patterns = [
            "logo",
            "nophoto",
            "no-image",
            "placeholder",
            "no-product",
            "default",
        ]
        
        for url in candidates:
            url_lower = str(url).lower()
            if not any(skip in url_lower for skip in skip_patterns):
                return url
        
        return candidates[0] if candidates else ""

    @staticmethod
    def _extract_volume_from_text(text):
        if not text:
            return ""
        match = re.search(r"(\d+\.?\d*)\s*(oz|cl|ml|l)\b", text, re.IGNORECASE)
        return f"{match.group(1)}{match.group(2)}".lower() if match else ""

    @staticmethod
    def _extract_diameter_from_text(text):
        if not text:
            return ""
        match = re.search(r"(\d+(?:[/-]\d+)?|\d+\.?\d*)[\"']?\s*(?:dia|diameter)", text, re.IGNORECASE)
        return match.group(1) if match else ""

    @staticmethod
    def _extract_material_from_text(text):
        if not text:
            return ""
        
        materials = {
            "vitrified china": r"vitrified china",
            "vitrified ceramic": r"vitrified ceramic",
            "alumina vitrified": r"alumina vitrified",
            "ceramic": r"ceramic",
            "porcelain": r"porcelain",
            "china": r"china",
        }
        
        text_lower = text.lower()
        for material, pattern in materials.items():
            if re.search(pattern, text_lower):
                return material
        
        return ""

    @staticmethod
    def _extract_pattern_from_text(text):
        if not text:
            return ""
        # Look for pattern names: typically "Range/Pattern Color" or similar
        match = re.search(r"(?:Steelite\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+[A-Z][a-z]+)?)\s+(?:Mustard|Mocha|Olive|Green|Blue|etc)", text)
        if match:
            return match.group(1).strip()
        return ""

    @staticmethod
    def _extract_color_from_text(text, pattern=""):
        if not text:
            return ""
        
        colors = [
            "mustard", "mocha", "olive", "green", "blue", "white", "black",
            "red", "pink", "yellow", "orange", "purple", "brown", "gray", "grey"
        ]
        
        text_lower = text.lower()
        for color in colors:
            if re.search(rf"\b{color}\b", text_lower):
                return color.capitalize()
        
        return ""

    @staticmethod
    def _extract_product_ld_json(response):
        ld_json = {}
        script_text = response.css('script[type="application/ld+json"]::text').get()
        
        if script_text:
            try:
                ld_data = json.loads(script_text)
                if isinstance(ld_data, dict):
                    ld_json = ld_data
            except json.JSONDecodeError:
                pass
        
        return ld_json

    def start_requests(self):
        # Warm up a browser context first to establish session cookies.
        yield scrapy.Request(
            url="https://www.drinkstuff.com/",
            callback=self.parse_warmup,
            errback=self.errback_request,
            meta={
                "playwright": True,
                "playwright_context": "drinkstuff",
                "search_url": "https://www.drinkstuff.com/",
            },
            dont_filter=True,
        )

    def parse_warmup(self, response):
        for catalog_number in self.catalog_numbers:
            encoded_catalog = quote_plus(catalog_number)
            url = f"https://www.drinkstuff.com/search/?q={encoded_catalog}"

            yield scrapy.Request(
                url=url,
                callback=self.parse_search,
                errback=self.errback_request,
                meta={
                    "searched_catalog_number": catalog_number,
                    "search_url": url,
                    "playwright": True,
                    "playwright_context": "drinkstuff",
                },
            )

    def parse_search(self, response):
        searched_catalog_number = response.meta["searched_catalog_number"]
        search_url = response.meta.get("search_url", response.url)
        searched_catalog_normalized = self._normalize_catalog(searched_catalog_number)

        # Handle blocked and missing responses explicitly.
        if response.status == 403:
            self.logger.warning(f"Search failed with status {response.status} for {searched_catalog_number}")
            yield {
                "searched_catalog_number": searched_catalog_number,
                "found": False,
                "blocked": True,
                "search_url": search_url,
                "error": f"HTTP {response.status}",
            }
            return
        if response.status == 404:
            yield {
                "searched_catalog_number": searched_catalog_number,
                "found": False,
                "blocked": False,
                "search_url": search_url,
                "error": f"HTTP {response.status}",
            }
            return

        # Some queries redirect straight to a product page.
        if "/p/" in response.url.lower():
            yield scrapy.Request(
                url=response.url,
                callback=self.parse_product,
                errback=self.errback_request,
                dont_filter=True,
                meta={
                    "searched_catalog_number": searched_catalog_number,
                    "searched_catalog_normalized": searched_catalog_normalized,
                    "search_url": search_url,
                    "playwright": True,
                    "playwright_context": "drinkstuff",
                },
            )
            return

        # Extract only catalog-relevant product links from search results.
        candidate_links = []
        for anchor in response.css("a[href*='/p/']"):
            href = anchor.attrib.get("href", "")
            if not href:
                continue
            product_url = response.urljoin(href)
            anchor_text = " ".join(anchor.css("::text").getall()).strip()
            combined = f"{product_url} {anchor_text}"
            if searched_catalog_normalized in self._normalize_catalog(combined):
                candidate_links.append(product_url)

        # De-duplicate while preserving order.
        product_links = list(dict.fromkeys(candidate_links))

        if not product_links:
            self.logger.info(f"No exact catalog links found in search page for: {searched_catalog_number}")
            yield {
                "searched_catalog_number": searched_catalog_number,
                "found": False,
                "blocked": False,
                "search_url": search_url,
                "note": "No exact catalog link found on search page",
            }
            return

        self.logger.info(f"Found {len(product_links)} catalog-matched links for: {searched_catalog_number}")

        # Follow only matched product links.
        for product_url in product_links:
            yield scrapy.Request(
                url=product_url,
                callback=self.parse_product,
                errback=self.errback_request,
                meta={
                    "searched_catalog_number": searched_catalog_number,
                    "searched_catalog_normalized": searched_catalog_normalized,
                    "search_url": search_url,
                    "playwright": True,
                    "playwright_context": "drinkstuff",
                },
            )

    def errback_request(self, failure):
        request = failure.request
        searched_catalog_number = request.meta.get("searched_catalog_number", "")
        search_url = request.meta.get("search_url", request.url)
        error_text = str(failure.value or "request failed")
        error_text_lower = error_text.lower()

        blocked = (
            "403" in error_text
            or "connection closed" in error_text_lower
            or "target.createtarget" in error_text_lower
            or "protocol error" in error_text_lower
        )

        payload = {
            "searched_catalog_number": searched_catalog_number,
            "found": False,
            "blocked": blocked,
            "search_url": search_url,
            "error": error_text[:220],
        }

        if "/p/" in request.url.lower():
            payload["product_url"] = request.url

        yield payload

    def parse_product(self, response):
        searched_catalog_number = response.meta["searched_catalog_number"]
        searched_catalog_normalized = response.meta["searched_catalog_normalized"]
        search_url = response.meta["search_url"]

        if response.status == 403:
            yield {
                "searched_catalog_number": searched_catalog_number,
                "found": False,
                "blocked": True,
                "search_url": search_url,
                "product_url": response.url,
                "error": "HTTP 403",
            }
            return
        if response.status == 404:
            yield {
                "searched_catalog_number": searched_catalog_number,
                "found": False,
                "blocked": False,
                "search_url": search_url,
                "product_url": response.url,
                "error": "HTTP 404",
            }
            return

        # Extract from JSON-LD first
        product_ld = self._extract_product_ld_json(response)
        
        # Get catalog number from JSON-LD or specifications
        catalog_number = product_ld.get("mpn", "").strip()
        
        # If not found in JSON-LD, extract from specs section
        if not catalog_number:
            mpn_span = response.css("div.product-detail-section.specs div:contains('Manufacturer') span::text").get()
            if mpn_span:
                catalog_number = mpn_span.strip()
        
        # Normalize and compare
        catalog_normalized = self._normalize_catalog(catalog_number)
        
        # Check if this matches our searched catalog
        if not catalog_normalized or catalog_normalized != searched_catalog_normalized:
            self.logger.debug(f"Catalog mismatch: searched {searched_catalog_normalized}, found {catalog_normalized}")
            return
        
        # Extract product details
        product_name = response.css("h1::text").get(default="").strip()
        if not product_name:
            product_name = product_ld.get("name", "").strip()

        # Image extraction
        image_candidates = [
            response.urljoin(src.strip())
            for src in response.css(
                ".product-slick img::attr(src), "
                "img.image_zoom_cls::attr(src), "
                "meta[property='og:image']::attr(content)"
            ).getall()
            if src and str(src).strip()
        ]
        image_link = self._preferred_image(image_candidates)

        # Overview from meta description or description section
        overview = response.css("meta[name='description']::attr(content)").get(default="").strip()
        if not overview:
            description_text = " ".join(
                response.css("div.product-detail-section p::text").getall()
            ).strip()
            overview = description_text[:500] if description_text else ""

        # Specifications and dimensions
        specs = {}
        
        # Parse specifications section
        spec_rows = response.css("div.product-detail-section.specs div")
        for row in spec_rows:
            # Check for label-value pairs
            label_text = row.css("b::text").get(default="").strip()
            if label_text:
                # Get the value(s) following the label
                values = row.css("span::text").getall()
                if values:
                    value = " ".join(v.strip() for v in values).strip()
                    specs[label_text.lower()] = value

        # Extract specific fields
        length = specs.get("length", "")
        width = specs.get("width", "")
        height = specs.get("height", "")
        diameter = specs.get("diameter", "") or self._extract_diameter_from_text(overview)
        
        volume = (
            specs.get("capacity", "")
            or specs.get("volume", "")
            or self._extract_volume_from_text(overview)
        )

        material = specs.get("material", "") or self._extract_material_from_text(overview)
        pattern = self._extract_pattern_from_text(overview)
        color = specs.get("color", "") or self._extract_color_from_text(overview, pattern)

        # Barcode and EAN from JSON-LD or specs
        barcode = (
            specs.get("barcode", "")
            or product_ld.get("gtin", "")
            or product_ld.get("gtin13", "")
        ).strip()
        
        ean_code = specs.get("ean code", "") or specs.get("ean", "")

        yield {
            "searched_catalog_number": searched_catalog_number,
            "catalog_number": catalog_number,
            "product_name": product_name,
            "product_url": response.url,
            "search_url": search_url,
            "image_link": image_link,
            "overview": overview,
            "length": length,
            "width": width,
            "height": height,
            "volume": volume,
            "diameter": diameter,
            "color": color,
            "material": material,
            "ean_code": ean_code,
            "pattern": pattern,
            "barcode": barcode,
            "blocked": False,
            "found": True,
        }
