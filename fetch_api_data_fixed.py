#!/usr/bin/env python
import requests
import json
import re
import os
from pathlib import Path

def fetch_steelite_data():
    print("Fetching product data from https://www.steelite-utopia.com/data...")
    
    try:
        response = requests.get(
            'https://www.steelite-utopia.com/data',
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'},
            timeout=60
        )
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching data: {e}")
        return None
    
    if response.status_code != 200:
        print(f"Error: Got status {response.status_code}")
        return None
    
    # Extract JSON from JavaScript
    match = re.search(r'cfg=(\{.*\})', response.text, re.DOTALL)
    if not match:
        print("Error: Could not find JSON in response")
        return None
    
    try:
        data = json.loads(match.group(1))
        print(f"✓ Successfully fetched and parsed data")
        print(f"  Products available: {len(data.get('products', {}))}")
        return data
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        return None

def extract_product_data(product):
    images_count = product.get('images', 0)
    downloads = product.get('downloads', [])
    attributes = product.get('attributes', {})
    description = product.get('description', {})
    product_id = product.get('productId', '')
    
    # Handle description - it could be dict or list
    intro_text = ''
    if isinstance(description, dict):
        intro_text = description.get('intro', '')
    elif isinstance(description, list) and len(description) > 0:
        intro_text = description[0].get('intro', '') if isinstance(description[0], dict) else ''
    
    # Extract image links - images is a count, construct URLs
    image_links = []
    if isinstance(images_count, int) and images_count > 0:
        # Generate image URLs based on count
        for i in range(1, images_count + 1):
            # First image has no suffix, subsequent ones have -2, -3, etc.
            suffix = '' if i == 1 else f'-{i}'
            image_links.append(f'https://www.steelite-utopia.com/images/products/large/{product_id}{suffix}')
    
    # Extract downloads - downloads is an array of {name, size, link}
    download_list = []
    if isinstance(downloads, list):
        for dl_data in downloads:
            if isinstance(dl_data, dict):
                link = dl_data.get('link', dl_data.get('url', ''))
                # Convert relative URLs to absolute
                if link and not link.startswith('http'):
                    link = f'https://www.steelite-utopia.com{link}'
                download_list.append({
                    'name': dl_data.get('name', 'Unknown'),
                    'url': link,
                    'size': dl_data.get('size', None)
                })
    
    return {
        'catalog_number': str(product_id),
        'product_name': product.get('name', ''),
        'url': f"https://www.steelite-utopia.com/products/{product_id}",
        'description': intro_text,
        'image_links': image_links,
        'downloads': download_list,
        'attributes': attributes,
        'pack_size': product.get('packSize', None),
        'box_size': product.get('boxSize', None),
        'stock': product.get('stock', None),
    }

def main():
    # Load incomplete catalog numbers
    incomplete_file = 'incomplete_catalog_numbers.json'
    if not os.path.exists(incomplete_file):
        print(f"Error: {incomplete_file} not found")
        return False
    
    with open(incomplete_file, 'r') as f:
        incomplete_catalogs = json.load(f)
    
    # Convert to set of strings for faster lookup
    incomplete_set = set(str(cat).strip() for cat in incomplete_catalogs if cat and str(cat).lower() != 'nan')
    print(f"Looking for {len(incomplete_set)} incomplete catalogs...")
    
    # Fetch all data
    all_data = fetch_steelite_data()
    if not all_data:
        return False
    
    products = all_data.get('products', {})
    
    # Extract matching products
    results = []
    found = 0
    not_found = []
    
    for catalog_num in sorted(incomplete_set):
        if catalog_num in products:
            product_data = extract_product_data(products[catalog_num])
            results.append(product_data)
            found += 1
        else:
            not_found.append(catalog_num)
    
    # Save results
    output_file = 'steelite_utopia_products_from_api.json'
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n{'='*60}")
    print("RESULTS")
    print(f"{'='*60}")
    print(f"Total incomplete catalogs: {len(incomplete_set)}")
    print(f"Found in API: {found}")
    print(f"Not found: {len(not_found)}")
    print(f"Results saved to: {output_file}")
    
    # Show sample
    if results:
        sample = results[0]
        print(f"\nSample product:")
        print(f"  ID: {sample['catalog_number']}")
        print(f"  Name: {sample['product_name']}")
        print(f"  Images: {len(sample['image_links'])}")
        print(f"  Downloads: {len(sample['downloads'])}")
        if sample['description']:
            print(f"  Description: {sample['description'][:100]}...")
    
    if not_found and len(not_found) <= 10:
        print(f"\nNot found ({len(not_found)}):")
        for cat in not_found[:10]:
            print(f"  - {cat}")
    elif not_found:
        print(f"\nNot found: {len(not_found)} total")
    
    return True

if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)