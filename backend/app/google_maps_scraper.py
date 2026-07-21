"""
google_maps_scraper.py
----------------------
Selenium scraper to find competitor businesses on Google Maps.
CSS selectors verified against live Google Maps HTML.

Quadrant search strategy
-------------------------
A single Google Maps search from one query (e.g. "Cafe in Ernakulam") tends
to expand in only one direction from the city center, missing businesses on
the opposite side of the radius circle. To fix this, the radius circle is
split into 4 quadrants (NE, NW, SE, SW) around the origin coordinate, and a
separate Maps search is run centered on each quadrant's midpoint using
lat/lng-based URL search instead of a text query. Results are merged and
deduplicated by URL afterwards.
"""

import math
import time
import random
import re
import logging
import urllib.parse
from typing import List, Dict, Optional, Callable
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.actions.wheel_input import ScrollOrigin
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def extract_coords_from_url(url: str):
    """Extract lat/lng from a Google Maps place URL."""
    match = re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', url)
    if match:
        return float(match.group(1)), float(match.group(2))
    return None, None


def haversine_km(lat1, lng1, lat2, lng2) -> float:
    """Straight-line distance between two coordinates in km."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlng / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def get_quadrant_centers(origin_lat: float, origin_lng: float, radius_km: float):
    """
    Split the radius circle into 4 quadrants (NE, NW, SE, SW) and return
    the center coordinate of each quadrant. Each quadrant center sits at
    roughly half the radius distance, diagonally offset from the origin —
    this gives Google Maps' own search algorithm (which expands outward
    from whatever point it's centered on) four different starting points
    so it covers the full circle instead of just one side of it.
    """
    # Half-radius offset in km, split evenly across lat/lng diagonal
    offset_km = radius_km * 0.5
    # 1 degree latitude ≈ 111 km
    dlat = offset_km / 111.0
    # 1 degree longitude ≈ 111 km * cos(latitude)
    dlng = offset_km / (111.0 * math.cos(math.radians(origin_lat)) or 1)

    return {
        "NE": (origin_lat + dlat, origin_lng + dlng),
        "NW": (origin_lat + dlat, origin_lng - dlng),
        "SE": (origin_lat - dlat, origin_lng + dlng),
        "SW": (origin_lat - dlat, origin_lng - dlng),
    }


def init_driver():
    """Initialize headless Chromium with anti-bot measures."""
    options = Options()
    options.binary_location = "/usr/bin/chromium"
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--lang=en-US,en")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    service = Service("/usr/bin/chromedriver")
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return driver


def _scrape_one_search(
    driver,
    search_url: str,
    keyword: str,
    limit: int,
    seen_urls: set,
    progress_callback: Optional[Callable] = None,
    progress_offset: int = 0,
    progress_total: int = 100,
) -> List[Dict]:
    """
    Run a single Google Maps search (one quadrant) and scrape up to `limit`
    NEW results (deduplicated against the shared seen_urls set across all
    quadrant searches). Returns the list of places found in this pass.
    """
    results = []

    logger.info(f"[SCRAPER] Loading: {search_url}")
    driver.get(search_url)

    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.m6QErb[role='feed']"))
        )
    except TimeoutException:
        logger.error("[SCRAPER] Results feed did not load within 20s for this quadrant")
        return results

    time.sleep(2)

    try:
        feed = driver.find_element(By.CSS_SELECTOR, "div.m6QErb[role='feed']")
    except NoSuchElementException:
        logger.error("[SCRAPER] Could not find feed container for this quadrant")
        return results

    scroll_attempts = 0
    max_stale = 20
    max_total = 60  # fewer scrolls per quadrant since 4 quadrants run total

    actions = ActionChains(driver)
    scroll_origin = ScrollOrigin.from_element(feed)
    total_scrolls = 0

    while len(results) < limit and scroll_attempts < max_stale and total_scrolls < max_total:
        total_scrolls += 1
        prev_count = len(results)

        for i in range(8):
            actions.scroll_from_origin(scroll_origin, 0, 1200).perform()
            time.sleep(random.uniform(0.3, 0.5))

        time.sleep(random.uniform(1.2, 1.8))

        cards = driver.find_elements(By.CSS_SELECTOR, "div.Nv2PK")

        for card in cards:
            if len(results) >= limit:
                break
            try:
                try:
                    anchor = card.find_element(By.CSS_SELECTOR, "a.hfpxzc")
                    url = anchor.get_attribute("href") or ""
                except NoSuchElementException:
                    url = ""

                if url and url in seen_urls:
                    continue
                if url:
                    seen_urls.add(url)

                try:
                    name = card.find_element(By.CSS_SELECTOR, "div.qBF1Pd").text.strip()
                except NoSuchElementException:
                    name = "Unknown"

                if not name or name == "Unknown":
                    continue

                try:
                    rating_text = card.find_element(By.CSS_SELECTOR, "span.MW4etd").text.strip()
                    rating = float(rating_text) if rating_text else None
                except (NoSuchElementException, ValueError):
                    rating = None

                try:
                    review_text = card.find_element(By.CSS_SELECTOR, "span.UY7F9").text.strip()
                    review_count = int(re.sub(r"[^\d]", "", review_text)) if review_text else 0
                except (NoSuchElementException, ValueError):
                    review_count = 0

                address = ""
                try:
                    detail_spans = card.find_elements(By.CSS_SELECTOR, "div.W4Efsd div.W4Efsd > span")
                    span_texts = [s.text.strip() for s in detail_spans if s.text.strip()]
                    clean_elements = [txt for txt in span_texts if txt and txt != "·" and len(txt) > 2]
                    if len(clean_elements) > 1:
                        address = clean_elements[-1].lstrip("· ").strip()
                    elif len(clean_elements) == 1:
                        address = clean_elements[0]
                except Exception:
                    address = ""

                results.append({
                    "name":     name,
                    "address":  address,
                    "rating":   rating,
                    "reviews":  review_count,
                    "url":      url,
                    "selected": True,
                })

                if progress_callback:
                    overall = progress_offset + int((len(results) / max(limit, 1)) * (progress_total / 4))
                    progress_callback(overall, progress_total, f"Found {len(seen_urls)} places so far...")

            except StaleElementReferenceException:
                continue
            except Exception as e:
                logger.warning(f"[SCRAPER] Card parse error: {e}")
                continue

        if len(results) == prev_count:
            scroll_attempts += 1
            actions.scroll_from_origin(scroll_origin, 0, -2000).perform()
            time.sleep(0.8)
            actions.scroll_from_origin(scroll_origin, 0, 3000).perform()
            time.sleep(2.0)

            try:
                end_banner = driver.find_element(By.CSS_SELECTOR, "span.HlvSq")
                if end_banner and end_banner.is_displayed():
                    break
            except NoSuchElementException:
                pass
        else:
            scroll_attempts = 0

        try:
            end_of_list = driver.find_elements(By.CSS_SELECTOR, "div.lXJj5c.Hk4XGb")
            if end_of_list:
                spinner = driver.find_elements(By.CSS_SELECTOR, "div.lXJj5c .OBAKjf")
                if not spinner:
                    break
        except Exception:
            pass

    logger.info(f"[SCRAPER] Quadrant pass done — found {len(results)} new places")
    return results


def search_google_maps_competitors(
    keyword: str,
    city: str,
    establishment_name: str,
    radius_km: float = 5,
    limit: int = 100,
    origin_lat: float = None,
    origin_lng: float = None,
    progress_callback: Optional[Callable] = None,
) -> List[Dict]:
    """
    Search Google Maps for businesses matching keyword within radius_km of
    (origin_lat, origin_lng). Splits the search into 4 quadrant passes so
    results cover the full circle instead of expanding in just one direction
    from a single text-query search.

    Falls back to a single city-text search if origin_lat/origin_lng are not
    provided (keeps backward compatibility).
    """
    driver = None
    all_results: List[Dict] = []
    seen_urls = set()

    try:
        driver = init_driver()

        if origin_lat is not None and origin_lng is not None:
            # ── Quadrant search — 4 passes covering the full radius circle ──
            quadrants = get_quadrant_centers(origin_lat, origin_lng, radius_km)
            per_quadrant_limit = max(1, limit // 4) + 5  # small buffer for dedup losses

            logger.info(
                f"[SCRAPER] Quadrant search enabled — origin=({origin_lat},{origin_lng}) "
                f"radius={radius_km}km, {len(quadrants)} quadrants, "
                f"~{per_quadrant_limit} per quadrant"
            )

            for i, (quad_name, (qlat, qlng)) in enumerate(quadrants.items()):
                if len(all_results) >= limit:
                    break

                encoded_kw = urllib.parse.quote_plus(keyword)
                # lat,lng in the URL centers the Maps search on that point —
                # zoom 14 (z) roughly matches a few-km viewport
                search_url = (
                    f"https://www.google.com/maps/search/{encoded_kw}"
                    f"/@{qlat},{qlng},14z"
                )

                logger.info(f"[SCRAPER] Quadrant {quad_name} ({i+1}/{len(quadrants)})")

                quadrant_results = _scrape_one_search(
                    driver=driver,
                    search_url=search_url,
                    keyword=keyword,
                    limit=per_quadrant_limit,
                    seen_urls=seen_urls,
                    progress_callback=progress_callback,
                    progress_offset=i * 25,
                    progress_total=100,
                )
                all_results.extend(quadrant_results)

        else:
            # ── Fallback — single text-query search (old behavior) ──
            logger.info("[SCRAPER] No origin coordinates provided — falling back to single search")
            query = f"{keyword} in {city}"
            encoded = urllib.parse.quote_plus(query)
            search_url = f"https://www.google.com/maps/search/{encoded}"

            all_results = _scrape_one_search(
                driver=driver,
                search_url=search_url,
                keyword=keyword,
                limit=limit,
                seen_urls=seen_urls,
                progress_callback=progress_callback,
                progress_offset=0,
                progress_total=100,
            )

        logger.info(f"[SCRAPER] All quadrants done — {len(all_results)} total places found")

    except Exception as e:
        logger.error(f"[SCRAPER] Fatal error: {e}")

    finally:
        if driver:
            driver.quit()

    # ── Distance calculation ──────────────────────────────────────────────
    for place in all_results:
        lat, lng = extract_coords_from_url(place.get("url", ""))
        place["lat"] = lat
        place["lng"] = lng

        if origin_lat and origin_lng and lat and lng:
            dist = haversine_km(origin_lat, origin_lng, lat, lng)
            place["distance_km"]   = round(dist, 2)
            place["within_radius"] = dist <= radius_km
        else:
            place["distance_km"]   = None
            place["within_radius"] = None

    # ── Filter to only places within radius (keep unknown-distance places) ──
    filtered = [
        p for p in all_results
        if p.get("within_radius") is True or p.get("within_radius") is None
    ]

    logger.info(
        f"[SCRAPER] Distance filter: {len(all_results)} total → "
        f"{len(filtered)} within {radius_km}km radius"
    )

    return filtered[:limit]