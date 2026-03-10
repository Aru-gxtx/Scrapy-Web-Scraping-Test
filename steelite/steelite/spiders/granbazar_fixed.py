import re
import scrapy


class GranbazarSpider(scrapy.Spider):
    name = "granbazar"
    allowed_domains = ["granbazar.ru"]
    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "HTTPERROR_ALLOW_ALL": True,
        "CONCURRENT_REQUESTS": 2,
        "DOWNLOAD_DELAY": 1.0,
        "USER_AGENT": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    }

    def __init__(self, max_pages=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_pages = int(max_pages) if max_pages else 102
        self.logger.info(f"Will scrape up to {self.max_pages} pages of GranBazar STEELITE products")

    @staticmethod
    def _normalize_text(value):
        if value is None:
            return ""
        text = str(value).strip()
        text = re.sub(r"\s+", " ", text)
        return text

    @staticmethod
    def _extract_from_dl(response, label_text):
        """Extract value from dt/dd pairs in specification list"""
        for dt in response.css("dl dt"):
            if label_text.lower() in dt.css("::text").get(default="").lower():
                # The next dd sibling contains the value
                dd = dt.xpath("following-sibling::dd[1]/text()").get(default="").strip()
                return dd
        return ""

    def start_requests(self):
        base_url = "https://granbazar.ru/search/?q=STEELITE&PAGEN_1={page}"
        
        for page in range(1, self.max_pages + 1):
            url = base_url.format(page=page)
            yield scrapy.Request(
                url=url,
                callback=self.parse_search_page,
                errback=self.errback_request,
                meta={"page_number": page},
                dont_filter=True,
            )

    def parse_search_page(self, response):
        page_number = response.meta.get("page_number", 1)
        
        if response.status != 200:
            self.logger.warning(f"Search page {page_number} returned status {response.status}")
            return

        self.logger.info(f"Parsing search page {page_number}")

        # Extract product items from gallery
        product_items = response.css("div.gallery_item")
        
        if not product_items:
            self.logger.warning(f"No products found on page {page_number}")
            return

        self.logger.info(f"Found {len(product_items)} products on page {page_number}")

        for item in product_items:
            product_id = item.attrib.get("data-id", "")
            product_url = item.css("a.image_link::attr(href)").get(default="").strip()
            
            if not product_url:
                continue
            
            # Extract preview info from search listing
            product_name = item.css("h5.gallery_item_title a::text").get(default="").strip()
            price_text = item.css("div.gallery_item_price span::text").getall()
            price = ""
            if price_text:
                # Get price value (span with number)
                for span in price_text:
                    if span.strip() and (span.strip().isdigit() or "," in span or "." in span):
                        price = span.strip()
                        break
            
            # Extract image from search listing (use higher resolution from srcset)
            preview_image = ""
            img = item.css("figure img")
            if img:
                # Try to get high-res from srcset
                srcset = img.attrib.get("srcset", "")
                if srcset:
                    # srcset format: url1 150w, url2 810w - get the last (highest res)
                    urls = [part.strip().split()[0] for part in srcset.split(",")]
                    preview_image = urls[-1] if urls else ""
                if not preview_image:
                    preview_image = img.attrib.get("src", "")
            
            yield scrapy.Request(
                url=response.urljoin(product_url),
                callback=self.parse_product,
                errback=self.errback_request,
                meta={
                    "page_number": page_number,
                    "product_id": product_id,
                    "product_name_preview": product_name,
                    "preview_image": preview_image,
                    "price": price,
                },
            )

    def parse_product(self, response):
        page_number = response.meta.get("page_number", 0)
        product_id = response.meta.get("product_id", "")
        product_name_preview = response.meta.get("product_name_preview", "")
        preview_image = response.meta.get("preview_image", "")
        price = response.meta.get("price", "")
        
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

        # Extract product name from detail page
        product_name = response.css("h1::text, .product-name::text").get(default=product_name_preview).strip()
        
        # Extract image - prefer high-res version
        image_link = ""
        img = response.css("figure img")
        if img:
            srcset = img.attrib.get("srcset", "")
            if srcset:
                urls = [part.strip().split()[0] for part in srcset.split(",")]
                image_link = urls[-1] if urls else ""
            if not image_link:
                image_link = img.attrib.get("src", "")
        if not image_link:
            image_link = preview_image
        
        if image_link:
            image_link = response.urljoin(image_link)

        # Extract overview/description
        overview = response.css("p[itemprop='description'].seoGen::text").get(default="")
        overview = self._normalize_text(overview)
        diameter = ""
        diameter_match = re.search(r"D=(\d+)", product_name, re.IGNORECASE)
        if diameter_match:
            diameter = diameter_match.group(1)
        
        # Extract height (H=\d+)
        height = ""
        height_match = re.search(r"H=(\d+)", product_name, re.IGNORECASE)
        if height_match:
            height = height_match.group(1)
        
        # Extract volume (number followed by л or l or ml or мл)
        volume = ""
        volume_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:л|l|ml|мл)", product_name, re.IGNORECASE)
        if volume_match:
            volume = volume_match.group(1).replace(",", ".")
        
        # Extract material from name if it contains common keywords
        material = ""
        if "фарфор" in product_name.lower():
            material = "Фарфор"
        elif "керамика" in product_name.lower():
            material = "Керамика"
        elif "стекло" in product_name.lower():
            material = "Стекло"
        elif "пластик" in product_name.lower():
            material = "Пластик"
        
        # Extract color if present
        colors = ["белый", "черный", "красный", "синий", "зеленый", "желтый", "серебристый", "золотой"]
        color = ""
        for col in colors:
            if col in product_name.lower():
                color = col.capitalize()
                break
        
        # Extract shape/description
        shape = ""
        shapes = ["чашка", "блюдце", "салатник", "миска", "тарелка", "кружка", "форма"]
        for shp in shapes:
            if shp in product_name.lower():
                shape = shp.capitalize()
                break
        
        # Extract SKU from DL (Артикул)
        ean_code = self._extract_from_dl(response, "Артикул")
        barcode = ""
        
        # Try to extract from description if not found
        if not ean_code:
            ean_match = re.search(r"EAN[:\s]+(\d+)", overview, re.IGNORECASE)
            if ean_match:
                ean_code = ean_match.group(1)
        
        if not barcode:
            barcode_match = re.search(r"Barcode[:\s]+(\d+)", overview, re.IGNORECASE)
            if barcode_match:
                barcode = barcode_match.group(1)

        yield {
            "product_id": product_id,
            "product_name": product_name,
            "product_url": response.url,
            "image_link": image_link,
            "overview": overview,
            "length": "",
            "width": "",
            "height": height,
            "capacity": volume,
            "volume": volume,
            "diameter": diameter,
            "color": color,
            "shape": shape,
            "material": material,
            "pattern": "",
            "ean_code": ean_code,
            "barcode": barcode,
            "price": price,
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
