import pandas as pd
import json

# Read the Excel file
df = pd.read_excel('sources/STEELITE.xlsx')

# Get all columns from E onwards (column index 4 and beyond)
columns_from_e = df.iloc[:, 4:]

# Find rows where all columns from E onwards are blank/NaN
incomplete_rows = df[columns_from_e.isna().all(axis=1)]

# Get the Mfr Catalog No. from incomplete rows
incomplete_mfrs = incomplete_rows['Mfr Catalog No.'].tolist()

# Save to a JSON file
with open('incomplete_catalog_numbers_v0.8.json', 'w') as f:
    json.dump(incomplete_mfrs, f, indent=2)

print(f"Found {len(incomplete_mfrs)} manufacturers with no data in columns E onwards")
print(f"Saved to incomplete_catalog_numbers_v0.1.json\n")

# Print the results
if incomplete_mfrs:
    print("Incomplete Mfr Catalog Numbers:")
    for item in incomplete_mfrs:
        print(item)
else:
    print("No incomplete manufacturers found!")
