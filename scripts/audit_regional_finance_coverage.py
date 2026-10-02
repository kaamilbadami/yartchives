#!/usr/bin/env python3
"""Audit regional coverage for finance internships."""

import json
import math
import sys
from pathlib import Path

def haversine(lat1, lon1, lat2, lon2):
    R = 3959.0 # miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def get_coordinates(geo_data, location_str):
    # Try to match "City, State"
    parts = location_str.split(",")
    if len(parts) == 2:
        city = parts[0].strip().lower()
        state = parts[1].strip().upper()
        # Find in cities array: [state, city, lat, lon]
        for c in geo_data.get("cities", []):
            if c[0] == state and c[1] == city:
                return c[2], c[3]
    return None

def main():
    listings_path = Path("data/listings.json")
    geo_path = Path("assets/geo.json")

    if not listings_path.exists() or not geo_path.exists():
        print("Missing data files.", file=sys.stderr)
        return 1

    with open(listings_path) as f:
        listings = json.load(f)

    with open(geo_path) as f:
        geo = json.load(f)

    # Benchmarks
    benchmarks = {
        "Baltimore/Bel Air, MD": (39.5359, -76.3483), # Bel Air, MD
        "Washington, DC": (38.8951, -77.0364),
        "New York, NY": (40.7128, -74.0060),
        "Chicago, IL": (41.8781, -87.6298),
        "San Francisco, CA": (37.7749, -122.4194),
        "Atlanta, GA": (33.7490, -84.3880),
        "Charlotte, NC": (35.2271, -80.8431),
    }

    finance_jobs = []
    for job in listings.get("jobs", []):
        profiles = job.get("profiles", [])
        if "finance-econ" in profiles:
            finance_jobs.append(job)

    print("# Finance Internship Regional Coverage Audit\n")
    print(f"Total finance-econ jobs nationally: {len(finance_jobs)}\n")

    print("## Regional Coverage (within 50 miles)\n")
    for name, (lat, lon) in benchmarks.items():
        count = 0
        for job in finance_jobs:
            loc = job.get("location", "")
            coords = get_coordinates(geo, loc)
            if coords:
                j_lat, j_lon = coords
                dist = haversine(lat, lon, j_lat, j_lon)
                if dist <= 50:
                    count += 1
        print(f"- **{name}**: {count} jobs")
    return 0

if __name__ == "__main__":
    sys.exit(main())
