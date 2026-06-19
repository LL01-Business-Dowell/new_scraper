"""
google_maps_scraper.py
----------------------
Selenium scraper to find competitor businesses on Google Maps.
CSS selectors verified against live Google Maps HTML (June 2026).
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

# Set logging level to see debug details in the terminal
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
    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlng/2)**2)
    return R * 2 * math.asin(math.sqrt(a))

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
    Search Google Maps for businesses matching keyword in city with deep logging.
    """
    driver = None
    results = []
    seen_urls = set()

    try:
        driver = init_driver()

        query = f"{keyword} in {city}"
        encoded = urllib.parse.quote_plus(query)
        search_url = f"https://www.google.com/maps/search/{encoded}"

        logger.info(f"[SCRAPER] Loading: {search_url}")
        driver.get(search_url)

        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "div.m6QErb[role='feed']")
                )
            )
            logger.info("[DEBUG] Found results feed container in DOM.")
        except TimeoutException:
            logger.error("[SCRAPER] Results feed did not load within 20s")
            return results

        time.sleep(2)

        try:
            feed = driver.find_element(By.CSS_SELECTOR, "div.m6QErb[role='feed']")
        except NoSuchElementException:
            logger.error("[SCRAPER] Could not find feed container")
            return results

        scroll_attempts = 0
        max_scroll_attempts = 15
        
        actions = ActionChains(driver)
        scroll_origin = ScrollOrigin.from_element(feed)

        while len(results) < limit and scroll_attempts < max_scroll_attempts:
            prev_count = len(results)
            
            # Read browser dimensions before moving
            js_scroll_top = driver.execute_script("return arguments[0].scrollTop;", feed)
            js_scroll_height = driver.execute_script("return arguments[0].scrollHeight;", feed)
            logger.info(f"[DEBUG] Pre-scroll metrics -> Top: {js_scroll_top}px, Full Height: {js_scroll_height}px")

            # Wake up lazy loading by hovering over the last element card
            cards = driver.find_elements(By.CSS_SELECTOR, "div.Nv2PK")
            if cards:
                try:
                    actions.move_to_element(cards[-1]).perform()
                    time.sleep(0.2)
                except Exception:
                    pass

            logger.info("[DEBUG] Executing physical mouse wheel actions...")
            for i in range(6):
                actions.scroll_from_origin(scroll_origin, 0, 1500).perform()
                time.sleep(random.uniform(0.2, 0.4))
                
            # Fallback JavaScript injection to force bottom scrolling
            driver.execute_script("arguments[0].scrollTo(0, arguments[0].scrollHeight);", feed)
            time.sleep(random.uniform(1.5, 2.2)) 
            
            # Post-scroll sizing evaluation
            post_scroll_height = driver.execute_script("return arguments[0].scrollHeight;", feed)
            logger.info(f"[DEBUG] Post-scroll height tracking -> Old: {js_scroll_height}px, New: {post_scroll_height}px")
            
            cards = driver.find_elements(By.CSS_SELECTOR, "div.Nv2PK")
            logger.info(f"[DEBUG] DOM Scan: Located {len(cards)} matching card elements ('div.Nv2PK') in current view frame.")
            
            parsed_this_loop = 0
            duplicates_this_loop = 0

            for index, card in enumerate(cards):
                if len(results) >= limit:
                    break
                try:
                    try:
                        anchor = card.find_element(By.CSS_SELECTOR, "a.hfpxzc")
                        url = anchor.get_attribute("href") or ""
                    except NoSuchElementException:
                        url = ""

                    if url and url in seen_urls:
                        duplicates_this_loop += 1
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

                    # ── Robust Address Extraction ─────────────────────────
                    address = ""
                    try:
                        # Find all information row blocks inside this business card
                        info_rows = card.find_elements(By.CSS_SELECTOR, "div.W4Efsd")
                        candidates = []
                        
                        for row in info_rows:
                            row_text = row.text.strip()
                            if not row_text:
                                continue
                            
                            # Filter out rows that represent review stats or description quotes
                            if "·" in row_text and any(keyword in row_text.lower() for keyword in ["review", "rating", "★", "years in business"]):
                                continue
                            if row_text.startswith('"') and row_text.endswith('"'):
                                continue
                                
                            # Split segments separated by dots
                            parts = [p.strip() for p in row_text.split("·") if p.strip()]
                            for p in parts:
                                lower_p = p.lower()
                                # Eliminate store operational hours/status flags
                                if any(word in lower_p for word in ["open", "closed", "closes", "opens", "delivery", "dine-in", "takeout"]):
                                    continue
                                if len(p) > 2 and p not in candidates:
                                    candidates.append(p)
                                    
                        if candidates:
                            # Filter out simple business category keywords to isolate the genuine street location
                            address_candidates = [
                                c for c in candidates 
                                if not any(cat in c.lower() for cat in ["cafe", "coffee shop", "restaurant", "bakery", "patisserie", "lounge"])
                            ]
                            address = address_candidates[0] if address_candidates else candidates[0]
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
                    parsed_this_loop += 1

                    if progress_callback:
                        progress_callback(len(results), limit, f"Found {len(results)} places...")

                except StaleElementReferenceException:
                    logger.debug(f"[DEBUG] Card item index {index} went stale during evaluation loop processing.")
                    continue
                except Exception as e:
                    logger.warning(f"[SCRAPER] Card parse error: {e}")
                    continue

            logger.info(f"[DEBUG] Frame Processed: Scraped {parsed_this_loop} new items, skipped {duplicates_this_loop} duplicates. Total results: {len(results)}.")

            if len(results) == prev_count:
                scroll_attempts += 1
                logger.warning(f"[SCRAPER] Stall warning triggered! (Cycle {scroll_attempts}/{max_scroll_attempts}). Zero progress made.")
                
                logger.info("[DEBUG] Activating defensive recovery nudge sequence...")
                driver.execute_script("arguments[0].scrollTo(0, arguments[0].scrollTop - 1000);", feed)
                time.sleep(0.5)
                driver.execute_script("arguments[0].scrollTo(0, arguments[0].scrollHeight);", feed)
                time.sleep(2.0)

                try:
                    end_banner = driver.find_element(By.CSS_SELECTOR, "span.HlvSq")
                    if end_banner and end_banner.is_displayed():
                        logger.info("[SCRAPER] Hard end element parsed ('You've reached the end of the list'). Stopping execution cleanly.")
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
                        logger.info("[SCRAPER] End of list spinner gone — stopping.")
                        break
            except Exception:
                pass

        logger.info(f"[SCRAPER] Done — found {len(results)} places")

    except Exception as e:
        logger.error(f"[SCRAPER] Fatal error: {e}")

    finally:
        if driver:
            driver.quit()

    # ── Distance calculation ──────────────────────────────────────────────
    for place in results:
        lat, lng = extract_coords_from_url(place.get("url", ""))
        place["lat"] = lat
        place["lng"] = lng

        if origin_lat and origin_lng and lat and lng:
            dist = haversine_km(origin_lat, origin_lng, lat, lng)
            place["distance_km"]    = round(dist, 2)
            place["within_radius"]  = dist <= radius_km
        else:
            place["distance_km"]   = None
            place["within_radius"] = None

    filtered = [
        p for p in results
        if p.get("within_radius") is True or p.get("within_radius") is None
    ]
    
    logger.info(
        f"[SCRAPER] Distance filter: {len(results)} total → "
        f"{len(filtered)} within {radius_km}km radius"
    )
    
    return filtered