#!/usr/bin/env python
import os
import sys
import json
from pathlib import Path

def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")

def print_step(num, text):
    print(f"[Step {num}] {text}")

def main():
    print_header("STEELITE-UTOPIA WEB SCRAPER - QUICK START")
    
    # Step 1: Check incomplete_catalog_numbers.json
    print_step(1, "Checking for incomplete_catalog_numbers.json...")
    
    if not os.path.exists('incomplete_catalog_numbers.json'):
        print("  ✗ File not found!")
        print("\n  Run this first:")
        print("  $ python find_incomplete_mfrs.py")
        return 1
    
    # Count items
    with open('incomplete_catalog_numbers.json', 'r') as f:
        catalogs = json.load(f)
    
    # Filter valid catalogs
    valid_catalogs = [
        c for c in catalogs 
        if c and str(c).lower() != 'nan'
    ]
    
    print(f"  ✓ Found incomplete_catalog_numbers.json")
    print(f"  ✓ Total catalogs: {len(catalogs)}")
    print(f"  ✓ Valid catalogs: {len(valid_catalogs)}")
    
    # Step 2: Check spider exists
    print_step(2, "Checking spider setup...")
    
    spider_file = 'steelite/steelite/spiders/steelite_utopia.py'
    if not os.path.exists(spider_file):
        print("  ✗ Spider not found!")
        return 1
    
    print(f"  ✓ Spider found: {spider_file}")
    
    # Step 3: Check dependencies
    print_step(3, "Checking dependencies...")
    
    try:
        import scrapy
        print(f"  ✓ Scrapy {scrapy.__version__} installed")
    except ImportError:
        print("  ✗ Scrapy not installed")
        print("    Run: pip install scrapy")
        return 1
    
    # Step 4: Run options
    print_header("READY TO SCRAPE")
    print("Choose an option:\n")
    print("1. Run spider (interactive)")
    print("2. Run spider (non-interactive, full dataset)")
    print("3. Run spider (test mode, first 10 items)")
    print("4. Just show stats")
    print("5. Exit\n")
    
    choice = input("Select option (1-5): ").strip()
    
    if choice == '5':
        print("Exiting...")
        return 0
    
    if choice == '4':
        print_step(1, "Statistics")
        print(f"Total incomplete catalogs: {len(valid_catalogs)}")
        print(f"Spider location: {spider_file}")
        print(f"Output will be: steelite_utopia_products.json")
        return 0
    
    if choice in ['1', '2', '3']:
        import subprocess
        
        os.chdir('steelite')
        
        output_file = '../steelite_utopia_products.json'
        
        if choice == '3':
            print("\nTest mode: scraping only first 10 items")
            print("    Edit incomplete_catalog_numbers.json to limit items\n")
        
        print_step(1, f"Running spider (output: {output_file})")
        print("This may take a while depending on number of catalogs...\n")
        
        # Use Python 3.12 where Scrapy is installed
        python_exe = r"C:\Users\admin\AppData\Local\Programs\Python\Python312\python.exe"
        if not os.path.exists(python_exe):
            python_exe = sys.executable
        
        cmd = [
            python_exe, '-m', 'scrapy', 'crawl', 'steelite-utopia',
            '-o', output_file,
        ]
        
        try:
            result = subprocess.run(cmd, check=True)
            
            # Check if output file was created
            if os.path.exists(output_file):
                with open(output_file, 'r') as f:
                    items = json.load(f)
                
                print_header("SCRAPING COMPLETE!")
                print(f"✓ Successfully scraped {len(items)} items")
                
                successful = sum(1 for item in items if 'error' not in item)
                failed = len(items) - successful
                
                print(f"  Successful: {successful}")
                print(f"  Failed: {failed}")
                
                # Show sample
                if successful > 0:
                    sample = next(item for item in items if 'error' not in item)
                    print(f"\nSample product (ID: {sample.get('catalog_number')}):")
                    print(f"  Name: {sample.get('product_name')}")
                    print(f"  Image: {sample.get('image_link')}")
                    print(f"  Downloads: {len(sample.get('downloads', []))}")
            else:
                print("✗ Output file not created")
                return 1
        
        except subprocess.CalledProcessError as e:
            print(f"✗ Spider failed: {e}")
            return 1
    else:
        print("Invalid option")
        return 1
    
    # Final options
    print("\nNext steps:")
    print("1. Extract PDF data:")
    print("   $ python extract_pdf_data.py")
    print("2. Analyze data:")
    print("   $ python -c \"import pandas as pd; df = pd.read_json('steelite_utopia_products.json'); print(df.describe())\"")
    print("3. View documentation:")
    print("   $ cat STEELITE_SPIDER_README.md")
    
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)
