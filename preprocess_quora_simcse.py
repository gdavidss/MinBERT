import pandas as pd

# Load the dataset treating consecutive whitespaces as the delimiter
df = pd.read_csv('data/quora-dev.csv', sep='\t')

# Filter out entries where 'is_duplicate' equals 1
filtered_df = df[df['is_duplicate'] == 1.0]

# Save the filtered dataframe
# Since the original delimiter was irregular whitespace, we choose a standard one (e.g., tab) for the output file
filtered_df.to_csv('data/quora-dev-filtered.csv', sep='\t', index=False)

print("Filtered dataframe saved as filtered.csv")


"""
import csv

# Input and output file names
input_file = 'data/quora-dev.csv'
output_file = 'data/quora-dev-filtered.csv'

# Open the input CSV file for reading
with open(input_file, mode='r', newline='', encoding='utf-8') as infile:
    reader = csv.DictReader(infile, delimiter='\t')
     # Read the first row, which contains the column names
    headers = next(reader)
    
    # Print the column names
    print("Columns in the CSV file:", headers)
    # Open the output CSV file for writing
    with open(output_file, mode='w', newline='', encoding='utf-8') as outfile:
        # Use the fieldnames from the input file for the output file
        writer = csv.DictWriter(outfile, fieldnames=reader.fieldnames)
        writer.writeheader()

        # Iterate through each row of the input file
        for row in reader:
            # Check if the 'is_duplicate' column equals '1.0'
            if row['is_duplicate'] == '1.0':
                # Write the row to the output file
                writer.writerow(row)
"""