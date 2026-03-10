#!/usr/bin/env python
import os
import sys
import json
import subprocess
from pathlib import Path

def run_spider(output_file='steelite_utopia_products.json', skip_first=0, limit=None):
    spider_name = 'steelite-utopia'
    
    # Change to spider directory
    spider_dir = os.path.join(os.path.dirname(__file__), 'steelite')
    original_dir = os.getcwd()
    
    if not os.path.exists(spider_dir):
        print(f"Error: Spider directory not found at {spider_dir}")
        return False
    
    os.chdir(spider_dir)
    
    # Use Python 3.12 where Scrapy is installed
    python_exe = r"C:\Users\admin\AppData\Local\Programs\Python\Python312\python.exe"
    if not os.path.exists(python_exe):
        python_exe = sys.executable  # Fallback to system python
    
    # Build command
    cmd = [
        python_exe, '-m', 'scrapy', 'crawl', spider_name,
        '-o', output_file,
        '--nolog',  # Disable logging for cleaner output
    ]
    
    print(f"Running spider: {spider_name}")
    print(f"Output file: {output_file}")
    print(f"Command: {' '.join(cmd)}\n")
    
    try:
        result = subprocess.run(cmd, check=True)
        
        # Go back to original directory to check output file
        os.chdir(original_dir)
        output_path = os.path.join(spider_dir, output_file)
        
        if os.path.exists(output_path):
            print(f"\n✓ Spider completed successfully!")
            print(f"Results saved to: {output_path}")
            return True
        else:
            print(f"\n✗ Spider reported success but no output file found at: {output_path}")
            return False
    except subprocess.CalledProcessError as e:
        os.chdir(original_dir)
        print(f"✗ Spider failed with error: {str(e)}")
        return False
    except Exception as e:

        os.chdir(original_dir)
        print(f"✗ Error running spider: {str(e)}")
        return False
def extract_pdf_data(json_file):
    try:
        from extract_pdf_data import PDFDataExtractor
    except ImportError:
        print("The extract_pdf_data module is not available")
        return False
    
    print(f"\nProcessing PDF data from {json_file}...")
    
    try:
        # Install pdfplumber if not already installed
        try:
            import pdfplumber
        except ImportError:
            print("Installing pdfplumber for PDF processing...")
            python_exe = r"C:\Users\admin\AppData\Local\Programs\Python\Python312\python.exe"
            if not os.path.exists(python_exe):
                python_exe = sys.executable
            subprocess.run([python_exe, '-m', 'pip', 'install', 'pdfplumber', '-q'], check=True)
        
        extractor = PDFDataExtractor()
        extractor.process_scraped_data(json_file)
        print("✓ PDF data extraction completed!")
        return True
    except Exception as e:
        print(f"✗ PDF extraction failed: {str(e)}")
        return False

def display_stats(json_file):
    if not os.path.exists(json_file):
        print(f"Error: Output file not found: {json_file}")
        return
    
    with open(json_file, 'r') as f:
        items = json.load(f)
    
    print(f"\n{'='*60}")
    print("SCRAPING STATISTICS")
    print(f"{'='*60}")
    print(f"Total items scraped: {len(items)}")
    
    # Count successful vs failed items
    successful = sum(1 for item in items if 'error' not in item)
    failed = len(items) - successful
    
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    
    # Count items with each field
    has_image = sum(1 for item in items if item.get('image_link'))
    has_overview = sum(1 for item in items if item.get('overview'))
    has_details = sum(1 for item in items if item.get('details'))
    has_features = sum(1 for item in items if item.get('features'))
    has_downloads = sum(1 for item in items if item.get('downloads'))
    has_pdf_dimensions = sum(1 for item in items if item.get('pdf_dimensions'))
    
    print(f"\nField Coverage:")
    print(f"  Image links: {has_image}")
    print(f"  Overview: {has_overview}")
    print(f"  Details: {has_details}")
    print(f"  Features: {has_features}")
    print(f"  Downloads: {has_downloads}")
    print(f"  PDF Dimensions: {has_pdf_dimensions}")
    
    # Show sample item
    if successful > 0:
        sample = next(item for item in items if 'error' not in item)
        print(f"\nSample Item (Catalog: {sample.get('catalog_number')}):")
        print(json.dumps(sample, indent=2)[:500] + "...")
    
    print(f"{'='*60}\n")

def main():
    print(f"{'='*60}")
    print("STEELITE-UTOPIA WEB SCRAPER")
    print(f"{'='*60}\n")
    
    # Check if incomplete_catalog_numbers.json exists
    if not os.path.exists('incomplete_catalog_numbers.json'):
        print("Error: incomplete_catalog_numbers.json not found!")
        print("Please run: python find_incomplete_mfrs.py")
        return
    
    # Run spider
    output_file = 'steelite_utopia_products.json'
    if run_spider(output_file):
        # Display stats
        # Construct full path to output file (it's in steelite subdirectory)
        output_path = os.path.join('steelite', output_file)
        display_stats(output_path)
        
        # Ask about PDF extraction
        response = input("Would you like to extract data from PDF datasheets? (y/n): ").strip().lower()
        if response == 'y':
            extract_pdf_data(output_path)
    else:
        print("\nSpider execution failed. Please check the error above.")

if __name__ == '__main__':
    main()
