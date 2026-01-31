import geopandas as gpd

# Load 2020 ZCTA and tract shapefiles
zcta = gpd.read_file("tl_2020_us_zcta520.shp")
tracts = gpd.read_file("tl_2020_us_tract.shp")

# Pick your ZIP
zip_code = "20001"
zcta_geom = zcta[zcta["ZCTA5CE20"] == zip_code]

# Spatial join
joined = gpd.sjoin(tracts, zcta_geom, how="inner", predicate="intersects")

# List of tract GEOIDs
tract_list = joined["GEOID"].tolist()
print(tract_list)