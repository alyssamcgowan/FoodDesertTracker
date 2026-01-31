import pandas as pd

# Load the original tract-level dataset
DATA_PATH = "data/FoodAccessData2019.csv"
df = pd.read_csv(DATA_PATH)

# Columns used in your heuristic
required_columns = [
    "MedianFamilyIncome",
    "LATracts_half",
    "LATracts1",
    "HUNVFlag",
    "Distance_Miles"   # include only if present in your dataset
]

# Keep only columns that actually exist
required_columns = [c for c in required_columns if c in df.columns]

# Identify the county identifier column
# Most Food Access Atlas datasets use: County, CountyFIPS, or CountyCode
# Adjust this if your dataset uses a different name
county_col = "County" if "County" in df.columns else "CountyFIPS"

# Drop rows missing required attributes
clean_df = df.dropna(subset=required_columns)

# Build an aggregated county-level dataset
# Choose aggregation rules that make sense for each variable
aggregations = {
    "MedianFamilyIncome": "median",     # median income across tracts
    "LATracts_half": "sum",             # number of low-access tracts
    "LATracts1": "sum",
    "HUNVFlag": "mean",                 # average share of households without vehicles
}

# Add Distance_Miles if present
if "Distance_Miles" in clean_df.columns:
    aggregations["Distance_Miles"] = "mean"

county_df = clean_df.groupby(county_col).agg(aggregations).reset_index()

print("County-level dataset created:")
print(county_df.head())

# Optional: save to CSV
county_df.to_csv("data/FoodAccessAtlasData_by_county.csv", index=False)