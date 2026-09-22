import os
import time
import datetime
import logging
import json
import requests
from typing import Dict, List, Optional, Callable

logger = logging.getLogger(__name__)

APIFY_TOKEN = os.getenv("APIFY_API_TOKEN", "")
ACTOR_ID = "Xb8osYTtOjlsgI6k9"  # compass/google-maps-reviews-scraper
BASE_URL = "https://api.apify.com/v2"

DAYS_BACK = 30  # strict cutoff — 30 days from today
MASTER_FILE = "all_hotels_reviews.json"


def _cutoff_date() -> str:
    """Returns ISO date string 30 days ago."""
    d = datetime.date.today() - datetime.timedelta(days=DAYS_BACK)
    return d.isoformat()


def _start_run(
    place_url: str,
    max_reviews: Optional[int] = None
) -> Optional[str]:
    """Start an Apify actor run and return the run ID."""

    if not APIFY_TOKEN:
        logger.error("[APIFY] APIFY_API_TOKEN not set")
        return None

    cutoff = _cutoff_date()

    payload = {
        "startUrls": [{"url": place_url}],
        "reviewsSort": "newest",
        "reviewsStartDate": cutoff,
        "language": "en",
        "reviewsOrigin": "google",
        "personalData": False,
    }

    if max_reviews and max_reviews > 0:
        payload["maxReviews"] = max_reviews

    url = f"{BASE_URL}/acts/{ACTOR_ID}/runs?token={APIFY_TOKEN}"

    try:
        resp = requests.post(
            url,
            json=payload,
            timeout=30
        )

        if resp.status_code not in (200, 201):
            logger.error(
                f"[APIFY] Failed to start run: "
                f"{resp.status_code} {resp.text[:300]}"
            )
            return None

        run_id = resp.json().get("data", {}).get("id")

        logger.info(
            f"[APIFY] Started run {run_id} for {place_url} "
            f"(Cutoff: {cutoff})"
        )

        return run_id

    except Exception as e:
        logger.error(f"[APIFY] Start run error: {e}")
        return None


def _poll_run(
    run_id: str,
    timeout_seconds: int = 300
) -> bool:
    """Poll run status until SUCCEEDED or FAILED."""

    url = (
        f"{BASE_URL}/actor-runs/{run_id}"
        f"?token={APIFY_TOKEN}"
    )

    deadline = time.time() + timeout_seconds
    interval = 5

    while time.time() < deadline:

        try:
            resp = requests.get(
                url,
                timeout=15
            )

            if resp.status_code == 200:

                status = (
                    resp.json()
                    .get("data", {})
                    .get("status", "")
                )

                logger.info(
                    f"[APIFY] Run {run_id} status: {status}"
                )

                if status == "SUCCEEDED":
                    return True

                if status in (
                    "FAILED",
                    "TIMED-OUT",
                    "ABORTED"
                ):
                    logger.error(
                        f"[APIFY] Run {run_id} ended "
                        f"with status: {status}"
                    )
                    return False

        except Exception as e:
            logger.warning(
                f"[APIFY] Poll error: {e}"
            )

        time.sleep(interval)
        interval = min(interval + 5, 30)

    logger.error(
        f"[APIFY] Run {run_id} timed out "
        f"after {timeout_seconds}s"
    )

    return False


def _fetch_dataset(run_id: str) -> List[Dict]:
    """Fetch all items from the run's default dataset."""

    url = (
        f"{BASE_URL}/actor-runs/{run_id}"
        f"/dataset/items"
        f"?token={APIFY_TOKEN}"
        f"&format=json"
        f"&limit=1000"
    )

    try:
        resp = requests.get(
            url,
            timeout=30
        )

        if resp.status_code == 200:

            items = resp.json()

            logger.info(
                f"[APIFY] Fetched {len(items)} "
                f"items from dataset"
            )

            return items

        logger.error(
            f"[APIFY] Dataset fetch failed: "
            f"{resp.status_code}"
        )

        return []

    except Exception as e:
        logger.error(
            f"[APIFY] Dataset fetch error: {e}"
        )

        return []


def _parse_reviews(
    items: List[Dict]
) -> List[Dict]:
    """Parse Apify dataset items into standard review format."""

    reviews = []

    for item in items:

        text = (
            item.get("text")
            or item.get("reviewText")
            or ""
        )

        stars = (
            item.get("stars")
            or item.get("rating")
        )

        date = (
            item.get("publishedAtDateFormatted")
            or item.get("publishedAtDate")
            or ""
        )

        rating = None

        if stars is not None:
            try:
                rating = int(float(stars))
            except Exception:
                pass

        if date and "T" in date:
            date = date.split("T")[0]

        reviews.append({
            "author": item.get("name") or "Guest",
            "rating": rating,
            "date": date or "Recent",
            "text": (
                text.strip()
                if text
                else "[Rating Only]"
            ),
        })

    return reviews


def _extract_hotel_title(
    items: List[Dict]
) -> Optional[str]:
    """
    Tries to retrieve the actual hotel name directly
    from Apify dataset metadata.
    """

    for item in items:

        title = (
            item.get("title")
            or item.get("placeName")
            or item.get("locationName")
        )

        if title:
            return title

    return None


# =============================================================================
# EXTRACT OVERALL RATING
# =============================================================================

def _extract_overall_rating(items: List[Dict]) -> Optional[float]:
    """Extract overall place rating/total score from Apify dataset metadata."""

    for item in items:

        overall = (
            item.get("totalScore")
            or item.get("placeStars")
            or item.get("aggregateRating")
            or item.get("rating")
        )

        if overall is not None:
            try:
                score = float(overall)
                # Ensure it's a realistic 0-5 scale rating
                if 0 <= score <= 5:
                    return score
            except (TypeError, ValueError):
                pass

    return None


# =============================================================================
# EXTRACT COORDINATES
# =============================================================================

def _extract_coordinates(
    items: List[Dict]
) -> tuple[Optional[float], Optional[float]]:
    """
    Extract latitude and longitude from Apify dataset items.
    """

    for item in items:

        latitude = None
        longitude = None

        location = item.get("location")

        if isinstance(location, dict):

            latitude = (
                location.get("lat")
                or location.get("latitude")
            )

            longitude = (
                location.get("lng")
                or location.get("longitude")
            )

        if latitude is None:
            latitude = (
                item.get("latitude")
                or item.get("lat")
            )

        if longitude is None:
            longitude = (
                item.get("longitude")
                or item.get("lng")
            )

        coordinates = item.get("coordinates")

        if isinstance(coordinates, dict):

            if latitude is None:
                latitude = (
                    coordinates.get("latitude")
                    or coordinates.get("lat")
                )

            if longitude is None:
                longitude = (
                    coordinates.get("longitude")
                    or coordinates.get("lng")
                )

        try:
            if latitude is not None:
                latitude = float(latitude)

            if longitude is not None:
                longitude = float(longitude)

        except (TypeError, ValueError):
            latitude = None
            longitude = None

        if (
            latitude is not None
            and longitude is not None
            and -90 <= latitude <= 90
            and -180 <= longitude <= 180
        ):

            logger.info(
                f"[APIFY] Extracted coordinates: "
                f"{latitude}, {longitude}"
            )

            return latitude, longitude

    logger.warning(
        "[APIFY] Could not find latitude/longitude "
        "in dataset."
    )

    return None, None


# =============================================================================
# SAVE MASTER JSON
# =============================================================================

def _append_to_master_file(
    hotel_name: str,
    url: str,
    reviews: List[Dict],
    overall_rating: Optional[float] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    filepath: str = MASTER_FILE
):
    """
    Appends/updates hotel review data in the master JSON file.
    """

    master_data = {}

    if os.path.exists(filepath):

        try:

            with open(
                filepath,
                "r",
                encoding="utf-8"
            ) as f:

                master_data = json.load(f)

        except Exception as e:

            logger.warning(
                "[LOCAL DUMP] Could not read existing "
                f"master file, starting fresh: {e}"
            )

    # -------------------------------------------------------------------------
    # Store hotel data
    # -------------------------------------------------------------------------

    master_data[hotel_name] = {

        "url": url,

        "scraped_at": (
            datetime.datetime.now()
            .isoformat()
        ),

        "overall_rating": overall_rating,

        "total_reviews": len(reviews),

        "lat": latitude,

        "lng": longitude,

        "reviews": reviews,
    }

    # -------------------------------------------------------------------------
    # Write JSON
    # -------------------------------------------------------------------------

    try:

        with open(
            filepath,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                master_data,
                f,
                indent=4,
                ensure_ascii=False
            )

        logger.info(
            f"[LOCAL DUMP] Successfully saved "
            f"'{hotel_name}' "
            f"(rating={overall_rating}, {len(reviews)} reviews) "
            f"coordinates=({latitude}, {longitude}) "
            f"to {filepath}"
        )

    except Exception as e:

        logger.error(
            f"[LOCAL DUMP] Failed writing to "
            f"{filepath}: {e}"
        )


# =============================================================================
# MAIN SCRAPER
# =============================================================================

def scrape_hotel_reviews_apify(
    url: str,
    hotel_name: Optional[str] = None,
    max_reviews: Optional[int] = None,
    progress_callback: Optional[Callable] = None,
) -> Dict:
    """
    Scrapes Google Maps reviews and appends them to a single
    master JSON file, including overall rating, latitude, and longitude.
    """

    result = {
        "business_details": {},
        "reviews": [],
        "sentiment": {},
        "error": None,
    }

    if not url:
        result["error"] = "No URL provided"
        return result

    if not APIFY_TOKEN:
        result["error"] = (
            "APIFY_API_TOKEN not configured"
        )
        return result

    display_name = (
        hotel_name
        if hotel_name and hotel_name != "Unknown Hotel"
        else "Hotel"
    )

    if progress_callback:

        progress_callback(
            5,
            100,
            f"Starting review finder for {display_name}..."
        )

    # -------------------------------------------------------------------------
    # START APIFY
    # -------------------------------------------------------------------------

    run_id = _start_run(
        url,
        max_reviews
    )

    if not run_id:

        result["error"] = (
            "Failed to start Apify run"
        )

        return result

    if progress_callback:

        progress_callback(
            15,
            100,
            "Finding reviews (this takes 1-3 minutes)..."
        )

    # -------------------------------------------------------------------------
    # POLL
    # -------------------------------------------------------------------------

    succeeded = _poll_run(
        run_id,
        timeout_seconds=360
    )

    if not succeeded:

        result["error"] = (
            f"Apify run {run_id} did not succeed"
        )

        return result

    if progress_callback:

        progress_callback(
            80,
            100,
            "Fetching reviews..."
        )

    # -------------------------------------------------------------------------
    # FETCH DATASET
    # -------------------------------------------------------------------------

    items = _fetch_dataset(
        run_id
    )

    # -------------------------------------------------------------------------
    # REVIEWS
    # -------------------------------------------------------------------------

    reviews = (
        _parse_reviews(items)
        if items
        else []
    )

    result["reviews"] = reviews

    # -------------------------------------------------------------------------
    # EXTRACT HOTEL NAME
    # -------------------------------------------------------------------------

    extracted_name = _extract_hotel_title(
        items
    )

    if (
        hotel_name
        and hotel_name != "Unknown Hotel"
    ):

        final_hotel_name = hotel_name

    elif extracted_name:

        final_hotel_name = extracted_name

    else:

        cid = (
            url.split("cid=")[-1].split("&")[0]
            if "cid=" in url
            else url.rstrip("/").split("/")[-1]
        )

        final_hotel_name = (
            f"Hotel_{cid}"
        )

    # -------------------------------------------------------------------------
    # EXTRACT METADATA (COORDINATES & OVERALL RATING)
    # -------------------------------------------------------------------------

    latitude, longitude = _extract_coordinates(
        items
    )

    overall_rating = _extract_overall_rating(
        items
    )

    # -------------------------------------------------------------------------
    # ADD TO RESULT
    # -------------------------------------------------------------------------

    result["business_details"] = {
        "name": final_hotel_name,
        "overall_rating": overall_rating,
        "rating": overall_rating,
        "latitude": latitude,
        "longitude": longitude,
        "lat": latitude,
        "lng": longitude,
        "total_reviews": len(reviews),
    }

    # -------------------------------------------------------------------------
    # SAVE TO MASTER JSON
    # -------------------------------------------------------------------------

    _append_to_master_file(
        hotel_name=final_hotel_name,
        url=url,
        reviews=reviews,
        overall_rating=overall_rating,
        latitude=latitude,
        longitude=longitude,
    )

    if progress_callback:

        progress_callback(
            95,
            100,
            f"Got {len(reviews)} reviews — "
            "running sentiment analysis..."
        )

    logger.info(
        f"[APIFY] Done — "
        f"{len(reviews)} reviews for "
        f"{final_hotel_name} "
        f"overall_rating={overall_rating} "
        f"coordinates=({latitude}, {longitude})"
    )

    return result