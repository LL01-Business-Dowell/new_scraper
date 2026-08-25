import uuid
import logging
import urllib.parse
import os
import json
import io
import re
import time
import datetime
import statistics
from typing import List, Optional, Dict, Any
import requests
import numpy as np
from scipy import stats

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from transformers import pipeline
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, Image
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

from PIL import Image as PILImage, ImageDraw, ImageFont

import sys

try:
    import google.genai._api_client as genai_client
    
    async def _safe_aclose(self):
        # Prevent AttributeError if _async_httpx_client wasn't initialized
        client = getattr(self, "_async_httpx_client", None)
        if client is not None:
            await client.aclose()

    genai_client.BaseApiClient.aclose = _safe_aclose
except (ImportError, AttributeError):
    pass
# -------------------------------------------------------------

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/hotel-sentiment", tags=["Sentiment Analysis"])

# ─────────────────────────────────────────────────────────────────────────────
# 🎛️ CONFIGURATION SWITCH
# Set to True to test locally with zero Apify credits used.
# Set to False to run live scraping via Apify on Google Maps reviews.
USE_MOCK_DATA = False
# ─────────────────────────────────────────────────────────────────────────────

# Filter out non-luxury / budget / hostel properties from the approval list
EXCLUDED_KEYWORDS = [
    "pod", "capsule", "hostel", "budget", "motel", "inn", 
    "backpack", "dorm", "guesthouse", "guest house", "b&b", "bed & breakfast"
]

# Customer Journey Taxonomy Definition
CUSTOMER_JOURNEY_TAXONOMY = {
    "1. Pre-Arrival Phase": {
        "Digital Search & Discovery": ["website", "seo", "ota", "booking.com", "expedia", "social media", "virtual tour"],
        "Booking & Reservation Execution": ["booking engine", "ux", "payment", "confirmation", "reservation"],
        "Pre-Arrival Communication": ["welcome email", "upsell", "transfer", "spa package", "digital check-in"],
        "Special Request Management": ["early check-in", "high floor", "dietary", "anniversary", "birthday", "special request"]
    },
    "2. Arrival & Check-In Phase": {
        "Transportation & Valet Service": ["valet", "parking", "signage", "luggage assistance", "car transfer"],
        "Main Entrance & Doorman Greeting": ["doorman", "entrance", "lobby", "scent", "music", "welcome tone"],
        "Front Desk & Reception Desk Experience": ["queue", "wait time", "loyalty", "status", "upgrade", "check-in", "key", "reception"],
        "Baggage & Escort Service": ["bellboy", "bell staff", "escort", "luggage delivery", "room orientation"]
    },
    "3. In-Room & Stay Experience": {
        "Room First Impressions": ["cleanliness", "clean", "fresh scent", "ambient", "welcome amenity"],
        "In-Room Technology & Connectivity": ["wifi", "wi-fi", "climate control", "charging", "tv", "digital key"],
        "Comfort & Sleep Environment": ["bed", "pillow", "bedding", "curtain", "blackout", "quiet", "noise", "soundproof"],
        "In-Room Amenities & Hardware": ["minibar", "coffee", "tea", "iron", "safe", "deposit box"],
        "Bathroom Experience": ["bathroom", "shower", "water pressure", "hot water", "toiletries", "towel", "hair dryer"],
        "Housekeeping & Turn-Down Service": ["housekeeping", "linen", "dnd", "do not disturb", "turndown", "turn-down"]
    },
    "4. Food & Beverage (F&B) Touchpoints": {
        "Breakfast Service": ["breakfast", "buffet", "egg", "hostess", "coffee"],
        "In-Room Dining (Room Service)": ["room service", "in-room dining", "trolley", "delivery time", "food temperature"],
        "On-Site Restaurants & Bars": ["restaurant", "bar", "sommelier", "waitstaff", "dinner", "lunch", "menu"],
        "Executive Lounge Experience": ["lounge", "executive lounge", "cocktail", "afternoon tea", "club lounge"]
    },
    "5. Amenities, Wellness & Guest Facilities": {
        "Fitness Center & Gym": ["gym", "fitness", "workout", "treadmill", "weights"],
        "Spa & Wellness Center": ["spa", "massage", "therapist", "treatment", "locker"],
        "Pool & Beach Facilities": ["pool", "beach", "lounger", "sunbed", "lifeguard", "poolside"],
        "Business Center & Meeting Facilities": ["business center", "printing", "meeting room", "conference", "av"]
    },
    "6. Departure & Post-Departure Phase": {
        "Pre-Departure Communication": ["folio", "invoice", "express check-out"],
        "Front Desk Check-Out": ["check-out", "checkout", "dispute", "fee", "receipt"],
        "Service Recovery": ["complaint", "issue resolution", "apology", "manager", "rectified"],
        "Departure Assistance": ["taxi", "cab", "departure", "valet retrieval"],
        "Post-Stay Follow-Up": ["survey", "lost and found", "follow-up", "thank you"]
    }
}


def _is_valid_competitor(place: dict) -> bool:
    """Filters out budget, pod, and low-tier accommodations before user approval."""
    name_lower = place.get("name", "").lower()
    
    if any(keyword in name_lower for keyword in EXCLUDED_KEYWORDS):
        return False
        
    rating = place.get("rating")
    if rating and rating < 3.8:
        return False

    price_level = place.get("price_level")
    if price_level is not None:
        try:
            numeric_price = int(price_level)
            if numeric_price <= 1:
                return False
        except (ValueError, TypeError):
            str_price = str(price_level).upper()
            if "INEXPENSIVE" in str_price or str_price == "$":
                return False

    return True

def _fetch_static_map_image(results: list, width: int = 600, height: int = 280) -> Optional[io.BytesIO]:
    """
    Fetches a static map image directly from the Google Maps Static API 
    with custom pins pre-rendered on the server.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    
    base_url = "https://maps.googleapis.com/maps/api/staticmap"
    
    markers = []
    
    for place in results:
        lat = place.get("lat") or place.get("latitude")
        lng = place.get("lng") or place.get("longitude")
        
        if lat is not None and lng is not None:
            is_user = place.get("is_user_establishment", False)
            
            if is_user:
                markers.append(f"markers=color:red|label:S|{lat},{lng}")
            else:
                markers.append(f"markers=color:blue|size:mid|{lat},{lng}")

    if not markers:
        logger.warning("[PDF MAP] No geographic coordinates found.")
        return None

    params = {
        "size": f"{width}x{height}",
        "scale": "2",
        "maptype": "roadmap",
        "key": api_key,
    }

    query_string = "&".join(markers)
    full_url = f"{base_url}?{'&'.join([f'{k}={v}' for k, v in params.items()])}&{query_string}"

    try:
        response = requests.get(full_url, timeout=10)
        if response.status_code == 200:
            logger.info("[PDF MAP] Google Static Map successfully fetched.")
            return io.BytesIO(response.content)
        else:
            logger.error(f"[PDF MAP] Google Maps API error {response.status_code}: {response.text}")
            return None
    except Exception as e:
        logger.error(f"[PDF MAP] Request failed: {e}")
        return None


def _generate_offline_map_diagram(places: list, width: int = 600, height: int = 280) -> Optional[io.BytesIO]:
    """Generates a clean offline geometric coordinate map using Pillow (PIL) - zero extra dependencies."""
    try:
        img = PILImage.new("RGB", (width, height), color="#F8FAFC")
        draw = ImageDraw.Draw(img)

        draw.rectangle([0, 0, width - 1, height - 1], outline="#CBD5E1", width=1)
        for x in range(50, width, 100):
            draw.line([(x, 0), (x, height)], fill="#E2E8F0", width=1)
        for y in range(40, height, 60):
            draw.line([(0, y), (width, y)], fill="#E2E8F0", width=1)

        lats = [p["lat"] for p in places]
        lngs = [p["lng"] for p in places]
        min_lat, max_lat = min(lats), max(lats)
        min_lng, max_lng = min(lngs), max(lngs)

        lat_span = (max_lat - min_lat) or 0.01
        lng_span = (max_lng - min_lng) or 0.01
        
        padding = 40
        plot_w = width - (padding * 2)
        plot_h = height - (padding * 2)

        draw.text((padding, 12), "Property Coordinates & Location Relative Plot", fill="#1E293B")

        for p in places:
            x = padding + int(((p["lng"] - min_lng) / lng_span) * plot_w)
            y = height - padding - int(((p["lat"] - min_lat) / lat_span) * plot_h)

            radius = 7
            if p["is_user"]:
                draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill="#DC2626", outline="#7F1D1D")
                draw.text((x + 10, y - 6), "Subject Property", fill="#DC2626")
            else:
                draw.rectangle([x - radius, y - radius, x + radius, y + radius], fill="#2563EB", outline="#1E3A8A")
                draw.text((x + 10, y - 6), "Competitor", fill="#2563EB")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        logger.info("[PDF MAP] Successfully generated offline PIL map diagram.")
        return buf
    except Exception as e:
        logger.error(f"[PDF MAP] Offline PIL map fallback error: {e}")
        return None


# In-memory task store with basic TTL cleanup
hotel_sentiment_tasks: Dict[str, Dict[str, Any]] = {}

def _clean_expired_tasks(max_age_hours: int = 24):
    """Clean up old tasks from memory to prevent memory leaks."""
    now = datetime.datetime.now()
    expired_keys = []
    for task_id, task in hotel_sentiment_tasks.items():
        created_at = task.get("created_at")
        if created_at and (now - created_at).total_seconds() > (max_age_hours * 3600):
            expired_keys.append(task_id)
    for k in expired_keys:
        del hotel_sentiment_tasks[k]


# Initialize Hugging Face sentiment model pipeline
logger.info("[HOTEL SENTIMENT] Initializing Hugging Face sentiment model...")
try:
    hf_sentiment_analyzer = pipeline(
        "sentiment-analysis",
        model="cardiffnlp/twitter-roberta-base-sentiment-latest",
        return_all_scores=True,
        truncation=True,
        max_length=512
    )
    logger.info("[HOTEL SENTIMENT] Hugging Face sentiment model loaded successfully.")
except Exception as e:
    logger.error(f"[HOTEL SENTIMENT] Failed to load Hugging Face model: {e}")
    hf_sentiment_analyzer = None


# ── Request models ────────────────────────────────────────────────────────────

class HotelSearchRequest(BaseModel):
    city: str
    country: str
    establishment_name: str
    radius_km: float = 5.0
    limit: int = 100
    origin_lat: Optional[float] = None
    origin_lng: Optional[float] = None
    days_back: int = 30


class ApprovedPlaceItem(BaseModel):
    name: str
    url: Optional[str] = ""
    address: Optional[str] = ""
    rating: Optional[float] = None
    reviews: Optional[int] = 0
    distance_km: Optional[float] = 0.0
    selected: bool = True
    is_user_establishment: bool = False
    adr: Optional[float] = None
    revpar: Optional[float] = None
    occupancy_rate: Optional[float] = None


class HotelAnalyzeRequest(BaseModel):
    task_id: str
    approved_places: List[Dict[str, Any]]
    establishment_name: str = ""
    days_back: int = 30


# ── Sentence Splitting Helper ──────────────────────────────────────────────────

def _split_into_sentences(text: str) -> List[str]:
    """Splits text into sentences based on punctuation, preserving original phrase clarity."""
    if not text:
        return []
    sentences = re.split(r'(?<=[.!?])\s+|\n+', text)
    cleaned = [s.strip() for s in sentences if s and len(s.strip()) > 3]
    return cleaned if cleaned else [text.strip()]


# ── Sentence-Level Hugging Face Analysis Engine ──────────────────────────────

def _run_huggingface_sentiment_analysis(reviews: list) -> dict:
    """Processes reviews at sentence level through the Hugging Face sentiment pipeline using batching."""
    empty_journey = {
        phase: {sub: {"pos": 0, "neu": 0, "neg": 0} for sub in subs}
        for phase, subs in CUSTOMER_JOURNEY_TAXONOMY.items()
    }

    if not reviews or not hf_sentiment_analyzer:
        return {
            "overall_score": 0.0,
            "median_score": 0.0,
            "mode_score": 0.0,
            "overall_label": "Mixed / Neutral",
            "positive_count": 0,
            "neutral_count": 0,
            "negative_count": 0,
            "top_positive_phrases": [],
            "top_negative_phrases": [],
            "keyword_themes": {},
            "journey_breakdown": empty_journey
        }

    valid_reviews = [r for r in reviews if r.get("text") and r.get("text") != "[Rating Only]"]
    if not valid_reviews:
        return {
            "overall_score": 0.0,
            "median_score": 0.0,
            "mode_score": 0.0,
            "overall_label": "Mixed / Neutral",
            "positive_count": 0,
            "neutral_count": 0,
            "negative_count": 0,
            "top_positive_phrases": [],
            "top_negative_phrases": [],
            "keyword_themes": {},
            "journey_breakdown": empty_journey
        }

    positive_count = 0
    neutral_count = 0
    negative_count = 0
    total_compound = 0.0

    pos_phrases = []
    neg_phrases = []

    keyword_themes = {
        "Service & Staff": 0,
        "Room & Comfort": 0,
        "Dining & Breakfast": 0,
        "Location & Noise": 0,
        "Loyalty & Recognition": 0,
        "Check-in & Digital Key": 0,
        "Banquets & Events": 0
    }

    journey_breakdown = {
        phase: {sub: {"pos": 0, "neu": 0, "neg": 0} for sub in subs}
        for phase, subs in CUSTOMER_JOURNEY_TAXONOMY.items()
    }

    sentence_map = []
    for rev in valid_reviews:
        text = rev.get("text", "")
        sentences = _split_into_sentences(text)
        for s in sentences:
            sentence_map.append({
                "sentence": s,
                "author": rev.get("author", "Guest"),
                "date": rev.get("date", "Recent")
            })

    if not sentence_map:
        return {
            "overall_score": 0.0,
            "median_score": 0.0,
            "mode_score": 0.0,
            "overall_label": "Mixed / Neutral",
            "positive_count": 0,
            "neutral_count": 0,
            "negative_count": 0,
            "top_positive_phrases": [],
            "top_negative_phrases": [],
            "keyword_themes": {},
            "journey_breakdown": empty_journey
        }

    sentence_texts = [item["sentence"] for item in sentence_map]
    
    batch_size = 32
    pipeline_results = []
    for i in range(0, len(sentence_texts), batch_size):
        batch = sentence_texts[i:i + batch_size]
        results = hf_sentiment_analyzer(batch, truncation=True, max_length=512)
        pipeline_results.extend(results)

    compounds = []

    for item, results in zip(sentence_map, pipeline_results):
        sentence_text = item["sentence"]

        if isinstance(results, list) and len(results) > 0 and isinstance(results[0], list):
            results = results[0]

        if isinstance(results, dict):
            results = [results]

        scores = {}
        if isinstance(results, list):
            for res in results:
                if isinstance(res, dict) and 'label' in res and 'score' in res:
                    scores[res['label'].lower()] = res['score']

        pos_score = scores.get('positive', 0.0)
        neg_score = scores.get('negative', 0.0)
        neu_score = scores.get('neutral', 0.0)

        compound = pos_score - neg_score
        compounds.append(compound)
        total_compound += compound

        phrase_data = {
            "author": item["author"],
            "date": item["date"],
            "text": sentence_text
        }

        s_label = "neu"
        if pos_score > neg_score and pos_score > neu_score:
            positive_count += 1
            pos_phrases.append(phrase_data)
            s_label = "pos"
        elif neg_score > pos_score and neg_score > neu_score:
            negative_count += 1
            neg_phrases.append(phrase_data)
            s_label = "neg"
        else:
            neutral_count += 1

        sentence_lower = sentence_text.lower()
        if any(k in sentence_lower for k in ["staff", "service", "desk", "concierge"]):
            keyword_themes["Service & Staff"] += 1
        if any(k in sentence_lower for k in ["room", "bed", "bathroom", "clean"]):
            keyword_themes["Room & Comfort"] += 1
        if any(k in sentence_lower for k in ["breakfast", "dining", "restaurant", "food"]):
            keyword_themes["Dining & Breakfast"] += 1
        if any(k in sentence_lower for k in ["location", "noise", "renovation", "street"]):
            keyword_themes["Location & Noise"] += 1
        if any(k in sentence_lower for k in ["honors", "loyalty", "diamond", "gold", "member", "upgrade"]):
            keyword_themes["Loyalty & Recognition"] += 1
        if any(k in sentence_lower for k in ["check-in", "checkin", "digital key", "app", "front desk", "queue"]):
            keyword_themes["Check-in & Digital Key"] += 1
        if any(k in sentence_lower for k in ["banquet", "event", "wedding", "conference", "ballroom"]):
            keyword_themes["Banquets & Events"] += 1

        for phase_name, sub_dict in CUSTOMER_JOURNEY_TAXONOMY.items():
            for sub_name, keywords in sub_dict.items():
                if any(kw in sentence_lower for kw in keywords):
                    journey_breakdown[phase_name][sub_name][s_label] += 1

    # Statistical calculations for Hilton / Property level
    arr = np.array(compounds)
    n_samples = len(arr)
    
    avg_score = round(float(np.mean(arr)), 3) if n_samples > 0 else 0.0
    median_score = round(float(np.median(arr)), 3) if n_samples > 0 else 0.0
    var_val = float(np.var(arr, ddof=1)) if n_samples > 1 else 0.0

    # Calculate Continuous Mode via Kernel Density Estimation (KDE)
    if n_samples > 2 and var_val > 0:
        kde = stats.gaussian_kde(arr)
        x_eval = np.linspace(-1.0, 1.0, 500)
        mode_score = round(float(x_eval[np.argmax(kde(x_eval))]), 3)
    else:
        mode_score = avg_score

    if avg_score > 0.2:
        overall_label = "Positive"
    elif avg_score < -0.2:
        overall_label = "Negative"
    else:
        overall_label = "Mixed / Neutral"

    return {
        "overall_score": avg_score,
        "median_score": median_score,
        "mode_score": mode_score,
        "overall_label": overall_label,
        "positive_count": positive_count,
        "neutral_count": neutral_count,
        "negative_count": negative_count,
        "top_positive_phrases": pos_phrases[:3],
        "top_negative_phrases": neg_phrases[:3],
        "keyword_themes": {k: v for k, v in keyword_themes.items() if v > 0},
        "journey_breakdown": journey_breakdown
    }


# ── Review Provider Functions (Mock vs Apify) ───────────────────────────────

def _fetch_reviews_mock(name: str) -> List[dict]:
    """Loads reviews from local test_hotel_reviews.json file using fuzzy/partial key matching."""
    test_json_path = os.path.join(os.path.dirname(__file__), "test_hotel_reviews.json")
    if not os.path.exists(test_json_path):
        return []
    
    with open(test_json_path, "r", encoding="utf-8") as f:
        mock_data = json.load(f)

    if not mock_data:
        return []

    if name in mock_data:
        return mock_data[name]

    name_lower = name.lower()
    for key, reviews in mock_data.items():
        if key.lower() in name_lower or name_lower in key.lower():
            return reviews

    return list(mock_data.values())[0]


def _fetch_reviews_apify(url: str, progress_cb) -> tuple[List[dict], dict, Optional[str]]:
    """Calls Apify scraper to pull live Google Maps reviews."""
    from .hotel_apify_scraper import scrape_hotel_reviews_apify
    scraped = scrape_hotel_reviews_apify(url=url, max_reviews=0, progress_callback=progress_cb)
    if scraped.get("error"):
        return [], {}, scraped["error"]
    return scraped.get("reviews", []), scraped.get("business_details", {}), None


# ── Search worker ─────────────────────────────────────────────────────────────

def _hotel_search_worker(
    task_id: str, city: str, radius_km: float, limit: int,
    establishment_name: str, origin_lat: Optional[float], origin_lng: Optional[float],
):
    try:
        from .google_maps_scraper import search_google_maps_competitors

        keyword = f"Luxury Hotels near {city}"
        logger.info(f"[HOTEL SENTIMENT] task_id={task_id} searching: '{keyword}'")

        def progress(current, total, message):
            hotel_sentiment_tasks[task_id]["progress"] = int((current / max(total, 1)) * 90)
            hotel_sentiment_tasks[task_id]["status_message"] = message

        raw_places = search_google_maps_competitors(
            keyword=keyword,
            city=city,
            establishment_name=establishment_name,
            radius_km=radius_km,
            limit=limit,
            origin_lat=origin_lat,
            origin_lng=origin_lng,
            progress_callback=progress,
        )

        filtered_places = [p for p in raw_places if _is_valid_competitor(p)]

        query = f"{establishment_name}, {city}"
        establishment_maps_url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote_plus(query)}"

        establishment = {
            "name":                  establishment_name,
            "address":               f"{city} area",
            "rating":                4.8,
            "reviews":               120,
            "url":                   establishment_maps_url,
            "lat":                   origin_lat,
            "lng":                   origin_lng,
            "distance_km":           0.0,
            "within_radius":         True,
            "selected":              True,
            "is_user_establishment": True,
        }
        filtered_places.insert(0, establishment)

        hotel_sentiment_tasks[task_id].update({
            "status":         "ready_for_approval",
            "progress":       100,
            "status_message": f"Found {len(filtered_places)} luxury competitors. Please review and approve.",
            "places":         filtered_places,
        })

    except Exception as e:
        logger.error(f"[HOTEL SENTIMENT] Search failed task_id={task_id}: {e}")
        hotel_sentiment_tasks[task_id].update({
            "status": "error", "error": str(e), "progress": 100,
        })


# ── Sentiment analysis worker ─────────────────────────────────────────────────

def _hotel_sentiment_worker(task_id: str, places: List[dict], days_back: int):
    selected = [p for p in places if p.get("selected", True)]
    total    = len(selected)
    mode     = "LOCAL MOCK" if USE_MOCK_DATA else "APIFY PRODUCTION"
    logger.info(f"[HOTEL SENTIMENT] [{mode}] task_id={task_id} analysing {total} places")

    results = []
    errors  = []

    for i, place in enumerate(selected):
        name = place.get("name", f"Place {i+1}")
        url  = place.get("url", "")

        def progress_cb(current_step_pct, max_step_pct, msg):
            base_progress = (i / max(total, 1)) * 85
            step_contribution = (current_step_pct / max(max_step_pct, 1)) * (85 / max(total, 1))
            hotel_sentiment_tasks[task_id]["progress"] = min(85, int(base_progress + step_contribution))
            hotel_sentiment_tasks[task_id]["status_message"] = f"[{i+1}/{total}] {name}: {msg}"

        biz_details = {}
        reviews = []

        if USE_MOCK_DATA:
            time.sleep(0.5)
            hotel_sentiment_tasks[task_id]["progress"] = int(((i + 1) / max(total, 1)) * 85)
            hotel_sentiment_tasks[task_id]["status_message"] = f"[{i+1}/{total}] Hugging Face model running on {name}..."
            reviews = _fetch_reviews_mock(name)
        else:
            if url:
                try:
                    reviews, biz_details, err = _fetch_reviews_apify(url, progress_cb)
                    if err:
                        raise Exception(err)
                except Exception as e:
                    logger.error(f"[HOTEL SENTIMENT] Apify extraction failed for {name}: {e}")
                    errors.append({"name": name, "error": str(e)})

        review_count = len(reviews)
        sentiment = _run_huggingface_sentiment_analysis(reviews)

        results.append({
            "name":                 biz_details.get("name") or name,
            "address":              biz_details.get("address") or place.get("address", ""),
            "rating":               biz_details.get("rating") or place.get("rating"),
            "google_review_count":  biz_details.get("total_reviews") or place.get("reviews", review_count),
            "scraped_review_count": review_count,
            "url":                  url,
            "lat":                  place.get("lat"),
            "lng":                  place.get("lng"),
            "is_user_establishment": place.get("is_user_establishment", False),
            "distance_km":          place.get("distance_km", 0.0),
            "sentiment":            sentiment,
            "adr":                  place.get("adr"),
            "revpar":               place.get("revpar"),
            "occupancy_rate":       place.get("occupancy_rate"),
        })

    combined_report = _build_combined_sentiment_report(results)

    hotel_sentiment_tasks[task_id].update({
        "status":          "completed",
        "progress":        100,
        "status_message":  f"Sentiment analysis completed successfully ({mode} mode).",
        "results":         results,
        "combined_report": combined_report,
        "errors":          errors
    })


def _build_combined_sentiment_report(results: List[dict]) -> dict:
    if not results:
        return {}

    with_sentiment = [r for r in results if r.get("sentiment", {}).get("overall_score") is not None]
    with_rating    = [r for r in results if r.get("rating")]

    # Extract Hilton data
    hilton_result = next((r for r in results if r.get("is_user_establishment")), None)
    hilton_sentiment = hilton_result.get("sentiment", {}) if hilton_result else {}

    # Market Aggregations
    hotel_means = []
    hotel_sample_sizes = []
    market_pos_total = 0
    market_neu_total = 0
    market_neg_total = 0

    for r in results:
        sent = r.get("sentiment", {})
        score = sent.get("overall_score")
        n_sentences = (sent.get("positive_count", 0) + sent.get("neutral_count", 0) + sent.get("negative_count", 0))

        if score is not None and n_sentences > 0:
            hotel_means.append(score)
            hotel_sample_sizes.append(n_sentences)
            market_pos_total += sent.get("positive_count", 0)
            market_neu_total += sent.get("neutral_count", 0)
            market_neg_total += sent.get("negative_count", 0)

    # Combined Market Micro Average (Sentence Weighted Mean)
    micro_mean = float(np.average(hotel_means, weights=hotel_sample_sizes)) if hotel_means else 0.0

    # Combined Market Sentiments (%)
    total_market_sentences = (market_pos_total + market_neu_total + market_neg_total) or 1
    market_pos_pct = round((market_pos_total / total_market_sentences) * 100, 1)
    market_neu_pct = round((market_neu_total / total_market_sentences) * 100, 1)
    market_neg_pct = round((market_neg_total / total_market_sentences) * 100, 1)

    # Hilton Sentiments (%)
    hilton_pos = hilton_sentiment.get("positive_count", 0)
    hilton_neu = hilton_sentiment.get("neutral_count", 0)
    hilton_neg = hilton_sentiment.get("negative_count", 0)
    hilton_total = (hilton_pos + hilton_neu + hilton_neg) or 1

    hilton_pos_pct = round((hilton_pos / hilton_total) * 100, 1)
    hilton_neu_pct = round((hilton_neu / hilton_total) * 100, 1)
    hilton_neg_pct = round((hilton_neg / hilton_total) * 100, 1)

    # Structured Side-by-Side Sector Analysis Table Data
    sector_analysis_table = {
        "mean": {
            "hilton": hilton_sentiment.get("overall_score", 0.0),
            "market": round(micro_mean, 3)
        },
        "median": {
            "hilton": hilton_sentiment.get("median_score", 0.0),
            "market": None
        },
        "mode": {
            "hilton": hilton_sentiment.get("mode_score", 0.0),
            "market": None
        },
        "positive_pct": {
            "hilton": hilton_pos_pct,
            "market": market_pos_pct
        },
        "neutral_pct": {
            "hilton": hilton_neu_pct,
            "market": market_neu_pct
        },
        "negative_pct": {
            "hilton": hilton_neg_pct,
            "market": market_neg_pct
        }
    }

    avg_score = round(micro_mean, 3)

    if avg_score is None:   market_label = "No Data"
    elif avg_score > 0.5:  market_label = "Very Positive"
    elif avg_score > 0.2:  market_label = "Positive"
    elif avg_score > -0.2: market_label = "Mixed / Neutral"
    elif avg_score > -0.5: market_label = "Negative"
    else:                  market_label = "Very Negative"

    avg_rating = round(sum(r["rating"] for r in with_rating) / len(with_rating), 2) if with_rating else None

    hilton_stats = {
        "score": hilton_sentiment.get("overall_score", 0.0),
        "pos_pct": hilton_pos_pct,
        "neu_pct": hilton_neu_pct,
        "neg_pct": hilton_neg_pct,
        "total_positive": hilton_pos,
        "total_neutral": hilton_neu,
        "total_negative": hilton_neg,
        "journey": hilton_sentiment.get("journey_breakdown", {})
    }

    # Calculate Bayesian Weighted Sentiment Score
    m_threshold = 15.0
    market_mean = avg_score if avg_score is not None else 0.0

    for r in results:
        raw_score = r.get("sentiment", {}).get("overall_score", 0.0)
        v_count = float(r.get("scraped_review_count", 0))
        
        if raw_score is not None:
            bayes_score = (v_count / (v_count + m_threshold)) * raw_score + (m_threshold / (v_count + m_threshold)) * market_mean
            r["bayesian_sentiment_score"] = round(bayes_score, 3)
        else:
            r["bayesian_sentiment_score"] = -999.0

        r["insufficient_data"] = v_count < m_threshold

        adr = r.get("adr")
        if adr and raw_score:
            r["sentiment_adr_index"] = round(raw_score / adr, 4)

    ranked = sorted(
        results,
        key=lambda r: r.get("bayesian_sentiment_score", -999.0),
        reverse=True,
    )

    ranked_by_raw_score = sorted(
        results,
        key=lambda r: r.get("sentiment", {}).get("overall_score") if r.get("sentiment", {}).get("overall_score") is not None else -999.0,
        reverse=True,
    )

    reliable_ranked = [r for r in ranked if not r.get("insufficient_data")]
    if not reliable_ranked:
        reliable_ranked = ranked

    best  = reliable_ranked[0]  if reliable_ranked and with_sentiment else None
    worst = reliable_ranked[-1] if reliable_ranked and len(reliable_ranked) > 1 else None

    combined_themes = {}
    combined_journey = {
        phase: {sub: {"pos": 0, "neu": 0, "neg": 0} for sub in subs}
        for phase, subs in CUSTOMER_JOURNEY_TAXONOMY.items()
    }

    for r in results:
        for theme, count in r.get("sentiment", {}).get("keyword_themes", {}).items():
            combined_themes[theme] = combined_themes.get(theme, 0) + count

        p_journey = r.get("sentiment", {}).get("journey_breakdown", {})
        for phase_name, sub_dict in p_journey.items():
            if phase_name in combined_journey:
                for sub_name, counts in sub_dict.items():
                    if sub_name in combined_journey[phase_name]:
                        combined_journey[phase_name][sub_name]["pos"] += counts.get("pos", 0)
                        combined_journey[phase_name][sub_name]["neu"] += counts.get("neu", 0)
                        combined_journey[phase_name][sub_name]["neg"] += counts.get("neg", 0)

    total_pos = sum(r["sentiment"].get("positive_count", 0) for r in with_sentiment)
    total_neu = sum(r["sentiment"].get("neutral_count",  0) for r in with_sentiment)
    total_neg = sum(r["sentiment"].get("negative_count", 0) for r in with_sentiment)
    total_all = total_pos + total_neu + total_neg or 1

    positive_places = sum(1 for r in with_sentiment if r["sentiment"].get("overall_score", 0) > 0.2)
    neutral_places  = sum(1 for r in with_sentiment if -0.2 <= r["sentiment"].get("overall_score", 0) <= 0.2)
    negative_places = sum(1 for r in with_sentiment if r["sentiment"].get("overall_score", 0) < -0.2)

    insights = []
    if avg_score is not None:
        if avg_score > 0.4:
            insights.append("Customer sentiment across luxury hotels in this market is strongly positive — reputation and word-of-mouth are major drivers of bookings.")
        elif avg_score > 0.1:
            insights.append("Sentiment leans positive but inconsistently — there is a clear opportunity to differentiate through consistently excellent guest experience.")
        elif avg_score > -0.1:
            insights.append("Mixed sentiment indicates guests have varied experiences. Service consistency appears to be the primary challenge across the market.")
        else:
            insights.append("Negative sentiment dominates — a significant service quality gap exists in this luxury hotel market that a well-run property can exploit.")

    if best:
        insights.append(f"{best['name']} leads the market in customer sentiment (score: {best['sentiment']['overall_score']:+.3f}), setting the benchmark that other properties are judged against.")

    if worst and worst["name"] != best["name"]:
        insights.append(f"{worst['name']} has the lowest sentiment score ({worst['sentiment']['overall_score']:+.3f}) — their reviews likely reveal the most common guest pain points in this market.")

    if combined_themes:
        top_theme = max(combined_themes.items(), key=lambda x: x[1])[0]
        insights.append(f"'{top_theme}' is the most frequently mentioned topic across all hotel reviews — this is the primary decision factor for guests in this market.")

    total_scraped = sum(r.get("scraped_review_count", 0) for r in results)
    insights.append(f"Analysis based on {total_scraped:,} reviews found across {len(results)} hotel(s) over the selected period.")

    return {
        "total_analysed":         len(results),
        "total_reviews_analyzed": total_scraped,
        "with_sentiment":         len(with_sentiment),
        "avg_sentiment_score":    avg_score,
        "sector_analysis_table":  sector_analysis_table,
        "hilton_stats":           hilton_stats,
        "market_label":           market_label,
        "avg_rating":             avg_rating,
        "sentiment_ranking":      [
            {
                "name": r["name"],
                "score": r.get("sentiment", {}).get("overall_score"),
                "bayesian_score": r.get("bayesian_sentiment_score"),
                "insufficient_data": r.get("insufficient_data", False),
                "label": r.get("sentiment", {}).get("overall_label"),
                "rating": r.get("rating"),
                "isUser": r.get("is_user_establishment", False),
                "adr": r.get("adr"),
                "revpar": r.get("revpar")
            } for r in ranked_by_raw_score
        ],
        "best_sentiment":         {"name": best["name"], "score": best["sentiment"].get("overall_score")} if best else None,
        "worst_sentiment":        {"name": worst["name"], "score": worst["sentiment"].get("overall_score")} if worst else None,
        "total_positive":         total_pos,
        "total_neutral":          total_neu,
        "total_negative":         total_neg,
        "positive_pct":           round(total_pos / total_all * 100, 1) if with_sentiment else 0,
        "neutral_pct":            round(total_neu / total_all * 100, 1) if with_sentiment else 0,
        "negative_pct":           round(total_neg / total_all * 100, 1) if with_sentiment else 0,
        "positive_places":        positive_places,
        "neutral_places":         neutral_places,
        "negative_places":        negative_places,
        "combined_themes":        dict(sorted(combined_themes.items(), key=lambda x: x[1], reverse=True)),
        "combined_journey":       combined_journey,
        "insights":               insights,
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/test-instant")
async def test_instant_sentiment():
    _clean_expired_tasks()
    mock_file = os.path.join(os.path.dirname(__file__), "test_hotel_reviews.json")
    if not os.path.exists(mock_file):
        raise HTTPException(status_code=404, detail="test_hotel_reviews.json not found")

    with open(mock_file, "r", encoding="utf-8") as f:
        mock_data = json.load(f)

    results = []
    for idx, (place_name, reviews) in enumerate(mock_data.items()):
        sentiment = _run_huggingface_sentiment_analysis(reviews)
        results.append({
            "name": place_name,
            "address": "Mock Test Address",
            "rating": 4.7,
            "google_review_count": len(reviews),
            "scraped_review_count": len(reviews),
            "url": "https://maps.google.com",
            "lat": 25.2048 + (idx * 0.01),
            "lng": 55.2708 + (idx * 0.01), 
            "is_user_establishment": True if "Regency" in place_name else False,
            "distance_km": 0.0,
            "sentiment": sentiment,
            "adr": None,
            "revpar": None,
            "occupancy_rate": None
        })

    combined_report = _build_combined_sentiment_report(results)

    test_task_id = "instant-test-task"
    hotel_sentiment_tasks[test_task_id] = {
        "status": "completed",
        "progress": 100,
        "status_message": "Instant mock analysis complete.",
        "results": results,
        "combined_report": combined_report,
        "city": "Test City",
        "days_back": 30,
        "created_at": datetime.datetime.now()
    }

    return {
        "task_id": test_task_id,
        "status": "completed",
        "results": results,
        "combined_report": combined_report
    }

@router.post("/search")
async def hotel_search(request: HotelSearchRequest, background_tasks: BackgroundTasks):
    _clean_expired_tasks()
    task_id = str(uuid.uuid4())
    hotel_sentiment_tasks[task_id] = {
        "status": "searching", "progress": 0,
        "status_message": f"Searching for Luxury Hotels near {request.city}...",
        "places": [], "error": None, "city": request.city,
        "days_back": request.days_back,
        "created_at": datetime.datetime.now()
    }
    background_tasks.add_task(
        _hotel_search_worker,
        task_id=task_id,
        city=request.city,
        radius_km=request.radius_km,
        limit=request.limit,
        establishment_name=request.establishment_name,
        origin_lat=request.origin_lat,
        origin_lng=request.origin_lng,
    )
    return {"task_id": task_id}


@router.get("/progress/{task_id}")
async def hotel_progress(task_id: str):
    task = hotel_sentiment_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return {
        "status":          task.get("status"),
        "progress":        task.get("progress", 0),
        "status_message":  task.get("status_message", ""),
        "places":          task.get("places", []),
        "results":         task.get("results", []),
        "combined_report": task.get("combined_report", {}),
        "errors":          task.get("errors", []),
        "error":           task.get("error"),
    }


@router.post("/analyse")
async def hotel_analyse(request: HotelAnalyzeRequest, background_tasks: BackgroundTasks):
    task = hotel_sentiment_tasks.get(request.task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    task["status"]         = "analysing"
    task["progress"]       = 0
    task["status_message"] = "Starting sentiment analysis..."
    task["days_back"]      = request.days_back

    background_tasks.add_task(
        _hotel_sentiment_worker,
        task_id=request.task_id,
        places=request.approved_places,
        days_back=request.days_back,
    )
    return {"task_id": request.task_id, "status": "analysing"}


@router.get("/report/pdf/{task_id}")
async def download_sentiment_pdf(task_id: str, client_time: Optional[str] = None):
    task = hotel_sentiment_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if task.get("status") != "completed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Analysis not complete yet")
    try:
        pdf_bytes = _generate_sentiment_pdf(task, client_time=client_time)
        city      = task.get("city", "hotel")
        filename  = f"hotel-sentiment-{city.replace(' ','-')}-{datetime.date.today()}.pdf"
        return StreamingResponse(
            io.BytesIO(pdf_bytes), media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error(f"[HOTEL SENTIMENT] PDF generation failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"PDF generation failed: {e}")


def _generate_sentiment_pdf(task: dict, client_time: Optional[str] = None, **kwargs) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, PageBreak, KeepTogether, Image
    )
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

    results   = task.get("results", [])
    combined  = task.get("combined_report", {})
    days_back = task.get("days_back", 30)

    hilton_stats = combined.get("hilton_stats", {
        "score": 0.0, "pos_pct": 0.0, "neg_pct": 0.0,
        "total_positive": 0, "total_neutral": 0, "total_negative": 0, "journey": {}
    })

    establishment_name = task.get("establishment_name", "")
    user_est = None
    if results:
        user_est = next((r.get("name") for r in results if r.get("is_user_establishment")), None)
        if not establishment_name:
            establishment_name = user_est or results[0].get("name", "")

    PURPLE      = colors.HexColor("#7C3AED")
    PURPLE_DARK = colors.HexColor("#4C1D95")
    PURPLE_LITE = colors.HexColor("#EDE9FE")
    SLATE       = colors.HexColor("#1E293B")
    SLATE_MID   = colors.HexColor("#475569")
    SLATE_LITE  = colors.HexColor("#F8FAFC")
    GREEN       = colors.HexColor("#059669")
    RED         = colors.HexColor("#DC2626")
    AMBER       = colors.HexColor("#D97706")
    WHITE       = colors.white

    score = combined.get("avg_sentiment_score", 0) or 0

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, 
        pagesize=A4, 
        rightMargin=2*cm, 
        leftMargin=2*cm, 
        topMargin=2.5*cm, 
        bottomMargin=2.5*cm,
        title="Sentiment Analysis Report"
    )
    W = A4[0] - 4*cm

    def S(name, **kw): return ParagraphStyle(name, **kw)
    style_body       = S("Body",    fontSize=9,  leading=14, textColor=SLATE_MID,   fontName="Helvetica",      spaceAfter=4)
    style_body_bold  = S("BB",      fontSize=9,  leading=14, textColor=SLATE,       fontName="Helvetica-Bold")
    style_section    = S("Sect",    fontSize=13, leading=18, textColor=PURPLE_DARK, fontName="Helvetica-Bold", spaceBefore=18, spaceAfter=6)
    style_small      = S("Small",   fontSize=8,  leading=12, textColor=SLATE_MID,   fontName="Helvetica")
    style_cover_h1   = S("CH1",     fontSize=24, leading=28, textColor=PURPLE_DARK, fontName="Helvetica-Bold", alignment=TA_CENTER)
    style_cover_est  = S("CEst",    fontSize=16, leading=20, textColor=PURPLE,      fontName="Helvetica-Bold", alignment=TA_CENTER)
    style_cover_sub  = S("CSub",    fontSize=11, leading=15, textColor=SLATE_MID,   fontName="Helvetica",      alignment=TA_CENTER)
    style_italic     = S("It",      fontSize=8,  leading=13, textColor=SLATE_MID,   fontName="Helvetica-Oblique")

    logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
    has_logo = os.path.exists(logo_path)

    def draw_later_page_footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#CBD5E1"))
        canvas.setLineWidth(0.5)
        canvas.line(2*cm, 2*cm, A4[0] - 2*cm, 2*cm)
        
        if has_logo:
            try:
                canvas.drawImage(logo_path, 2*cm, 1.1*cm, width=1.8*cm, height=0.7*cm, preserveAspectRatio=True, mask='auto')
            except Exception:
                pass

        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(SLATE)
        canvas.drawString(4*cm if has_logo else 2*cm, 1.4*cm, "DoWell Research")
        
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(SLATE_MID)
        footer_date = client_time if client_time else datetime.date.today().strftime('%d %B %Y')
        canvas.drawString(4*cm if has_logo else 2*cm, 1.1*cm, f"Generated: {footer_date}  ·  Sentiment Analysis Report")
        
        canvas.drawRightString(A4[0] - 2*cm, 1.2*cm, f"Page {doc.page}")
        canvas.restoreState()

    def draw_cover_footer(canvas, doc):
        pass

    story = []

    # COVER PAGE
    story.append(Spacer(1, 0.5*cm))

    if has_logo:
        try:
            story.append(Image(logo_path, width=4*cm, height=1.5*cm, kind='proportional'))
            story.append(Spacer(1, 0.5*cm))
        except Exception:
            pass

    story.append(Paragraph("Sentiment Analysis Report", style_cover_h1))
    story.append(Paragraph("DoWell Research", style_cover_sub))
    story.append(Spacer(1, 0.3*cm))

    if establishment_name:
        story.append(Paragraph(f"{establishment_name}", style_cover_est))
        story.append(Spacer(1, 0.3*cm))

    story.append(HRFlowable(width=W*0.8, thickness=1.5, color=PURPLE, spaceAfter=15))
    report_date = client_time if client_time else datetime.date.today().strftime('%B %d, %Y')

    meta_table_data = [
        [Paragraph("<b>Report Date:</b>", style_small), Paragraph(report_date, style_small)],
        [Paragraph("<b>Sample Footprint:</b>", style_small), Paragraph(f"{len(results)} properties | {combined.get('total_reviews_analyzed', 0):,} reviews | {days_back} days", style_small)],
        [Paragraph("<b>Baseline Metrics:</b>", style_small), Paragraph(f"Market Sentiment Score: {score:+.3f} | Avg Rating: ★ {combined.get('avg_rating','—')}", style_small)],
        [Paragraph("<b>Prepared By:</b>", style_body_bold), Paragraph("DoWell Research", style_body_bold)],
    ]
    meta_table = Table(meta_table_data, colWidths=[W*0.35, W*0.45])
    meta_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, -1), SLATE_LITE),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 0.5*cm))

    story.append(PageBreak())

    # ==============================================================================
    # PAGE 2: SECTOR ANALYSIS
    # ==============================================================================

    story.append(Paragraph("Sector Analysis", style_section))
    story.append(HRFlowable(width=W, thickness=1, color=PURPLE_LITE))
    story.append(Spacer(1, 0.25*cm))

    # Fetch structured side-by-side analysis data
    sector_tbl = combined.get("sector_analysis_table", {})

    market_stats_data = [
        [
            Paragraph("<b>Statistical Indicator</b>", style_body_bold), 
            Paragraph(f"<b>{user_est or 'Hilton'} Value</b>", style_body_bold), 
            Paragraph("<b>Combined Market Value</b>", style_body_bold)
        ],
        [
            Paragraph("Mean (Average) Score", style_small), 
            Paragraph(f"{sector_tbl.get('mean', {}).get('hilton', 0.0):+.3f}", style_small),
            Paragraph(f"{sector_tbl.get('mean', {}).get('market', 0.0):+.3f}", style_small)
        ],
        [
            Paragraph("Median Score", style_small), 
            Paragraph(f"{sector_tbl.get('median', {}).get('hilton', 0.0):+.3f}", style_small),
            Paragraph("—", style_small)
        ],
        [
            Paragraph("Mode Score", style_small), 
            Paragraph(f"{sector_tbl.get('mode', {}).get('hilton', 0.0):+.3f}", style_small),
            Paragraph("—", style_small)
        ],
        [
            Paragraph("Positive Sentiment %", style_small), 
            Paragraph(f"{sector_tbl.get('positive_pct', {}).get('hilton', 0.0)}%", style_small),
            Paragraph(f"{sector_tbl.get('positive_pct', {}).get('market', 0.0)}%", style_small)
        ],
        [
            Paragraph("Neutral Sentiment %", style_small), 
            Paragraph(f"{sector_tbl.get('neutral_pct', {}).get('hilton', 0.0)}%", style_small),
            Paragraph(f"{sector_tbl.get('neutral_pct', {}).get('market', 0.0)}%", style_small)
        ],
        [
            Paragraph("Negative Sentiment %", style_small), 
            Paragraph(f"{sector_tbl.get('negative_pct', {}).get('hilton', 0.0)}%", style_small),
            Paragraph(f"{sector_tbl.get('negative_pct', {}).get('market', 0.0)}%", style_small)
        ]
    ]

    market_table = Table(market_stats_data, colWidths=[W * 0.40, W * 0.30, W * 0.30])
    market_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), SLATE_LITE),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
    ]))
    story.append(market_table)
    story.append(Spacer(1, 0.5*cm))

    est_label = user_est if user_est else "Hilton Baseline"

    story.append(Paragraph(f"{est_label} — Key Performance Snapshot", style_section))
    story.append(HRFlowable(width=W, thickness=1, color=PURPLE_LITE))
    story.append(Spacer(1, 0.25*cm))

    PURPLE_BASE = colors.HexColor("#4F46E5")
    styles = getSampleStyleSheet()

    style_kpi_num = ParagraphStyle(
        "KpiNum",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=18,
        alignment=1,
        textColor=PURPLE_BASE
    )

    style_kpi_label = ParagraphStyle(
        "KpiLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        alignment=1,
        textColor=colors.HexColor("#475569")
    )

    score_val = hilton_stats.get('score', 0.0)
    score_color = "#059669" if score_val >= 0 else "#DC2626"

    kpi_card_data = [
        [
            Paragraph(f'<font color="{score_color}">{score_val:+.3f}</font>', style_kpi_num),
            Paragraph(f"{hilton_stats.get('pos_pct', 0.0)}%", style_kpi_num),
            Paragraph(f"{hilton_stats.get('neu_pct', 0.0)}%", style_kpi_num),
            Paragraph(f"{hilton_stats.get('neg_pct', 0.0)}%", style_kpi_num),
        ],
        [
            Paragraph("OVERALL SCORE", style_kpi_label),
            Paragraph("POSITIVE SENTIMENT", style_kpi_label),
            Paragraph("NEUTRAL SENTIMENT", style_kpi_label),
            Paragraph("NEGATIVE SENTIMENT", style_kpi_label),
        ]
    ]

    col_w = W / 4.0
    kpi_card_table = Table(kpi_card_data, colWidths=[col_w, col_w, col_w, col_w])
    kpi_card_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ('BOX', (0, 0), (-1, -1), 1, PURPLE_LITE),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, -1), (-1, -1), 10),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))

    story.append(kpi_card_table)
    story.append(Spacer(1, 0.4*cm))

    # ── Geographic Distribution Section ─────────────────────────────────────────
    story.append(Paragraph("Geographic Distribution & Competitors", style_section))
    story.append(HRFlowable(width=W, thickness=1, color=PURPLE_LITE))
    story.append(Spacer(1, 0.25 * cm))

    map_buffer = _fetch_static_map_image(results)
    if map_buffer:
        try:
            map_img = Image(map_buffer, width=W, height=6.5 * cm, kind='proportional')
            story.append(map_img)
            story.append(Spacer(1, 0.4 * cm))
        except Exception as err:
            logger.error(f"[PDF MAP] Failed to render image flowable: {err}")

    # PAGE 3: SENTIMENT RANKING
    ranking = combined.get("sentiment_ranking", [])
    if ranking:
        story.append(PageBreak())
        story.append(Spacer(1, 0.4*cm))
        story.append(Paragraph("Sentiment Ranking Across Competitors", style_section))
        story.append(HRFlowable(width=W, thickness=1, color=PURPLE_LITE))
        story.append(Spacer(1, 0.2*cm))
        ranking_sorted = sorted(
            ranking,
            key=lambda item: item.get("score") if item.get("score") is not None else -999.0,
            reverse=True
        )
        rank_rows = [["#","Hotel","Sentiment","Score","Rating"]]
        for i, r in enumerate(ranking_sorted):
            sc = r.get("score")
            sc_color = "#059669" if sc and sc>0.2 else ("#DC2626" if sc and sc<-0.2 else "#B45309")
            hotel_name_markup = f"<b>[YOU] {r.get('name')}</b>" if r.get("isUser") else r.get("name","")
            rank_rows.append([
                str(i+1),
                Paragraph(hotel_name_markup, style_body),
                Paragraph(f'<font color="{sc_color}">{r.get("label","")}</font>', style_body),
                Paragraph(f'<font color="{sc_color}">{f"{sc:+.3f}" if sc is not None else "—"}</font>', style_body_bold),
                f"★ {r['rating']}" if r.get("rating") else "—",
            ])
        rt = Table(rank_rows, colWidths=[W*0.06,W*0.38,W*0.25,W*0.15,W*0.16])
        rt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),PURPLE_DARK),("TEXTCOLOR",(0,0),(-1,0),WHITE),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),8),("ALIGN",(0,0),(0,-1),"CENTER"),("ALIGN",(3,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("ROWBACKGROUNDS",(0,1),(-1,-1),[WHITE,SLATE_LITE]),("INNERGRID",(0,0),(-1,-1),0.3,colors.HexColor("#E2E8F0")),("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#CBD5E1")),("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),("LEFTPADDING",(0,0),(-1,-1),8)]))
        story.append(rt)

    # PAGE 4: TOUCHPOINT SENTIMENT COMPARISON
    cj_data = combined.get("combined_journey", {})
    hilton_cj_data = hilton_stats.get("journey", {})

    if cj_data:
        story.append(PageBreak())
        story.append(Paragraph("Touchpoint Sentiment Comparison", style_section))
        story.append(HRFlowable(width=W, thickness=1, color=PURPLE_LITE))
        story.append(Spacer(1, 0.2*cm))

        cj_rows = [["Operational Phase / Touchpoint", "Combined Market (+ / -)", "Hilton (+ / -)"]]
        
        for phase_name, sub_dict in cj_data.items():
            cj_rows.append([Paragraph(f"<b>{phase_name}</b>", style_body_bold), "", ""])

            for sub_name, counts in sub_dict.items():
                comb_pos, comb_neg = counts["pos"], counts["neg"]
                
                hilton_sub = hilton_cj_data.get(phase_name, {}).get(sub_name, {"pos": 0, "neg": 0})
                h_pos, h_neg = hilton_sub["pos"], hilton_sub["neg"]

                if (comb_pos + comb_neg) > 0 or (h_pos + h_neg) > 0:
                    cj_rows.append([
                        Paragraph(f"&nbsp;&nbsp;&nbsp;&nbsp;• {sub_name}", style_small),
                        Paragraph(f"<font color='#059669'>+{comb_pos}</font> / <font color='#DC2626'>-{comb_neg}</font>", style_small),
                        Paragraph(f"<font color='#059669'>+{h_pos}</font> / <font color='#DC2626'>-{h_neg}</font>", style_small)
                    ])

        cjt = Table(cj_rows, colWidths=[W*0.50, W*0.25, W*0.25])
        cjt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PURPLE_DARK),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, SLATE_LITE]),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E8F0")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4)
        ]))
        story.append(cjt)

    # INDIVIDUAL PROPERTY REPORT PAGES
    hilton_items = [r for r in results if r.get("is_user_establishment")]
    competitor_items = [r for r in results if not r.get("is_user_establishment")]

    competitor_items_sorted = sorted(
        competitor_items,
        key=lambda r: r.get("sentiment", {}).get("overall_score") if r.get("sentiment", {}).get("overall_score") is not None else -999.0,
        reverse=True
    )

    story.append(PageBreak())
    story.append(Paragraph("Individual Hotel Sentiment Breakdown", style_section))
    story.append(HRFlowable(width=W, thickness=1, color=PURPLE_LITE))
    story.append(Spacer(1, 0.2*cm))

    for i, r in enumerate(hilton_items + competitor_items_sorted):
        s = r.get("sentiment", {})
        sc = s.get("overall_score")
        pos = s.get("positive_count", 0)
        neu = s.get("neutral_count", 0)
        neg = s.get("negative_count", 0)
        total = pos + neu + neg or 1

        header = Table([[
            Paragraph(f"{'★ ' if r.get('is_user_establishment') else ''}{r.get('name','')}", ParagraphStyle("HN",fontSize=10,leading=14,textColor=WHITE if not r.get('is_user_establishment') else AMBER,fontName="Helvetica-Bold")),
            Paragraph(f"{s.get('overall_label','No Data')} · {f'{sc:+.3f}' if sc is not None else '—'}" + (f" · ★ {r['rating']}" if r.get('rating') else ""), ParagraphStyle("HS",fontSize=8,leading=12,textColor=PURPLE_LITE,fontName="Helvetica",alignment=TA_RIGHT)),
        ]], colWidths=[W*0.6, W*0.4])
        header.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),PURPLE_DARK),("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
        story.append(header)

        if r.get("scraped_review_count", 0) == 0:
            story.append(Table([[Paragraph("No reviews found for this period.",style_small)]],colWidths=[W],style=TableStyle([("BACKGROUND",(0,0),(-1,-1),SLATE_LITE),("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),("LEFTPADDING",(0,0),(-1,-1),10)])))
        else:
            body_rows = [
                [Paragraph(f"Reviews found: {r.get('scraped_review_count',0)}  ·  Positive: {pos} ({pos/total*100:.0f}%)  ·  Neutral: {neu} ({neu/total*100:.0f}%)  ·  Negative: {neg} ({neg/total*100:.0f}%)", style_small)],
            ]
            if s.get("top_positive_phrases"):
                p0 = s["top_positive_phrases"][0]
                body_rows.append([Paragraph(f'<font color="#059669">✓ {p0.get("author","")} ({p0.get("date","")}):</font> "{p0.get("text","")}"', style_italic)])
            if s.get("top_negative_phrases"):
                n0 = s["top_negative_phrases"][0]
                body_rows.append([Paragraph(f'<font color="#DC2626">✗ {n0.get("author","")} ({n0.get("date","")}):</font> "{n0.get("text","")}"', style_italic)])

            body = Table(body_rows, colWidths=[W])
            body.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),WHITE),("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),5),("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#E2E8F0"))]))
            story.append(body)

        story.append(Spacer(1, 0.3*cm))

    doc.build(story, onFirstPage=draw_cover_footer, onLaterPages=draw_later_page_footer)
    return buf.getvalue()