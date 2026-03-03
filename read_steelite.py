import pandas as pd
import json

# Read the Excel file and get Column B
df = pd.read_excel('sources/STEELITE.xlsx')
mfr_catalog_numbers = df['Mfr Catalog No.'].tolist()

# Save to a JSON file for the spider to use
with open('catalog_numbers.json', 'w') as f:
    json.dump(mfr_catalog_numbers, f, indent=2)

print(f"Saved {len(mfr_catalog_numbers)} catalog numbers to catalog_numbers.json")

# Print the results
for item in mfr_catalog_numbers:
    print(item)