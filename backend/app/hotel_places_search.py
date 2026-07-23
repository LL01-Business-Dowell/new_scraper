"""
hotel_places_search.py
----------------------
Google Places API (New) — Nearby Search for luxury hotels.
Uses POST https://places.googleapis.com/v1/places:searchNearby
"""

import os
import math
import time
import logging
import requests
from typing import List, Dict

logger = logging.getLogger(__name__)

PLACES_API_KEY  = os.getenv("GOOGLE_PLACES_API_KEY", "")
NEARBY_ENDPOINT = "https://places.googleapis.com/v1/places:searchNearby"

FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.rating",
    "places.userRatingCount",
    "places.location",
    "places.googleMapsUri",
    "nextPageToken",
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

    # ── Startup checks ────────────────────────────────────────────────────────
    if not PLACES_API_KEY:
        logger.error("[HOTEL PLACES] ❌ GOOGLE_PLACES_API_KEY is not set in environment")
        return []

    logger.info(
        f"[HOTEL PLACES] Starting search — "
        f"origin=({origin_lat}, {origin_lng}), "
        f"radius={radius_km}km ({radius_km * 1000:.0f}m), "
        f"limit={limit}, "
        f"establishment='{establishment_name}'"
    )
    logger.info(f"[HOTEL PLACES] API key present: {'yes' if PLACES_API_KEY else 'no'} "
                f"(first 8 chars: {PLACES_API_KEY[:8]}...)")
    logger.info(f"[HOTEL PLACES] Endpoint: {NEARBY_ENDPOINT}")
    logger.info(f"[HOTEL PLACES] Field mask: {FIELD_MASK}")

    radius_m   = min(radius_km * 1000, 50000)
    places     = []
    seen_ids   = set()
    next_token = None
    page       = 0
    max_pages  = 5

    while page < max_pages and len(places) < limit:

        logger.info(f"[HOTEL PLACES] ── Page {page + 1} ──────────────────────")

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
            logger.info(f"[HOTEL PLACES] Using pageToken: {next_token[:30]}...")

        headers = {
            "Content-Type":     "application/json",
            "X-Goog-Api-Key":   PLACES_API_KEY,
            "X-Goog-FieldMask": FIELD_MASK,
        }

        logger.info(f"[HOTEL PLACES] Request body: {body}")

        try:
            resp = requests.post(
                NEARBY_ENDPOINT,
                json=body,
                headers=headers,
                timeout=15,
            )

            logger.info(f"[HOTEL PLACES] Response status: {resp.status_code}")

            if resp.status_code != 200:
                logger.error(
                    f"[HOTEL PLACES] ❌ API error {resp.status_code}: {resp.text[:500]}"
                )
                break

            data       = resp.json()
            raw_places = data.get("places", [])
            next_token = data.get("nextPageToken")

            logger.info(f"[HOTEL PLACES] Response keys: {list(data.keys())}")
            logger.info(f"[HOTEL PLACES] Places returned this page: {len(raw_places)}")
            logger.info(f"[HOTEL PLACES] nextPageToken present: {bool(next_token)}")

            if not raw_places:
                logger.warning(
                    f"[HOTEL PLACES] ⚠️  Zero places returned on page {page + 1}. "
                    f"Full response: {resp.text[:500]}"
                )

            skipped_duplicate = 0
            skipped_outside   = 0

            for p in raw_places:
                place_id = p.get("id", "")

                if place_id in seen_ids:
                    skipped_duplicate += 1
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

                dist   = None
                within = None
                if lat and lng:
                    dist   = round(haversine_km(origin_lat, origin_lng, lat, lng), 2)
                    within = dist <= radius_km

                if within is False:
                    skipped_outside += 1
                    logger.debug(
                        f"[HOTEL PLACES] Skipping '{name}' — {dist}km > {radius_km}km radius"
                    )
                    continue

                logger.debug(
                    f"[HOTEL PLACES] ✓ Added: '{name}' | "
                    f"rating={rating} | reviews={reviews} | dist={dist}km"
                )

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
                        bool(establishment_name) and
                        establishment_name.strip().lower() == name.strip().lower()
                    ),
                })

                if len(places) >= limit:
                    logger.info(f"[HOTEL PLACES] Reached limit of {limit} — stopping pagination")
                    break

            logger.info(
                f"[HOTEL PLACES] Page {page + 1} summary: "
                f"added={len(raw_places) - skipped_duplicate - skipped_outside}, "
                f"skipped_duplicate={skipped_duplicate}, "
                f"skipped_outside_radius={skipped_outside}, "
                f"running_total={len(places)}"
            )

        except requests.exceptions.Timeout:
            logger.error(f"[HOTEL PLACES] ❌ Request timed out on page {page + 1}")
            break
        except requests.exceptions.ConnectionError as e:
            logger.error(f"[HOTEL PLACES] ❌ Connection error on page {page + 1}: {e}")
            break
        except Exception as e:
            logger.error(f"[HOTEL PLACES] ❌ Unexpected error on page {page + 1}: {e}")
            break

        page += 1

        if not next_token:
            logger.info(
                f"[HOTEL PLACES] No nextPageToken — all available results returned after {page} page(s)"
            )
            break

        logger.info(f"[HOTEL PLACES] Waiting 0.5s before next page request...")
        time.sleep(0.5)

    logger.info(
        f"[HOTEL PLACES] ✅ Search complete — "
        f"{len(places)} hotels found within {radius_km}km "
        f"after {page} page(s) | "
        f"seen_ids total: {len(seen_ids)}"
    )

    if len(places) == 0:
        logger.warning(
            "[HOTEL PLACES] ⚠️  Zero hotels returned. Possible reasons:\n"
            "  1. GOOGLE_PLACES_API_KEY is wrong or Places API (New) not enabled\n"
            "  2. No lodging places within the radius\n"
            "  3. Billing not enabled on the Google Cloud project\n"
            "  4. API quota exceeded"
        )

    return places