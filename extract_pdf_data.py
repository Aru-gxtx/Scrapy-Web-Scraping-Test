import os
import json
import requests
import re
from pathlib import Path

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False
    print("Warning: pdfplumber not installed. Install with: pip install pdfplumber")


class PDFDataExtractor:
    def __init__(self, output_dir='pdf_data'):
        self.output_dir = output_dir
        Path(self.output_dir).mkdir(exist_ok=True)
    
    def download_pdf(self, url, filename):
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            filepath = os.path.join(self.output_dir, filename)
            with open(filepath, 'wb') as f:
                f.write(response.content)
            return filepath
        except Exception as e:
            print(f"Error downloading PDF from {url}: {str(e)}")
            return None
    
    def extract_dimensions_from_pdf(self, pdf_path):
        if not HAS_PDFPLUMBER:
            return None
        
        try:
            dimensions = {
                'length': None,
                'width': None,
                'height': None,
                'capacity': None,
                'dimension_unit': 'mm',
                'capacity_unit': 'ml',
            }
            
            with pdfplumber.open(pdf_path) as pdf:
                # Extract text from all pages
                full_text = ''
                for page in pdf.pages:
                    full_text += page.extract_text() or ''

                length_match = re.search(r'[Ll]ength\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*mm', full_text)
                if length_match:
                    dimensions['length'] = float(length_match.group(1))
                
                width_match = re.search(r'[Ww]idth\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*mm', full_text)
                if width_match:
                    dimensions['width'] = float(width_match.group(1))
                
                height_match = re.search(r'[Hh]eight\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*mm', full_text)
                if height_match:
                    dimensions['height'] = float(height_match.group(1))
                
                capacity_match = re.search(r'[Cc]apacity\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*(?:ml|cc|oz)', full_text)
                if capacity_match:
                    dimensions['capacity'] = float(capacity_match.group(1))
                
                return dimensions if any(dimensions[k] is not None for k in ['length', 'width', 'height', 'capacity']) else None
        
        except Exception as e:
            print(f"Error extracting PDF data from {pdf_path}: {str(e)}")
            return None
    
    def process_scraped_data(self, json_file):
        if not os.path.exists(json_file):
            print(f"File not found: {json_file}")
            return
        
        with open(json_file, 'r') as f:
            scraped_items = json.load(f)
        
        # Process each item
        for item in scraped_items:
            catalog_number = item.get('catalog_number')
            downloads = item.get('downloads', [])
            
            # Find datasheet PDF
            for download in downloads:
                if 'datasheet' in download.get('name', '').lower():
                    pdf_url = download.get('url')
                    
                    # Download PDF
                    filename = f"{catalog_number}_datasheet.pdf"
                    pdf_path = self.download_pdf(pdf_url, filename)
                    
                    if pdf_path and os.path.exists(pdf_path):
                        # Extract dimensions
                        dimensions = self.extract_dimensions_from_pdf(pdf_path)
                        if dimensions:
                            item['pdf_dimensions'] = dimensions
                            print(f"Extracted dimensions for {catalog_number}: {dimensions}")
        
        # Save updated data
        output_file = json_file.replace('.json', '_with_pdf_data.json')
        with open(output_file, 'w') as f:
            json.dump(scraped_items, f, indent=2)
        
        print(f"Saved processed data to {output_file}")


if __name__ == '__main__':
    # This script can be run to extract PDF data after scraping
    extractor = PDFDataExtractor()
    
    # Define your scraped JSON file here
    scraped_file = 'steelite_utopia_products.json'  # Change this to your actual file
    
    if os.path.exists(scraped_file):
        print(f"Processing {scraped_file}...")
        extractor.process_scraped_data(scraped_file)
    else:
        print(f"Please run the spider first to generate {scraped_file}")
        print("Command: scrapy crawl steelite-utopia -o steelite_utopia_products.json")
