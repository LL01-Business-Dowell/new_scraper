"""
google_maps_scraper.py
----------------------
Google Places API (New) integration for finding competitor businesses.
Uses dynamic category expansion, spatial sub-grids, and Nearby/Text searches.
Includes structural competitor filtering (types, ratings, keywords, and volume).
"""

import os
import re
import time
import math
import logging
import requests
import urllib.parse
from typing import List, Dict, Optional, Callable

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY") or os.getenv("GOOGLE_PLACES_API_KEY")

# ── LOGICAL COMPETITOR FILTERING CONFIGURATION ────────────────────────────────

# Strict Place Types Allowed (Google Places API New)
ALLOWED_PRIMARY_TYPES = {
    "hotel", "resort_hotel"
}

# Excluded Place Types (Filters out malls, apartments, B&Bs, etc.)
DISALLOWED_TYPES = {
    "shopping_mall", "serviced_apartment", "extended_stay_lodging", 
    "bed_and_breakfast", "guest_house", "hostel", "motel"
}

# Regex patterns for non-competitor / budget / transit / non-hotel stays
EXCLUDED_NAME_PATTERNS = [
    r"\boyo\b", r"\btreebo\b", r"\bfabhotel\b", r"\bhostel\b", 
    r"\bpg\b", r"\btransit\b", r"\bapartment\b", r"\bsuites\b",
    r"\borb\b", r"\bmall\b", r"\bresidency\b", r"\bhomestay\b",
    r"\bpod\b", r"\bcapsule\b", r"\bguesthouse\b", r"\bguest house\b",
    r"\bdorm\b", r"\bmotel\b", r"\bbed & breakfast\b",r"\bginger\b", 
    r"\bibis\b", r"\bbeacon\b", r"\bhotel mumbai house\b",
    r"\boyo\b", r"\btreebo\b", r"\bfabhotel\b", r"\bhostel\b"
]


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Straight-line distance between two coordinates in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlng / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def _generate_subgrid_centers(lat: float, lng: float, radius_km: float) -> List[Dict[str, float]]:
    """Generates center + 8-point offset grid coordinates to guarantee full area saturation."""
    step = max(radius_km * 0.4, 2.5)  # Offset step in km
    lat_off = step / 111.0
    lng_off = step / (111.0 * math.cos(math.radians(lat)))

    return [
        {"lat": lat, "lng": lng},                           # Center
        {"lat": lat + lat_off, "lng": lng},                 # North
        {"lat": lat - lat_off, "lng": lng},                 # South
        {"lat": lat, "lng": lng + lng_off},                 # East
        {"lat": lat, "lng": lng - lng_off},                 # West
        {"lat": lat + lat_off, "lng": lng + lng_off},       # NE
        {"lat": lat + lat_off, "lng": lng - lng_off},       # NW
        {"lat": lat - lat_off, "lng": lng + lng_off},       # SE
        {"lat": lat - lat_off, "lng": lng - lng_off},       # SW
    ]


def _is_logical_competitor(
    place: Dict,
    target_rating: float = 4.8,
    min_reviews: int = 1500
) -> bool:
    """
    Logically evaluates if a place is a true luxury/upscale competitor.
    Filters out budget stays, non-hotels, malls, and small guesthouses.
    """
    name = place.get("displayName", {}).get("text", "") or place.get("name", "")
    name_lower = name.lower()
    primary_type = place.get("primaryType", "")
    place_types = set(place.get("types", []))
    rating = place.get("rating") or 0.0
    reviews = place.get("userRatingCount") or place.get("reviews") or 0

    # 1. Type Check: Disallow explicit non-hotel categories
    if primary_type in DISALLOWED_TYPES or any(t in DISALLOWED_TYPES for t in place_types):
        logger.debug(f"[COMPETITOR FILTER] Excluded '{name}' — Disallowed type: {primary_type}")
        return False

    # 2. Keyword Exclusion Check
    if any(re.search(pattern, name_lower, re.IGNORECASE) for pattern in EXCLUDED_NAME_PATTERNS):
        logger.debug(f"[COMPETITOR FILTER] Excluded '{name}' — Keyword pattern match")
        return False

    # 3. Minimum Review Volume Threshold (Eliminates tiny bed & breakfasts / low footprint)
    if reviews < min_reviews:
        logger.debug(f"[COMPETITOR FILTER] Excluded '{name}' — Low review count: {reviews} < {min_reviews}")
        return False

    # 4. Rating Quality Threshold (Keep comparable tier)
    if rating < 3.8 or abs(rating - target_rating) > 1.2:
        logger.debug(f"[COMPETITOR FILTER] Excluded '{name}' — Rating outlier: {rating}")
        return False

    return True


def _fetch_nearby_places(
    lat: float,
    lng: float,
    radius_km: float = 10.0,
    included_types: List[str] = None
) -> List[Dict]:
    """Executes Places API (New) Nearby Search using spatial bounding circles."""
    if not GOOGLE_PLACES_API_KEY:
        return []

    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,"
            "places.rating,places.userRatingCount,places.location,places.googleMapsUri,"
            "places.primaryType,places.types,places.priceLevel"
        )
    }

    types = included_types or ["hotel", "resort_hotel"]
    radius_m = min(float(radius_km * 1000.0), 50000.0)

    payload = {
        "includedTypes": types,
        "maxResultCount": 20,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": radius_m
            }
        }
    }

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=15)
        if res.status_code != 200:
            logger.error(f"[PLACES API] Nearby search failed ({res.status_code}): {res.text}")
            return []
        return res.json().get("places", [])
    except Exception as exc:
        logger.error(f"[PLACES API] Nearby search error: {exc}")
        return []


def _fetch_places_text_search(
    text_query: str,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    radius_km: float = 10.0,
) -> List[Dict]:
    """
    Calls Places API (New) Text Search with strict location restriction and valid v1 pagination.
    """
    if not GOOGLE_PLACES_API_KEY:
        return []

    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,"
            "places.rating,places.userRatingCount,places.location,places.googleMapsUri,"
            "places.primaryType,places.types,places.priceLevel,nextPageToken"
        )
    }

    fetched = []
    page_token = None

    while len(fetched) < 60:
        # Payload retains textQuery across pagination calls to comply with API v1
        payload = {
            "textQuery": text_query,
            "pageSize": 20
        }

        if page_token:
            payload["pageToken"] = page_token

        if lat is not None and lng is not None:
            radius_m = min(float(radius_km * 1000.0), 50000.0)
            payload["locationBias"] = {
                "circle": {
                    "center": {"latitude": lat, "longitude": lng},
                    "radius": radius_m
                }
            }

        try:
            res = requests.post(url, json=payload, headers=headers, timeout=15)
            if res.status_code != 200:
                logger.error(f"[PLACES API] Text query '{text_query}' failed ({res.status_code}): {res.text}")
                break

            data = res.json()
            places = data.get("places", [])
            fetched.extend(places)

            page_token = data.get("nextPageToken")
            if not page_token or not places:
                break

            time.sleep(1.5)

        except Exception as exc:
            logger.error(f"[PLACES API] Text search exception for query '{text_query}': {exc}")
            break

    return fetched


def search_google_maps_competitors(
    keyword: str,
    city: str,
    establishment_name: str,
    radius_km: float = 10,
    limit: int = 100,
    origin_lat: float = None,
    origin_lng: float = None,
    progress_callback: Optional[Callable] = None,
) -> List[Dict]:
    """Fetches up to `limit` unique, logically-filtered competitor establishments."""
    all_places = []
    seen_place_ids = set()

    def process_and_add(raw_places: List[Dict]):
        for p in raw_places:
            place_id = p.get("id")
            if not place_id or place_id in seen_place_ids:
                continue

            display_name = p.get("displayName", {}).get("text", "Unknown")

            # Exclude target hotel itself from competitors list
            if establishment_name and establishment_name.lower() in display_name.lower():
                continue

            # Apply Logical Competitor Filter
            if not _is_logical_competitor(p):
                continue

            seen_place_ids.add(place_id)

            location = p.get("location", {})
            plat = location.get("latitude")
            plng = location.get("longitude")
            rating = p.get("rating")
            reviews = p.get("userRatingCount", 0)

            maps_url = p.get("googleMapsUri") or (
                f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote_plus(display_name)}"
            )

            # Assign Competitor Tier based on review volume and rating standard
            tier = "Tier 1 (Direct Primary)" if (reviews >= 10000 and rating and rating >= 4.3) else "Tier 2 (Secondary)"

            all_places.append({
                "name": display_name,
                "address": p.get("formattedAddress", ""),
                "rating": rating,
                "reviews": reviews,
                "url": maps_url,
                "lat": plat,
                "lng": plng,
                "place_id": place_id,
                "primary_type": p.get("primaryType", "hotel"),
                "price_level": p.get("priceLevel", "UNKNOWN"),
                "competitor_tier": tier,
                "selected": True,
            })

    # Strategy 1: Spatial Grid Search
    if origin_lat is not None and origin_lng is not None:
        grid = _generate_subgrid_centers(origin_lat, origin_lng, radius_km)
        for idx, pt in enumerate(grid):
            if progress_callback:
                progress_callback(
                    min(50, int((idx / len(grid)) * 50)),
                    limit,
                    "Discovering nearby luxury hotels..."
                )

            nearby_raw = _fetch_nearby_places(pt["lat"], pt["lng"], radius_km)
            process_and_add(nearby_raw)

    # Strategy 2: Expanded Area Search targeting luxury/upscale categories
    search_terms = [
        f"Luxury Hotels in {city}",
        f"5 star hotels in {city}",
        f"4 star hotels in {city}",
        f"Boutique hotels in {city}",
        f"Resorts in {city}",
    ]

    for idx, term in enumerate(search_terms):
        if progress_callback:
            pct = 50 + min(45, int((idx / len(search_terms)) * 45))
            progress_callback(
                pct,
                limit,
                "Expanding search radius for direct competitors..."
            )

        text_raw = _fetch_places_text_search(term, origin_lat, origin_lng, radius_km)
        process_and_add(text_raw)

    # Calculate Distances & Filter strictly by radius_km using haversine_km
    filtered_places = []
    for place in all_places:
        plat = place.get("lat")
        plng = place.get("lng")
        if origin_lat is not None and origin_lng is not None and plat and plng:
            dist = haversine_km(origin_lat, origin_lng, plat, plng)
            place["distance_km"] = round(dist, 2)
            is_within = dist <= radius_km
            place["within_radius"] = is_within
            
            if is_within:
                filtered_places.append(place)
        else:
            place["distance_km"] = 0.0
            place["within_radius"] = True
            filtered_places.append(place)

    logger.info(f"[PLACES API] Competitor filtering complete. Yielded {len(filtered_places)} true competitors within {radius_km} km.")

    if progress_callback:
        progress_callback(100, limit, f"Found {len(filtered_places[:limit])} direct competitors matching your criteria.")

    return filtered_places[:limit]