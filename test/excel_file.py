import pandas as pd
import random
import argparse
from pathlib import Path

# Generate random 12-digit number
def generate_12_digit():
    return str(random.randint(10**11, 10**12 - 1))

# Generate random 10-digit Indian mobile number
def generate_mobile():
    return str(random.randint(6000000000, 9999999999))

parser = argparse.ArgumentParser(description="Add random Aadhaar and mobile values to a student workbook.")
parser.add_argument(
    "input_file",
    nargs="?",
    default="Students_data.xlsx",
    help="Input Excel workbook (default: Students_data.xlsx)",
)
parser.add_argument(
    "-o",
    "--output",
    default="Students_data121212.xlsx",
    help="Output Excel workbook (default: Students_data121212.xlsx)",
)
args = parser.parse_args()

input_path = Path(args.input_file).expanduser()
if not input_path.is_file():
    raise FileNotFoundError(
        f"Input workbook not found: {input_path}\n"
        "Place the workbook in the current folder or pass its path as the first argument."
    )

df = pd.read_excel(input_path)

# Add random columns
df["Random_12_Digit"] = [generate_12_digit() for _ in range(len(df))]
df["Random_Mobile"] = [generate_mobile() for _ in range(len(df))]

# Save
df.to_excel(args.output, index=False)

print(df[["Student Name", "Random_12_Digit", "Random_Mobile"]].head())