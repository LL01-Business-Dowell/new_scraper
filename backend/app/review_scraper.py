"""
review_scraper.py
-----------------
Robust Google Maps review scraper.

Key fixes vs previous versions:
1. Uses ?hl=en&view=reviews&sort=1 URL param to open the reviews panel
   (clicking a Reviews tab button is unreliable — this URL approach matches
   the original working Flask scraper exactly)
2. Clicks Sort → Newest after the panel opens so reviews are newest-first,
   making the days_back cutoff work correctly
3. Multiple fallback selectors for every element
4. Retries with fresh driver on total failure
"""

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


# ── Driver ────────────────────────────────────────────────────────────────────

def init_driver():
    """Initialize headless Chromium with anti-bot measures."""
    options = Options()
    options.binary_location = "/usr/bin/chromium"
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=en-US,en")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("prefs", {"intl.accept_languages": "en-US,en"})
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


# ── Date parsing ──────────────────────────────────────────────────────────────

def parse_relative_date(text: str) -> datetime.datetime:
    now = datetime.datetime.now()
    if not text:
        return now
    # Strip " on Google" / " on Maps" / " on Booking" etc.
    t = re.sub(r'\s+on\s+\w+$', '', text, flags=re.IGNORECASE)
    t = re.sub(r'\(edited\)', '', t.lower().strip()).replace("edited", "").replace("new", "").strip()
    if not t or t in ("recent", ""):
        return now
    if "just now" in t or "moment" in t:
        return now
    if "minute" in t:
        m = re.search(r"(\d+)", t)
        return now - datetime.timedelta(minutes=int(m.group(1)) if m else 1)
    if "hour" in t:
        m = re.search(r"(\d+)", t)
        return now - datetime.timedelta(hours=int(m.group(1)) if m else 1)
    if "today" in t:
        return now
    if "yesterday" in t:
        return now - datetime.timedelta(days=1)
    if "day" in t:
        m = re.search(r"(\d+)", t)
        return now - datetime.timedelta(days=int(m.group(1)) if m else 1)
    if "week" in t:
        m = re.search(r"(\d+)", t)
        return now - datetime.timedelta(weeks=int(m.group(1)) if m else 1)
    if "month" in t:
        m = re.search(r"(\d+)", t)
        return now - datetime.timedelta(days=30 * (int(m.group(1)) if m else 1))
    if "year" in t:
        m = re.search(r"(\d+)", t)
        return now - datetime.timedelta(days=365 * (int(m.group(1)) if m else 1))
    if "an " in t or "a " in t:
        if "hour" in t:
            return now - datetime.timedelta(hours=1)
        if "day" in t:
            return now - datetime.timedelta(days=1)
        if "week" in t:
            return now - datetime.timedelta(weeks=1)
        if "month" in t:
            return now - datetime.timedelta(days=30)
        if "year" in t:
            return now - datetime.timedelta(days=365)
    if HAS_DATEUTIL:
        try:
            return dateutil_parser.parse(t, fuzzy=True)
        except Exception:
            pass
    return now


# ── Business details ──────────────────────────────────────────────────────────

def extract_business_details(driver) -> Dict:
    details = {
        "name": "Unknown", "address": "", "phone": "",
        "website": "", "rating": None, "total_reviews": 0,
    }
    try:
        for sel in ["h1.DUwDvf", "h1.fontHeadlineLarge", "h1"]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el.text.strip():
                    details["name"] = el.text.strip()
                    break
            except Exception:
                continue

        for sel in ['[data-item-id="address"]', ".Io6YTe", ".rogA2c"]:
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


# ── Navigate to reviews ───────────────────────────────────────────────────────

def _navigate_to_reviews(driver):
    """
    Open the reviews panel. Strips existing URL params first,
    then reloads with ?hl=en&view=reviews&sort=1 on a clean base URL.
    """
    current_url = driver.current_url

    # Strip everything after ? to get a clean base URL
    base_url = current_url.split("?")[0]

    # Also strip fragment
    base_url = base_url.split("#")[0]

    reviews_url = f"{base_url}?hl=en&view=reviews&sort=1"
    logger.info(f"[REVIEW SCRAPER] Navigating to reviews: {reviews_url}")
    driver.get(reviews_url)
    time.sleep(5)


def _sort_by_newest(driver):
    """
    Click Sort → Newest so reviews load newest-first.
    Required for days_back cutoff to work: without this Maps shows
    'Most Relevant' which mixes old and new reviews unpredictably.
    Silently skips if the sort button can't be found.
    """
    try:
        sort_btn = None
        for sel in [
            '//button[@data-value="Sort"]',
            '//button[contains(@aria-label, "Sort")]',
            '//button[contains(@aria-label, "sort")]',
            '//span[text()="Sort"]/ancestor::button',
        ]:
            try:
                els = driver.find_elements(By.XPATH, sel)
                for el in els:
                    if el.is_displayed():
                        sort_btn = el
                        break
                if sort_btn:
                    break
            except Exception:
                continue

        if not sort_btn:
            logger.warning("[REVIEW SCRAPER] Sort button not found — skipping sort")
            return

        driver.execute_script("arguments[0].click();", sort_btn)
        time.sleep(2)

        newest = None
        for sel in [
            '//div[@role="menuitemradio" and contains(., "Newest")]',
            '//div[@role="menuitem" and contains(., "Newest")]',
            '//li[contains(., "Newest")]',
        ]:
            items = driver.find_elements(By.XPATH, sel)
            if items:
                newest = items[0]
                break

        if newest:
            driver.execute_script("arguments[0].click();", newest)
            logger.info("[REVIEW SCRAPER] Sorted by newest")
            time.sleep(3)
        else:
            logger.warning("[REVIEW SCRAPER] 'Newest' menu item not found")
            # Close menu by pressing Escape
            driver.find_element(By.TAG_NAME, "body").send_keys("\ue00c")
            time.sleep(1)

    except Exception as e:
        logger.warning(f"[REVIEW SCRAPER] Sort failed (non-fatal): {e}")


# ── Scrollable feed ───────────────────────────────────────────────────────────

def _find_scrollable_feed(driver):
    # Wait for feed with longer timeout
    for sel in [
        "div.m6QErb.XiKgde",
        'div.m6QErb[role="feed"]',
        'div[role="feed"]',
        "div.m6QErb.DxyBCb.kA9KIf",
        "div.m6QErb.DxyBCb",
        "div.m6QErb",
    ]:
        try:
            el = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, sel))
            )
            if el.is_displayed():
                logger.info(f"[REVIEW SCRAPER] Found feed with selector: {sel}")
                return el
        except Exception:
            continue

    # Last resort — check if ANY feed-like container exists
    try:
        els = driver.find_elements(By.CSS_SELECTOR, "div.m6QErb")
        for el in els:
            if el.is_displayed():
                logger.info("[REVIEW SCRAPER] Found feed via fallback div.m6QErb")
                return el
    except Exception:
        pass

    logger.warning("[REVIEW SCRAPER] No scrollable feed found")
    return None


# ── Review card extraction ────────────────────────────────────────────────────

def _extract_card(card) -> Optional[Dict]:
    """Extract all fields from a single review card. Returns None if card is unusable."""
    try:
        # Author
        author = "Google User"
        for sel in [".d4r55", "button.al6Kxe", ".TSUbDb", ".DUJq1d"]:
            try:
                t = card.find_element(By.CSS_SELECTOR, sel).text.strip()
                if t:
                    author = t
                    break
            except Exception:
                pass

        # Date
        date_str = "Recent"
        for sel in ["span.rsqaWe", ".rsqaWe", "span.dehysf", ".dehysf"]:
            try:
                t = card.find_element(By.CSS_SELECTOR, sel).text.strip()
                if t:
                    date_str = t
                    break
            except Exception:
                pass

        # Rating
        rating = None
        for sel in ["span.kvMYJc", 'span[aria-label*="star"]', 'span[aria-label*="Star"]']:
            try:
                aria = card.find_element(By.CSS_SELECTOR, sel).get_attribute("aria-label") or ""
                m = re.search(r"(\d+)", aria)
                if m:
                    rating = int(m.group(1))
                    break
            except Exception:
                pass

        # Review text
        review_text = ""
        for sel in ["span.wiI7pd", "div.MyEned span", ".wiI7pd", ".MyEned"]:
            try:
                t = card.find_element(By.CSS_SELECTOR, sel).text.strip()
                if t and t.upper() not in ("NEW", "TRANSLATE", "SEE MORE"):
                    review_text = t
                    break
            except Exception:
                pass
        if not review_text:
            review_text = "[Rating Only]"

        # Review ID — prefer DOM attribute, fall back to hash
        rev_id = card.get_attribute("data-review-id")
        if not rev_id:
            rev_id = f"{author}_{date_str}_{hashlib.md5(review_text.encode()).hexdigest()[:8]}"

        return {
            "rev_id": rev_id,
            "author": author,
            "rating": rating,
            "date": date_str,
            "text": review_text,
        }

    except StaleElementReferenceException:
        return None
    except Exception as e:
        logger.debug(f"[REVIEW SCRAPER] Card extraction error: {e}")
        return None


# ── Main scrape function ──────────────────────────────────────────────────────

def _scrape_reviews_with_driver(
    driver,
    url: str,
    max_reviews: int,
    days_back: int,
    progress_callback: Optional[Callable],
) -> Dict:
    """Core scraping logic using an already-initialized driver."""
    result = {"business_details": {}, "reviews": [], "error": None}
 
    driver.get(url)
    time.sleep(4)
 
    result["business_details"] = extract_business_details(driver)
    place_name = result["business_details"].get("name", "Unknown")
    logger.info(f"[REVIEW SCRAPER] Loaded: {place_name}")
 
    if progress_callback:
        progress_callback(0, max_reviews, f"Loaded {place_name}")
 
    # Step 1 — navigate to reviews via clean URL (strip existing params first)
    current_url = driver.current_url
    base_url    = current_url.split("?")[0].split("#")[0]
    reviews_url = f"{base_url}?hl=en&view=reviews&sort=1"
    logger.info(f"[REVIEW SCRAPER] Navigating to reviews: {reviews_url}")
    driver.get(reviews_url)
    time.sleep(5)
 
    # Step 2 — sort by newest
    _sort_by_newest(driver)
 
    # Step 3 — find scrollable feed
    scrollable = None
    for sel in [
        "div.m6QErb.XiKgde",
        'div.m6QErb[role="feed"]',
        'div[role="feed"]',
        "div.m6QErb.DxyBCb.kA9KIf",
        "div.m6QErb.DxyBCb",
        "div.m6QErb",
    ]:
        try:
            el = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, sel))
            )
            if el.is_displayed():
                logger.info(f"[REVIEW SCRAPER] Found feed: {sel}")
                scrollable = el
                break
        except Exception:
            continue
 
    if not scrollable:
        try:
            els = driver.find_elements(By.CSS_SELECTOR, "div.m6QErb")
            for el in els:
                if el.is_displayed():
                    scrollable = el
                    logger.info("[REVIEW SCRAPER] Found feed via fallback div.m6QErb")
                    break
        except Exception:
            pass
 
    if not scrollable:
        logger.warning(f"[REVIEW SCRAPER] No scrollable feed found for {place_name}")
 
    cutoff = datetime.datetime.now() - datetime.timedelta(days=days_back)
    reviews = []
    processed_ids = set()
    stale_count = 0
    consecutive_oob = 0
 
    for scroll_loop in range(80):
 
        # Expand "More" / "See more" buttons
        try:
            for btn in driver.find_elements(By.CSS_SELECTOR, "button.w8nwRe, button.M77dve")[:15]:
                try:
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].click();", btn)
                        time.sleep(0.1)
                except Exception:
                    pass
        except Exception:
            pass
 
        # Find review cards
        cards = []
        for card_sel in [
            'div.jftiEf[data-review-id]',
            'div[data-review-id]',
            'div.jftiEf',
            'div[role="article"]',
        ]:
            cards = driver.find_elements(By.CSS_SELECTOR, card_sel)
            if cards:
                break
 
        new_this_round = 0
        oob_this_round = 0
 
        for card in cards:
            if len(reviews) >= max_reviews:
                break
            try:
                # ── Author ────────────────────────────────────────────────────
                author = "Google User"
                for sel in [".d4r55", "button.al6Kxe", ".TSUbDb", ".DUJq1d"]:
                    try:
                        t = card.find_element(By.CSS_SELECTOR, sel).text.strip()
                        if t:
                            author = t
                            break
                    except Exception:
                        pass
 
                # ── Date — new selector is span.xRkPPb, strip "on Google" ───
                date_str = "Recent"
                for sel in ["span.xRkPPb", "span.rsqaWe", ".rsqaWe", "span.dehysf"]:
                    try:
                        t = card.find_element(By.CSS_SELECTOR, sel).text.strip()
                        if t:
                            # Strip " on Google" / " on Maps" suffix
                            t = re.sub(r'\s+on\s+\w+$', '', t, flags=re.IGNORECASE).strip()
                            date_str = t
                            break
                    except Exception:
                        pass
 
                # ── Rating — now "5/5" text format, aria-label as fallback ──
                rating = None
                # Try aria-label first (old format)
                for sel in ["span.kvMYJc", 'span[aria-label*="star"]', 'span[aria-label*="Star"]']:
                    try:
                        aria = card.find_element(By.CSS_SELECTOR, sel).get_attribute("aria-label") or ""
                        m = re.search(r"(\d+)", aria)
                        if m:
                            rating = int(m.group(1))
                            break
                    except Exception:
                        pass
                # Fallback — parse "5/5" text format (new format)
                if rating is None:
                    try:
                        for span in card.find_elements(By.CSS_SELECTOR, "span"):
                            t = span.text.strip()
                            m = re.match(r'^(\d)/5$', t)
                            if m:
                                rating = int(m.group(1))
                                break
                    except Exception:
                        pass
 
                # ── Review text ───────────────────────────────────────────────
                review_text = ""
                for sel in ["span.wiI7pd", "div.MyEned span", ".wiI7pd", ".MyEned"]:
                    try:
                        t = card.find_element(By.CSS_SELECTOR, sel).text.strip()
                        if t and t.upper() not in ("NEW", "TRANSLATE", "SEE MORE"):
                            review_text = t
                            break
                    except Exception:
                        pass
                if not review_text:
                    review_text = "[Rating Only]"
 
                # ── Review ID ─────────────────────────────────────────────────
                rev_id = card.get_attribute("data-review-id")
                if not rev_id:
                    rev_id = f"{author}_{date_str}_{hashlib.md5(review_text.encode()).hexdigest()[:8]}"
                if rev_id in processed_ids:
                    continue
 
                # ── Date cutoff ───────────────────────────────────────────────
                parsed_date = parse_relative_date(date_str)
                if parsed_date < cutoff:
                    oob_this_round += 1
                    continue
 
                processed_ids.add(rev_id)
                reviews.append({
                    "author": author,
                    "rating": rating,
                    "date":   date_str,
                    "text":   review_text,
                })
                new_this_round += 1
 
                if progress_callback:
                    progress_callback(len(reviews), max_reviews, f"Scraped {len(reviews)} reviews...")
 
            except StaleElementReferenceException:
                continue
            except Exception as e:
                logger.debug(f"[REVIEW SCRAPER] Card parse error: {e}")
                continue
 
        if oob_this_round > 0 and new_this_round == 0:
            consecutive_oob += 1
        else:
            consecutive_oob = 0
 
        if consecutive_oob >= 5:
            logger.info(f"[REVIEW SCRAPER] Hit {days_back}-day cutoff after {scroll_loop} scrolls")
            break
 
        if len(reviews) >= max_reviews:
            break
 
        # Scroll
        if scrollable:
            try:
                prev = driver.execute_script("return arguments[0].scrollTop", scrollable)
                driver.execute_script("arguments[0].scrollBy(0, 3000);", scrollable)
                time.sleep(random.uniform(2.0, 2.8))
                after = driver.execute_script("return arguments[0].scrollTop", scrollable)
                if after <= prev:
                    stale_count += 1
                    driver.execute_script("arguments[0].scrollBy(0, -1500);", scrollable)
                    time.sleep(0.8)
                    driver.execute_script("arguments[0].scrollBy(0, 3000);", scrollable)
                    time.sleep(2.0)
                else:
                    stale_count = 0
            except Exception:
                stale_count += 1
        else:
            prev_h = driver.execute_script("return document.documentElement.scrollHeight")
            driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight);")
            time.sleep(random.uniform(2.0, 2.8))
            new_h = driver.execute_script("return document.documentElement.scrollHeight")
            if new_h == prev_h and new_this_round == 0:
                stale_count += 1
            else:
                stale_count = 0
 
        if stale_count >= 10:
            logger.info(f"[REVIEW SCRAPER] Stale scroll limit after {scroll_loop} scrolls")
            break
 
    result["reviews"] = reviews
    logger.info(
        f"[REVIEW SCRAPER] Done — scraped {len(reviews)} reviews "
        f"for {place_name} (days_back={days_back})"
    )
    return result


def scrape_place_reviews(
    url: str,
    max_reviews: int = 50,
    days_back: int = 30,
    progress_callback: Optional[Callable] = None,
) -> Dict:
    """
    Scrape reviews for a single Google Maps place URL.

    Retries once with a fresh driver if the first attempt returns 0 reviews
    and no error — this handles transient page-load failures.

    Returns:
        {
            "business_details": {name, address, rating, total_reviews, ...},
            "reviews": [{"author", "rating", "date", "text"}, ...],
            "error": None | str
        }
    """
    if not url:
        return {"business_details": {}, "reviews": [], "error": "No URL provided"}

    # Attempt 1
    driver = None
    result = {"business_details": {}, "reviews": [], "error": None}
    try:
        driver = init_driver()
        result = _scrape_reviews_with_driver(driver, url, max_reviews, days_back, progress_callback)
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"[REVIEW SCRAPER] Fatal error (attempt 1) for {url}: {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    # Retry once if 0 reviews and no hard error — may be a transient load failure
    if len(result.get("reviews", [])) == 0 and not result.get("error"):
        logger.info(f"[REVIEW SCRAPER] 0 reviews on attempt 1 — retrying: {url}")
        driver2 = None
        try:
            time.sleep(3)
            driver2 = init_driver()
            result2 = _scrape_reviews_with_driver(driver2, url, max_reviews, days_back, progress_callback)
            if len(result2.get("reviews", [])) > 0 or result2.get("error"):
                result = result2
        except Exception as e:
            logger.error(f"[REVIEW SCRAPER] Fatal error (attempt 2) for {url}: {e}")
        finally:
            if driver2:
                try:
                    driver2.quit()
                except Exception:
                    pass

    return result