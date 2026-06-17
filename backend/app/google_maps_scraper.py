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
    Scrolls progressively using small intervals to reliably trigger AJAX loads,
    continuing until the limit is matched or Google specifies no more listings exist.
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
        max_scroll_attempts = 35  
        
        while len(results) < limit and scroll_attempts < max_scroll_attempts:
            # Capture layout height prior to structural moving actions
            last_height = driver.execute_script("return arguments[0].scrollHeight", feed)
            
            # FIX 1: Progressive Human-Like Scrolling Sequence
            # Divides current height into 3 segments, executing scrolling steps incrementally.
            # This triggers Google's scroll listeners far more reliably than an instantaneous jump.
            for scroll_step in range(3):
                driver.execute_script(
                    f"arguments[0].scrollBy(0, {int(last_height / 3)});", feed
                )
                time.sleep(random.uniform(0.6, 1.0))
                
            # Bring viewport explicitly down to absolute container floor baseline
            driver.execute_script("arguments[0].scrollTo(0, arguments[0].scrollHeight);", feed)
            time.sleep(random.uniform(2.0, 3.0)) 
            
            # Check if the container grew or remained unchanged
            new_height = driver.execute_script("return arguments[0].scrollHeight", feed)
            
            # Extract and parse matching elements currently visible inside DOM layout
            cards = driver.find_elements(By.CSS_SELECTOR, "div.Nv2PK")
            prev_count = len(results)
            
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
                        review_count = int(re.sub(r"[^\d]", "", review_text))
                    except (NoSuchElementException, ValueError):
                        review_count = 0

                    # Address Extraction
                    try:
                        address_spans = card.find_elements(By.CSS_SELECTOR, "div.W4Efsd div.W4Efsd span span")
                        address = address_spans[1].text.strip() if len(address_spans) > 1 else ""
                    except (NoSuchElementException, IndexError):
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
            if len(results) == prev_count and new_height == last_height:
                scroll_attempts += 1
                logger.info(f"[SCRAPER] Container pending update (Stall cycle {scroll_attempts}/{max_scroll_attempts})")
                
                # FIX 2: Case-Insensitive Multi-String Boundary Termination Check
                source_html = driver.page_source.lower()
                if (
                    "you've reached the end of the list" in source_html 
                    or "no more results" in source_html
                ):
                    logger.info("[SCRAPER] Hard endpoint reached — Google Maps reports list end boundary.")
                    break
            else:
                # Reset instantly if items were scraped or structural growth occurred
                scroll_attempts = 0

        logger.info(f"[SCRAPER] Done — found {len(results)} places")

    except Exception as e:
        logger.error(f"[SCRAPER] Fatal error: {e}")

    finally:
        if driver:
            driver.quit()

    return results