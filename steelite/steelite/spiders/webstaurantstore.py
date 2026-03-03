import scrapy
import json
import os


class WebstaurantstoreSpider(scrapy.Spider):
    name = "webstaurantstore"
    allowed_domains = ["www.webstaurantstore.com"]

    def __init__(self, *args, **kwargs):
        # Load catalog numbers from the JSON file
        json_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../catalog_numbers.json'))
        try:
            with open(json_file, 'r') as f:
                self.catalog_numbers = json.load(f)
            # Limit to first 10 for testing
            self.catalog_numbers = self.catalog_numbers
            # Generate URLs for each catalog number
            self.start_urls = [f"https://www.webstaurantstore.com/search/{catalog}.html" for catalog in self.catalog_numbers]
        except FileNotFoundError:
            self.logger.error(f"catalog_numbers.json not found at {json_file}")
            self.catalog_numbers = []
            self.start_urls = []
        
        super().__init__(*args, **kwargs)
        self.logger.info(f"Loaded {len(self.catalog_numbers)} catalog numbers")

    def parse(self, response):
        # Extract the search catalog number from the URL
        search_catalog = response.url.split('/')[-1].split('.')[0]
        
        # Get all product containers
        products = response.css('div.product-box-container')
        
        for product in products:
            # Extract item number
            item_number = product.css('::attr(data-item-number)').get()
            
            # Extract product name
            product_name = product.css('span[data-testid="itemDescription"]::text').get()
            
            # Extract URL
            url = product.css('a[data-testid="itemLink"]::attr(href)').get()
            if url and not url.startswith('http'):
                url = response.urljoin(url)
            
            # Follow the product link to get detailed information
            if url:
                yield scrapy.Request(
                    url,
                    callback=self.parse_product_detail,
                    meta={
                        'catalog_number': search_catalog,
                        'item_number': item_number,
                        'product_name': product_name,
                    }
                )
        
        self.logger.info(f"Found {len(products)} products on {response.url}")

    def parse_product_detail(self, response):
        # Get metadata from search results
        catalog_number = response.meta['catalog_number']
        item_number = response.meta['item_number']
        product_name = response.meta['product_name']
        
        # Extract image link
        image_link = response.css('img#GalleryImage::attr(src)').get()
        
        # Extract overview/features (bullet points)
        overview = response.css('ul.m-0.mb-5.list-none li span::text').getall()
        
        # Extract specifications from the dl structure
        specs = {}
        spec_dts = response.css('dl#tbSpecSheetRows dt')
        spec_dds = response.css('dl#tbSpecSheetRows dd')
        
        for dt, dd in zip(spec_dts, spec_dds):
            key = dt.css('::text').get()
            # Handle values that might have multiple spans/text nodes
            value_parts = dd.css('::text').getall()
            value = ' '.join([part.strip() for part in value_parts if part.strip()])
            if key:
                specs[key.strip()] = value
        
        yield {
            'catalog_number': catalog_number,
            'item_number': item_number,
            'product_name': product_name,
            'url': response.url,
            'image_link': image_link,
            'overview': overview,
            'specifications': specs,
        }
        
        self.logger.info(f"Scraped detailed product info for {item_number}")
