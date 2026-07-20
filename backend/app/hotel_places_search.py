"""
hotel_places_search.py
----------------------
Google Places API (New) integration for hotel sentiment route.
Replaces the Selenium-based google_maps_scraper.py for the hotel sentiment flow only.

Uses:
- POST https://places.googleapis.com/v1/places:searchNearby
- Searches for "lodging" type within radius of origin coordinates
- Returns up to 20 places per call (API max), paginates via nextPageToken
  up to 100 results total
- Returns place name, address, rating, review count, Google Maps URL, lat/lng

Env vars required:
- GOOGLE_PLACES_API_KEY
"""

import os
import math
import logging
import requests
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

PLACES_API_KEY  = os.getenv("GOOGLE_PLACES_API_KEY", "")
NEARBY_ENDPOINT = "https://places.googleapis.com/v1/places:searchNearby"

# Fields we want back from Places API — only request what we need to minimise cost
FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.rating",
    "places.userRatingCount",
    "places.location",
    "places.googleMapsUri",
    "places.websiteUri",
    "places.nationalPhoneNumber",
])


def haversine_km(lat1, lng1, lat2, lng2) -> float:
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlng / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def search_luxury_hotels(
    origin_lat: float,
    origin_lng: float,
    radius_km: float = 5.0,
    limit: int = 100,
    establishment_name: str = "",
) -> List[Dict]:
    """
    Search Google Places API for hotels near origin_lat/lng within radius_km.
    Returns up to `limit` places formatted to match the existing place dict schema.

    Each returned dict has:
        name, address, rating, reviews, url, lat, lng,
        distance_km, within_radius, selected
    """
    if not PLACES_API_KEY:
        logger.error("[HOTEL PLACES] GOOGLE_PLACES_API_KEY not set")
        return []

    radius_m = min(radius_km * 1000, 50000)  # API max is 50,000m
    places   = []
    seen_ids = set()

    # Places API (New) max is 20 per call — paginate up to 5 pages = 100 results
    max_pages    = math.ceil(limit / 20)
    next_token   = None
    page         = 0

    while page < max_pages and len(places) < limit:
        body = {
            "includedTypes":      ["lodging"],
            "maxResultCount":     20,
            "locationRestriction": {
                "circle": {
                    "center": {
                        "latitude":  origin_lat,
                        "longitude": origin_lng,
                    },
                    "radius": radius_m,
                }
            },
            "rankPreference": "POPULARITY",
        }

        if next_token:
            body["pageToken"] = next_token

        headers = {
            "Content-Type":    "application/json",
            "X-Goog-Api-Key":  PLACES_API_KEY,
            "X-Goog-FieldMask": FIELD_MASK + ",nextPageToken",
        }

        try:
            resp = requests.post(NEARBY_ENDPOINT, json=body, headers=headers, timeout=15)
            if resp.status_code != 200:
                logger.error(f"[HOTEL PLACES] API error {resp.status_code}: {resp.text[:300]}")
                break

            data = resp.json()
            raw_places  = data.get("places", [])
            next_token  = data.get("nextPageToken")

            logger.info(f"[HOTEL PLACES] Page {page+1}: {len(raw_places)} places returned")

            for p in raw_places:
                place_id = p.get("id", "")
                if place_id in seen_ids:
                    continue
                seen_ids.add(place_id)

                name    = p.get("displayName", {}).get("text", "Unknown")
                address = p.get("formattedAddress", "")
                rating  = p.get("rating")
                reviews = p.get("userRatingCount", 0)
                url     = p.get("googleMapsUri", "")
                loc     = p.get("location", {})
                lat     = loc.get("latitude")
                lng     = loc.get("longitude")

                # Distance filter
                dist = None
                within = None
                if lat and lng:
                    dist   = round(haversine_km(origin_lat, origin_lng, lat, lng), 2)
                    within = dist <= radius_km

                # Skip if outside radius and we have coordinates
                if within is False:
                    continue

                places.append({
                    "name":            name,
                    "address":         address,
                    "rating":          rating,
                    "reviews":         reviews,
                    "url":             url,
                    "lat":             lat,
                    "lng":             lng,
                    "distance_km":     dist,
                    "within_radius":   within,
                    "selected":        True,
                    "place_id":        place_id,
                    "is_user_establishment": (
                        establishment_name.strip().lower() == name.strip().lower()
                    ),
                })

                if len(places) >= limit:
                    break

        except Exception as e:
            logger.error(f"[HOTEL PLACES] Request error: {e}")
            break

        page += 1
        if not next_token:
            break

    logger.info(f"[HOTEL PLACES] Total places found: {len(places)}")
    return places