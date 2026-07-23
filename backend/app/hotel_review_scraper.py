"""
hotel_review_scraper.py
-----------------------
Dedicated review scraper for the /hotel-sentiment route.
Do not merge with review_scraper.py.
"""

import datetime
import time
import random
import hashlib
import re
import logging
import traceback
from typing import Dict, List, Optional, Callable

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException

try:
    from dateutil import parser as dateutil_parser
    HAS_DATEUTIL = True
except ImportError:
    HAS_DATEUTIL = False

logger = logging.getLogger(__name__)

# --- Hugging Face Transformer Initialization ---
sentiment_pipeline = None

def get_sentiment_pipeline():
    """Lazy-loads and returns the Hugging Face sentiment analysis pipeline."""
    global sentiment_pipeline
    if sentiment_pipeline is not None:
        return sentiment_pipeline

    try:
        from transformers import pipeline
        import torch

        # Detect CUDA GPU hardware availability if available
        device = 0 if torch.cuda.is_available() else -1
        logger.info(f"[HOTEL SCRAPER] Loading Hugging Face Sentiment Model on device: {device}...")

        # RoBERTa-base sentiment classifier fine-tuned on user reviews
        sentiment_pipeline = pipeline(
            "sentiment-analysis",
            model="cardiffnlp/twitter-roberta-base-sentiment-latest",
            return_all_scores=True,
            device=device,
            truncation=True,
            max_length=512
        )
        logger.info("[HOTEL SCRAPER] Hugging Face Sentiment Pipeline successfully loaded.")
    except Exception as e:
        sentiment_pipeline = None
        logger.error(f"[HOTEL SCRAPER] Failed to initialize Hugging Face Pipeline: {e}\n{traceback.format_exc()}")

    return sentiment_pipeline

# Eagerly attempt to initialize on module import
get_sentiment_pipeline()


# ── Driver ────────────────────────────────────────────────────────────────────

def _init_driver():
    logger.info("[HOTEL SCRAPER] Initializing Chrome Driver with headless options...")
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
    try:
        service = Service("/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=options)
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
        )
        logger.info("[HOTEL SCRAPER] Chrome Driver initialized successfully.")
        return driver
    except Exception as e:
        logger.error(f"[HOTEL SCRAPER] Failed to initialize Chrome Driver: {e}", exc_info=True)
        raise e


# ── Date parsing ──────────────────────────────────────────────────────────────

def _parse_relative_date(text: str) -> datetime.datetime:
    now = datetime.datetime.now()
    if not text:
        return now
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
    if "an " in t or t.startswith("a "):
        if "hour" in t:  return now - datetime.timedelta(hours=1)
        if "day" in t:   return now - datetime.timedelta(days=1)
        if "week" in t:  return now - datetime.timedelta(weeks=1)
        if "month" in t: return now - datetime.timedelta(days=30)
        if "year" in t:  return now - datetime.timedelta(days=365)
    if HAS_DATEUTIL:
        try:
            return dateutil_parser.parse(t, fuzzy=True)
        except Exception:
            pass
    return now


# ── Business details ──────────────────────────────────────────────────────────

def _extract_business_details(driver) -> Dict:
    logger.info("[HOTEL SCRAPER] Attempting to extract business details...")
    details = {"name": "Unknown", "address": "", "rating": None, "total_reviews": 0}
    try:
        # 1. Name
        for sel in ["h1.DUwDvf", "h1.fontHeadlineLarge", "h1"]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el.text.strip():
                    details["name"] = el.text.strip()
                    logger.info(f"[HOTEL SCRAPER] Extracted business name: {details['name']}")
                    break
            except Exception:
                continue

        # 2. Address
        for sel in ['[data-item-id="address"]', ".Io6YTe", ".rogA2c"]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el.text.strip():
                    details["address"] = el.text.strip().replace("\ue0c8\n", "").strip()
                    logger.info(f"[HOTEL SCRAPER] Extracted address: {details['address']}")
                    break
            except Exception:
                continue

        # 3. Rating
        try:
            rating_text = driver.find_element(By.CSS_SELECTOR, '.F7nice span[aria-hidden="true"]').text.strip()
            details["rating"] = float(rating_text)
            logger.info(f"[HOTEL SCRAPER] Extracted general rating: {details['rating']}")
        except Exception as e:
            logger.debug(f"[HOTEL SCRAPER] Failed to extract general rating text: {e}")

        # 4. Total Reviews
        try:
            raw = driver.find_element(By.CSS_SELECTOR, ".F7nice .bC3Nkc").text.strip()
            details["total_reviews"] = int(re.sub(r"[^\d]", "", raw) or "0")
            logger.info(f"[HOTEL SCRAPER] Extracted total review count: {details['total_reviews']}")
        except Exception as e:
            logger.debug(f"[HOTEL SCRAPER] Failed to extract total review counts: {e}")

    except Exception as e:
        logger.warning(f"[HOTEL SCRAPER] Business detail extraction encountered a soft error: {e}")
    return details


# ── Navigate to reviews ───────────────────────────────────────────────────────

def _navigate_to_reviews(driver):
    logger.info("[HOTEL SCRAPER] Locating and navigating to the Reviews tab...")
    clicked = False
    try:
        combined_tab_xpath = ' | '.join([
            '//button[contains(@aria-label, "Reviews")]',
            '//button[@data-tab-index="1"]',
            '//button[@data-tab-index="2"]',
            '//button[.//div[contains(text(), "Reviews")]]'
        ])
        
        review_btns = driver.find_elements(By.XPATH, combined_tab_xpath)
        for btn in review_btns:
            if btn.is_displayed():
                driver.execute_script("arguments[0].click();", btn)
                logger.info("[HOTEL SCRAPER] Clicked Reviews tab button.")
                clicked = True
                time.sleep(3)
                break

        if clicked:
            logger.info("[HOTEL SCRAPER] Successfully verified Reviews tab rendering. Proceeding...")
            return

    except Exception as e:
        logger.warning(f"[HOTEL SCRAPER] Direct click on reviews tab failed: {e}. Executing URL fallback...")

    current_url = driver.current_url
    base_url    = current_url.split("?")[0].split("#")[0]
    reviews_url = f"{base_url}?hl=en&view=reviews&sort=1"
    logger.info(f"[HOTEL SCRAPER] Navigating directly to Reviews view fallback URL: {reviews_url}")
    driver.get(reviews_url)
    time.sleep(5)


# ── Sort by newest ────────────────────────────────────────────────────────────

def _sort_by_newest(driver):
    logger.info("[HOTEL SCRAPER] Attempting to Sort by Newest reviews...")
    try:
        combined_sort_xpath = ' | '.join([
            '//button[contains(@aria-label, "Sort reviews")]',
            '//button[contains(@aria-label, "Sort")]',
            '//div[@role="button" and .//div[contains(text(), "Sort")]]',
            '//span[contains(text(), "Sort")]/ancestor::button',
            '//button[@data-value="Sort"]'
        ])

        try:
            sort_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, combined_sort_xpath))
            )
        except Exception:
            logger.warning("[HOTEL SCRAPER] Sort button could not be matched. Skipping sort operations.")
            return

        driver.execute_script("arguments[0].click();", sort_btn)
        logger.info("[HOTEL SCRAPER] Opened the Sort option dropdown.")
        time.sleep(1.5)

        combined_newest_xpath = ' | '.join([
            '//div[@role="menuitem" or @role="menuitemradio" or @role="menuitemcheckbox"][.//div[contains(text(), "Newest")]]',
            '//span[contains(text(), "Newest")]',
            '//div[contains(text(), "Newest")]',
            '//button[.//div[contains(text(), "Newest")]]'
        ])

        newest = None
        try:
            newest = WebDriverWait(driver, 4).until(
                EC.element_to_be_clickable((By.XPATH, combined_newest_xpath))
            )
        except Exception:
            pass

        if newest:
            driver.execute_script("arguments[0].click();", newest)
            logger.info("[HOTEL SCRAPER] Order changed: Sorted by newest.")
            time.sleep(3)
        else:
            logger.warning("[HOTEL SCRAPER] 'Newest' option element was not found in the DOM. Closing menu.")
            driver.find_element(By.TAG_NAME, "body").send_keys("\ue00c")
            time.sleep(1)

    except Exception as e:
        logger.warning(f"[HOTEL SCRAPER] Sort operations encountered a non-fatal error: {e}")


# ── Find scrollable feed ──────────────────────────────────────────────────────

def _find_feed(driver):
    logger.info("[HOTEL SCRAPER] Searching for the main scrollable review feed element...")
    
    target_selectors = [
        'div.m6QErb.DxyBCb.kA9KIf.dS8AEf',
        'div.m6QErb[role="feed"]',
        'div[role="feed"]',
        'div.m6QErb.XiKgde',
        'div.WscY9b'
    ]
    
    try:
        for selector in target_selectors:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for el in elements:
                if el.is_displayed():
                    has_reviews = driver.execute_script(
                        "return arguments[0].querySelector('div.jftiEf, div.g7vRke, [data-review-id]') !== null || "
                        "arguments[0].getElementsByTagName('div').length > 5;", el
                    )
                    is_scrollable = driver.execute_script(
                        "return arguments[0].scrollHeight > arguments[0].clientHeight;", el
                    )
                    
                    if has_reviews and is_scrollable:
                        logger.info(f"[HOTEL SCRAPER] Successfully verified true review feed container.")
                        return el
    except Exception as e:
        logger.debug(f"[HOTEL SCRAPER] Selector search error: {e}")
            
    try:
        logger.info("[HOTEL SCRAPER] Executing strict dynamic DOM fallback...")
        el = driver.execute_script(
            "return Array.from(document.querySelectorAll('div')).find(el => { "
            "  const style = window.getComputedStyle(el); "
            "  const isScrollable = style.overflowY === 'auto' || style.overflowY === 'scroll'; "
            "  const hasScrollHeight = el.scrollHeight > el.clientHeight; "
            "  return isScrollable && hasScrollHeight; "
            "});"
        )
        if el:
            logger.info("[HOTEL SCRAPER] True dynamic review scrollpane found via strict JS validation.")
            return el
    except Exception as e:
        logger.debug(f"[HOTEL SCRAPER] Strict JS fallback failed: {e}")

    logger.warning("[HOTEL SCRAPER] Warning: No valid nested scrollpane found. Falling back to body context.")
    return None


# ── Single text score helper ──────────────────────────────────────────────────

def _predict_text_compound_score(text: str) -> float:
    """
    Evaluates text through the RoBERTa Transformer model and converts
    class probabilities into a compound score between -1.0 and +1.0.
    """
    pipeline_instance = get_sentiment_pipeline()
    if not pipeline_instance or not text or text == "[Rating Only]":
        return 0.0

    try:
        # Run inference through Transformer model pipeline
        raw_outputs = pipeline_instance(text[:512])[0]
        
        # Map label probabilities: [{'label': 'positive', 'score': 0.85}, ...]
        scores = {p['label'].lower(): p['score'] for p in raw_outputs}
        
        pos = scores.get('positive', 0.0)
        neg = scores.get('negative', 0.0)
        
        # Calculate compound polarity score on a [-1.0, 1.0] scale
        compound = pos - neg
        return round(compound, 3)
    except Exception as e:
        logger.debug(f"[HOTEL SCRAPER] Inference error for text snippet: {e}")
        return 0.0


# ── Sentiment analysis ────────────────────────────────────────────────────────

def _run_sentiment_analysis(reviews: List[Dict]) -> Dict:
    pipeline_instance = get_sentiment_pipeline()
    logger.info(f"[HOTEL SCRAPER] Commencing Hugging Face Transformer analysis on {len(reviews)} reviews...")
    
    if not reviews or not pipeline_instance:
        logger.warning("[HOTEL SCRAPER] Hugging Face Sentiment pipeline not loaded or review stack is empty.")
        return {
            "overall_score": 0, "overall_label": "Unknown",
            "positive_count": 0, "neutral_count": 0, "negative_count": 0,
            "total_with_text": 0, "avg_rating": None,
            "rating_distribution": {"5":0,"4":0,"3":0,"2":0,"1":0},
            "monthly_breakdown": {}, "top_positive_phrases": [],
            "top_negative_phrases": [], "keyword_themes": {},
        }

    texts = [r["text"] for r in reviews if r.get("text") and r["text"] != "[Rating Only]"]
    
    # Run batch inference through Transformer pipeline for performance
    try:
        batch_inputs = [t[:512] for t in texts]
        batch_results = pipeline_instance(batch_inputs) if batch_inputs else []
    except Exception as e:
        logger.error(f"[HOTEL SCRAPER] Batch inference failed, falling back to sequential evaluation: {e}")
        batch_results = []

    scores = []
    positive_count = neutral_count = negative_count = 0
    scored_reviews_map = {}

    for idx, text in enumerate(texts):
        if idx < len(batch_results):
            raw_scores = {p['label'].lower(): p['score'] for p in batch_results[idx]}
            pos = raw_scores.get('positive', 0.0)
            neg = raw_scores.get('negative', 0.0)
            score = round(pos - neg, 3)
        else:
            score = _predict_text_compound_score(text)

        scores.append(score)
        scored_reviews_map[text] = score

        if score > 0.2:    positive_count += 1
        elif score < -0.2: negative_count += 1
        else:              neutral_count  += 1

    overall_score = round(sum(scores) / len(scores), 3) if scores else 0

    if overall_score > 0.5:    overall_label = "Very Positive"
    elif overall_score > 0.2:  overall_label = "Positive"
    elif overall_score > -0.2: overall_label = "Mixed / Neutral"
    elif overall_score > -0.5: overall_label = "Negative"
    else:                      overall_label = "Very Negative"

    rating_dist = {"5":0,"4":0,"3":0,"2":0,"1":0}
    ratings = [r["rating"] for r in reviews if r.get("rating") is not None]
    avg_rating = round(sum(ratings)/len(ratings), 2) if ratings else None
    for r in ratings:
        key = str(min(5, max(1, int(round(r)))))
        rating_dist[key] = rating_dist.get(key, 0) + 1

    monthly = {}
    for review in reviews:
        parsed = _parse_relative_date(review.get("date", ""))
        mk = parsed.strftime("%Y-%m")
        if mk not in monthly:
            monthly[mk] = {"count": 0, "total_score": 0, "ratings": []}
        monthly[mk]["count"] += 1
        
        rev_text = review.get("text", "")
        if rev_text and rev_text != "[Rating Only]":
            monthly[mk]["total_score"] += scored_reviews_map.get(rev_text, 0.0)
        
        if review.get("rating") is not None:
            monthly[mk]["ratings"].append(review["rating"])

    monthly_breakdown = {}
    for month, data in sorted(monthly.items()):
        avg_sc = round(data["total_score"] / data["count"], 3) if data["count"] else 0
        avg_rt = round(sum(data["ratings"])/len(data["ratings"]), 1) if data["ratings"] else None
        monthly_breakdown[month] = {"count": data["count"], "avg_sentiment": avg_sc, "avg_rating": avg_rt}

    combined = " ".join(texts).lower()
    keyword_themes = {
        "Food & Quality":  sum(combined.count(w) for w in ["food","taste","fresh","quality","flavour","delicious","amazing","bland","stale"]),
        "Service":         sum(combined.count(w) for w in ["service","staff","friendly","rude","helpful","attentive","slow","fast"]),
        "Ambiance":        sum(combined.count(w) for w in ["ambiance","atmosphere","decor","cozy","noisy","comfortable","vibe","place"]),
        "Value & Pricing": sum(combined.count(w) for w in ["price","expensive","cheap","value","worth","overpriced","affordable","costly"]),
        "Wait Time":       sum(combined.count(w) for w in ["wait","queue","slow","quick","fast","long","delay","time"]),
        "Cleanliness":     sum(combined.count(w) for w in ["clean","dirty","hygiene","neat","tidy","messy","spotless"]),
        "Room & Comfort":  sum(combined.count(w) for w in ["room","bed","comfortable","spacious","noisy","view","bathroom","shower","ac","aircon"]),
        "Location":        sum(combined.count(w) for w in ["location","central","near","access","transport","airport","metro","walk"]),
    }

    scored = []
    for review in reviews:
        rev_text = review.get("text", "")
        if rev_text and rev_text != "[Rating Only]":
            sc = scored_reviews_map.get(rev_text, 0.0)
            scored.append((sc, rev_text[:120].strip(), review.get("author",""), review.get("date","")))
    
    scored.sort(key=lambda x: x[0], reverse=True)
    top_positive = [{"score":s,"text":t,"author":a,"date":d} for s,t,a,d in scored[:5]]
    top_negative = [{"score":s,"text":t,"author":a,"date":d} for s,t,a,d in scored[-5:] if s < 0]

    logger.info(f"[HOTEL SCRAPER] Sentiment processing ended. Overall Sentiment: {overall_label} ({overall_score})")
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


# ── Main scrape function ──────────────────────────────────────────────────────

def scrape_hotel_reviews(
    url: str,
    days_back: int = 30,
    max_reviews: int = 50,
    progress_callback: Optional[Callable] = None,
) -> Dict:
    logger.info(f"[HOTEL SCRAPER] Executing scraping program. Target limits: {days_back} days back, max {max_reviews} reviews.")
    if not url:
        logger.error("[HOTEL SCRAPER] Aborting: URL provided is empty or invalid.")
        return {"business_details": {}, "reviews": [], "sentiment": {}, "error": "No URL provided"}

    driver = None
    result = {"business_details": {}, "reviews": [], "sentiment": {}, "error": None}

    try:
        driver = _init_driver()
        logger.info(f"[HOTEL SCRAPER] Dispatching navigation request: {url}")

        if progress_callback:
            progress_callback(0, 100, "Loading hotel page...")

        driver.get(url)
        time.sleep(4)

        result["business_details"] = _extract_business_details(driver)
        place_name = result["business_details"].get("name", "Unknown")
        logger.info(f"[HOTEL SCRAPER] Target loaded: {place_name}")

        if progress_callback:
            progress_callback(5, 100, f"Opened {place_name}. Finding reviews...")

        _navigate_to_reviews(driver)
        _sort_by_newest(driver)

        if progress_callback:
            progress_callback(10, 100, "Scraping reviews...")

        feed = _find_feed(driver)
        if not feed:
            logger.warning("[HOTEL SCRAPER] Feed element context is missing. Attempting parsing without scoped element scroll limits.")

        # --- HYDRATION GATE ---
        logger.info("[HOTEL SCRAPER] Waiting for review cards to populate in the DOM...")
        try:
            WebDriverWait(driver, 8).until(
                lambda d: len(d.find_elements(By.XPATH, (
                    "//div["
                    "  (count(descendant::span) >= 2 or count(descendant::div) >= 3) and "
                    "  (contains(@class, 'Ef') or contains(@data-review-id, '') or @role='listitem' or count(descendant::*[contains(@aria-label, 'star')]) > 0)"
                    "]"
                ))) > 0
            )
            logger.info("[HOTEL SCRAPER] Review tree components successfully detected in DOM.")
        except Exception:
            logger.warning("[HOTEL SCRAPER] Timeout waiting for structural element tree hydration. Starting fallback loops.")

        cutoff = datetime.datetime.now() - datetime.timedelta(days=days_back)
        logger.info(f"[HOTEL SCRAPER] Target cutoff date is calculated as: {cutoff.strftime('%Y-%m-%d')}")
        
        reviews = []
        processed_ids = set()
        stale_count = 0
        consecutive_oob = 0

        logger.info("[HOTEL SCRAPER] Starting review scraping loops...")
        for scroll_loop in range(80):
            logger.info(f"[HOTEL SCRAPER] --- Loop {scroll_loop + 1}/80 --- Current Review Count: {len(reviews)}")
            
            # Expand "More" / "See more" buttons safely
            try:
                expandable_buttons = driver.find_elements(By.CSS_SELECTOR, "button.w8nwRe, button.M77dve")
                if expandable_buttons:
                    logger.info(f"[HOTEL SCRAPER] Found {len(expandable_buttons)} truncated text 'More' buttons. Clicking them...")
                    for btn in expandable_buttons[:15]:
                        try:
                            if btn.is_displayed():
                                driver.execute_script("arguments[0].click();", btn)
                                time.sleep(0.05)
                        except Exception:
                            pass
            except Exception as e:
                logger.debug(f"[HOTEL SCRAPER] Encountered error processing expand buttons: {e}")

            # STRATEGY: Grab card components layout-agnostically by density and structure attributes
            cards = driver.find_elements(By.XPATH, (
                "//div["
                "  (count(descendant::span) >= 2 or count(descendant::div) >= 3) and "
                "  (contains(@class, 'Ef') or contains(@data-review-id, '') or @role='listitem' or count(descendant::*[contains(@aria-label, 'star')]) > 0)"
                "]"
            ))

            logger.info(f"[HOTEL SCRAPER] Extracted {len(cards)} structural matching trees in viewport.")

            new_this_round = 0
            oob_this_round = 0

            for idx, card in enumerate(cards):
                if len(reviews) >= max_reviews:
                    logger.info(f"[HOTEL SCRAPER] Max reviews limit reached ({max_reviews}). Stopping extraction.")
                    break
                try:
                    card_text = card.text.strip()
                    if not card_text or len(card_text) < 12 or "Sort" in card_text[:15]:
                        continue

                    lines = [line.strip() for line in card_text.split('\n') if line.strip()]
                    if len(lines) < 2:
                        continue

                    author = lines[0]
                    date_str = lines[1]
                    
                    if "guide" in date_str.lower() or "review" in date_str.lower() and len(lines) > 2:
                        date_str = lines[2]
                        text_pool = lines[3:]
                    else:
                        text_pool = lines[2:]

                    review_text = " ".join([t for t in text_pool if "helpful" not in t.lower() and "share" not in t.lower()])
                    review_text = review_text.strip() if review_text else "[Rating Only]"

                    rev_id = card.get_attribute("data-review-id") or f"{author}_{date_str}_{hashlib.md5(review_text.encode()).hexdigest()[:8]}"

                    if rev_id in processed_ids:
                        continue

                    rating = 5
                    try:
                        aria = card.get_attribute("aria-label") or ""
                        stars_match = re.search(r"(\d+)\s*star", aria.lower())
                        if stars_match:
                            rating = int(stars_match.group(1))
                        else:
                            stars_elements = card.find_elements(By.XPATH, ".//*[contains(@aria-label, 'star')]")
                            if stars_elements:
                                rating = len(stars_elements)
                            else:
                                for sel in [".fzvQIb", "span.kvMYJc"]:
                                    el = card.find_element(By.CSS_SELECTOR, sel)
                                    raw_val = el.text.strip()
                                    if "/" in raw_val:
                                        rating = int(raw_val.split("/")[0])
                                        break
                    except Exception:
                        pass

                    parsed_date = _parse_relative_date(date_str)
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

                    logger.info(f"[HOTEL SCRAPER] Extracted {len(reviews)}: [{author}] -> \"{review_text[:50]}...\" ({date_str})")

                    if progress_callback and len(reviews) % 5 == 0:
                        pct = min(90, 10 + int((len(reviews) / max(max_reviews, 1)) * 80))
                        progress_callback(pct, 100, f"Scraped {len(reviews)} reviews...")

                except StaleElementReferenceException:
                    logger.debug(f"[HOTEL SCRAPER] Stale element reference on card index {idx}. Skipping card.")
                    continue
                except Exception as e:
                    logger.debug(f"[HOTEL SCRAPER] Non-fatal card extraction failure: {e}")
                    continue

            logger.info(f"[HOTEL SCRAPER] Loop {scroll_loop + 1} processing summary: {new_this_round} newly processed, {oob_this_round} out-of-bounds.")

            if oob_this_round > 0 and new_this_round == 0:
                consecutive_oob += 1
            else:
                consecutive_oob = 0

            if consecutive_oob >= 5:
                logger.info(f"[HOTEL SCRAPER] Confirmed {days_back}-day age cutoff barrier matched. Stopping loops.")
                break

            if len(reviews) >= max_reviews:
                break

            if feed:
                try:
                    prev = driver.execute_script("return arguments[0].scrollTop", feed)
                    driver.execute_script("arguments[0].scrollBy(0, 2500);", feed)
                    time.sleep(random.uniform(2.2, 2.8))
                    after = driver.execute_script("return arguments[0].scrollTop", feed)
                    logger.info(f"[HOTEL SCRAPER] Scroll feed positions: Previous: {prev}px -> After: {after}px")
                    if after <= prev:
                        logger.info("[HOTEL SCRAPER] Feed scroll position did not increment. Emulating Keyboard Arrow Down event...")
                        try:
                            feed.send_keys("\ue015" * 10)
                        except Exception:
                            pass
                        stale_count += 1
                    else:
                        stale_count = 0
                except StaleElementReferenceException:
                    logger.warning("[HOTEL SCRAPER] Feed element went stale! Re-acquiring target scroll container...")
                    feed = _find_feed(driver)
                    if feed:
                        try:
                            prev = driver.execute_script("return arguments[0].scrollTop", feed)
                            driver.execute_script("arguments[0].scrollBy(0, 2500);", feed)
                            time.sleep(random.uniform(2.2, 2.8))
                            after = driver.execute_script("return arguments[0].scrollTop", feed)
                            logger.info(f"[HOTEL SCRAPER] Scroll feed positions (after recovery): Previous: {prev}px -> After: {after}px")
                            if after <= prev:
                                stale_count += 1
                            else:
                                stale_count = 0
                        except Exception as retry_err:
                            logger.warning(f"[HOTEL SCRAPER] Scroll retry failed: {retry_err}")
                            stale_count += 1
                    else:
                        logger.warning("[HOTEL SCRAPER] Failed to re-acquire feed element after stale reference.")
                        stale_count += 1
                except Exception as e:
                    logger.warning(f"[HOTEL SCRAPER] Internal scroll execution error on feed element: {e}")
                    stale_count += 1
            else:
                prev_h = driver.execute_script("return document.body.scrollHeight")
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(random.uniform(2.2, 2.8))
                new_h = driver.execute_script("return document.body.scrollHeight")
                logger.info(f"[HOTEL SCRAPER] Scroll page body positions: Previous height: {prev_h}px -> After height: {new_h}px")
                stale_count = 0 if new_h != prev_h or new_this_round > 0 else stale_count + 1

            if stale_count >= 10:
                logger.warning(f"[HOTEL SCRAPER] Exceeded stale scroll limitations ({stale_count}/10 iterations without changes). Ending loop sequence.")
                break

        result["reviews"] = reviews
        logger.info(f"[HOTEL SCRAPER] Review scraping complete. Successfully parsed {len(reviews)} reviews for \"{place_name}\".")

        if progress_callback:
            progress_callback(92, 100, f"Running sentiment analysis on {len(reviews)} reviews...")

        result["sentiment"] = _run_sentiment_analysis(reviews)

        if progress_callback:
            progress_callback(100, 100, "Complete!")

    except Exception as e:
        result["error"] = str(e)
        logger.error(f"[HOTEL SCRAPER] Fatal core process execution failure: {e}", exc_info=True)
    finally:
        if driver:
            try:
                logger.info("[HOTEL SCRAPER] Releasing driver resource context...")
                driver.quit()
                logger.info("[HOTEL SCRAPER] Driver successfully terminated.")
            except Exception as e:
                logger.warning(f"[HOTEL SCRAPER] Exception thrown closing active driver instance: {e}")

    return result