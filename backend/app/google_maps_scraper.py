"""
google_maps_scraper.py
----------------------
Google Places API (New) integration for finding competitor businesses.
Uses dynamic category expansion, spatial sub-grids, and Nearby/Text searches.
"""

import os
import time
import math
import logging
import requests
import urllib.parse
from typing import List, Dict, Optional, Callable

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY") or os.getenv("GOOGLE_PLACES_API_KEY")


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
            "places.rating,places.userRatingCount,places.location,places.googleMapsUri"
        )
    }

    types = included_types or ["hotel", "lodging", "resort_hotel"]
    
    # Radius in meters (Max 50000)
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
            "places.rating,places.userRatingCount,places.location,places.googleMapsUri,nextPageToken"
        )
    }

    fetched = []
    page_token = None

    while len(fetched) < 60:
        if page_token:
            payload = {"pageToken": page_token}
        else:
            payload = {
                "textQuery": text_query,
                "pageSize": 20
            }
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
    """Fetches up to `limit` unique competitor establishments."""
    all_places = []
    seen_place_ids = set()

    def process_and_add(raw_places: List[Dict]):
        for p in raw_places:
            place_id = p.get("id")
            if not place_id or place_id in seen_place_ids:
                continue

            display_name = p.get("displayName", {}).get("text", "Unknown")

            # Filter out target hotel itself
            if establishment_name and establishment_name.lower() in display_name.lower():
                continue

            seen_place_ids.add(place_id)

            location = p.get("location", {})
            plat = location.get("latitude")
            plng = location.get("longitude")

            maps_url = p.get("googleMapsUri") or (
                f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote_plus(display_name)}"
            )

            all_places.append({
                "name": display_name,
                "address": p.get("formattedAddress", ""),
                "rating": p.get("rating"),
                "reviews": p.get("userRatingCount", 0),
                "url": maps_url,
                "lat": plat,
                "lng": plng,
                "place_id": place_id,
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
                    "Discovering nearby hotels..."
                )

            nearby_raw = _fetch_nearby_places(pt["lat"], pt["lng"], radius_km)
            process_and_add(nearby_raw)

    # Strategy 2: Expanded Area Search
    search_terms = [
        f"Hotels in {city}",
        f"Luxury Hotels in {city}",
        f"Boutique hotels in {city}",
        f"Resorts in {city}",
        f"5 star hotels in {city}",
        f"4 star hotels in {city}",
        f"Lodging in {city}",
    ]

    for idx, term in enumerate(search_terms):
        if progress_callback:
            pct = 50 + min(45, int((idx / len(search_terms)) * 45))
            progress_callback(
                pct,
                limit,
                "Expanding search radius and gathering additional hotels..."
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

    logger.info(f"[PLACES API] Search finished. Yielded {len(filtered_places)} places within {radius_km} km.")

    if progress_callback:
        progress_callback(100, limit, f"Found {len(filtered_places[:limit])} hotels matching your criteria.")

    return filtered_places[:limit]