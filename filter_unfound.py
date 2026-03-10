import json
import sys
from pathlib import Path

def filter_unfound(json_file):
    json_path = Path(json_file)
    if not json_path.exists():
        print(f"Error: File not found: {json_file}")
        sys.exit(1)
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    unfound = [item for item in data if item.get('found') is False]
    found = [item for item in data if item.get('found') is True]
    blocked = [item for item in unfound if item.get('blocked') is True]
    true_unfound = [item for item in unfound if item.get('blocked') is not True]
    
    print(f"\n{'='*70}")
    print(
        f"SUMMARY: {len(found)} FOUND | {len(unfound)} NOT FOUND "
        f"({len(blocked)} BLOCKED, {len(true_unfound)} TRUE NOT FOUND)"
    )
    print(f"{'='*70}\n")
    
    if blocked:
        print(f"Blocked Items ({len(blocked)}):")
        print("-" * 70)
        for item in blocked:
            searched = item.get('searched_catalog_number', 'N/A')
            error = item.get('error', 'No match found')
            print(f"  {searched:20} → {error}")

        blocked_file = json_path.parent / f"{json_path.stem}_blocked.json"
        with open(blocked_file, 'w', encoding='utf-8') as f:
            json.dump(blocked, f, indent=2)
        print(f"\nBlocked items saved to: {blocked_file}")

    if true_unfound:
        print(f"\nTrue NOT FOUND Items ({len(true_unfound)}):")
        print("-" * 70)
        for item in true_unfound:
            searched = item.get('searched_catalog_number', 'N/A')
            error = item.get('error', 'No match found')
            print(f"  {searched:20} → {error}")
        
        # Save unfound to separate file
        unfound_file = json_path.parent / f"{json_path.stem}_unfound.json"
        with open(unfound_file, 'w', encoding='utf-8') as f:
            json.dump(unfound, f, indent=2)
        print(f"\nUnfound items saved to: {unfound_file}")
    
    if found:
        print(f"\n\nItems FOUND ({len(found)}):")
        print("-" * 70)
        for item in found:
            searched = item.get('searched_catalog_number', 'N/A')
            product = item.get('product_name', 'N/A')
            print(f"  {searched:20} → {product}")
        
        # Save found to separate file
        found_file = json_path.parent / f"{json_path.stem}_found.json"
        with open(found_file, 'w', encoding='utf-8') as f:
            json.dump(found, f, indent=2)
        print(f"\nFound items saved to: {found_file}")

if __name__ == "__main__":
    # Default to drinkstuff.json
    json_file = "steelite/drinkstuff.json" if len(sys.argv) < 2 else sys.argv[1]
    filter_unfound(json_file)
