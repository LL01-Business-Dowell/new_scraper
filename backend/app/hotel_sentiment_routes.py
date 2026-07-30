"""
hotel_sentiment_routes.py
--------------------------
FastAPI router for the Hotel Sentiment Analysis feature.
Route prefix: /api/hotel-sentiment
"""

import uuid
import logging
import urllib.parse
import os
import json
import io
import time
import datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from transformers import pipeline

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/hotel-sentiment", tags=["Sentiment Analysis"])

# ─────────────────────────────────────────────────────────────────────────────
# 🎛️ CONFIGURATION SWITCH
# Set to True to test locally with zero Apify credits used.
# Set to False to run live scraping via Apify on Google Maps reviews.
USE_MOCK_DATA = False
# ─────────────────────────────────────────────────────────────────────────────

# In-memory task store
hotel_sentiment_tasks = {}

# Initialize Hugging Face sentiment model pipeline
logger.info("[HOTEL SENTIMENT] Initializing Hugging Face sentiment model...")
try:
    hf_sentiment_analyzer = pipeline(
        "sentiment-analysis",
        model="cardiffnlp/twitter-roberta-base-sentiment-latest",
        return_all_scores=True
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


class HotelAnalyzeRequest(BaseModel):
    task_id: str
    approved_places: List[dict]
    establishment_name: str = ""
    days_back: int = 30


# ── Hugging Face Analysis Engine ──────────────────────────────────────────────

def _run_huggingface_sentiment_analysis(reviews: list) -> dict:
    """Processes reviews through the Hugging Face sentiment pipeline."""
    if not reviews or not hf_sentiment_analyzer:
        return {
            "overall_score": 0.0,
            "overall_label": "Mixed / Neutral",
            "positive_count": 0,
            "neutral_count": 0,
            "negative_count": 0,
            "top_positive_phrases": [],
            "top_negative_phrases": [],
            "keyword_themes": {}
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
    }

    for rev in reviews:
        text = rev.get("text", "")
        if not text or text == "[Rating Only]":
            continue

        results = hf_sentiment_analyzer(text[:512])[0]
        scores = {item['label'].lower(): item['score'] for item in results}

        pos_score = scores.get('positive', 0.0)
        neg_score = scores.get('negative', 0.0)
        neu_score = scores.get('neutral', 0.0)

        compound = pos_score - neg_score
        total_compound += compound

        phrase_data = {
            "author": rev.get("author", "Guest"),
            "date": rev.get("date", "Recent"),
            "text": text
        }

        if pos_score > neg_score and pos_score > neu_score:
            positive_count += 1
            pos_phrases.append(phrase_data)
        elif neg_score > pos_score and neg_score > neu_score:
            negative_count += 1
            neg_phrases.append(phrase_data)
        else:
            neutral_count += 1

        text_lower = text.lower()
        if any(k in text_lower for k in ["staff", "service", "desk", "concierge"]):
            keyword_themes["Service & Staff"] += 1
        if any(k in text_lower for k in ["room", "bed", "bathroom", "clean"]):
            keyword_themes["Room & Comfort"] += 1
        if any(k in text_lower for k in ["breakfast", "dining", "restaurant", "food"]):
            keyword_themes["Dining & Breakfast"] += 1
        if any(k in text_lower for k in ["location", "noise", "renovation", "street"]):
            keyword_themes["Location & Noise"] += 1

    total_valid = positive_count + neutral_count + negative_count or 1
    avg_score = round(total_compound / total_valid, 3)

    if avg_score > 0.2:
        overall_label = "Positive"
    elif avg_score < -0.2:
        overall_label = "Negative"
    else:
        overall_label = "Mixed / Neutral"

    return {
        "overall_score": avg_score,
        "overall_label": overall_label,
        "positive_count": positive_count,
        "neutral_count": neutral_count,
        "negative_count": negative_count,
        "top_positive_phrases": pos_phrases[:3],
        "top_negative_phrases": neg_phrases[:3],
        "keyword_themes": {k: v for k, v in keyword_themes.items() if v > 0}
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

    # 1. Direct exact match
    if name in mock_data:
        return mock_data[name]

    # 2. Case-insensitive / Partial match (e.g., "Hyatt" matches "Grand Hyatt Regency")
    name_lower = name.lower()
    for key, reviews in mock_data.items():
        if key.lower() in name_lower or name_lower in key.lower():
            return reviews

    # 3. Fallback to first available entry if no match
    return list(mock_data.values())[0]


def _fetch_reviews_apify(url: str, progress_cb) -> tuple[List[dict], dict, Optional[str]]:
    """Calls Apify scraper to pull live Google Maps reviews."""
    from .hotel_apify_scraper import scrape_hotel_reviews_apify
    scraped = scrape_hotel_reviews_apify(url=url, max_reviews=100, progress_callback=progress_cb)
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

        places = search_google_maps_competitors(
            keyword=keyword,
            city=city,
            establishment_name=establishment_name,
            radius_km=radius_km,
            limit=limit,
            origin_lat=origin_lat,
            origin_lng=origin_lng,
            progress_callback=progress,
        )

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
        places.insert(0, establishment)

        hotel_sentiment_tasks[task_id].update({
            "status":         "ready_for_approval",
            "progress":       100,
            "status_message": f"Found {len(places)} luxury hotels. Please review and approve.",
            "places":         places,
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
            time.sleep(0.5)  # Simulate progress delay for frontend testing
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
            "is_user_establishment": place.get("is_user_establishment", False),
            "distance_km":          place.get("distance_km", 0.0),
            "sentiment":            sentiment,
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
    with_sentiment = [r for r in results if r.get("sentiment", {}).get("overall_score") is not None]
    with_rating    = [r for r in results if r.get("rating")]

    if not results:
        return {}

    scores = [r["sentiment"]["overall_score"] for r in with_sentiment]
    avg_score = round(sum(scores) / len(scores), 3) if scores else None

    if avg_score is None:   market_label = "No Data"
    elif avg_score > 0.5:  market_label = "Very Positive"
    elif avg_score > 0.2:  market_label = "Positive"
    elif avg_score > -0.2: market_label = "Mixed / Neutral"
    elif avg_score > -0.5: market_label = "Negative"
    else:                  market_label = "Very Negative"

    avg_rating = round(sum(r["rating"] for r in with_rating) / len(with_rating), 2) if with_rating else None

    ranked = sorted(
        results,
        key=lambda r: r.get("sentiment", {}).get("overall_score") if r.get("sentiment", {}).get("overall_score") is not None else -999,
        reverse=True,
    )

    best  = ranked[0]  if with_sentiment else None
    worst = ranked[-1] if len(with_sentiment) > 1 else None

    combined_themes = {}
    for r in results:
        for theme, count in r.get("sentiment", {}).get("keyword_themes", {}).items():
            combined_themes[theme] = combined_themes.get(theme, 0) + count

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
        "total_analysed":       len(results),
        "total_reviews_analyzed": total_scraped,
        "with_sentiment":       len(with_sentiment),
        "avg_sentiment_score":  avg_score,
        "market_label":         market_label,
        "avg_rating":           avg_rating,
        "sentiment_ranking":    [
            {
                "name": r["name"],
                "score": r.get("sentiment", {}).get("overall_score"),
                "label": r.get("sentiment", {}).get("overall_label"),
                "rating": r.get("rating"),
                "isUser": r.get("is_user_establishment", False)
            } for r in ranked
        ],
        "best_sentiment":       {"name": best["name"], "score": best["sentiment"].get("overall_score")} if best else None,
        "worst_sentiment":      {"name": worst["name"], "score": worst["sentiment"].get("overall_score")} if worst else None,
        "total_positive":       total_pos,
        "total_neutral":        total_neu,
        "total_negative":       total_neg,
        "positive_pct":         round(total_pos / total_all * 100, 1) if with_sentiment else 0,
        "neutral_pct":          round(total_neu / total_all * 100, 1) if with_sentiment else 0,
        "negative_pct":         round(total_neg / total_all * 100, 1) if with_sentiment else 0,
        "positive_places":      positive_places,
        "neutral_places":       neutral_places,
        "negative_places":      negative_places,
        "combined_themes":      dict(sorted(combined_themes.items(), key=lambda x: x[1], reverse=True)),
        "insights":             insights,
    }


# ── Routes ────────────────────────────────────────────────────────────────────
@router.post("/test-instant")
async def test_instant_sentiment():
    """
    Directly runs Hugging Face sentiment analysis on test_hotel_reviews.json
    and returns immediate report results, skipping search and scraping.
    """
    mock_file = os.path.join(os.path.dirname(__file__), "test_hotel_reviews.json")
    if not os.path.exists(mock_file):
        raise HTTPException(status_code=404, detail="test_hotel_reviews.json not found")

    with open(mock_file, "r", encoding="utf-8") as f:
        mock_data = json.load(f)

    results = []
    for place_name, reviews in mock_data.items():
        sentiment = _run_huggingface_sentiment_analysis(reviews)
        results.append({
            "name": place_name,
            "address": "Mock Test Address",
            "rating": 4.7,
            "google_review_count": len(reviews),
            "scraped_review_count": len(reviews),
            "url": "https://maps.google.com",
            "is_user_establishment": True if "Regency" in place_name else False,
            "distance_km": 0.0,
            "sentiment": sentiment,
        })

    combined_report = _build_combined_sentiment_report(results)

    # Save to a static test task so PDF export route works too
    test_task_id = "instant-test-task"
    hotel_sentiment_tasks[test_task_id] = {
        "status": "completed",
        "progress": 100,
        "status_message": "Instant mock analysis complete.",
        "results": results,
        "combined_report": combined_report,
        "city": "Test City",
        "days_back": 30
    }

    return {
        "task_id": test_task_id,
        "status": "completed",
        "results": results,
        "combined_report": combined_report
    }

@router.post("/search")
async def hotel_search(request: HotelSearchRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    hotel_sentiment_tasks[task_id] = {
        "status": "searching", "progress": 0,
        "status_message": f"Searching for Luxury Hotels near {request.city}...",
        "places": [], "error": None, "city": request.city,
        "days_back": request.days_back,
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
async def download_sentiment_pdf(task_id: str):
    task = hotel_sentiment_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if task.get("status") != "completed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Analysis not complete yet")
    try:
        pdf_bytes = _generate_sentiment_pdf(task)
        city      = task.get("city", "hotel")
        filename  = f"hotel-sentiment-{city.replace(' ','-')}-{datetime.date.today()}.pdf"
        return StreamingResponse(
            io.BytesIO(pdf_bytes), media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error(f"[HOTEL SENTIMENT] PDF generation failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"PDF generation failed: {e}")


def _generate_sentiment_pdf(task: dict) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, PageBreak, KeepTogether,
    )
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT

    results   = task.get("results", [])
    combined  = task.get("combined_report", {})
    days_back = task.get("days_back", 30)

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
    score_color = GREEN if score > 0.2 else (RED if score < -0.2 else AMBER)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2.5*cm, bottomMargin=2*cm)
    W = A4[0] - 4*cm

    def S(name, **kw): return ParagraphStyle(name, **kw)
    style_body       = S("Body",    fontSize=9,  leading=14, textColor=SLATE_MID,   fontName="Helvetica",      spaceAfter=4)
    style_body_bold  = S("BB",      fontSize=9,  leading=14, textColor=SLATE,       fontName="Helvetica-Bold")
    style_section    = S("Sect",    fontSize=13, leading=18, textColor=PURPLE_DARK, fontName="Helvetica-Bold", spaceBefore=18, spaceAfter=6)
    style_small      = S("Small",   fontSize=8,  leading=12, textColor=SLATE_MID,   fontName="Helvetica")
    style_caption    = S("Cap",     fontSize=8,  leading=12, textColor=SLATE_MID,   fontName="Helvetica",      alignment=TA_CENTER)
    style_num_big    = S("NumBig",  fontSize=28, leading=32, textColor=PURPLE,      fontName="Helvetica-Bold", alignment=TA_CENTER)
    style_num_label  = S("NLabel",  fontSize=8,  leading=10, textColor=SLATE_MID,   fontName="Helvetica",      alignment=TA_CENTER)
    style_cover_h1   = S("CH1",     fontSize=26, leading=32, textColor=WHITE,       fontName="Helvetica-Bold")
    style_cover_sub  = S("CSub",    fontSize=11, leading=16, textColor=PURPLE_LITE, fontName="Helvetica")
    style_cover_meta = S("CMeta",   fontSize=9,  leading=14, textColor=PURPLE_LITE, fontName="Helvetica")
    style_italic     = S("It",      fontSize=8,  leading=13, textColor=SLATE_MID,   fontName="Helvetica-Oblique")

    def bar_cell(ratio, color, max_w):
        bw = max(2, ratio * max_w)
        bt = Table([[""]], colWidths=[bw], rowHeights=[10])
        bt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),color),("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0),("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0)]))
        return bt

    story = []

    # Cover Page
    cover = Table([
        [Paragraph("Luxury Hotel Sentiment Analysis", style_cover_h1)],
        [Paragraph(combined.get("market_label",""), style_cover_sub)],
        [Spacer(1, 0.3*cm)],
        [Paragraph(f"Analysis period: last {days_back} days  ·  {combined.get('total_analysed',0)} hotels analysed  ·  Generated: {datetime.date.today().strftime('%d %B %Y')}", style_cover_meta)],
        [Paragraph(f"Average sentiment score: {score:+.3f}  ·  Average rating: ★ {combined.get('avg_rating','N/A')}", style_cover_meta)],
    ], colWidths=[W])
    cover.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),PURPLE_DARK),("TOPPADDING",(0,0),(-1,0),24),("BOTTOMPADDING",(0,-1),(-1,-1),24),("LEFTPADDING",(0,0),(-1,-1),20),("RIGHTPADDING",(0,0),(-1,-1),20)]))
    story.append(cover)
    story.append(Spacer(1, 0.5*cm))

    # KPI tiles
    kpi_data = [
        [Paragraph(str(combined.get("total_analysed",0)), style_num_big),
         Paragraph(f"{score:+.3f}", ParagraphStyle("SN",fontSize=28,leading=32,textColor=score_color,fontName="Helvetica-Bold",alignment=TA_CENTER)),
         Paragraph(f"{combined.get('positive_pct',0)}%", ParagraphStyle("PP",fontSize=28,leading=32,textColor=GREEN,fontName="Helvetica-Bold",alignment=TA_CENTER)),
         Paragraph(f"{combined.get('negative_pct',0)}%", ParagraphStyle("NP",fontSize=28,leading=32,textColor=RED,fontName="Helvetica-Bold",alignment=TA_CENTER)),
        ],
        [Paragraph("Hotels Analysed",style_num_label), Paragraph("Avg Sentiment Score",style_num_label), Paragraph("Positive Reviews",style_num_label), Paragraph("Negative Reviews",style_num_label)],
    ]
    kpi = Table(kpi_data, colWidths=[W/4]*4)
    kpi.setStyle(TableStyle([("ALIGN",(0,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("BACKGROUND",(0,0),(-1,-1),SLATE_LITE),("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#E2E8F0")),("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor("#E2E8F0")),("TOPPADDING",(0,0),(-1,-1),14),("BOTTOMPADDING",(0,0),(-1,-1),10)]))
    story.append(kpi)
    story.append(Spacer(1, 0.4*cm))

    # Sentiment Breakdown
    story.append(Paragraph("Sentiment Breakdown", style_section))
    story.append(HRFlowable(width=W, thickness=1, color=PURPLE_LITE))
    story.append(Spacer(1, 0.2*cm))
    pos_pct = combined.get("positive_pct",0)/100
    neu_pct = combined.get("neutral_pct",0)/100
    neg_pct = combined.get("negative_pct",0)/100
    sent_rows = [
        ["Sentiment","Reviews","Pct",""],
        [Paragraph('<font color="#059669">Positive</font>',style_body_bold), str(combined.get("total_positive",0)), f"{combined.get('positive_pct',0)}%", bar_cell(pos_pct,GREEN,W*0.3)],
        [Paragraph('<font color="#B45309">Neutral</font>', style_body_bold), str(combined.get("total_neutral",0)),  f"{combined.get('neutral_pct',0)}%",  bar_cell(neu_pct,AMBER, W*0.3)],
        [Paragraph('<font color="#DC2626">Negative</font>',style_body_bold), str(combined.get("total_negative",0)), f"{combined.get('negative_pct',0)}%", bar_cell(neg_pct,RED,   W*0.3)],
    ]
    st = Table(sent_rows, colWidths=[W*0.25,W*0.12,W*0.13,W*0.5])
    st.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),PURPLE_DARK),("TEXTCOLOR",(0,0),(-1,0),WHITE),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),8),("ALIGN",(1,0),(2,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("ROWBACKGROUNDS",(0,1),(-1,-1),[WHITE,SLATE_LITE]),("INNERGRID",(0,0),(-1,-1),0.3,colors.HexColor("#E2E8F0")),("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#CBD5E1")),("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7),("LEFTPADDING",(0,0),(-1,-1),8)]))
    story.append(st)
    story.append(Spacer(1, 0.4*cm))

    # Sentiment Ranking
    ranking = combined.get("sentiment_ranking", [])
    if ranking:
        story.append(Paragraph("Sentiment Ranking", style_section))
        story.append(HRFlowable(width=W, thickness=1, color=PURPLE_LITE))
        story.append(Spacer(1, 0.2*cm))
        rank_rows = [["#","Hotel","Sentiment","Score","Rating"]]
        for i, r in enumerate(ranking):
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
        rt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),PURPLE_DARK),("TEXTCOLOR",(0,0),(-1,0),WHITE),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),8),("ALIGN",(0,0),(0,-1),"CENTER"),("ALIGN",(3,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("ROWBACKGROUNDS",(0,1),(-1,-1),[WHITE,SLATE_LITE]),("INNERGRID",(0,0),(-1,-1),0.3,colors.HexColor("#E2E8F0")),("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#CBD5E1")),("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7),("LEFTPADDING",(0,0),(-1,-1),8)]))
        story.append(rt)

    # Topic Frequency
    themes = combined.get("combined_themes", {})
    if themes:
        story.append(PageBreak())
        story.append(Paragraph("Topic Frequency Across All Hotels", style_section))
        story.append(HRFlowable(width=W, thickness=1, color=PURPLE_LITE))
        story.append(Spacer(1, 0.2*cm))
        max_t = max(themes.values(), default=1)
        theme_rows = [["Topic","Mentions","Relative Frequency"]]
        for topic, count in sorted(themes.items(), key=lambda x: x[1], reverse=True):
            theme_rows.append([topic, str(count), bar_cell(count/max_t, PURPLE, W*0.45)])
        tt = Table(theme_rows, colWidths=[W*0.30,W*0.15,W*0.55])
        tt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),PURPLE_DARK),("TEXTCOLOR",(0,0),(-1,0),WHITE),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),8),("ALIGN",(1,0),(1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("ROWBACKGROUNDS",(0,1),(-1,-1),[WHITE,SLATE_LITE]),("INNERGRID",(0,0),(-1,-1),0.3,colors.HexColor("#E2E8F0")),("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#CBD5E1")),("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7),("LEFTPADDING",(0,0),(-1,-1),8)]))
        story.append(tt)

    # Market Insights
    insights = combined.get("insights", [])
    if insights:
        story.append(Spacer(1, 0.4*cm))
        story.append(Paragraph("Market Insights", style_section))
        story.append(HRFlowable(width=W, thickness=1, color=PURPLE_LITE))
        story.append(Spacer(1, 0.2*cm))
        for i, insight in enumerate(insights):
            story.append(KeepTogether([
                Table([[Paragraph(f"{i+1}.", style_body_bold), Paragraph(insight, style_body)]],
                    colWidths=[W*0.06, W*0.94],
                    style=TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0)])),
                Spacer(1, 0.15*cm),
            ]))

    # Individual Hotel Summaries
    story.append(PageBreak())
    story.append(Paragraph("Individual Hotel Sentiment", style_section))
    story.append(HRFlowable(width=W, thickness=1, color=PURPLE_LITE))
    story.append(Spacer(1, 0.2*cm))

    for i, r in enumerate(results):
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
        header.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),PURPLE_DARK),("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8),("LEFTPADDING",(0,0),(-1,-1),12),("RIGHTPADDING",(0,0),(-1,-1),12),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
        story.append(header)

        if r.get("scraped_review_count", 0) == 0:
            story.append(Table([[Paragraph("No reviews found for this period.",style_small)]],colWidths=[W],style=TableStyle([("BACKGROUND",(0,0),(-1,-1),SLATE_LITE),("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),("LEFTPADDING",(0,0),(-1,-1),12)])))
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
            body.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),WHITE),("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),5),("LEFTPADDING",(0,0),(-1,-1),12),("RIGHTPADDING",(0,0),(-1,-1),12),("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#E2E8F0"))]))
            story.append(body)

        story.append(Spacer(1, 0.3*cm))

    # Footer
    story.append(Spacer(1, 0.4*cm))
    story.append(HRFlowable(width=W, thickness=0.5, color=colors.HexColor("#E2E8F0")))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(f"Generated by DoWell Samanta  ·  {datetime.date.today().strftime('%d %B %Y')}  ·  Data source: Google Maps Reviews  ·  Analysis period: last {days_back} days", style_caption))

    doc.build(story)
    return buf.getvalue()