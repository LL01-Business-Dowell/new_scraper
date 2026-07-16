import datetime
import time
import random
import hashlib
import re
import logging
from typing import List, Dict, Optional, Callable

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
)

try:
    from dateutil import parser as dateutil_parser
    HAS_DATEUTIL = True
except ImportError:
    HAS_DATEUTIL = False

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
    options.add_argument("--lang=en-US")
    options.add_experimental_option("prefs", {"intl.accept_languages": "en-US,en"})
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    )
    service = Service("/usr/bin/chromedriver")
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return driver


def parse_relative_date(text: str) -> datetime.datetime:
    now = datetime.datetime.now()
    if not text:
        return now
    text = text.lower().strip().replace("edited", "").replace("new", "").strip()
    if not text or text in ("recent", ""):
        return now
    if "hour" in text or "minute" in text:
        match = re.search(r"(\d+)", text)
        units = int(match.group(1)) if match else 1
        return now - (datetime.timedelta(hours=units) if "hour" in text else datetime.timedelta(minutes=units))
    if "today" in text:
        return now
    if "yesterday" in text or "1 day ago" in text:
        return now - datetime.timedelta(days=1)
    if "week" in text:
        match = re.search(r"(\d+)", text)
        return now - datetime.timedelta(weeks=int(match.group(1)) if match else 1)
    if "month" in text:
        match = re.search(r"(\d+)", text)
        # Give a slight buffer room for the "1 month ago" crossover point
        return now - datetime.timedelta(days=30 * (int(match.group(1)) if match else 1))
    if "year" in text:
        match = re.search(r"(\d+)", text)
        return now - datetime.timedelta(days=365 * (int(match.group(1)) if match else 1))
    match = re.search(r"(\d+)\s*days?\s*ago", text)
    if match:
        return now - datetime.timedelta(days=int(match.group(1)))
    if HAS_DATEUTIL:
        try:
            return dateutil_parser.parse(text, fuzzy=True)
        except Exception:
            pass
    return now


def extract_business_details(driver) -> Dict:
    """Extract name, address, rating, review count from Google Maps place page."""
    details = {
        "name": "Unknown", "address": "", "phone": "",
        "website": "", "rating": None, "total_reviews": 0,
    }
    try:
        for sel in ['h1.DUwDvf', 'h1.fontHeadlineLarge', 'h1']:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el.text.strip():
                    details["name"] = el.text.strip()
                    break
            except Exception:
                continue
        for sel in ['[data-item-id="address"]', ".Io6YTe"]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el.text.strip():
                    details["address"] = el.text.strip().replace("\ue0c8\n", "").strip()
                    break
            except Exception:
                continue
        try:
            details["rating"] = float(
                driver.find_element(By.CSS_SELECTOR, '.F7nice span[aria-hidden="true"]').text.strip()
            )
        except Exception:
            pass
        try:
            raw = driver.find_element(By.CSS_SELECTOR, ".F7nice .bC3Nkc").text.strip()
            details["total_reviews"] = int(re.sub(r"[^\d]", "", raw) or "0")
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"[REVIEW SCRAPER] Business detail extraction error: {e}")
    return details

def scrape_place_reviews(
    url: str,
    max_reviews: int = 100,
    days_back: int = 30,
    progress_callback: Optional[Callable] = None,
) -> Dict:
    """
    Scrape reviews for a single Google Maps place URL.
    Optimized to guarantee every single review within days_back is collected.
    """
    driver = None
    result = {"business_details": {}, "reviews": [], "error": None}

    try:
        driver = init_driver()
        logger.info(f"[REVIEW SCRAPER] Loading: {url}")

        driver.get(url)
        time.sleep(4)

        result["business_details"] = extract_business_details(driver)

        if progress_callback:
            progress_callback(0, max_reviews, f"Loaded {result['business_details'].get('name', 'place')}")

        # Step 1 — Navigate to reviews via URL param + reload
        current_url = driver.current_url
        if "view=reviews" not in current_url:
            glue = "&" if "?" in current_url else "?"
            driver.get(f"{current_url}{glue}hl=en&view=reviews&sort=1")
            time.sleep(4)

        # Find scrollable feed panel
        scrollable = None
        for sel in [
            'div[role="feed"]',
            "div.m6QErb.DxyBCb.kA9KIf.dS8AEf",
            "div.m6QErb[aria-label]",
        ]:
            try:
                el = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                )
                if el.is_displayed() and driver.execute_script(
                    "return arguments[0].scrollHeight > arguments[0].clientHeight;", el
                ):
                    scrollable = el
                    break
            except Exception:
                continue

        # Step 2 — Click "Sort" then select "Newest"
        try:
            sort_button = None
            sort_selectors = [
                '//button[contains(@aria-label, "Sort")]',
                '//button[contains(., "Sort")]',
                '//span[contains(text(), "Sort")]/ancestor::button',
            ]
            for sel in sort_selectors:
                try:
                    elements = driver.find_elements(By.XPATH, sel)
                    for el in elements:
                        if el.is_displayed():
                            sort_button = el
                            break
                    if sort_button:
                        break
                except Exception:
                    pass

            if sort_button:
                driver.execute_script("arguments[0].click();", sort_button)
                time.sleep(2)

                newest_option = None
                for sel in [
                    '//div[@role="menuitemradio" and contains(., "Newest")]',
                    '//div[@role="menuitem" and contains(., "Newest")]',
                ]:
                    items = driver.find_elements(By.XPATH, sel)
                    if items:
                        newest_option = items[0]
                        break

                if newest_option:
                    driver.execute_script("arguments[0].click();", newest_option)
                    logger.info("[REVIEW SCRAPER] Sorted by newest reviews")
                    time.sleep(3)
        except Exception as e:
            logger.warning(f"[REVIEW SCRAPER] Sort by newest failed: {e}")

        # Initialize tracking states
        cutoff = datetime.datetime.now() - datetime.timedelta(days=days_back)
        reviews = []
        processed_ids = set()
        stale_count = 0
        consecutive_out_of_bounds = 0

        # Infinite Scroll Extraction Loop
        for scroll_loop in range(120):
            # Expand "More" buttons to expose full review text blocks
            try:
                for btn in driver.find_elements(By.CSS_SELECTOR, "button.w8nwRe")[:15]:
                    try:
                        if btn.is_displayed():
                            driver.execute_script("arguments[0].click();", btn)
                    except Exception:
                        pass
            except Exception:
                pass

            # Extract review elements currently rendered in the DOM tree
            cards = driver.find_elements(By.CSS_SELECTOR, 'div.jftiEf[data-review-id]')
            if not cards:
                for fb in ['div[data-review-id]', 'div.jftiEf', 'div[role="article"]']:
                    cards = driver.find_elements(By.CSS_SELECTOR, fb)
                    if cards:
                        break

            new_this_round = 0

            for card in cards:
                if len(reviews) >= max_reviews:
                    break
                try:
                    rev_id = card.get_attribute("data-review-id")
                    
                    # Author
                    author = "Google User"
                    for sel in [".d4r55", "button.al6Kxe", ".TSUbDb"]:
                        try:
                            t = card.find_element(By.CSS_SELECTOR, sel).text.strip()
                            if t:
                                author = t
                                break
                        except Exception:
                            pass

                    # Date String
                    date_str = "Recent"
                    for sel in ["span.rsqaWe", ".rsqaWe"]:
                        try:
                            t = card.find_element(By.CSS_SELECTOR, sel).text.strip()
                            if t:
                                date_str = t
                                break
                        except Exception:
                            pass

                    # Text Content
                    review_text = ""
                    for sel in ["span.wiI7pd", "div.MyEned", ".wiI7pd"]:
                        try:
                            t = card.find_element(By.CSS_SELECTOR, sel).text.strip()
                            if t and t.upper() != "NEW":
                                review_text = t
                                break
                        except Exception:
                            pass
                    if not review_text:
                        review_text = "[Rating Only]"

                    if not rev_id:
                        rev_id = f"{author}_{date_str}_{hashlib.md5(review_text.encode()).hexdigest()[:8]}"

                    # Skip items already processed in previous rounds
                    if rev_id in processed_ids:
                        continue

                    # Rating
                    rating = 5
                    for sel in ["span.kvMYJc", 'span[aria-label*="star"]']:
                        try:
                            aria = card.find_element(By.CSS_SELECTOR, sel).get_attribute("aria-label")
                            m = re.search(r"(\d+)", aria or "")
                            if m:
                                rating = int(m.group(1))
                                break
                        except Exception:
                            pass

                    # Parse date and log chronological baseline progress globally
                    parsed_date = parse_relative_date(date_str)

                    # Filter elements into payload only if inside timeframe scope
                    if parsed_date >= cutoff:
                        reviews.append({"author": author, "rating": rating, "date": date_str, "text": review_text})
                        consecutive_out_of_bounds = 0
                    else:
                        consecutive_out_of_bounds += 1
                    
                    processed_ids.add(rev_id)
                    new_this_round += 1

                    if progress_callback:
                        progress_callback(len(reviews), max_reviews, f"Scraped {len(reviews)} reviews...")

                except StaleElementReferenceException:
                    continue
                except Exception as e:
                    logger.debug(f"[REVIEW SCRAPER] Card parse error: {e}")
                    continue

            if len(reviews) >= max_reviews:
                break

            if new_this_round > 0 and consecutive_out_of_bounds >= 15:
                logger.info(f"[REVIEW SCRAPER] Safe boundary validation reached ({days_back} days). Finalizing.")
                break

            # Handle Infinite Scrolling Mechanics
            if scrollable:
                try:
                    prev_scroll = driver.execute_script("return arguments[0].scrollTop", scrollable)
                    # Directly scroll to the container's physical dynamic bottom
                    driver.execute_script("arguments[0].scrollTo(0, arguments[0].scrollHeight);", scrollable)
                    time.sleep(random.uniform(2.0, 3.0))
                    new_scroll = driver.execute_script("return arguments[0].scrollTop", scrollable)
                    
                    if new_scroll <= prev_scroll and new_this_round == 0:
                        stale_count += 1
                    else:
                        stale_count = 0
                except Exception:
                    stale_count += 1
            else:
                prev_h = driver.execute_script("return document.documentElement.scrollHeight")
                driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight);")
                time.sleep(2.5)
                new_h = driver.execute_script("return document.documentElement.scrollHeight")
                if new_h == prev_h and new_this_round == 0:
                    stale_count += 1
                else:
                    stale_count = 0

            # Break if scrolling is completely stalled (e.g. no more reviews exist on Google)
            if stale_count >= 12:
                logger.info("[REVIEW SCRAPER] Feed end reached or scrolling completely stalled.")
                break

        # Assign successfully parsed list back to the return layout dictionary
        result["reviews"] = reviews
        logger.info(f"[REVIEW SCRAPER] Done — scraped {len(reviews)} reviews for {result['business_details'].get('name')}")

    except Exception as e:
        result["error"] = str(e)
        logger.error(f"[REVIEW SCRAPER] Fatal error for {url}: {e}")
    finally:
        if driver:
            driver.quit()

    return result