import pandas as pd

# Paths to your CSV files
data_path = "data/FoodAccessData2019.csv"        # main data
lookup_path = "data/VariableLookup.csv"          # variable descriptions

# Load the main dataset
data_df = pd.read_csv(data_path)

# Load the variable lookup table
lookup_df = pd.read_csv(lookup_path)

# Quick sanity checks
print("Data shape:", data_df.shape)
print("Lookup shape:", lookup_df.shape)

print("\nFirst few rows of data:")
print(data_df.head())

print("\nFirst few rows of variable lookup:")
print(lookup_df.head())

def food_desert_score(row, state_median_income):
    # 1. Low income
    low_income = 1 if row["MedianFamilyIncome"] < state_median_income else 0

    # 2. Low access (binary)
    low_access = 1 if (row["LATracts_half"] == 1 or row["LATracts1"] == 1) else 0

    # 3. Vehicle access
    vehicle_issue = row["HUNVFlag"]  # already 0 or 1

    # 4. Distance severity (optional)
    distance = row.get("Distance_Miles", 0)
    distance_norm = min(distance / 10, 1)  # cap at 10 miles

    # Weights
    w1, w2, w3, w4 = 0.35, 0.40, 0.15, 0.10

    score = (
        w1 * low_income +
        w2 * low_access +
        w3 * vehicle_issue +
        w4 * distance_norm
    )

    return round(score * 100, 1)


def score_random_row():
    random_row = data_df.sample(1).iloc[0]

    print("Random row:")
    print(random_row)
    print("\n")

    state_median_income = data_df["MedianFamilyIncome"].median()

    score = food_desert_score(random_row, state_median_income)

    print(f"Food Desert Score for this tract: {score}")

