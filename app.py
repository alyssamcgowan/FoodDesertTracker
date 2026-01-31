from flask import Flask, request, jsonify
from google import genai
from dotenv import load_dotenv
import pandas as pd
import requests
import os
from flask_cors import CORS

load_dotenv()

app = Flask(__name__)
CORS(app)

# -----------------------------
# Gemini client
# -----------------------------
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# -----------------------------
# Load datasets once at startup
# -----------------------------
DATA_PATH = "data/cleanedFoodAccessData.csv"
LOOKUP_PATH = "data/VariableLookup.csv"
DATA_BY_COUNTY_PATH = "data/FoodAccessAtlasData_by_county.csv"

data_df = pd.read_csv(DATA_PATH)
lookup_df = pd.read_csv(LOOKUP_PATH)

# Simple in-memory cache: tract_id -> { score, explanation }
explanation_cache = {}

# Precompute state median income for heuristic
state_median_income = data_df["MedianFamilyIncome"].median()

# Food Desert Score Heuristic
def food_desert_score(row, state_median_income):
    low_income = 1 if row["MedianFamilyIncome"] < state_median_income else 0
    low_access = 1 if (row["LATracts_half"] == 1 or row["LATracts1"] == 1) else 0
    vehicle_issue = row["HUNVFlag"]
    distance = row.get("Distance_Miles", 0)
    distance_norm = min(distance / 10, 1)

    w1, w2, w3, w4 = 0.35, 0.40, 0.15, 0.10

    score = (
        w1 * low_income +
        w2 * low_access +
        w3 * vehicle_issue +
        w4 * distance_norm
    )

    return round(score * 100, 1)

# Geocode census tract lookup
def geocode_address(address):
    url = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
    params = {
        "address": address,
        "benchmark": "Public_AR_ACS2022",
        "vintage": "ACS2022_Current",
        "format": "json"
    }

    r = requests.get(url, params=params).json()
    matches = r.get("result", {}).get("addressMatches", [])

    if not matches:
        return None

    geos = matches[0].get("geographies", {})
    tracts = geos.get("Census Tracts", [])

    if not tracts:
        return None

    return tracts[0].get("TRACT")


import requests
import os

HUD_API_KEY = os.getenv("HUD_API_KEY")

def get_tracts_for_zip(zipcode):
    url = "https://www.huduser.gov/hudapi/public/usps"
    params = {
        "type": 1,              # 1 = ZIP → Tract crosswalk
        "query": str(zipcode)
    }
    headers = {
        "Authorization": f"Bearer {HUD_API_KEY}"
    }

    r = requests.get(url, headers=headers, params=params)
    data = r.json()

    # HUD wraps results inside data["data"]["results"]
    root = data.get("data")

    if not isinstance(root, dict):
        return {"error": "Unexpected HUD API format", "raw": data}

    results = root.get("results")
    if not isinstance(results, list):
        return {"error": "No results found", "raw": root}

    # Extract geoid values
    tracts = sorted({row["geoid"] for row in results})

    return {
        "zipcode": zipcode,
        "count": len(tracts),
        "tracts": tracts
    }


import numpy as np
import math

def make_json_safe(value):
    # Handle scalars
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        if math.isnan(value) or math.isinf(value):
            return None
        return float(value)
    if isinstance(value, (np.bool_, bool)):
        return bool(value)

    # Handle dicts
    if isinstance(value, dict):
        return {k: make_json_safe(v) for k, v in value.items()}

    # Handle lists
    if isinstance(value, list):
        return [make_json_safe(v) for v in value]

    # Everything else (strings, None, etc.)
    return value


# -----------------------------
# Routes
# -----------------------------
@app.route("/explain_address", methods=["POST"])
def explain_address():
    data = request.get_json()
    address = data.get("address", "")

    if not address:
        return jsonify({"error": "Address is required"}), 400

    # 1. Geocode
    tract = geocode_address(address)
    if not tract:
        return jsonify({"error": "Could not determine census tract"}), 404

    # 2. Lookup row in dataset
    row = data_df[data_df["CensusTract"] == int(tract)]
    if row.empty:
        return jsonify({"error": "Tract not found in dataset"}), 404

    row = row.iloc[0]

    # 3. Compute heuristic score
    score = food_desert_score(row, state_median_income)

    # 4. Prepare prompt for Gemini
    heuristic_description = """
    The heuristic evaluates food desert severity using:
    - Low income (MedianFamilyIncome < state median)
    - Low access (LATracts_half == 1 or LATracts1 == 1)
    - Vehicle access issues (HUNVFlag)
    - Distance severity (Distance_Miles normalized to 0–1)
    Weighted as: 0.35*income + 0.40*access + 0.15*vehicles + 0.10*distance.
    Score is 0–100.
    """

    prompt = f"""
    You are analyzing food access for a census tract.

    Address: {address}
    Census tract: {tract}

    Heuristic used:
    {heuristic_description}

    Row of data:
    {row.to_dict()}

    Variable lookup table:
    {lookup_df.to_dict(orient='records')}

    Food desert score for this tract: {score}

    Explain this score in clear, human-friendly language.
    Highlight which factors contributed most and why.
    """

    # 5. Call Gemini
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        explanation = response.text
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # 6. Return everything
    return jsonify({
        "address": address,
        "tract": tract,
        "score": score,
        "row": row.to_dict(),
        "explanation": explanation
    })



@app.route("/random_tract", methods=["GET"])
def random_tract():
    # 1. Pick a random row
    row = data_df.sample(1).iloc[0]
    tract = int(row.get("CensusTract"))

    # 2. If cached, return immediately
    if tract in explanation_cache:
        cached_entry = explanation_cache[tract]
        return jsonify({
            "tract": tract,
            "score": cached_entry["score"],
            "row": row.to_dict(),
            "explanation": cached_entry["explanation"],
            "cached": True
        })

    # 3. Compute score
    score = food_desert_score(row, state_median_income)

    # 4. Build heuristic description
    heuristic_description = """
    The heuristic evaluates food desert severity using:
    - Low income (MedianFamilyIncome < state median)
    - Low access (LATracts_half == 1 or LATracts1 == 1)
    - Vehicle access issues (HUNVFlag)
    - Distance severity (Distance_Miles normalized to 0–1)
    Weighted as: 0.35*income + 0.40*access + 0.15*vehicles + 0.10*distance.
    Score is 0–100.
    """

    # # 5. Build Gemini prompt
    # prompt = f"""
    # You are analyzing food access for a census tract.

    # Heuristic used:
    # {heuristic_description}

    # Row of data:
    # {row.to_dict()}

    # Variable lookup table:
    # {lookup_df.to_dict(orient='records')}

    # Food desert score for this tract: {score}

    # Explain this score in clear, human-friendly language.
    # Highlight which factors contributed most and why.
    # """

    # # 6. Call Gemini
    # try:
    #     response = client.models.generate_content(
    #         model="gemini-2.0-flash",
    #         contents=prompt
    #     )
    #     explanation = response.text
    # except Exception as e:
    #     return jsonify({"error": str(e)}), 500

    # # 7. Store in cache
    # explanation_cache[tract] = {
    #     "score": score,
    #     "explanation": explanation
    # }

    # 8. Return response
    return jsonify({
        "tract": tract,
        "score": score,
        "row": row.to_dict(),
        # "explanation": explanation,
        "cached": False
    })

@app.route("/score/<tract_id>", methods=["GET"])
def score_for_tract(tract_id):
    try:
        tract_int = int(tract_id)
    except ValueError:
        return jsonify({"error": "Invalid tract ID"}), 400

    # 1. Lookup row
    row = data_df[data_df["CensusTract"] == tract_int]
    if row.empty:
        return jsonify({"error": "Tract not found in dataset"}), 404

    row = row.iloc[0]

    # 2. Compute score
    score = food_desert_score(row, state_median_income)

    # 3. Convert row to JSON-safe dict
    row_dict = make_json_safe(row.to_dict())

    # 4. Return result
    return jsonify({
        "tract": tract_int,
        "score": score,
        "row": row_dict
    })

@app.route("/score_county/<county_name>", methods=["GET"])
def score_for_county(county_name):

    # 1. Lookup row
    row = data_df[data_df["County"] == county_name]
    if row.empty:
        return jsonify({"error": "County not found in dataset"}), 404

    row = row.iloc[0]

    # 2. Compute score
    score = food_desert_score(row, state_median_income)

    # 3. Convert row to JSON-safe dict
    row_dict = make_json_safe(row.to_dict())

    return jsonify({
        "county": county_name,
        "score": score,
        "row": row_dict
    })

@app.route("/tracts_for_zip/<zipcode>", methods=["GET"])
def tracts_for_zip(zipcode):
    tracts = get_tracts_for_zip(zipcode)

    if tracts is None:
        return jsonify({"error": "No data returned from HUD API"}), 500

    return jsonify({
        "zipcode": zipcode,
        "tracts": tracts,
        "count": len(tracts)
    })

@app.route("/score_for_zip/<zipcode>", methods=["GET"])
def score_for_zip(zipcode):
    # 1. Get tracts for this ZIP
    result = get_tracts_for_zip(zipcode)

    # Handle HUD API errors
    if "error" in result:
        return jsonify({"error": result["error"]}), 500

    tracts = result.get("tracts", [])
    if not tracts:
        return jsonify({"error": "No tracts found for this ZIP"}), 404

    # 2. Take the first tract
    first_tract = tracts[0]

    # Convert to int if needed
    try:
        tract_int = int(first_tract)
    except ValueError:
        return jsonify({"error": f"Invalid tract format: {first_tract}"}), 500

    # 3. Lookup row in your dataset
    row = data_df[data_df["CensusTract"] == tract_int]
    if row.empty:
        return jsonify({"error": "Tract not found in dataset"}), 404

    row = row.iloc[0]

    # 4. Compute score
    score = food_desert_score(row, state_median_income)

    # 5. Make row JSON-safe
    row_dict = make_json_safe(row.to_dict())

    # 6. Return result
    response = {
        "zipcode": zipcode,
        "tract": tract_int,
        "score": score,
        "row": row_dict
    }

    return jsonify(make_json_safe(response))


if __name__ == "__main__":
    app.run(debug=True)