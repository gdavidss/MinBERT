import pandas as pd
import random

# Set a seed for reproducibility
random.seed(42)

# Load the CSV file without setting an index column
file_path = 'quora-train.csv'  # Make sure to put the correct path to your file
df = pd.read_csv(file_path, sep='\t')

# Shuffle the sentences in 'sentence2'
shuffled_sentences = df['sentence2'].sample(frac=1).reset_index(drop=True)

# Insert 'sentence3' as the third column, containing shuffled sentences from 'sentence2'
df.insert(4, 'sentence3', shuffled_sentences)

# Save the modified DataFrame to a new CSV file without writing the index
df.to_csv('quora-train-filtered.csv', sep='\t', index=False)

print("File saved as 'quora-train_modified.csv' without creating an 'Unnamed: 0' column, preserving 'id', and with 'sentence3' as the third column.")
