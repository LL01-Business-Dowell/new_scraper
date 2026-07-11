"""
single_review_scraper.py
------------------------
Dedicated scraper for a single Google Maps establishment.
Scrapes ALL reviews for the last 12 months (days_back=365).

Completely separate from review_scraper.py which is used by the
competitor analysis pipeline. Do not merge these files.

Key behaviour:
- Navigates to place URL, appends ?hl=en&view=reviews&sort=1
- Sorts by Newest so cutoff works correctly
- Scrolls until 12-month cutoff hit or max_reviews reached
- Returns full review list + business details + sentiment breakdown
"""

import datetime
import time
import random
import hashlib
import re
import logging
from typing import Dict, List, Optional, Callable

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException, NoSuchElementException, TimeoutException

try:
    from dateutil import parser as dateutil_parser
    HAS_DATEUTIL = True
except ImportError:
    HAS_DATEUTIL = False

try:
    from nltk.sentiment import SentimentIntensityAnalyzer
    sia = SentimentIntensityAnalyzer()
except Exception:
    sia = None

logger = logging.getLogger(__name__)


# ── Driver ────────────────────────────────────────────────────────────────────

def _init_driver():
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

    options.add_experimental_option(
        "prefs",
        {
            "intl.accept_languages": "en-US,en"
        },
    )

    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    )

    service = Service("/usr/bin/chromedriver")

    driver = webdriver.Chrome(
        service=service,
        options=options,
    )

    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            """
        },
    )

    return driver


# ── Date parsing ──────────────────────────────────────────────────────────────

def _parse_relative_date(text: str) -> datetime.datetime:
    now = datetime.datetime.now()

    if not text:
        return now

    text = text.lower().strip()
    text = re.sub(r"\(edited\)", "", text)
    text = text.replace("edited", "").replace("new", "").strip()

    if not text or text == "recent":
        return now

    if "just now" in text or "moment" in text:
        return now

    if "minute" in text:
        m = re.search(r"(\d+)", text)
        return now - datetime.timedelta(minutes=int(m.group(1)) if m else 1)

    if "hour" in text:
        m = re.search(r"(\d+)", text)
        return now - datetime.timedelta(hours=int(m.group(1)) if m else 1)

    if "today" in text:
        return now

    if "yesterday" in text:
        return now - datetime.timedelta(days=1)

    if "day" in text:
        m = re.search(r"(\d+)", text)
        return now - datetime.timedelta(days=int(m.group(1)) if m else 1)

    if "week" in text:
        m = re.search(r"(\d+)", text)
        return now - datetime.timedelta(weeks=int(m.group(1)) if m else 1)

    if "month" in text:
        m = re.search(r"(\d+)", text)
        return now - datetime.timedelta(days=30 * (int(m.group(1)) if m else 1))

    if "year" in text:
        m = re.search(r"(\d+)", text)
        return now - datetime.timedelta(days=365 * (int(m.group(1)) if m else 1))

    if HAS_DATEUTIL:
        try:
            return dateutil_parser.parse(text, fuzzy=True)
        except Exception:
            pass

    return now


# ── Business details ──────────────────────────────────────────────────────────

def _extract_business_details(driver) -> Dict:
    details = {
        "name": "Unknown",
        "address": "",
        "phone": "",
        "website": "",
        "rating": None,
        "total_reviews": 0,
    }

    try:
        # Name
        for sel in [
            "h1.DUwDvf",
            "h1.fontHeadlineLarge",
            "h1",
        ]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el.text.strip():
                    details["name"] = el.text.strip()
                    break
            except Exception:
                continue

        # Address
        for sel in [
            '[data-item-id="address"]',
            ".Io6YTe",
            ".rogA2c",
        ]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el.text.strip():
                    details["address"] = (
                        el.text.strip()
                        .replace("\ue0c8\n", "")
                        .strip()
                    )
                    break
            except Exception:
                continue

        # Rating
        try:
            details["rating"] = float(
                driver.find_element(
                    By.CSS_SELECTOR,
                    '.F7nice span[aria-hidden="true"]'
                ).text.strip()
            )
        except Exception:
            pass

        # Total reviews
        try:
            raw = driver.find_element(
                By.CSS_SELECTOR,
                ".F7nice .bC3Nkc"
            ).text.strip()

            details["total_reviews"] = int(
                re.sub(r"[^\d]", "", raw) or "0"
            )
        except Exception:
            pass

    except Exception as e:
        logger.warning(
            f"[SINGLE SCRAPER] Business detail extraction error: {e}"
        )

    return details

def _navigate_to_reviews(driver):
    """
    Open the reviews panel by appending ?hl=en&view=reviews&sort=1
    to the URL.
    """
    current_url = driver.current_url

    if "view=reviews" not in current_url:
        glue = "&" if "?" in current_url else "?"
        new_url = f"{current_url}{glue}hl=en&view=reviews&sort=1"

        logger.info(f"[SINGLE SCRAPER] Navigating to reviews: {new_url}")

        driver.get(new_url)
        time.sleep(4)
    else:
        logger.info("[SINGLE SCRAPER] Already on reviews URL")


def _sort_by_newest(driver):
    """
    Click Sort → Newest so reviews load newest-first.
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
            logger.warning("[SINGLE SCRAPER] Sort button not found")
            return

        driver.execute_script(
            "arguments[0].click();",
            sort_btn,
        )

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
            driver.execute_script(
                "arguments[0].click();",
                newest,
            )

            logger.info("[SINGLE SCRAPER] Sorted by newest")

            time.sleep(3)

        else:
            logger.warning("[SINGLE SCRAPER] 'Newest' menu item not found")

            driver.find_element(
                By.TAG_NAME,
                "body",
            ).send_keys("\ue00c")

            time.sleep(1)

    except Exception as e:
        logger.warning(
            f"[SINGLE SCRAPER] Sort failed (non-fatal): {e}"
        )

def _find_scrollable_feed(driver):

    for sel in [
        'div.m6QErb[role="feed"]',
        'div[role="feed"]',
        "div.m6QErb.DxyBCb.kA9KIf",
        "div.m6QErb.DxyBCb",
        "div.m6QErb[aria-label]",
    ]:
        try:
            el = WebDriverWait(driver, 6).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, sel)
                )
            )

            if el.is_displayed():
                return el

        except Exception:
            continue

    return None

def _extract_card(card) -> Optional[Dict]:
    """
    Extract all fields from a single review card.
    Returns None if card cannot be parsed.
    """

    try:

        # Author
        author = "Google User"

        for sel in [
            ".d4r55",
            "button.al6Kxe",
            ".TSUbDb",
            ".DUJq1d",
        ]:
            try:
                t = card.find_element(
                    By.CSS_SELECTOR,
                    sel,
                ).text.strip()

                if t:
                    author = t
                    break

            except Exception:
                pass

        # Date
        date_str = "Recent"

        for sel in [
            "span.rsqaWe",
            ".rsqaWe",
            "span.dehysf",
            ".dehysf",
        ]:
            try:
                t = card.find_element(
                    By.CSS_SELECTOR,
                    sel,
                ).text.strip()

                if t:
                    date_str = t
                    break

            except Exception:
                pass

        # Rating
        rating = None

        for sel in [
            "span.kvMYJc",
            'span[aria-label*="star"]',
            'span[aria-label*="Star"]',
        ]:
            try:
                aria = card.find_element(
                    By.CSS_SELECTOR,
                    sel,
                ).get_attribute("aria-label") or ""

                m = re.search(r"(\d+)", aria)

                if m:
                    rating = int(m.group(1))
                    break

            except Exception:
                pass

        # Review text
        review_text = ""

        for sel in [
            "span.wiI7pd",
            "div.MyEned span",
            ".wiI7pd",
            ".MyEned",
        ]:
            try:
                t = card.find_element(
                    By.CSS_SELECTOR,
                    sel,
                ).text.strip()

                if t and t.upper() not in (
                    "NEW",
                    "TRANSLATE",
                    "SEE MORE",
                ):
                    review_text = t
                    break

            except Exception:
                pass

        if not review_text:
            review_text = "[Rating Only]"

        rev_id = card.get_attribute("data-review-id")

        if not rev_id:
            rev_id = (
                f"{author}_{date_str}_"
                f"{hashlib.md5(review_text.encode()).hexdigest()[:8]}"
            )

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
        logger.debug(f"[SINGLE SCRAPER] Card extraction error: {e}")
        return None
    



# ── Sentiment analysis ────────────────────────────────────────────────────────

def _run_sentiment_analysis(reviews: List[Dict]) -> Dict:
    """
    Run VADER sentiment on all scraped reviews.
    Returns a comprehensive sentiment breakdown.
    """
    if not reviews or not sia:
        return {
            "overall_score": 0,
            "overall_label": "Unknown",
            "positive_count": 0,
            "neutral_count": 0,
            "negative_count": 0,
            "avg_rating": None,
            "rating_distribution": {"5": 0, "4": 0, "3": 0, "2": 0, "1": 0},
            "monthly_breakdown": {},
            "top_positive_phrases": [],
            "top_negative_phrases": [],
            "keyword_themes": {},
        }

    texts = [r["text"] for r in reviews if r.get("text") and r["text"] != "[Rating Only]"]
    scores = []
    positive_count = 0
    neutral_count = 0
    negative_count = 0

    if texts and sia:
        for text in texts:
            score = sia.polarity_scores(text)["compound"]
            scores.append(score)
            if score > 0.2:
                positive_count += 1
            elif score < -0.2:
                negative_count += 1
            else:
                neutral_count += 1

    overall_score = round(sum(scores) / len(scores), 3) if scores else 0

    if overall_score > 0.5:
        overall_label = "Very Positive"
    elif overall_score > 0.2:
        overall_label = "Positive"
    elif overall_score > -0.2:
        overall_label = "Mixed / Neutral"
    elif overall_score > -0.5:
        overall_label = "Negative"
    else:
        overall_label = "Very Negative"

    # Rating distribution
    rating_dist = {"5": 0, "4": 0, "3": 0, "2": 0, "1": 0}
    ratings = [r["rating"] for r in reviews if r.get("rating") is not None]
    avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else None
    for r in ratings:
        key = str(min(5, max(1, int(round(r)))))
        rating_dist[key] = rating_dist.get(key, 0) + 1

    # Monthly breakdown
    monthly = {}
    for review in reviews:
        parsed = _parse_relative_date(review.get("date", ""))
        month_key = parsed.strftime("%Y-%m")
        if month_key not in monthly:
            monthly[month_key] = {"count": 0, "total_score": 0, "ratings": []}
        monthly[month_key]["count"] += 1
        if review.get("text") and review["text"] != "[Rating Only]" and sia:
            sc = sia.polarity_scores(review["text"])["compound"]
            monthly[month_key]["total_score"] += sc
        if review.get("rating") is not None:
            monthly[month_key]["ratings"].append(review["rating"])

    monthly_breakdown = {}
    for month, data in sorted(monthly.items()):
        avg_sc = round(data["total_score"] / data["count"], 3) if data["count"] else 0
        avg_rt = round(sum(data["ratings"]) / len(data["ratings"]), 1) if data["ratings"] else None
        monthly_breakdown[month] = {
            "count": data["count"],
            "avg_sentiment": avg_sc,
            "avg_rating": avg_rt,
        }

    # Keyword themes
    combined = " ".join(texts).lower()
    keyword_themes = {
        "Food & Quality":   sum(combined.count(w) for w in ["food", "taste", "fresh", "quality", "flavour", "delicious", "amazing", "bland", "stale"]),
        "Service":          sum(combined.count(w) for w in ["service", "staff", "friendly", "rude", "helpful", "attentive", "slow", "fast"]),
        "Ambiance":         sum(combined.count(w) for w in ["ambiance", "atmosphere", "decor", "cozy", "noisy", "comfortable", "vibe", "place"]),
        "Value & Pricing":  sum(combined.count(w) for w in ["price", "expensive", "cheap", "value", "worth", "overpriced", "affordable", "costly"]),
        "Wait Time":        sum(combined.count(w) for w in ["wait", "queue", "slow", "quick", "fast", "long", "delay", "time"]),
        "Cleanliness":      sum(combined.count(w) for w in ["clean", "dirty", "hygiene", "neat", "tidy", "messy", "spotless"]),
    }

    # Top positive and negative review snippets (first 100 chars)
    scored_reviews = []
    for review in reviews:
        if review.get("text") and review["text"] != "[Rating Only]" and sia:
            sc = sia.polarity_scores(review["text"])["compound"]
            scored_reviews.append((sc, review["text"][:120].strip(), review.get("author", ""), review.get("date", "")))

    scored_reviews.sort(key=lambda x: x[0], reverse=True)
    top_positive = [{"score": s, "text": t, "author": a, "date": d} for s, t, a, d in scored_reviews[:5]]
    top_negative = [{"score": s, "text": t, "author": a, "date": d} for s, t, a, d in scored_reviews[-5:] if s < 0]

    return {
        "overall_score":        overall_score,
        "overall_label":        overall_label,
        "positive_count":       positive_count,
        "neutral_count":        neutral_count,
        "negative_count":       negative_count,
        "total_with_text":      len(texts),
        "avg_rating":           avg_rating,
        "rating_distribution":  rating_dist,
        "monthly_breakdown":    monthly_breakdown,
        "top_positive_phrases": top_positive,
        "top_negative_phrases": top_negative,
        "keyword_themes":       keyword_themes,
    }


def _scrape_reviews_with_driver(
    driver,
    url: str,
    days_back: int,
    progress_callback: Optional[Callable],
) -> Dict:
    """
    Core scraping logic using an already initialized driver.
    """
    result = {
        "business_details": {},
        "reviews": [],
        "error": None,
    }

    driver.get(url)
    time.sleep(4)

    result["business_details"] = _extract_business_details(driver)

    place_name = result["business_details"].get("name", "Unknown")

    logger.info(f"[SINGLE SCRAPER] Loaded: {place_name}")

    if progress_callback:
        progress_callback(0, f"Loaded {place_name}")

    # Step 1
    _navigate_to_reviews(driver)

    # Step 2
    _sort_by_newest(driver)

    # Step 3
    scrollable = _find_scrollable_feed(driver)

    if not scrollable:
        logger.warning(
            f"[SINGLE SCRAPER] No scrollable feed found for {place_name}"
        )

    cutoff = datetime.datetime.now() - datetime.timedelta(days=days_back)

    reviews = []
    processed_ids = set()

    stale_count = 0
    consecutive_oob = 0

    scroll_loop = 0

    while True:
        scroll_loop += 1

        #
        # Expand "See More"
        #
        try:
            for btn in driver.find_elements(
                By.CSS_SELECTOR,
                "button.w8nwRe, button.M77dve",
            )[:15]:
                try:
                    if btn.is_displayed():
                        driver.execute_script(
                            "arguments[0].click();",
                            btn,
                        )
                        time.sleep(0.1)
                except Exception:
                    pass
        except Exception:
            pass

        #
        # Find review cards
        #
        cards = []

        for card_sel in [
            'div.jftiEf[data-review-id]',
            'div[data-review-id]',
            'div.jftiEf',
            'div[role="article"]',
        ]:
            cards = driver.find_elements(
                By.CSS_SELECTOR,
                card_sel,
            )

            if cards:
                break

        new_this_round = 0
        oob_this_round = 0

        for card in cards:

            data = _extract_card(card)

            if data is None:
                continue

            rev_id = data["rev_id"]

            if rev_id in processed_ids:
                continue

            parsed_date = _parse_relative_date(data["date"])

            if parsed_date < cutoff:
                oob_this_round += 1
                continue

            processed_ids.add(rev_id)

            reviews.append(
                {
                    "author": data["author"],
                    "rating": data["rating"],
                    "date": data["date"],
                    "text": data["text"],
                }
            )

            new_this_round += 1
            consecutive_oob = 0

            if progress_callback:
                progress_callback(
                    0,
                    0,
                    f"Scraped {len(reviews)} reviews..."
                )

        #
        # Cutoff detection
        #
        if oob_this_round > 0 and new_this_round == 0:
            consecutive_oob += 1
        else:
            consecutive_oob = 0

        if consecutive_oob >= 5:
            logger.info(
                f"[SINGLE SCRAPER] Hit {days_back}-day cutoff "
                f"after {scroll_loop} scrolls"
            )
            break

        #
        # Scroll
        #
        if scrollable:

            try:
                prev = driver.execute_script(
                    "return arguments[0].scrollTop",
                    scrollable,
                )

                driver.execute_script(
                    "arguments[0].scrollBy(0,3000);",
                    scrollable,
                )

                time.sleep(random.uniform(2.0, 2.8))

                after = driver.execute_script(
                    "return arguments[0].scrollTop",
                    scrollable,
                )

                if after <= prev:

                    stale_count += 1

                    driver.execute_script(
                        "arguments[0].scrollBy(0,-1500);",
                        scrollable,
                    )

                    time.sleep(0.8)

                    driver.execute_script(
                        "arguments[0].scrollBy(0,3000);",
                        scrollable,
                    )

                    time.sleep(2.0)

                else:
                    stale_count = 0

            except Exception:
                stale_count += 1

        else:

            prev_h = driver.execute_script(
                "return document.documentElement.scrollHeight"
            )

            driver.execute_script(
                "window.scrollTo(0, document.documentElement.scrollHeight);"
            )

            time.sleep(random.uniform(2.0, 2.8))

            new_h = driver.execute_script(
                "return document.documentElement.scrollHeight"
            )

            if new_h == prev_h and new_this_round == 0:
                stale_count += 1
            else:
                stale_count = 0

        if stale_count >= 10:
            logger.info(
                f"[SINGLE SCRAPER] "
                f"Stale scroll limit reached after {scroll_loop} scrolls"
            )
            break

    result["reviews"] = reviews

    logger.info(
        f"[SINGLE SCRAPER] Done — scraped {len(reviews)} reviews "
        f"for {place_name}"
    )

    return result

# ── Main scrape function ──────────────────────────────────────────────────────

def scrape_single_establishment(
    url: str,
    days_back: int = 365,
    progress_callback: Optional[Callable] = None,
) -> Dict:
    """
    Scrape all reviews for a single Google Maps establishment.

    Returns:
        {
            "business_details": {...},
            "reviews": [...],
            "sentiment": {...},
            "scraped_at": "...",
            "error": None | str
        }
    """

    if not url:
        return {
            "business_details": {},
            "reviews": [],
            "sentiment": {},
            "scraped_at": datetime.datetime.utcnow().isoformat() + "Z",
            "error": "No URL provided",
        }

    result = {
        "business_details": {},
        "reviews": [],
        "sentiment": {},
        "scraped_at": datetime.datetime.utcnow().isoformat() + "Z",
        "error": None,
    }

    #
    # First attempt
    #
    driver = None

    try:
        driver = _init_driver()

        result = _scrape_reviews_with_driver(
            driver,
            url,
            days_back,
            progress_callback,
        )

    except Exception as e:
        result["error"] = str(e)
        logger.error(
            f"[SINGLE SCRAPER] Fatal error (attempt 1) for {url}: {e}"
        )

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    #
    # Retry once if we received zero reviews but no hard error
    #
    if (
        len(result.get("reviews", [])) == 0
        and not result.get("error")
    ):

        logger.info(
            f"[SINGLE SCRAPER] 0 reviews on attempt 1 — retrying: {url}"
        )

        driver2 = None

        try:
            time.sleep(3)

            driver2 = _init_driver()

            retry_result = _scrape_reviews_with_driver(
                driver2,
                url,
                days_back,
                progress_callback,
            )

            if (
                len(retry_result.get("reviews", [])) > 0
                or retry_result.get("error")
            ):
                result = retry_result

        except Exception as e:
            logger.error(
                f"[SINGLE SCRAPER] Fatal error (attempt 2) for {url}: {e}"
            )

        finally:
            if driver2:
                try:
                    driver2.quit()
                except Exception:
                    pass

    #
    # Sentiment analysis
    #
    if progress_callback:
        progress_callback(
            95,
            100,
            f"Running sentiment analysis on {len(result['reviews'])} reviews..."
        )

    result["sentiment"] = _run_sentiment_analysis(
        result["reviews"]
    )

    result["scraped_at"] = (
        datetime.datetime.utcnow().isoformat() + "Z"
    )

    result["review_count"] = len(result["reviews"])
    result["days_back"] = days_back

    if progress_callback:
        progress_callback(
            100,
            100,
            "Complete!"
        )

    return result