import pandas as pd
import re

# =====================================
# CONFIG
# =====================================
INPUT_FILE = "output.xlsx"  # Change to your file name
SHEET_NAME = 0                 # First sheet

# =====================================
# CLEAN NUMBER FUNCTION
# Converts scientific notation to digits
# =====================================
def clean_number(value):
    if pd.isna(value):
        return ""

    value = str(value).strip()

    try:
        if "E+" in value.upper() or "E-" in value.upper():
            value = str(int(float(value)))
    except Exception:
        pass

    return re.sub(r"\D", "", value)

# =====================================
# LOAD EXCEL
# =====================================
df = pd.read_excel(
    INPUT_FILE,
    sheet_name=SHEET_NAME,
    dtype=str
)

print(f"Loaded {len(df)} records")

# =====================================
# CLEAN COLUMN NAMES
# =====================================
df.columns = df.columns.str.strip()

# =====================================
# CLEAN AADHAAR / PHONE COLUMNS
# =====================================
for col in ["Aadhaar", "Aadhaar.1", "Phn. No."]:
    if col in df.columns:
        df[col] = df[col].apply(clean_number)

# =====================================
# CLEAN STUDENT ID
# =====================================
if "Student ID" in df.columns:
    df["Student ID"] = df["Student ID"].apply(clean_number)

# =====================================
# CLEAN DOB
# =====================================
df["DOB"] = pd.to_datetime(
    df["DOB"],
    errors="coerce",
    dayfirst=True
)

# =====================================
# CALCULATE AGE
# Change cutoff date if required
# =====================================
cutoff_date = pd.Timestamp.today()

df["Age"] = (
    (cutoff_date - df["DOB"]).dt.days / 365.25
)

# =====================================
# FIND DUPLICATE STUDENT IDs
# =====================================
duplicate_student_ids = df[
    df.duplicated(subset=["Student ID"], keep=False)
].sort_values("Student ID")

if len(duplicate_student_ids) > 0:
    duplicate_student_ids.to_csv(
        "duplicate_student_ids.csv",
        index=False
    )

    print(
        f"Duplicate Student IDs found: "
        f"{duplicate_student_ids['Student ID'].nunique()}"
    )

    print(
        "Saved -> duplicate_student_ids.csv"
    )
else:
    print("No duplicate Student IDs found")

# =====================================
# REMOVE DUPLICATES
# 1. Student ID
# 2. Name + Father + DOB
# =====================================
before_count = len(df)

df = df.drop_duplicates(
    subset=["Student ID"],
    keep="first"
)

if all(
    col in df.columns
    for col in ["Student Name", "Father's Name", "DOB"]
):
    df = df.drop_duplicates(
        subset=[
            "Student Name",
            "Father's Name",
            "DOB"
        ],
        keep="first"
    )

after_count = len(df)

print(
    f"Removed {before_count - after_count} duplicate rows"
)

# =====================================
# AGE GROUPS
# =====================================
under14 = df[
    (df["Age"] >= 8) &
    (df["Age"] < 14)
].copy()

under17 = df[
    (df["Age"] >= 14) &
    (df["Age"] < 17)
].copy()

under21 = df[
    (df["Age"] >= 17) &
    (df["Age"] < 21)
].copy()

# =====================================
# SAVE CSV FILES
# =====================================
under14.to_csv(
    "under14.csv",
    index=False,
    encoding="utf-8-sig"
)

under17.to_csv(
    "under17.csv",
    index=False,
    encoding="utf-8-sig"
)

under21.to_csv(
    "under21.csv",
    index=False,
    encoding="utf-8-sig"
)

# =====================================
# OPTIONAL VALIDATION REPORT
# =====================================
if "Aadhaar" in df.columns:
    df["Aadhaar_Length"] = (
        df["Aadhaar"]
        .astype(str)
        .str.len()
    )

if "Phn. No." in df.columns:
    df["Phone_Length"] = (
        df["Phn. No."]
        .astype(str)
        .str.len()
    )

df.to_csv(
    "cleaned_students.csv",
    index=False,
    encoding="utf-8-sig"
)

# =====================================
# SUMMARY
# =====================================
print("\n========== SUMMARY ==========")
print(f"Total after cleaning : {len(df)}")
print(f"Under 14             : {len(under14)}")
print(f"Under 17             : {len(under17)}")
print(f"Under 21             : {len(under21)}")

print("\nGenerated Files:")
print("  cleaned_students.csv")
print("  duplicate_student_ids.csv")
print("  under14.csv")
print("  under17.csv")
print("  under21.csv")