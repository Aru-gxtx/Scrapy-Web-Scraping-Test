import json
import re
from pathlib import Path
from urllib.parse import quote_plus

import scrapy


class RussoequipSpider(scrapy.Spider):
    name = "russoequip"
    allowed_domains = ["www.russoequip.com"]
    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "DOWNLOAD_HANDLERS": {
            "http": "scrapy.core.downloader.handlers.http.HTTPDownloadHandler",
            "https": "scrapy.core.downloader.handlers.http.HTTPDownloadHandler",
        },
    }

    def __init__(self, catalog_file=None, limit=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        default_catalog_file = Path(__file__).resolve().parents[3] / "incomplete_catalog_numbers_v0.3.json"
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

        match = re.search(r"\b([A-Z0-9]{5,})\b", str(text).upper())
        return match.group(1) if match else ""

    @staticmethod
    def _preferred_image(candidates):
        for image in candidates:
            if not image:
                continue
            lowered = image.lower()
            if "logo" in lowered or "no-image" in lowered or "nophoto" in lowered:
                continue
            return image
        return candidates[0] if candidates else ""

    @staticmethod
    def _extract_volume_from_text(text):
        if not text:
            return ""

        match = re.search(r"(\d+(?:[\./]\d+)?)\s*(oz|cl|ml|l)\b", text, flags=re.IGNORECASE)
        if not match:
            return ""
        return f"{match.group(1)} {match.group(2).lower()}"

    @staticmethod
    def _extract_diameter_from_text(text):
        if not text:
            return ""

        match = re.search(r"([0-9]+(?:-[0-9]+/[0-9]+|\.[0-9]+)?)\s*\"?\s*dia", text, flags=re.IGNORECASE)
        if not match:
            return ""
        return f"{match.group(1)}\""

    @staticmethod
    def _extract_material_from_text(text):
        if not text:
            return ""

        match = re.search(r"\b(vitrified china|fully vitrified|ceramic|china|porcelain|stoneware)\b", text, flags=re.IGNORECASE)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _extract_pattern_from_text(text):
        if not text:
            return ""

        # Example: "..., Steelite Performance, Terramesa Mustard (...)"
        match = re.search(r"Steelite\s+Performance,\s*([^,(]+)", text, flags=re.IGNORECASE)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _extract_color_from_text(text, pattern):
        if pattern:
            parts = pattern.split()
            if len(parts) > 1:
                return parts[-1]

        if not text:
            return ""

        match = re.search(
            r"\b(black|white|brown|green|blue|red|yellow|mustard|olive|mocha|terracotta|gray|grey)\b",
            text,
            flags=re.IGNORECASE,
        )
        return match.group(1).strip() if match else ""

    @staticmethod
    def _extract_product_ld_json(response):
        for script_text in response.css("script[type='application/ld+json']::text").getall():
            script_text = script_text.strip()
            if not script_text:
                continue

            try:
                data = json.loads(script_text)
            except Exception:
                continue

            if isinstance(data, dict) and str(data.get("@type", "")).lower() == "product":
                return data
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and str(item.get("@type", "")).lower() == "product":
                        return item

        return {}

    def start_requests(self):
        for catalog_number in self.catalog_numbers:
            encoded_catalog = quote_plus(catalog_number)
            url = (
                "https://www.russoequip.com/search?type=product&options%5Bprefix%5D=last"
                f"&q={encoded_catalog}"
            )

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

        cards = response.css("div.product-item")
        if not cards:
            yield {
                "searched_catalog_number": searched_catalog_number,
                "found": False,
                "search_url": response.url,
            }
            return

        matched_data = None
        candidate_names = []

        for card in cards:
            title = card.css("a.product-item__title::text").get(default="").strip()
            vendor = card.css("a.product-item__vendor::text").get(default="").strip()
            product_url = card.css("a.product-item__title::attr(href), a.product-item__image-wrapper::attr(href)").get()
            product_url = response.urljoin(product_url) if product_url else ""

            image_link = card.css("img.product-item__primary-image::attr(src), img::attr(src)").get(default="").strip()
            if image_link:
                image_link = response.urljoin(image_link)

            if title:
                candidate_names.append(title)

            title_normalized = self._normalize_catalog(title)
            url_normalized = self._normalize_catalog(product_url)

            extracted_catalog = self._extract_catalog_from_text(title)
            if not extracted_catalog:
                extracted_catalog = self._extract_catalog_from_text(product_url)

            extracted_catalog_normalized = self._normalize_catalog(extracted_catalog)
            if (
                extracted_catalog_normalized == searched_catalog_normalized
                or (searched_catalog_normalized and searched_catalog_normalized in title_normalized)
                or (searched_catalog_normalized and searched_catalog_normalized in url_normalized)
            ):
                # Use the searched catalog as canonical when title/url contains it.
                extracted_catalog = searched_catalog_number
                matched_data = {
                    "catalog_number": extracted_catalog,
                    "product_name": title,
                    "product_url": product_url,
                    "image_link": image_link,
                    "vendor": vendor,
                }
                break

        if not matched_data:
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
                "vendor": matched_data["vendor"],
                "product_url": "",
                "image_link": matched_data["image_link"],
                "overview": "",
                "price": "",
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
                "vendor": matched_data["vendor"],
                "search_url": response.url,
            },
        )

    def parse_product(self, response):
        searched_catalog_number = response.meta["searched_catalog_number"]
        catalog_number = response.meta["catalog_number"]
        search_product_name = response.meta["product_name"]
        search_image_link = response.meta["search_image_link"]
        vendor = response.meta["vendor"]
        search_url = response.meta["search_url"]

        product_name = response.css("h1.product-meta__title::text, h1.product-title::text, h1::text").get(default="").strip()
        if not product_name:
            product_name = search_product_name

        image_candidates = [
            response.urljoin(src.strip())
            for src in response.css(
                ".product-gallery img::attr(src), "
                "img.product__featured-image::attr(src), "
                "meta[property='og:image']::attr(content), "
                "meta[name='twitter:image']::attr(content), "
                "img.product-item__primary-image::attr(src)"
            ).getall()
            if src and str(src).strip()
        ]
        image_link = self._preferred_image(image_candidates)
        if not image_link:
            image_link = search_image_link

        price = response.css("span.price::text, .price-list .price::text, [data-money-convertible]::text").get(default="").strip()
        price = re.sub(r"\s+", " ", price)

        overview = response.css("meta[name='description']::attr(content)").get(default="").strip()
        if not overview:
            overview = " ".join(
                text.strip() for text in response.css("div.rte p::text, .product-meta__description *::text").getall() if text.strip()
            )

        specs = {}
        for row in response.css(".table-wrapper tr, table tr"):
            key = row.css("td:nth-child(1)::text").get(default="").strip()
            value = row.css("td:nth-child(2)::text").get(default="").strip()
            if key and value:
                specs[key.lower()] = value

        product_ld = self._extract_product_ld_json(response)

        length = specs.get("length", "")
        width = specs.get("width", "")
        height = specs.get("height", "")
        diameter = specs.get("diameter", "") or self._extract_diameter_from_text(overview)

        volume = (
            specs.get("volume", "")
            or specs.get("capacity", "")
            or self._extract_volume_from_text(overview)
        )

        material = specs.get("material", "") or self._extract_material_from_text(overview)
        pattern = specs.get("pattern", "") or self._extract_pattern_from_text(overview)
        color = specs.get("color", "") or self._extract_color_from_text(overview, pattern)

        ean_code = (
            specs.get("ean", "")
            or specs.get("ean code", "")
            or str(product_ld.get("gtin13") or product_ld.get("gtin") or "").strip()
        )
        barcode = (
            specs.get("barcode", "")
            or specs.get("upc", "")
            or str(product_ld.get("mpn") or "").strip()
        )

        yield {
            "searched_catalog_number": searched_catalog_number,
            "catalog_number": catalog_number,
            "product_name": product_name,
            "vendor": vendor,
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
            "price": price,
            "found": True,
        }
