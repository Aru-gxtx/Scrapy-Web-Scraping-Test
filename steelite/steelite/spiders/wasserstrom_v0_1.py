import re
import scrapy


class WasserstromV01Spider(scrapy.Spider):
    name = "wasserstrom_v0.1"
    allowed_domains = ["www.wasserstrom.com"]
    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "USER_AGENT": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "HTTPERROR_ALLOW_ALL": True,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
        "DOWNLOAD_DELAY": 1.0,
        "DEFAULT_REQUEST_HEADERS": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        },
    }

    def __init__(self, max_pages=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Allow limiting the number of pages to scrape (for testing)
        self.max_pages = int(max_pages) if max_pages else 120
        self._seen_product_urls = set()
        self.logger.info(f"Will scrape up to {self.max_pages} pages of STEELITE products")

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
            "noimage_wasserstrom",
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
        match = re.search(r"(\d+\.?\d*)\s*(oz|ounce|ounces|cl|ml|l)\b", text, re.IGNORECASE)
        return f"{match.group(1)}{match.group(2)}".lower() if match else ""

    @staticmethod
    def _extract_material_from_text(text):
        if not text:
            return ""
        
        materials = {
            "vitrified china": r"vitrified\s+china",
            "vitrified ceramic": r"vitrified\s+ceramic",
            "alumina vitrified": r"alumina\s+vitrified",
            "ceramic": r"ceramic",
            "porcelain": r"porcelain",
            "china": r"\bchina\b",
            "stainless steel": r"stainless\s+steel",
            "glass": r"\bglass\b",
            "plastic": r"plastic",
            "melamine": r"melamine",
        }
        
        text_lower = text.lower()
        for material, pattern in materials.items():
            if re.search(pattern, text_lower):
                return material
        
        return ""

    @staticmethod
    def _extract_color_from_text(text):
        if not text:
            return ""
        
        colors = [
            "white", "black", "red", "blue", "green", "yellow", "orange",
            "purple", "brown", "gray", "grey", "beige", "cream", "ivory",
            "mustard", "mocha", "olive", "tan", "navy", "burgundy"
        ]
        
        text_lower = text.lower()
        for color in colors:
            if re.search(rf"\b{color}\b", text_lower):
                return color.capitalize()
        
        return ""

    @staticmethod
    def _build_listing_url(begin_index, page_size=100):
        return (
            "https://www.wasserstrom.com/restaurant-supplies-equipment/WassProductListingView"
            "?top_category3="
            "&top_category2="
            "&top_category5="
            "&top_category4="
            "&advancedSearch="
            "&manufacturer="
            "&metaData="
            "&enableSKUListView=false"
            "&catalogId=3074457345616677089"
            "&searchTerm=STEELITE"
            f"&resultsPerPage={page_size}"
            "&filterFacet="
            "&resultCatEntryType=2"
            "&gridPosition="
            "&top_category="
            "&categoryFacetHierarchyPath="
            "&ajaxStoreImageDir=%2Fwcsstore%2FWasserstromStorefrontAssetStore%2F"
            "&searchType="
            "&filterTerm="
            "&searchTermScope="
            "&storeId=10051"
            "&ddkey=ProductListingView_5_3074457345618260656_3074457345618262060"
            "&sType=SimpleSearch"
            "&emsName=Widget_WASSCatalogEntryListWidget_3074457345618262060"
            "&disableProductCompare=false"
            "&langId=-1"
            "&facet="
            "&categoryId="
            "&parent_category_rn="
            f"&beginIndex={begin_index}"
        )

    def start_requests(self):
        # Start with the first listing chunk. beginIndex drives server-side pagination.
        page_size = 100
        base_url = self._build_listing_url(begin_index=0, page_size=page_size)
        
        yield scrapy.Request(
            url=base_url,
            callback=self.parse_search_results,
            errback=self.errback_request,
            meta={
                "page_number": 1,
                "begin_index": 0,
                "page_size": 100,
            },
            dont_filter=True,
        )

    def parse_search_results(self, response):
        page_number = response.meta.get("page_number", 1)
        begin_index = response.meta.get("begin_index", 0)
        page_size = response.meta.get("page_size", 100)

        if response.status != 200:
            self.logger.warning(f"Search page {page_number} returned status {response.status}")
            yield {
                "error": f"HTTP {response.status}",
                "page_number": page_number,
                "search_url": response.url,
            }
            return

        self.logger.info(f"Parsing search results page {page_number} (beginIndex={begin_index})")

        # Extract total number of pages from pagination controls.
        page_numbers = []
        for candidate in re.findall(r'pageNumber:"(\d+)"', response.text):
            try:
                page_numbers.append(int(candidate))
            except ValueError:
                continue
        discovered_max_page = max(page_numbers) if page_numbers else None
        effective_max_pages = min(self.max_pages, discovered_max_page) if discovered_max_page else self.max_pages

        # Extract all product links from the search results
        product_links = []
        
        for anchor in response.css('div.product_name a[href*="restaurant-supplies-equipment"]'):
            href = anchor.attrib.get("href", "")
            if not href:
                continue
            
            # Skip non-product links
            if any(x in href for x in ("/SearchDisplay", "/catalogsearch/", "/products", "/shop-by-business")):
                continue
            
            # Convert to absolute URL and ensure HTTPS
            product_url = response.urljoin(href).replace("http://", "https://", 1)
            
            # Extract model number if available in the same product container
            product_div = anchor.xpath('./ancestor::div[contains(@class, "product")]').get()
            model_number = ""
            if product_div:
                model_match = re.search(r'Model #:\s*([A-Za-z0-9\-]+)', product_div)
                if model_match:
                    model_number = model_match.group(1).strip()
            
            product_card = anchor.xpath('./ancestor::div[contains(@class, "product")]')

            # Extract item number from the card to pick the matching image.
            item_number_hint = ""
            if product_div:
                item_match = re.search(r"Item\s*#\s*:\s*(\d+)", product_div, re.IGNORECASE)
                if item_match:
                    item_number_hint = item_match.group(1).strip()

            image_hint = ""
            image_candidates = [
                src.strip()
                for src in product_card.css("div.product_image img::attr(dat-src), div.product_image img::attr(src)").getall()
                if src and str(src).strip()
            ]
            for candidate in image_candidates:
                c_lower = candidate.lower()
                if "minority_n" in c_lower or "spinner" in c_lower:
                    continue
                if "noimage_wasserstrom" in c_lower:
                    continue
                if item_number_hint and item_number_hint not in candidate:
                    continue
                image_hint = candidate
                break

            if not image_hint and image_candidates:
                image_hint = image_candidates[0]

            product_links.append({
                "url": product_url,
                "model": model_number,
                "image_hint": response.urljoin(image_hint) if image_hint else "",
            })

        # De-duplicate while preserving order
        seen_urls = set()
        unique_products = []
        for product in product_links:
            if product["url"] not in seen_urls:
                seen_urls.add(product["url"])
                unique_products.append(product)

        self.logger.info(f"Found {len(unique_products)} products on page {page_number}")

        # Scrape each product
        duplicate_count = 0
        new_count = 0
        for product in unique_products:
            if product["url"] in self._seen_product_urls:
                duplicate_count += 1
                continue

            new_count += 1
            self._seen_product_urls.add(product["url"])
            yield scrapy.Request(
                url=product["url"],
                callback=self.parse_product,
                errback=self.errback_request,
                meta={
                    "model_number_hint": product["model"],
                    "search_image_hint": product.get("image_hint", ""),
                    "page_number": page_number,
                },
            )

        self.logger.info(f"Page {page_number}: {new_count} new products, {duplicate_count} duplicates")

        has_next = page_number < effective_max_pages

        if has_next:
            next_begin_index = begin_index + page_size
            next_url = self._build_listing_url(begin_index=next_begin_index, page_size=page_size)
            self.logger.info(f"Requesting next page {page_number + 1} with beginIndex={next_begin_index}")
            yield scrapy.Request(
                url=next_url,
                callback=self.parse_search_results,
                errback=self.errback_request,
                meta={
                    "page_number": page_number + 1,
                    "begin_index": next_begin_index,
                    "page_size": page_size,
                },
                dont_filter=True,
            )

    def parse_product(self, response):
        model_number_hint = response.meta.get("model_number_hint", "")
        search_image_hint = response.meta.get("search_image_hint", "")
        page_number = response.meta.get("page_number", 0)

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

        # Extract catalog number from Model #
        catalog_number = ""
        model_line = response.xpath("normalize-space(//span[contains(@class,'sku')][contains(., 'Model #')])").get(default="")
        if model_line:
            model_match = re.search(r"Model\s*#\s*:?\s*([A-Za-z0-9\-]+)", model_line, re.IGNORECASE)
            if model_match:
                catalog_number = model_match.group(1).strip()
        
        # Fallback to hint from search page
        if not catalog_number and model_number_hint:
            catalog_number = model_number_hint
        
        # Fallback: extract from URL or title
        if not catalog_number:
            title = response.css("h1.main_header::text").get(default="")
            catalog_number = self._extract_catalog_from_text(title)

        # Extract product details
        product_name = response.css("h1.main_header::text").get(default="").strip()
        
        # Item number (Wasserstrom's internal SKU) - extract early for image construction
        item_number = ""
        item_line = response.xpath("normalize-space(//span[contains(@class,'sku')][contains(., 'Item #')])").get(default="")
        if item_line:
            item_match = re.search(r"Item\s*#\s*:?\s*([A-Za-z0-9\-]+)", item_line, re.IGNORECASE)
            if item_match:
                item_number = item_match.group(1).strip()

        image_candidates = []

        # Prefer search-card image if it is product-specific.
        if search_image_hint:
            hint = response.urljoin(search_image_hint.strip())
            hint_lower = hint.lower()
            if (
                "about-us-icon" not in hint_lower
                and "favicon" not in hint_lower
                and "noimage_wasserstrom" not in hint_lower
                and "minority_n" not in hint_lower
                and "pdp-banner" not in hint_lower
                and "pdp-leaderboard" not in hint_lower
                and "prop-65-warning" not in hint_lower
                and (not item_number or item_number in hint)
            ):
                image_candidates.append(hint)
        
        # Prefer page-level product images and filter out generic site icons.
        for img in response.css('img[itemprop="image"]::attr(src), img[src*="cloudinary"]::attr(src), img[src*="/image/upload/"]::attr(src), meta[property="og:image"]::attr(content)').getall():
            img = response.urljoin(img.strip()) if img else ""
            img_lower = img.lower()
            if not img:
                continue
            if "about-us-icon" in img_lower or "favicon" in img_lower:
                continue
            if "minority_n" in img_lower:
                continue
            if "pdp-banner" in img_lower or "pdp-leaderboard" in img_lower or "prop-65-warning" in img_lower:
                continue
            if "noimage_wasserstrom" in img_lower:
                continue
            if item_number and item_number not in img and "image/upload" in img_lower:
                continue
            if "cloudinary.com" in img_lower or "assets.wasserstrom.com/image/upload" in img_lower:
                image_candidates.append(img)
        
        # Extract from JavaScript variables - look for var item = XXXXX
        if not image_candidates:
            script_text = " ".join(response.css("script::text").getall())
            
            # Look for: var item = 6119669
            item_match = re.search(r'var\s+item\s*=\s*(\d+)', script_text)
            if item_match:
                js_item_number = item_match.group(1)
                # Try Wasserstrom's asset CDN URL
                cloudinary_url = f"https://assets.wasserstrom.com/image/upload/{js_item_number}"
                image_candidates.append(cloudinary_url)
            elif item_number:
                # Use item_number extracted from page
                cloudinary_url = f"https://assets.wasserstrom.com/image/upload/{item_number}"
                image_candidates.append(cloudinary_url)
        
        # Strong fallback: image from the search-card listing item.
        if not image_candidates and search_image_hint:
            hint = response.urljoin(search_image_hint.strip())
            hint_lower = hint.lower()
            if (
                "about-us-icon" not in hint_lower
                and "favicon" not in hint_lower
                and "noimage_wasserstrom" not in hint_lower
                and "minority_n" not in hint_lower
                and "pdp-banner" not in hint_lower
                and "pdp-leaderboard" not in hint_lower
                and "prop-65-warning" not in hint_lower
            ):
                image_candidates.append(hint)
        
        image_link = self._preferred_image(image_candidates)

        # Overview/description
        overview = response.css("p[itemprop='description']::text, #product_shortdescription::text, .product_text p::text").get(default="").strip()
        if not overview:
            overview = response.css("meta[name='description']::attr(content)").get(default="").strip()

        # Parse specifications section
        specs = {}
        spec_rows = response.css("div.widget_product_compare div.row")
        
        for row in spec_rows:
            heading = row.css("div.heading::text").get(default="").strip()
            value = row.css("div.item::text").get(default="").strip()
            
            if heading and value:
                # Normalize heading for easier matching
                heading_lower = heading.lower().replace(":", "").strip()
                specs[heading_lower] = value

        # Extract specific fields from specs
        material = specs.get("material", "") or self._extract_material_from_text(overview)
        color = specs.get("color", "") or self._extract_color_from_text(product_name)
        pattern = specs.get("pattern", "")
        
        # Dimensions
        width_raw = specs.get("each width", "")
        height_raw = specs.get("each height", "")
        length_raw = specs.get("each length", "")
        
        width = width_raw if width_raw else ""
        height = height_raw if height_raw else ""
        length = length_raw if length_raw else ""
        
        # Volume/Capacity
        volume = specs.get("volume capacity", "") or specs.get("capacity", "")
        if not volume:
            volume = self._extract_volume_from_text(product_name + " " + overview)

        # Diameter
        diameter = specs.get("diameter", "") or specs.get("each diameter", "")

        # Other attributes
        country_of_origin = specs.get("country of origin", "")
        warranty = specs.get("warranty", "")

        # Manufacturer
        manufacturer = response.css("span.sku a[id*='manufacturer']::text, span.manufacturer::text").get(default="").strip()
        if manufacturer.startswith("By:"):
            manufacturer = manufacturer[3:].strip()

        yield {
            "catalog_number": catalog_number,
            "product_name": product_name,
            "product_url": response.url,
            "image_link": image_link,
            "overview": overview,
            "length": length,
            "width": width,
            "height": height,
            "volume": volume,
            "diameter": diameter,
            "color": color,
            "material": material,
            "pattern": pattern,
            "country_of_origin": country_of_origin,
            "warranty": warranty,
            "item_number": item_number,
            "manufacturer": manufacturer,
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
            or "ignoring non-200 response" in error_text_lower
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

        if "/restaurant-supplies-equipment/" in request.url:
            payload["product_url"] = request.url
        else:
            payload["search_url"] = request.url

        yield payload
