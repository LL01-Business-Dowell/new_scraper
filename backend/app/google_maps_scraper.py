"""
google_maps_scraper.py
----------------------
Selenium scraper to find competitor businesses on Google Maps.
CSS selectors verified against live Google Maps HTML (June 2026).
"""

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
    driver.execute_cmd(
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
    progress_callback: Optional[Callable] = None,
) -> List[Dict]:
    """
    Search Google Maps for businesses matching keyword in city.
    Uses target tracking ids to survive local worker container drops.
    """
    driver = None
    results = []
    
    # Track items using unique identifiers to prevent multi-worker index resetting
    processed_place_ids = set()

    try:
        driver = init_driver()

        query = f"{keyword} in {city}"
        encoded = urllib.parse.quote_plus(query)
        search_url = f"https://www.google.com/maps/search/{encoded}"

        logger.info(f"[SCRAPER] Loading payload canvas target: {search_url}")
        driver.get(search_url)

        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.m6QErb[role='feed']"))
            )
        except TimeoutException:
            logger.error("[SCRAPER] Results feed timeout.")
            return results

        time.sleep(2)

        try:
            feed = driver.find_element(By.CSS_SELECTOR, "div.m6QErb[role='feed']")
        except NoSuchElementException:
            logger.error("[SCRAPER] Missing main feed container framework element.")
            return results

        scroll_attempts = 0
        max_scroll_attempts = 30  
        
        actions = ActionChains(driver)
        scroll_origin = ScrollOrigin.from_element(feed)

        while len(results) < limit and scroll_attempts < max_scroll_attempts:
            # Snapshot baseline loop metrics
            initial_count = len(results)
            
            # Fire structural canvas wheel rotation events
            for _ in range(4):
                actions.scroll_from_origin(scroll_origin, 0, 850).perform()
                time.sleep(random.uniform(0.4, 0.6))
                
            time.sleep(random.uniform(2.0, 3.0)) 
            
            # Capture structural card components inside current viewport
            cards = driver.find_elements(By.CSS_SELECTOR, "div.Nv2PK")
            
            for card in cards:
                if len(results) >= limit:
                    break
                try:
                    # FIX: Extract unique data attribute identifier to guarantee tracking integrity
                    place_id = card.get_attribute("data-item-id") or ""
                    
                    try:
                        anchor = card.find_element(By.CSS_SELECTOR, "a.hfpxzc")
                        url = anchor.get_attribute("href") or ""
                    except NoSuchElementException:
                        url = ""

                    # Fallback lookup verification key setup
                    lookup_key = place_id if place_id else url
                    if not lookup_key or lookup_key in processed_place_ids:
                        continue

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

                    # Persistent assignment
                    processed_place_ids.add(lookup_key)
                    results.append({
                        "name":     name,
                        "address":  address,
                        "rating":   rating,
                        "reviews":  review_count,
                        "url":      url,
                        "selected": True,
                    })

                    if progress_callback:
                        progress_callback(len(results), limit, f"Collected {len(results)} matches.")

                except StaleElementReferenceException:
                    continue
                except Exception as e:
                    logger.debug(f"[SCRAPER] Entry skip exception: {e}")
                    continue

            # Stall mitigation handling
            if len(results) == initial_count:
                scroll_attempts += 1
                
                # Dynamic nudge displacement injection pattern
                actions.scroll_from_origin(scroll_origin, 0, -350).perform()
                time.sleep(0.5)
                actions.scroll_from_origin(scroll_origin, 0, 900).perform()
                time.sleep(1.5)

                try:
                    end_banner = driver.find_element(By.CSS_SELECTOR, "span.HlvSq")
                    if end_banner and end_banner.is_displayed():
                        logger.info("[SCRAPER] Natural end of list reached.")
                        break
                except NoSuchElementException:
                    pass
            else:
                scroll_attempts = 0

        logger.info(f"[SCRAPER] Process completed successfully: saved {len(results)} items.")

    except Exception as e:
        logger.error(f"[SCRAPER] Structural crash: {e}")

    finally:
        if driver:
            driver.quit()

    return results