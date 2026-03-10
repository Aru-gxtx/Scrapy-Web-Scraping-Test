import json
import re
import scrapy
from pathlib import Path
from urllib.parse import quote_plus, urljoin
from difflib import SequenceMatcher
from scrapy_playwright.page import PageMethod


class KitchenrestockSpider(scrapy.Spider):
    name = "kitchenrestock"
    allowed_domains = ["kitchenrestock.com"]
    
    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "USER_AGENT": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "HTTPERROR_ALLOWED_CODES": [403, 404, 429],
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "DOWNLOAD_DELAY": 2.0,
        "PLAYWRIGHT_BROWSER_TYPE": "chromium",
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 60_000,
        "PLAYWRIGHT_LAUNCH_OPTIONS": {
            "headless": True,
            "args": [
                "--disable-blink-features=AutomationControlled",
            ],
        },
        "DOWNLOAD_HANDLERS": {
            "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
            "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        },
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
        "DEFAULT_REQUEST_HEADERS": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        },
    }

    def __init__(self, catalog_file=None, limit=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        default_catalog_file = Path(__file__).resolve().parents[3] / "incomplete_catalog_numbers_v0.7.json"
        self.catalog_file = Path(catalog_file) if catalog_file else default_catalog_file
        if not self.catalog_file.is_absolute():
            self.catalog_file = (Path.cwd() / self.catalog_file).resolve()

        self.limit = int(limit) if limit else None
        self.catalog_numbers = self._load_catalog_numbers()

        if self.limit is not None and self.limit >= 0:
            self.catalog_numbers = self.catalog_numbers[:self.limit]

        self.logger.info(f"Loaded {len(self.catalog_numbers)} catalog numbers from {self.catalog_file}")

    def _load_catalog_numbers(self):
        try:
            with open(self.catalog_file, "r", encoding="utf-8") as file:
                raw_items = json.load(file)
        except FileNotFoundError:
            self.logger.error(f"Catalog file not found: {self.catalog_file}")
            return []

        catalog_numbers = []
        for item in raw_items:
            if item is None:
                continue
            catalog = str(item).strip()
            if catalog and catalog.lower() != "nan":
                catalog_numbers.append(catalog)

        return catalog_numbers

    async def errback_close_page(self, failure):
        page = failure.request.meta.get("playwright_page")
        if page:
            await page.close()
        self.logger.error(f"Request failed: {failure.request.url} - {failure.value}")

    @staticmethod
    def _normalize_catalog(value):
        if value is None:
            return ""
        text = str(value).strip().upper()
        text = re.sub(r"[^A-Z0-9]", "", text)
        return text

    @staticmethod
    def _extract_catalog_from_title(text):
        if not text:
            return ""
        # Look for patterns like "Steelite 11330321" or just standalone numbers
        match = re.search(r'(?:steelite\s+)?([A-Z0-9]{5,})', text, re.IGNORECASE)
        return match.group(1).upper() if match else ""

    @staticmethod
    def _similarity_score(a, b):
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()

    def start_requests(self):
        for catalog_number in self.catalog_numbers:
            search_url = f"https://kitchenrestock.com/search?options%5Bprefix%5D=last&q={quote_plus(str(catalog_number))}"
            yield scrapy.Request(
                url=search_url,
                callback=self.parse_search,
                meta={
                    "catalog_number": catalog_number,
                    "search_url": search_url,
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_page_methods": [
                        PageMethod("wait_for_timeout", 3000),  # Wait 3 seconds for page to load
                    ],
                },
                dont_filter=True,
                errback=self.errback_close_page
            )

    async def parse_search(self, response):
        catalog_number = response.meta["catalog_number"]
        normalized_search = self._normalize_catalog(catalog_number)
        
        self.logger.info(f"Parsing search results for catalog: {catalog_number}")

        # Find all product cards in search results
        product_cards = response.css('li.js-pagination-result product-card')
        
        # Close Playwright page
        page = response.meta.get("playwright_page")
        if page:
            await page.close()
        
        if not product_cards:
            self.logger.warning(f"No products found for catalog: {catalog_number}")
            return

        best_match = None
        best_score = 0
        
        for card in product_cards:
            # Extract product title and URL
            title = card.css('p.card__title a::text').get()
            product_url = card.css('p.card__title a::attr(href)').get()
            
            if not title or not product_url:
                continue
            
            # Extract catalog from title
            extracted_catalog = self._extract_catalog_from_title(title)
            normalized_extracted = self._normalize_catalog(extracted_catalog)
            
            # Check for exact match first
            if normalized_extracted == normalized_search:
                best_match = {
                    'title': title.strip(),
                    'url': response.urljoin(product_url),
                    'score': 1.0
                }
                self.logger.info(f"Exact match found for {catalog_number}: {title}")
                break
            
            # Calculate similarity score
            score = self._similarity_score(normalized_search, normalized_extracted)
            if score > best_score:
                best_score = score
                best_match = {
                    'title': title.strip(),
                    'url': response.urljoin(product_url),
                    'score': score
                }
        
        if best_match and best_match['score'] >= 0.5:  # Minimum threshold
            self.logger.info(f"Best match for {catalog_number}: {best_match['title']} (score: {best_match['score']:.2f})")
            yield scrapy.Request(
                url=best_match['url'],
                callback=self.parse_product,
                meta={
                    "catalog_number": catalog_number,
                    "product_title": best_match['title'],
                    "match_score": best_match['score'],
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_page_methods": [
                        PageMethod("wait_for_timeout", 3000),
                    ],
                },
                errback=self.errback_close_page
            )
        else:
            self.logger.warning(f"No suitable match found for catalog: {catalog_number}")

    async def parse_product(self, response):
        catalog_number = response.meta["catalog_number"]
        
        self.logger.info(f"Parsing product page for catalog: {catalog_number}")

        # Close Playwright page
        page = response.meta.get("playwright_page")
        if page:
            await page.close()

        # Extract image URL from media gallery
        image_url = response.css(
            'media-gallery img.product-image::attr(src), '
            'media-gallery img[data-src]::attr(data-src), '
            '.pmslider-slide img::attr(src)'
        ).get()
        
        if image_url and image_url.startswith('//'):
            image_url = 'https:' + image_url
        elif image_url:
            image_url = response.urljoin(image_url)

        # Extract overview/description
        overview = response.css(
            'div.product-description-content .metafield-rich_text_field p::text, '
            'div.product-description-content .rte p::text'
        ).getall()
        overview_text = ' '.join(overview).strip() if overview else ''

        # Extract features
        features = response.css(
            'div.product-bullets-list-guest .metafield-rich_text_field li::text'
        ).getall()
        features_text = ' | '.join([f.strip() for f in features if f.strip()])

        # Extract specs from table
        specs = {}
        spec_rows = response.css('div.specs-container table tr')
        
        for row in spec_rows:
            label = row.css('th::text').get()
            value = row.css('td::text').get()
            
            if label and value:
                label = label.strip()
                value = value.strip()
                specs[label] = value

        # Map specs to output fields
        item = {
            "Catalog Number": catalog_number,
            "Product Title": response.meta.get("product_title", ""),
            "Match Score": response.meta.get("match_score", 0),
            "Product URL": response.url,
            "Image Link": image_url or '',
            "Overview": overview_text,
            "Features": features_text,
            "Length": '',
            "Width": specs.get('Width', ''),
            "Height": specs.get('Height', ''),
            "Volume": '',
            "Diameter": '',
            "Capacity": specs.get('Capacity', ''),
            "Color": specs.get('Color', ''),
            "Shape": specs.get('Shape', ''),
            "Material": specs.get('Material', ''),
            "EAN Code": specs.get('UPC', specs.get('EAN', '')),
            "Pattern": specs.get('Pattern', ''),
            "Barcode": specs.get('Barcode', specs.get('UPC', '')),
            "Model Number": specs.get('Model Number', ''),
            "Manufacturer": specs.get('Manufacturer', ''),
            "Manufacturer Part": specs.get('Manufacturer Part #', ''),
            "Size": specs.get('Size', ''),
            "Depth": specs.get('Depth', ''),
            "Weight": specs.get('Weight', ''),
        }

        yield item
