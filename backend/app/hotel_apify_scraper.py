"""
hotel_apify_scraper.py
----------------------
Apify Google Maps Reviews Scraper integration for hotel sentiment route.
Replaces hotel_review_scraper.py (Selenium) for the hotel sentiment flow only.

Actor: compass/google-maps-reviews-scraper (Xb8osYTtOjlsgI6k9)
Docs: https://apify.com/compass/google-maps-reviews-scraper/input-schema

Flow:
1. POST to Apify API to start the actor run
2. Poll run status until finished
3. Fetch dataset items (reviews)
4. Parse and return in the same format as hotel_review_scraper.py

Env vars required:
- APIFY_API_TOKEN

Review cutoff: 90 days from today (passed as reviewsStartDate)
"""

import os
import time
import datetime
import logging
import requests
from typing import Dict, List, Optional, Callable

logger = logging.getLogger(__name__)

APIFY_TOKEN    = os.getenv("APIFY_API_TOKEN", "")
ACTOR_ID       = "Xb8osYTtOjlsgI6k9"  # compass/google-maps-reviews-scraper
BASE_URL       = "https://api.apify.com/v2"
DAYS_BACK      = 90  # cutoff — 90 days from today


def _cutoff_date() -> str:
    """Returns ISO date string 90 days ago, e.g. '2025-04-18'"""
    d = datetime.date.today() - datetime.timedelta(days=DAYS_BACK)
    return d.isoformat()


def _start_run(place_url: str, max_reviews: int) -> Optional[str]:
    """Start an Apify actor run and return the run ID."""
    if not APIFY_TOKEN:
        logger.error("[APIFY] APIFY_API_TOKEN not set")
        return None

    cutoff = _cutoff_date()
    payload = {
        "startUrls":          [{"url": place_url}],
        "maxReviews":         max_reviews,
        "reviewsSort":        "newest",
        "reviewsStartDate":   cutoff,
        "language":           "en",
        "reviewsOrigin":      "google",
        "personalData":       False,   # GDPR — no reviewer personal data
    }

    url = f"{BASE_URL}/acts/{ACTOR_ID}/runs?token={APIFY_TOKEN}"
    try:
        resp = requests.post(url, json=payload, timeout=30)
        if resp.status_code not in (200, 201):
            logger.error(f"[APIFY] Failed to start run: {resp.status_code} {resp.text[:300]}")
            return None
        run_id = resp.json().get("data", {}).get("id")
        logger.info(f"[APIFY] Started run {run_id} for {place_url}")
        return run_id
    except Exception as e:
        logger.error(f"[APIFY] Start run error: {e}")
        return None


def _poll_run(run_id: str, timeout_seconds: int = 300) -> bool:
    """
    Poll run status until SUCCEEDED or FAILED.
    Returns True if succeeded, False otherwise.
    """
    url      = f"{BASE_URL}/actor-runs/{run_id}?token={APIFY_TOKEN}"
    deadline = time.time() + timeout_seconds
    interval = 5  # poll every 5 seconds

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
        interval = min(interval + 5, 30)  # back off up to 30s

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
    """
    Parse Apify dataset items into the review format used by _run_sentiment_analysis.
    
    Apify compass/google-maps-reviews-scraper returns fields:
        text, stars, publishedAtDate, publishedAtDateFormatted,
        name (reviewer), reviewUrl, responseFromOwnerText, etc.
    """
    reviews = []
    for item in items:
        text   = item.get("text") or item.get("reviewText") or ""
        stars  = item.get("stars") or item.get("rating")
        date   = item.get("publishedAtDateFormatted") or item.get("publishedAtDate", "")

        # Normalise rating to int
        rating = None
        if stars is not None:
            try:
                rating = int(float(stars))
            except Exception:
                pass

        # Clean date string — keep just the date part
        if date and "T" in date:
            date = date.split("T")[0]

        reviews.append({
            "author": "Guest",        # personalData=False so no reviewer name
            "rating": rating,
            "date":   date or "Recent",
            "text":   text.strip() if text else "[Rating Only]",
        })

    return reviews


def scrape_hotel_reviews_apify(
    url: str,
    max_reviews: int = 200,
    progress_callback: Optional[Callable] = None,
) -> Dict:
    """
    Scrape reviews for a single hotel Google Maps URL using Apify.
    Returns the same format as hotel_review_scraper.scrape_hotel_reviews().

    {
        "business_details": {},   # empty — Places API provides this separately
        "reviews":  [...],
        "sentiment": {},          # filled by _run_sentiment_analysis in routes
        "error": None | str
    }
    """
    result = {"business_details": {}, "reviews": [], "sentiment": {}, "error": None}

    if not url:
        result["error"] = "No URL provided"
        return result

    if not APIFY_TOKEN:
        result["error"] = "APIFY_API_TOKEN not configured"
        return result

    if progress_callback:
        progress_callback(5, 100, "Starting review finder...")

    # 1. Start run
    run_id = _start_run(url, max_reviews)
    if not run_id:
        result["error"] = "Failed to start Apify run"
        return result

    if progress_callback:
        progress_callback(15, 100, "Finding reviews (this takes 1-3 minutes)...")

    # 2. Poll until done
    succeeded = _poll_run(run_id, timeout_seconds=360)
    if not succeeded:
        result["error"] = f"Apify run {run_id} did not succeed"
        return result

    if progress_callback:
        progress_callback(80, 100, "Fetching reviews...")

    # 3. Fetch dataset
    items = _fetch_dataset(run_id)
    if not items:
        logger.warning(f"[APIFY] No reviews returned for {url}")
        result["reviews"] = []
        return result

    # 4. Parse into standard format
    reviews = _parse_reviews(items)
    result["reviews"] = reviews

    if progress_callback:
        progress_callback(95, 100, f"Got {len(reviews)} reviews — running sentiment analysis...")

    logger.info(f"[APIFY] Done — {len(reviews)} reviews for {url}")
    return result