import json
import re
from pathlib import Path
from urllib.parse import quote_plus

import scrapy


class BgbentonSpider(scrapy.Spider):
    name = "bgbenton"
    allowed_domains = ["www.bgbenton.co.uk"]
    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "DOWNLOAD_HANDLERS": {
            "http": "scrapy.core.downloader.handlers.http.HTTPDownloadHandler",
            "https": "scrapy.core.downloader.handlers.http.HTTPDownloadHandler",
        }
    }

    def __init__(self, catalog_file=None, limit=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        default_catalog_file = Path(__file__).resolve().parents[3] / "incomplete_catalog_numbers_v0.8.json"
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

    def start_requests(self):
        for catalog_number in self.catalog_numbers:
            encoded_catalog = quote_plus(catalog_number)
            url = f"https://www.bgbenton.co.uk/?s={encoded_catalog}&post_type=product"

            yield scrapy.Request(
                url=url,
                callback=self.parse_search,
                meta={
                    "searched_catalog_number": catalog_number,
                },
                errback=self.errback_search,
            )

    def errback_search(self, failure):
        searched_catalog_number = failure.request.meta.get("searched_catalog_number", "")
        self.logger.warning(
            "Search request failed for catalog %s: %s",
            searched_catalog_number,
            failure.value,
        )
        yield {
            "searched_catalog_number": searched_catalog_number,
            "found": False,
            "blocked": True,
            "error": str(failure.value),
        }

    def parse_search(self, response):
        searched_catalog_number = response.meta["searched_catalog_number"]
        searched_catalog_normalized = self._normalize_catalog(searched_catalog_number)

        product_items = response.css("li.product")
        if not product_items:
            yield {
                "searched_catalog_number": searched_catalog_number,
                "found": False,
                "search_url": response.url,
            }
            return

        matched_item = None
        matched_data = None
        candidate_names = []

        for item in product_items:
            # Extract SKU from data attributes or text content
            sku = item.css("::attr(data-product_sku)").get(default="").strip()
            if not sku:
                sku_text = item.css("span.sku::text").get(default="").strip()
                sku = sku_text

            # Extract product URL
            product_url = item.css("h3.woocommerce-loop-product__title a::attr(href)").get(default="").strip()
            if not product_url:
                product_url = item.css("a.woocommerce-LoopProduct-link::attr(href)").get(default="").strip()
            product_url = response.urljoin(product_url) if product_url else ""

            # Extract product name
            product_name = item.css("h3.woocommerce-loop-product__title a::text").get(default="").strip()
            if product_name:
                candidate_names.append(product_name)

            # Extract image link
            image_link = item.css("img.attachment-woocommerce_thumbnail::attr(src)").get(default="").strip()
            if not image_link:
                image_link = item.css("a.woocommerce-LoopProduct-link img::attr(src)").get(default="").strip()
            image_link = response.urljoin(image_link) if image_link else ""

            # Extract price
            price_text = " ".join(item.css("span.price *::text").getall())
            price_text = re.sub(r"\s+", " ", price_text).strip()

            title_attr = item.css("h3.woocommerce-loop-product__title a::attr(title)").get(default="").strip()
            image_alt = item.css("img::attr(alt)").get(default="").strip()
            combined_text = " ".join([
                product_name,
                title_attr,
                image_alt,
                product_url,
                image_link,
                " ".join(item.css("*::text").getall()),
            ])
            combined_text_normalized = self._normalize_catalog(combined_text)

            matched_catalog = ""
            if searched_catalog_normalized and searched_catalog_normalized in combined_text_normalized:
                matched_catalog = searched_catalog_number
            elif self._normalize_catalog(sku) == searched_catalog_normalized:
                matched_catalog = searched_catalog_number

            if matched_catalog:
                matched_item = item
                matched_data = {
                    "catalog_number": matched_catalog,
                    "sku": sku,
                    "product_name": product_name,
                    "product_url": product_url,
                    "image_link": image_link,
                    "price": price_text,
                }
                break

        if not matched_item or not matched_data:
            yield {
                "searched_catalog_number": searched_catalog_number,
                "found": False,
                "search_url": response.url,
                "note": "No exact catalog match found in search results",
                "candidate_product_names": candidate_names[:10],
            }
            return

        # If we have a product URL, request the detail page for more information
        if matched_data["product_url"]:
            yield scrapy.Request(
                url=matched_data["product_url"],
                callback=self.parse_product,
                meta={
                    "searched_catalog_number": searched_catalog_number,
                    "matched_data": matched_data,
                },
                errback=self.errback_product,
            )
        else:
            # Return basic data if no product URL
            matched_data["searched_catalog_number"] = searched_catalog_number
            matched_data["found"] = True
            matched_data["search_url"] = response.url
            yield matched_data

    def errback_product(self, failure):
        meta = failure.request.meta
        matched_data = meta.get("matched_data", {})
        searched_catalog_number = meta.get("searched_catalog_number", "")

        self.logger.warning(
            "Product detail request failed for %s: %s",
            searched_catalog_number,
            failure.value,
        )
        matched_data["searched_catalog_number"] = searched_catalog_number
        matched_data["found"] = True
        matched_data["blocked"] = True
        yield matched_data

    def parse_product(self, response):
        searched_catalog_number = response.meta["searched_catalog_number"]
        matched_data = response.meta.get("matched_data", {})

        # Extract overview/description
        overview_text = " ".join(
            response.css("div.woocommerce-Tabs-panel--description *::text").getall()
        )
        overview_text = re.sub(r"\s+", " ", overview_text).strip()
        if overview_text:
            matched_data["overview"] = overview_text

        # Extract main product image from gallery
        main_image = response.css("img.wp-post-image::attr(src)").get(default="").strip()
        if not main_image:
            main_image = response.css("img.woocommerce-product-gallery__image img::attr(src)").get(
                default=""
            ).strip()
        if main_image and not matched_data.get("image_link"):
            matched_data["image_link"] = response.urljoin(main_image)

        # Extract SKU/EAN/Barcode
        sku = response.css("span.sku::text").get(default="").strip()
        if sku:
            matched_data["sku"] = sku
            matched_data["barcode"] = sku  # SKU often serves as EAN/Barcode

        # Extract specs from product tables or description
        # Try to find specifications table
        spec_rows = response.css("table tr")
        if spec_rows:
            for row in spec_rows:
                cells = row.css("td::text").getall()
                if len(cells) >= 2:
                    key = cells[0].strip().lower()
                    value = cells[1].strip()

                    if "length" in key:
                        matched_data["length"] = value
                    elif "width" in key:
                        matched_data["width"] = value
                    elif "height" in key:
                        matched_data["height"] = value
                    elif "diameter" in key:
                        matched_data["diameter"] = value
                    elif "volume" in key or "capacity" in key:
                        matched_data["volume"] = value
                    elif "color" in key:
                        matched_data["color"] = value
                    elif "material" in key:
                        matched_data["material"] = value
                    elif "pattern" in key:
                        matched_data["pattern"] = value

        # Extract dimensions from product description/name using regex patterns
        full_text = (
            matched_data.get("product_name", "")
            + " "
            + matched_data.get("overview", "")
        )
        
        # Length extraction (cm, mm, inches)
        if "length" not in matched_data:
            length_match = re.search(r"Length[:\s]+(\d+(?:\.\d+)?)\s*(cm|mm|in|\")", full_text, re.IGNORECASE)
            if length_match:
                matched_data["length"] = f"{length_match.group(1)}{length_match.group(2)}"
        
        # Diameter extraction
        if "diameter" not in matched_data:
            diameter_match = re.search(r"Diameter[:\s]+(\d+(?:\.\d+)?)\s*(cm|mm|in|\")", full_text, re.IGNORECASE)
            if diameter_match:
                matched_data["diameter"] = f"{diameter_match.group(1)}{diameter_match.group(2)}"

        # Extract color (common colors)
        if "color" not in matched_data:
            color_keywords = [
                "grey", "gray", "white", "black", "red", "blue", "green", "yellow",
                "gold", "silver", "purple", "pink", "brown", "tan", "cream", "ivory",
                "natural", "burgundy", "navy", "teal", "beige", "bronze", "copper"
            ]
            for color in color_keywords:
                if re.search(rf"\b{color}\b", full_text, re.IGNORECASE):
                    matched_data["color"] = color.capitalize()
                    break

        # Extract material
        if "material" not in matched_data:
            material_keywords = [
                "porcelain", "ceramic", "china", "stoneware", "earthenware", "glass",
                "abs", "plastic", "stainless steel", "steel", "metal", "wood", "bamboo"
            ]
            for material in material_keywords:
                if re.search(rf"\b{material}\b", full_text, re.IGNORECASE):
                    matched_data["material"] = material.capitalize()
                    break

        matched_data["searched_catalog_number"] = searched_catalog_number
        matched_data["found"] = True
        matched_data["product_url"] = response.url
        yield matched_data
