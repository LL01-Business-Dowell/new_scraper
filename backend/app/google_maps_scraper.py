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
    progress_callback: Optional[Callable] = None,
) -> List[Dict]:
    """
    Search Google Maps for businesses matching keyword in city.
    Scrolls progressively using hardware ActionChains mouse wheel inputs to natively 
    trigger AJAX payloads and break virtualization limits.
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

        # Wait for the results feed to appear
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "div.m6QErb[role='feed']")
                )
            )
        except TimeoutException:
            logger.error("[SCRAPER] Results feed did not load within 20s")
            return results

        time.sleep(2)

        # Get feed container for scrolling operations
        try:
            feed = driver.find_element(By.CSS_SELECTOR, "div.m6QErb[role='feed']")
        except NoSuchElementException:
            logger.error("[SCRAPER] Could not find feed container")
            return results

        scroll_attempts = 0
        max_scroll_attempts = 45  
        
        # Instantiate continuous browser Action Context
        actions = ActionChains(driver)
        # Create an origin point directly inside the sidebar feed layout component
        scroll_origin = ScrollOrigin.from_element(feed)

        while len(results) < limit and scroll_attempts < max_scroll_attempts:
            prev_count = len(results)
            
            # PHYSICAL MOUSE SCROLL INPUTS
            # Emulates continuous wheel turns directly over the targeted container element
            for _ in range(5):
                actions.scroll_from_origin(scroll_origin, 0, 750).perform()
                time.sleep(random.uniform(0.5, 0.8))
                
            # Wait time for elements to load asynchronously over the network
            time.sleep(random.uniform(2.5, 3.5)) 
            
            # Extract and parse matching elements currently visible inside DOM layout
            cards = driver.find_elements(By.CSS_SELECTOR, "div.Nv2PK")
            
            for card in cards:
                if len(results) >= limit:
                    break
                try:
                    # URL Extraction
                    try:
                        anchor = card.find_element(By.CSS_SELECTOR, "a.hfpxzc")
                        url = anchor.get_attribute("href") or ""
                    except NoSuchElementException:
                        url = ""

                    # Skip duplicate entries
                    if url and url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)

                    # Name Extraction
                    try:
                        name = card.find_element(By.CSS_SELECTOR, "div.qBF1Pd").text.strip()
                    except NoSuchElementException:
                        name = "Unknown"

                    if not name or name == "Unknown":
                        continue

                    # Rating Extraction
                    try:
                        rating_text = card.find_element(By.CSS_SELECTOR, "span.MW4etd").text.strip()
                        rating = float(rating_text) if rating_text else None
                    except (NoSuchElementException, ValueError):
                        rating = None

                    # Review Count Extraction
                    try:
                        review_text = card.find_element(By.CSS_SELECTOR, "span.UY7F9").text.strip()
                        review_count = int(re.sub(r"[^\d]", "", review_text)) if review_text else 0
                    except (NoSuchElementException, ValueError):
                        review_count = 0

                    # Resilient Fallback Address Processing Logic
                    address = ""
                    try:
                        detail_spans = card.find_elements(By.CSS_SELECTOR, "div.W4Efsd div.W4Efsd > span")
                        span_texts = [s.text.strip() for s in detail_spans if s.text.strip()]
                        clean_elements = [txt for txt in span_texts if txt and txt != "·" and len(txt) > 2]
                        
                        if len(clean_elements) > 1:
                            raw_address = clean_elements[-1]
                            address = raw_address.lstrip("· ").strip()
                        elif len(clean_elements) == 1:
                            address = clean_elements[0]
                    except Exception as addr_err:
                        logger.debug(f"[SCRAPER] Address array exception, falling back to empty text: {addr_err}")
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
                        progress_callback(len(results), limit, f"Found {len(results)} places...")

                except StaleElementReferenceException:
                    continue
                except Exception as e:
                    logger.warning(f"[SCRAPER] Card parse error: {e}")
                    continue

            # Check if execution stalled
            if len(results) == prev_count:
                scroll_attempts += 1
                logger.info(f"[SCRAPER] Container pending update (Stall cycle {scroll_attempts}/{max_scroll_attempts})")
                
                # PHYSICAL NUDGE STRATEGY:
                # Perform a slight backward mouse wheel pull up, then push down hard to break layout deadlocks.
                actions.scroll_from_origin(scroll_origin, 0, -400).perform()
                time.sleep(0.6)
                actions.scroll_from_origin(scroll_origin, 0, 1000).perform()
                time.sleep(2.0)

                # Native endpoint tracking by targeted element checking
                try:
                    end_banner = driver.find_element(By.CSS_SELECTOR, "span.HlvSq")
                    if end_banner and end_banner.is_displayed():
                        logger.info("[SCRAPER] Hard endpoint reached via Maps End Banner element.")
                        break
                except NoSuchElementException:
                    pass
            else:
                # Reset instantly if tracking list progressed
                scroll_attempts = 0

        logger.info(f"[SCRAPER] Done — found {len(results)} places")

    except Exception as e:
        logger.error(f"[SCRAPER] Fatal error: {e}")

    finally:
        if driver:
            driver.quit()

    return results