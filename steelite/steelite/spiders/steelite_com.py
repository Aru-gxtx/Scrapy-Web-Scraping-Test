import re
import scrapy


class SteeliteComSpider(scrapy.Spider):
    name = "steelite.com"
    allowed_domains = ["www.steelite.com"]
    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "HTTPERROR_ALLOW_ALL": True,
        "CONCURRENT_REQUESTS": 1,
        "DOWNLOAD_DELAY": 3.0,
        "PLAYWRIGHT_BROWSER_TYPE": "chromium",
        "PLAYWRIGHT_LAUNCH_OPTIONS": {
            "headless": False,  # Use visible browser to bypass detection
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        },
        "PLAYWRIGHT_CONTEXT_ARGS": {
            "ignore_https_errors": True,
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        },
        "DOWNLOAD_HANDLERS": {
            "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        },
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
    }

    def __init__(self, max_pages=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Allow limiting the number of pages to scrape (for testing)
        self.max_pages = int(max_pages) if max_pages else 95
        self.logger.info(f"Will scrape up to {self.max_pages} pages of STEELITE products")

    @staticmethod
    def _normalize_text(value):
        if value is None:
            return ""
        text = str(value).strip()
        text = re.sub(r"\s+", " ", text)
        return text

    @staticmethod
    def _extract_dimensions(size_text):
        if not size_text:
            return "", "", ""
        
        # Try to extract dimensions
        # Pattern: "30 x 20 cm" or "25.25 cm (10\")"
        match = re.search(r"(\d+\.?\d*)\s*x\s*(\d+\.?\d*)\s*cm", size_text, re.IGNORECASE)
        if match:
            return match.group(1) + " cm", match.group(2) + " cm", ""
        
        # Single dimension (likely diameter)
        match = re.search(r"(\d+\.?\d*)\s*cm", size_text, re.IGNORECASE)
        if match:
            return "", "", match.group(1) + " cm"
        
        return "", "", ""

    @staticmethod
    def _extract_capacity(text):
        if not text:
            return ""
        
        # Look for patterns like "850 ml", "1.5 L", "12 oz"
        match = re.search(r"(\d+\.?\d*)\s*(ml|l|oz|cl)\b", text, re.IGNORECASE)
        if match:
            return f"{match.group(1)} {match.group(2)}"
        
        return ""

    @staticmethod
    def _preferred_image(candidates):
        if not candidates:
            return ""
        
        # Prefer highest resolution images (3x, 1200x1200, etc.)
        for url in candidates:
            if "1200x1200" in url or "3x" in url:
                return url
        
        # Fallback to first available
        return candidates[0] if candidates else ""

    def start_requests(self):
        base_url = "https://www.steelite.com/catalogsearch/result/index/"
        
        for page in range(1, self.max_pages + 1):
            url = f"{base_url}?p={page}&q=STEELITE"
            yield scrapy.Request(
                url=url,
                callback=self.parse_search_page,
                errback=self.errback_request,
                meta={
                    "page_number": page,
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_page_goto_kwargs": {
                        "wait_until": "networkidle",
                        "timeout": 60000,
                    },
                },
                dont_filter=True,
            )

    async def parse_search_page(self, response):
        page_number = response.meta.get("page_number", 1)
        page = response.meta.get("playwright_page")
        
        # Check if we got a valid page with content
        if response.status != 200:
            self.logger.warning(f"Search page {page_number} returned status {response.status}")
            if page:
                await page.close()
            return

        self.logger.info(f"Parsing search page {page_number}")
        
        # Check if Cloudflare challenge is present
        page_content = response.text
        if "Cloudflare" in page_content and "challenge" in page_content.lower():
            self.logger.error(f"Page {page_number} blocked by Cloudflare - manual intervention may be required")
            if page:
                await page.close()
            return
        
        # Close the page after we're done
        if page:
            await page.close()

        # Extract all product items with data-link attribute
        product_items = response.css("li[data-link][data-productid]")
        
        if not product_items:
            self.logger.warning(f"No products found on page {page_number}")
            return

        self.logger.info(f"Found {len(product_items)} products on page {page_number}")

        for item in product_items:
            product_url = item.attrib.get("data-link", "")
            product_id = item.attrib.get("data-productid", "")
            
            if not product_url:
                continue
            
            # Extract SKU/catalog number from the listing
            sku = item.css("strong::text").get(default="").strip()
            
            # Extract preview info
            product_name = item.css("a.name::text").get(default="").strip()
            preview_image = item.css("img::attr(src)").get(default="").strip()
            
            yield scrapy.Request(
                url=response.urljoin(product_url),
                callback=self.parse_product,
                errback=self.errback_request,
                meta={
                    "page_number": page_number,
                    "product_id": product_id,
                    "sku_preview": sku,
                    "product_name_preview": product_name,
                    "preview_image": preview_image,
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_page_goto_kwargs": {
                        "wait_until": "domcontentloaded",
                        "timeout": 30000,
                    },
                },
            )

    async def parse_product(self, response):
        page_number = response.meta.get("page_number", 0)
        product_id = response.meta.get("product_id", "")
        sku_preview = response.meta.get("sku_preview", "")
        
        # Close the Playwright page to free resources
        page = response.meta.get("playwright_page")
        if page:
            await page.close()
        
        if response.status == 403:
            yield {
                "found": False,
                "blocked": True,
                "product_url": response.url,
                "error": "HTTP 403",
                "page_number": page_number,
            }
            return
        
        if response.status == 404:
            yield {
                "found": False,
                "blocked": False,
                "product_url": response.url,
                "error": "HTTP 404",
                "page_number": page_number,
            }
            return

        # Extract product name
        product_name = response.css("h1::text, h1.product-name::text").get(default="").strip()
        
        # Extract images - prefer high resolution
        image_candidates = []
        
        # Main product images
        for img in response.css("div.l a.zoom::attr(href), div.l a.zoom::attr(data-3x)"):
            img_url = response.urljoin(img.strip()) if img else ""
            if img_url:
                image_candidates.append(img_url)
        
        # Thumbnail images as fallback
        for img in response.css("div.l ul li img::attr(data-xlarge), div.l ul li img::attr(src)"):
            img_url = response.urljoin(img.strip()) if img else ""
            if img_url:
                image_candidates.append(img_url)
        
        image_link = self._preferred_image(image_candidates)

        # Extract overview/description
        overview = response.css("div.product-description p::text, div.description p::text").get(default="")
        overview = self._normalize_text(overview)

        # Extract specifications from table
        specs = {}
        spec_rows = response.css("table tr")
        
        for row in spec_rows:
            th = row.css("th::text").get()
            td_text = " ".join(row.css("td::text").getall()).strip()
            
            if th and td_text:
                key = self._normalize_text(th).lower()
                value = self._normalize_text(td_text)
                specs[key] = value

        # Extract specific fields from specs
        sku = specs.get("sku", sku_preview)
        pattern = specs.get("pattern", "")
        material = specs.get("material", "")
        barcode = specs.get("barcode", "")
        ean_code = specs.get("ean", specs.get("ean code", ""))
        
        # Extract dimensions
        size = specs.get("size", "")
        height = specs.get("height", "")
        
        length, width, diameter = self._extract_dimensions(size)
        
        # If height is in specs, use it
        if not height:
            height = ""
        
        # Extract capacity/volume
        capacity = specs.get("capacity", "")
        volume = self._extract_capacity(overview + " " + str(specs))
        if not volume:
            volume = capacity

        # Extract color - may be in pattern name or specs
        color = specs.get("color", specs.get("colour", ""))
        if not color and pattern:
            # Try to extract color from pattern name
            color_keywords = ["white", "black", "blue", "green", "red", "yellow", "grey", "gray", 
                             "brown", "cream", "aqua", "slate", "amber", "emerald", "charcoal"]
            pattern_lower = pattern.lower()
            for keyword in color_keywords:
                if keyword in pattern_lower:
                    color = keyword.capitalize()
                    break

        # Extract shape if available
        shape = specs.get("shape", "")

        yield {
            "sku": sku,
            "product_id": product_id,
            "product_name": product_name,
            "product_url": response.url,
            "image_link": image_link,
            "overview": overview,
            "length": length,
            "width": width,
            "height": height,
            "capacity": capacity,
            "volume": volume,
            "diameter": diameter,
            "color": color,
            "shape": shape,
            "material": material,
            "pattern": pattern,
            "ean_code": ean_code,
            "barcode": barcode,
            "found": True,
            "blocked": False,
            "page_number": page_number,
        }

    def errback_request(self, failure):
        request = failure.request
        page_number = request.meta.get("page_number", 0)
        error_text = str(failure.value or "request failed")
        error_text_lower = error_text.lower()

        status_code = None
        if getattr(failure.value, "response", None) is not None:
            status_code = getattr(failure.value.response, "status", None)

        blocked = (
            "403" in error_text
            or "429" in error_text
            or "connection closed" in error_text_lower
            or "timeout" in error_text_lower
            or (status_code in (403, 429, 500, 502, 503, 504))
        )

        payload = {
            "found": False,
            "blocked": blocked,
            "error": error_text[:220],
            "page_number": page_number,
        }

        if status_code is not None:
            payload["status_code"] = status_code

        payload["product_url"] = request.url

        yield payload
