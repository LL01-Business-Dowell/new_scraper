import os
import time
import datetime
import logging
import json
import requests
from typing import Dict, List, Optional, Callable

logger = logging.getLogger(__name__)

APIFY_TOKEN    = os.getenv("APIFY_API_TOKEN", "")
ACTOR_ID       = "Xb8osYTtOjlsgI6k9"  # compass/google-maps-reviews-scraper
BASE_URL       = "https://api.apify.com/v2"
DAYS_BACK      = 30  # strict cutoff — 30 days from today
MASTER_FILE    = "all_hotels_reviews.json"


def _cutoff_date() -> str:
    """Returns ISO date string 30 days ago, e.g. '2026-07-28'"""
    d = datetime.date.today() - datetime.timedelta(days=DAYS_BACK)
    return d.isoformat()


def _start_run(place_url: str, max_reviews: Optional[int] = None) -> Optional[str]:
    """Start an Apify actor run and return the run ID."""
    if not APIFY_TOKEN:
        logger.error("[APIFY] APIFY_API_TOKEN not set")
        return None

    cutoff = _cutoff_date()
    payload = {
        "startUrls":          [{"url": place_url}],
        "reviewsSort":        "newest",
        "reviewsStartDate":   cutoff,
        "language":           "en",
        "reviewsOrigin":      "google",
        "personalData":       False,   # GDPR — no reviewer personal data
    }

    if max_reviews and max_reviews > 0:
        payload["maxReviews"] = max_reviews

    url = f"{BASE_URL}/acts/{ACTOR_ID}/runs?token={APIFY_TOKEN}"
    try:
        resp = requests.post(url, json=payload, timeout=30)
        if resp.status_code not in (200, 201):
            logger.error(f"[APIFY] Failed to start run: {resp.status_code} {resp.text[:300]}")
            return None
        run_id = resp.json().get("data", {}).get("id")
        logger.info(f"[APIFY] Started run {run_id} for {place_url} (Cutoff: {cutoff})")
        return run_id
    except Exception as e:
        logger.error(f"[APIFY] Start run error: {e}")
        return None


def _poll_run(run_id: str, timeout_seconds: int = 300) -> bool:
    """Poll run status until SUCCEEDED or FAILED."""
    url      = f"{BASE_URL}/actor-runs/{run_id}?token={APIFY_TOKEN}"
    deadline = time.time() + timeout_seconds
    interval = 5

    while time.time() < deadline:
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                status = resp.json().get("data", {}).get("status", "")
                logger.info(f"[APIFY] Run {run_id} status: {status}")
                if status == "SUCCEEDED":
                    return True
                if status in ("FAILED", "TIMED-OUT", "ABORTED"):
                    logger.error(f"[APIFY] Run {run_id} ended with status: {status}")
                    return False
        except Exception as e:
            logger.warning(f"[APIFY] Poll error: {e}")

        time.sleep(interval)
        interval = min(interval + 5, 30)

    logger.error(f"[APIFY] Run {run_id} timed out after {timeout_seconds}s")
    return False


def _fetch_dataset(run_id: str) -> List[Dict]:
    """Fetch all items from the run's default dataset."""
    url = f"{BASE_URL}/actor-runs/{run_id}/dataset/items?token={APIFY_TOKEN}&format=json&limit=1000"
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code == 200:
            items = resp.json()
            logger.info(f"[APIFY] Fetched {len(items)} items from dataset")
            return items
        else:
            logger.error(f"[APIFY] Dataset fetch failed: {resp.status_code}")
            return []
    except Exception as e:
        logger.error(f"[APIFY] Dataset fetch error: {e}")
        return []


def _parse_reviews(items: List[Dict]) -> List[Dict]:
    """Parse Apify dataset items into standard review format."""
    reviews = []
    for item in items:
        text   = item.get("text") or item.get("reviewText") or ""
        stars  = item.get("stars") or item.get("rating")
        date   = item.get("publishedAtDateFormatted") or item.get("publishedAtDate", "")

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
            "date":   date or "Recent",
            "text":   text.strip() if text else "[Rating Only]",
        })

    return reviews


def _extract_hotel_title(items: List[Dict]) -> Optional[str]:
    """Tries to retrieve the actual hotel name directly from Apify dataset metadata."""
    for item in items:
        title = item.get("title") or item.get("placeName") or item.get("locationName")
        if title:
            return title
    return None


def _append_to_master_file(hotel_name: str, url: str, reviews: List[Dict], filepath: str = MASTER_FILE):
    """Appends/updates hotel review data in a single master JSON file safely without overwriting other properties."""
    master_data = {}

    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                master_data = json.load(f)
        except Exception as e:
            logger.warning(f"[LOCAL DUMP] Could not read existing master file, starting fresh: {e}")

    # Key by Hotel Name with nested details and reviews
    master_data[hotel_name] = {
        "url": url,
        "scraped_at": datetime.datetime.now().isoformat(),
        "total_reviews": len(reviews),
        "reviews": reviews
    }

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(master_data, f, indent=4, ensure_ascii=False)
        logger.info(f"[LOCAL DUMP] Successfully saved '{hotel_name}' ({len(reviews)} reviews) to {filepath}")
    except Exception as e:
        logger.error(f"[LOCAL DUMP] Failed writing to {filepath}: {e}")


def scrape_hotel_reviews_apify(
    url: str,
    hotel_name: Optional[str] = None,
    max_reviews: Optional[int] = None,
    progress_callback: Optional[Callable] = None,
) -> Dict:
    """Scrapes Google Maps reviews and appends them to a single master JSON file."""
    result = {"business_details": {}, "reviews": [], "sentiment": {}, "error": None}

    if not url:
        result["error"] = "No URL provided"
        return result

    if not APIFY_TOKEN:
        result["error"] = "APIFY_API_TOKEN not configured"
        return result

    display_name = hotel_name if hotel_name and hotel_name != "Unknown Hotel" else "Hotel"
    if progress_callback:
        progress_callback(5, 100, f"Starting review finder for {display_name}...")

    run_id = _start_run(url, max_reviews)
    if not run_id:
        result["error"] = "Failed to start Apify run"
        return result

    if progress_callback:
        progress_callback(15, 100, "Finding reviews (this takes 1-3 minutes)...")

    succeeded = _poll_run(run_id, timeout_seconds=360)
    if not succeeded:
        result["error"] = f"Apify run {run_id} did not succeed"
        return result

    if progress_callback:
        progress_callback(80, 100, "Fetching reviews...")

    items = _fetch_dataset(run_id)
    reviews = _parse_reviews(items) if items else []
    result["reviews"] = reviews

    # --- RESOLVE HOTEL NAME ---
    # Try passed name -> dataset metadata -> URL fallback key to prevent overwrites
    extracted_name = _extract_hotel_title(items)
    if hotel_name and hotel_name != "Unknown Hotel":
        final_hotel_name = hotel_name
    elif extracted_name:
        final_hotel_name = extracted_name
    else:
        # Fallback to unique CID or URL string key if name is truly unknown
        cid = url.split("cid=")[-1].split("&")[0] if "cid=" in url else url.rstrip("/").split("/")[-1]
        final_hotel_name = f"Hotel_{cid}"

    # --- SAVE TO MASTER JSON FILE ---
    _append_to_master_file(hotel_name=final_hotel_name, url=url, reviews=reviews)

    if progress_callback:
        progress_callback(95, 100, f"Got {len(reviews)} reviews — running sentiment analysis...")

    logger.info(f"[APIFY] Done — {len(reviews)} reviews for {final_hotel_name}")
    return result