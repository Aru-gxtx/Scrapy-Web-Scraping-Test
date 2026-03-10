import json
import re
from pathlib import Path

import scrapy


class RillcateringSpider(scrapy.Spider):
    name = "rillcatering"
    allowed_domains = ["www.rillcatering.com"]
    custom_settings = {
        "HTTPERROR_ALLOWED_CODES": [404],
    }

    def _load_catalog_numbers(self):
        json_path = Path(__file__).resolve().parents[3] / "incomplete_catalog_numbers_v0.1.json"
        with open(json_path, "r", encoding="utf-8") as file:
            raw_items = json.load(file)

        catalog_numbers = []
        for item in raw_items:
            if item is None:
                continue
            catalog = str(item).strip()
            # Filter out NaN values
            if catalog and catalog.lower() != "nan":
                catalog_numbers.append(catalog)

        return catalog_numbers

    def start_requests(self):
        for catalog_number in self._load_catalog_numbers():
            # Try English search first with Playwright for JS rendering
            url = f"https://www.rillcatering.com/search/{catalog_number}/"
            yield scrapy.Request(
                url=url,
                callback=self.parse_search,
                meta={
                    "searched_catalog_number": catalog_number,
                    "tried_fallback": False,
                    "playwright": True,  # Enable Playwright rendering
                },
            )

    def parse_search(self, response):
        searched_catalog_number = response.meta["searched_catalog_number"]
        tried_fallback = response.meta["tried_fallback"]

        if response.status == 404 and not tried_fallback:
            self.logger.warning(f"Search not found for {searched_catalog_number}, trying Hungarian endpoint...")
            # Try Hungarian fallback
            fallback_url = f"https://www.rillcatering.com/kereses/{searched_catalog_number}/"
            yield scrapy.Request(
                url=fallback_url,
                callback=self.parse_search,
                meta={
                    "searched_catalog_number": searched_catalog_number,
                    "tried_fallback": True,
                    "playwright": True,
                },
            )
            return

        if response.status == 404:
            self.logger.warning(f"Product not found on rillcatering.com: {searched_catalog_number}")
            yield {
                "searched_catalog_number": searched_catalog_number,
                "found": False,
                "error": "Product not found (404)",
            }
            return

        product_cards = response.css("div.productListCont div.row.album")
        if not product_cards:
            self.logger.info(f"No results for: {searched_catalog_number}")
            yield {
                "searched_catalog_number": searched_catalog_number,
                "found": False,
                "search_url": response.url,
            }
            return

        self.logger.info(f"Found {len(product_cards)} results for: {searched_catalog_number}")
        for card in product_cards:
            title = card.css("div.details div.title.product a::text").get(default="").strip()
            product_url = card.css("div.details div.title.product a::attr(href)").get()
            
            # Extract image from style attribute
            image_style = card.css("div.image a.limageBg::attr(style)").get(default="")
            image_link = ""
            if image_style:
                match = re.search(r"url\((.*?)\)", image_style)
                if match:
                    image_link = match.group(1).strip("'\"")
            
            code_text = card.css("div.label.code::text").get(default="")
            catalog_match = re.search(r"(?:SKU|Cikksz[aá]m):\s*(\S+)", code_text, flags=re.IGNORECASE)
            catalog_number = catalog_match.group(1).strip() if catalog_match else ""

            price_text = card.css("span[itemprop='price']::text").get(default="").strip()
            stock_text = card.css("div.store::text").get(default="").strip()
            
            # Yield search result and request product details
            if product_url:
                product_url = response.urljoin(product_url)
                yield scrapy.Request(
                    url=product_url,
                    callback=self.parse_product,
                    meta={
                        "searched_catalog_number": searched_catalog_number,
                        "catalog_number": catalog_number,
                        "product_name": title,
                        "image_link": image_link,
                        "price": price_text,
                        "stock": stock_text,
                    },
                )
            else:
                yield {
                    "searched_catalog_number": searched_catalog_number,
                    "catalog_number": catalog_number,
                    "product_name": title,
                    "product_url": "",
                    "image_link": image_link,
                    "price": price_text,
                    "stock": stock_text,
                    "search_url": response.url,
                    "found": True,
                }

    def parse_product(self, response):
        searched_catalog_number = response.meta["searched_catalog_number"]
        catalog_number = response.meta["catalog_number"]
        product_name = response.meta["product_name"]
        search_image_link = response.meta["image_link"]
        price = response.meta["price"]
        stock = response.meta["stock"]
        
        # Try to extract additional image from product page
        product_image = response.css("div.image a::attr(style)").re_first(r"url\((.*?)\)")
        image_link = product_image if product_image else search_image_link
        
        # Try to extract dimensions/specs (these may be in product description or specs table)
        overview = " ".join(response.css("div#product div.body ::text").getall()).strip()
        
        yield {
            "searched_catalog_number": searched_catalog_number,
            "catalog_number": catalog_number,
            "product_name": product_name,
            "product_url": response.url,
            "image_link": image_link,
            "overview": overview[:500] if overview else "",
            "length": "",
            "width": "",
            "height": "",
            "volume": "",
            "diameter": "",
            "color": "",
            "material": "",
            "ean_code": "",
            "pattern": "",
            "barcode": "",
            "price": price,
            "stock": stock,
            "found": True,
        }
