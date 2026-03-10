import json
import re
from pathlib import Path
from urllib.parse import quote_plus

import scrapy


class TabletopstyleSpider(scrapy.Spider):
    name = "tabletopstyle"
    allowed_domains = ["www.tabletopstyle.com"]
    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "DOWNLOAD_HANDLERS": {
            "http": "scrapy.core.downloader.handlers.http.HTTPDownloadHandler",
            "https": "scrapy.core.downloader.handlers.http.HTTPDownloadHandler",
        }
    }

    def __init__(self, catalog_file=None, limit=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        default_catalog_file = Path(__file__).resolve().parents[3] / "incomplete_catalog_numbers_v0.2.json"
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
    def _extract_catalog_from_url(url):
        if not url:
            return ""

        match = re.search(r"/p/([^/?#]+)\.htm", url, flags=re.IGNORECASE)
        return match.group(1).strip() if match else ""

    def start_requests(self):
        for catalog_number in self.catalog_numbers:
            encoded_catalog = quote_plus(catalog_number)
            url = f"https://www.tabletopstyle.com/searchresults.asp?Search={encoded_catalog}&Submit="

            yield scrapy.Request(
                url=url,
                callback=self.parse_search,
                meta={
                    "searched_catalog_number": catalog_number,
                },
            )

    def parse_search(self, response):
        searched_catalog_number = response.meta["searched_catalog_number"]
        searched_catalog_normalized = self._normalize_catalog(searched_catalog_number)

        cards = response.css("div.v-product")
        if not cards:
            yield {
                "searched_catalog_number": searched_catalog_number,
                "found": False,
                "search_url": response.url,
            }
            return

        matched_card = None
        matched_data = None
        candidate_names = []

        for card in cards:
            product_url = card.css("a.v-product__title::attr(href), a.v-product__img::attr(href)").get()
            product_url = response.urljoin(product_url) if product_url else ""

            product_name = card.css("a.v-product__title::text").get(default="").strip()
            if product_name:
                candidate_names.append(product_name)

            image_link = card.css("a.v-product__img img::attr(src), img::attr(src)").get(default="").strip()
            image_link = response.urljoin(image_link) if image_link else ""

            price_text = " ".join(card.css("div.product_productprice *::text").getall())
            price_text = re.sub(r"\s+", " ", price_text).strip()

            title_attr = card.css("a.v-product__title::attr(title)").get(default="")
            extracted_catalog = self._extract_catalog_from_url(product_url)
            if not extracted_catalog and title_attr:
                match = re.search(r",\s*([A-Z0-9]+)\s*$", title_attr, flags=re.IGNORECASE)
                if match:
                    extracted_catalog = match.group(1).strip()

            extracted_catalog_normalized = self._normalize_catalog(extracted_catalog)
            if extracted_catalog_normalized and extracted_catalog_normalized == searched_catalog_normalized:
                matched_card = card
                matched_data = {
                    "catalog_number": extracted_catalog,
                    "product_name": product_name,
                    "product_url": product_url,
                    "image_link": image_link,
                    "price": price_text,
                }
                break

        if not matched_card or not matched_data:
            yield {
                "searched_catalog_number": searched_catalog_number,
                "found": False,
                "search_url": response.url,
                "note": "No exact catalog match found in search results",
                "candidate_product_names": candidate_names[:10],
            }
            return

        if not matched_data["product_url"]:
            yield {
                "searched_catalog_number": searched_catalog_number,
                "catalog_number": matched_data["catalog_number"],
                "product_name": matched_data["product_name"],
                "product_url": "",
                "image_link": matched_data["image_link"],
                "price": matched_data["price"],
                "overview": "",
                "features": [],
                "alternative_image_links": [],
                "found": True,
            }
            return

        yield scrapy.Request(
            url=matched_data["product_url"],
            callback=self.parse_product,
            meta={
                "searched_catalog_number": searched_catalog_number,
                "catalog_number": matched_data["catalog_number"],
                "product_name": matched_data["product_name"],
                "search_image_link": matched_data["image_link"],
                "search_price": matched_data["price"],
                "search_url": response.url,
            },
        )

    def parse_product(self, response):
        searched_catalog_number = response.meta["searched_catalog_number"]
        catalog_number = response.meta["catalog_number"]
        search_product_name = response.meta["product_name"]
        search_image_link = response.meta["search_image_link"]
        search_price = response.meta["search_price"]
        search_url = response.meta["search_url"]

        product_root = response.css("div[itemtype='http://schema.org/Product']")

        product_name = product_root.css("h1::text").get(default="").strip() if product_root else ""
        if not product_name:
            product_name = search_product_name

        image_link = product_root.css("img#product_photo::attr(src)").get(default="").strip() if product_root else ""
        if not image_link:
            image_link = search_image_link
        else:
            image_link = response.urljoin(image_link)

        alternative_image_links = []
        if product_root:
            for alt in product_root.css("#altviews img::attr(src)").getall():
                alt = alt.strip()
                if alt:
                    alternative_image_links.append(response.urljoin(alt))

        price = product_root.css("span[itemprop='price']::attr(content)").get(default="").strip() if product_root else ""
        if not price:
            price = " ".join(product_root.css("div.product_productprice *::text").getall()) if product_root else ""
            price = re.sub(r"\s+", " ", price).strip()
        if not price:
            price = search_price

        overview = response.css("meta[name='description']::attr(content)").get(default="").strip()

        features = []
        if product_root:
            for feature in product_root.css("ul li::text").getall():
                feature = feature.strip()
                if feature:
                    features.append(feature)

        yield {
            "searched_catalog_number": searched_catalog_number,
            "catalog_number": catalog_number,
            "product_name": product_name,
            "product_url": response.url,
            "search_url": search_url,
            "image_link": image_link,
            "alternative_image_links": alternative_image_links,
            "overview": overview,
            "features": features,
            "price": price,
            "found": True,
        }
