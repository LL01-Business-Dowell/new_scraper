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
    radius_km: float = 5,
    limit: int = 100,
    progress_callback: Optional[Callable] = None,
) -> List[Dict]:
    """
    Search Google Maps for businesses matching keyword in city.

    Selectors verified against Google Maps HTML June 2026:
      feed container : div.m6QErb[role="feed"]
      place card     : div.Nv2PK (role="article")
      place link/url : a.hfpxzc  (href contains /maps/place/)
      name           : div.qBF1Pd
      rating         : span.MW4etd
      review count   : span.UY7F9
      address line   : div.W4Efsd > div.W4Efsd > span > span (second W4Efsd block)

    Returns list of dicts with keys:
        name, address, rating, reviews, url, selected
    """
    driver = None
    results = []
    seen_urls = set()

    try:
        driver = init_driver()

        # Search URL — "100 cafe near me" style search scoped to city
        query = f"{keyword} in {city}"
        import urllib.parse
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

        # Get feed container for scrolling
        try:
            feed = driver.find_element(By.CSS_SELECTOR, "div.m6QErb[role='feed']")
        except NoSuchElementException:
            logger.error("[SCRAPER] Could not find feed container")
            return results

        stale_count = 0
        max_stale = 25

        while len(results) < limit and stale_count < max_stale:
            prev_count = len(results)

            # Scroll feed down
            driver.execute_script(
                "arguments[0].scrollTo(0, arguments[0].scrollHeight);", feed
            )
            time.sleep(random.uniform(2.5, 3.5))

            # Extract all visible place cards
            cards = driver.find_elements(By.CSS_SELECTOR, "div.Nv2PK")

            for card in cards:
                if len(results) >= limit:
                    break
                try:
                    # URL — from the anchor tag
                    try:
                        anchor = card.find_element(By.CSS_SELECTOR, "a.hfpxzc")
                        url = anchor.get_attribute("href") or ""
                    except NoSuchElementException:
                        url = ""

                    # Skip duplicates
                    if url and url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)

                    # Name
                    try:
                        name = card.find_element(By.CSS_SELECTOR, "div.qBF1Pd").text.strip()
                    except NoSuchElementException:
                        name = "Unknown"

                    if not name or name == "Unknown":
                        continue

                    # Rating
                    try:
                        rating_text = card.find_element(
                            By.CSS_SELECTOR, "span.MW4etd"
                        ).text.strip()
                        rating = float(rating_text) if rating_text else None
                    except (NoSuchElementException, ValueError):
                        rating = None

                    # Review count — strip brackets and commas: "(1,367)" → 1367
                    try:
                        review_text = card.find_element(
                            By.CSS_SELECTOR, "span.UY7F9"
                        ).text.strip()
                        review_count = int(re.sub(r"[^\d]", "", review_text))
                    except (NoSuchElementException, ValueError):
                        review_count = 0

                    # Address — second W4Efsd block inside the card
                    try:
                        address_spans = card.find_elements(
                            By.CSS_SELECTOR, "div.W4Efsd div.W4Efsd span span"
                        )
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
                        progress_callback(
                            len(results), limit, f"Found {len(results)} places..."
                        )

                except StaleElementReferenceException:
                    continue
                except Exception as e:
                    logger.warning(f"[SCRAPER] Card parse error: {e}")
                    continue

            if len(results) == prev_count:
                stale_count += 1
                logger.info(f"[SCRAPER] No new results (stale {stale_count}/{max_stale})")
            else:
                stale_count = 0

        logger.info(f"[SCRAPER] Done — found {len(results)} places")

    except Exception as e:
        logger.error(f"[SCRAPER] Fatal error: {e}")

    finally:
        if driver:
            driver.quit()

    return results