import scrapy
import json
import os


class SteeliteUtopiaSpider(scrapy.Spider):
    name = "steelite-utopia"
    allowed_domains = ["www.steelite-utopia.com"]

    def __init__(self, *args, **kwargs):
        # Load catalog numbers from the incomplete JSON file
        json_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../incomplete_catalog_numbers.json'))
        try:
            with open(json_file, 'r') as f:
                self.catalog_numbers = json.load(f)
            
            # Filter out NaN and invalid entries
            self.catalog_numbers = [
                str(cat).strip() 
                for cat in self.catalog_numbers 
                if cat and str(cat).lower() != 'nan'
            ]
        except FileNotFoundError:
            self.logger.error(f"incomplete_catalog_numbers.json not found at {json_file}")
            self.catalog_numbers = []
        
        super().__init__(*args, **kwargs)
        self.logger.info(f"Loaded {len(self.catalog_numbers)} catalog numbers from incomplete_catalog_numbers.json")

    def start_requests(self):
        for catalog in self.catalog_numbers:
            url = f"https://www.steelite-utopia.com/products/{catalog}"
            yield scrapy.Request(
                url,
                meta={'playwright': True},
                callback=self.parse,
                errback=self.errback_parse
            )

    def errback_parse(self, failure):
        self.logger.error(f"Request failed: {failure.request.url} - {failure.value}")
        catalog_number = failure.request.url.split('/')[-1]
        yield {
            'catalog_number': catalog_number,
            'url': failure.request.url,
            'error': str(failure.value),
        }

    def parse(self, response):
        # Extract catalog number from URL
        catalog_number = response.url.split('/')[-1]
        
        # Check if page exists (404 or error)
        if response.status == 404:
            self.logger.warning(f"Product page not found: {response.url}")
            yield {
                'catalog_number': catalog_number,
                'error': 'Page not found (404)',
            }
            return
        
        try:
            # Extract product name/title
            product_name = response.css('h1.info-name::text').get()
            
            # Extract all image links
            image_links = response.css('div.info-image-outer img.info-image-inner::attr(src)').getall()
            image_links = [
                response.urljoin(img_link) if img_link and not img_link.startswith('http') else img_link
                for img_link in image_links
            ] if image_links else []
            
            # Extract overview
            overview = response.css('div.info-value::text').get()
            if overview:
                overview = overview.strip()
            
            # Extract product details from the info section
            details = {}
            # Try multiple selector patterns to be robust
            info_items = response.css('div.info-col1 div')
            for item in info_items:
                key = item.css('span.info-key::text').get()
                value = item.css('span.info-value::text').get()
                if key and value:
                    details[key.strip()] = value.strip()
            
            # Extract features/icons
            features = []
            icon_items = response.css('div.info-icon-outer')
            
            for icon_item in icon_items:
                feature_name = icon_item.css('div.info-icon-text::text').get()
                feature_tooltip = icon_item.css('::attr(data-title-right)').get()
                
                if feature_name:
                    features.append({
                        'name': feature_name.strip(),
                        'description': feature_tooltip.strip() if feature_tooltip else None,
                    })
            
            # Extract download links
            downloads = []
            download_items = response.css('div.info-downloads a.info-download, a.info-download')
            
            for download in download_items:
                download_name = download.css('div.info-download-name::text').get()
                download_size = download.css('div.info-download-size::text').get()
                download_url = download.css('::attr(href)').get()
                
                if download_url:
                    if not download_url.startswith('http'):
                        download_url = response.urljoin(download_url)
                    
                    downloads.append({
                        'name': download_name.strip() if download_name else 'Unknown',
                        'size': download_size.strip() if download_size else None,
                        'url': download_url,
                    })
            
            yield {
                'catalog_number': catalog_number,
                'product_name': product_name,
                'url': response.url,
                'image_links': image_links,
                'overview': overview,
                'details': details,
                'features': features,
                'downloads': downloads,
            }
            
            self.logger.info(f"Successfully scraped product: {catalog_number}")
            
        except Exception as e:
            self.logger.error(f"Error parsing product {catalog_number}: {str(e)}")
            yield {
                'catalog_number': catalog_number,
                'error': f'Parse error: {str(e)}',
                'url': response.url,
            }
