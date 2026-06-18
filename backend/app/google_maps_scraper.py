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

# Set logging level to see debug details in the terminal
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
        max_scroll_attempts = 25 
        max_total_scrolls = 120 
        
        actions = ActionChains(driver)
        scroll_origin = ScrollOrigin.from_element(feed)

        total_scrolls = 0
        max_stale = 25
        max_total = 120

        while len(results) < limit and scroll_attempts < max_scroll_attempts:
            total_scrolls += 1
            prev_count = len(results)
            
            # Read browser dimensions before moving
            js_scroll_top = driver.execute_script("return arguments[0].scrollTop;", feed)
            js_scroll_height = driver.execute_script("return arguments[0].scrollHeight;", feed)
            logger.info(f"[DEBUG] Pre-scroll metrics -> Top: {js_scroll_top}px, Full Height: {js_scroll_height}px")

            logger.info("[DEBUG] Executing physical mouse wheel actions...")
            for i in range(8):
                actions.scroll_from_origin(scroll_origin, 0, 1200).perform()
                time.sleep(random.uniform(0.3, 0.5))
                
            time.sleep(random.uniform(1.2, 1.8)) 
            
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

                    address = ""
                    try:
                        detail_spans = card.find_elements(By.CSS_SELECTOR, "div.W4Efsd div.W4Efsd > span")
                        span_texts = [s.text.strip() for s in detail_spans if s.text.strip()]
                        clean_elements = [txt for txt in span_texts if txt and txt != "·" and len(txt) > 2]
                        
                        if len(clean_elements) > 1:
                            address = clean_elements[-1].lstrip("· ").strip()
                        elif len(clean_elements) == 1:
                            address = clean_elements[0]
                    except Exception as addr_err:
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
                actions.scroll_from_origin(scroll_origin, 0, -2000).perform()
                time.sleep(0.8)
                actions.scroll_from_origin(scroll_origin, 0, 3000).perform()
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

    return results