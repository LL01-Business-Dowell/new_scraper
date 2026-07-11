"""
hotel_sentiment_routes.py
--------------------------
FastAPI router for the Hotel Sentiment Analysis feature.
Route prefix: /api/hotel-sentiment

Key difference from competitor_routes.py:
- Search keyword is HARDCODED to "Luxury Hotels near {city}"
  regardless of what the frontend sends
- Analysis produces VADER sentiment per place (not SWOT)
- Combined report is sentiment-focused (not SWOT-focused)
- No Datacube saving
"""

import uuid
import logging
import threading
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory task store — separate from competitor_tasks
hotel_sentiment_tasks = {}


# ── Request models ────────────────────────────────────────────────────────────

class HotelSearchRequest(BaseModel):
    city: str
    country: str
    establishment_name: str
    radius_km: float = 5.0
    limit: int = 100
    origin_lat: Optional[float] = None
    origin_lng: Optional[float] = None


class HotelAnalyzeRequest(BaseModel):
    task_id: str
    approved_places: List[dict]
    establishment_name: str = ""
    days_back: int = 30


# ── Search worker ─────────────────────────────────────────────────────────────

def _hotel_search_worker(
    task_id: str, city: str, radius_km: float, limit: int,
    establishment_name: str, origin_lat: Optional[float], origin_lng: Optional[float],
):
    """
    Searches Google Maps for 'Luxury Hotels near {city}'.
    Keyword is hardcoded — frontend keyword is ignored entirely.
    """
    try:
        from .google_maps_scraper import search_google_maps_competitors

        # HARDCODED keyword — this is the core behaviour of this route
        keyword = f"Luxury Hotels near {city}"
        logger.info(f"[HOTEL SENTIMENT] task_id={task_id} searching: '{keyword}'")

        def progress(current, total, message):
            hotel_sentiment_tasks[task_id]["progress"] = int((current / max(total,1)) * 90)
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

        # Prepend user's own establishment
        establishment = {
            "name": establishment_name,
            "address": f"{city} area",
            "rating": None,
            "reviews": 0,
            "url": "",
            "selected": True,
            "is_user_establishment": True,
        }
        places.insert(0, establishment)

        hotel_sentiment_tasks[task_id].update({
            "status":         "ready_for_approval",
            "progress":       100,
            "status_message": f"Found {len(places)} luxury hotels. Please review and approve.",
            "places":         places,
        })
        logger.info(f"[HOTEL SENTIMENT] task_id={task_id} search complete. {len(places)} places.")

    except Exception as e:
        logger.error(f"[HOTEL SENTIMENT] Search failed task_id={task_id}: {e}")
        hotel_sentiment_tasks[task_id].update({
            "status": "error", "error": str(e), "progress": 100,
        })


# ── Sentiment analysis worker ─────────────────────────────────────────────────

def _hotel_sentiment_worker(task_id: str, places: List[dict], days_back: int):
    """
    For each selected place:
      1. Scrape reviews (days_back days)
      2. Run VADER sentiment analysis
    Then generate combined sentiment report.
    """
    from .review_scraper import scrape_place_reviews
    from .single_review_scraper import _run_sentiment_analysis

    selected = [p for p in places if p.get("selected", True)]
    total    = len(selected)
    logger.info(f"[HOTEL SENTIMENT] task_id={task_id} analysing {total} places")

    results = []
    errors  = []

    for i, place in enumerate(selected):
        name = place.get("name", f"Place {i+1}")
        url  = place.get("url", "")

        hotel_sentiment_tasks[task_id]["status_message"] = f"Finding reviews for {name} ({i+1}/{total})..."
        hotel_sentiment_tasks[task_id]["progress"]       = int((i / max(total,1)) * 85)

        sentiment = {}
        review_count = 0
        biz_details  = {}

        if url:
            try:
                scraped      = scrape_place_reviews(url=url, max_reviews=50, days_back=days_back)
                biz_details  = scraped.get("business_details", {})
                reviews      = scraped.get("reviews", [])
                review_count = len(reviews)
                sentiment    = _run_sentiment_analysis(reviews)
                logger.info(f"[HOTEL SENTIMENT] {name} — {review_count} reviews, score={sentiment.get('overall_score')}")
            except Exception as e:
                logger.error(f"[HOTEL SENTIMENT] Scrape failed for {name}: {e}")
                errors.append({"name": name, "error": str(e)})
        else:
            logger.info(f"[HOTEL SENTIMENT] No URL for {name} — rating-only entry")

        results.append({
            "name":                 biz_details.get("name") or name,
            "address":              biz_details.get("address") or place.get("address", ""),
            "rating":               biz_details.get("rating") or place.get("rating"),
            "google_review_count":  biz_details.get("total_reviews") or place.get("reviews", 0),
            "scraped_review_count": review_count,
            "url":                  url,
            "is_user_establishment": place.get("is_user_establishment", False),
            "distance_km":          place.get("distance_km"),
            "sentiment":            sentiment,
        })

    # Combined report
    combined = _build_combined_sentiment_report(results)

    hotel_sentiment_tasks[task_id].update({
        "status":           "complete",
        "progress":         100,
        "status_message":   f"Done! Analysed {len(results)} hotels ({len(errors)} errors).",
        "results":          results,
        "combined_report":  combined,
        "errors":           errors,
    })
    logger.info(f"[HOTEL SENTIMENT] task_id={task_id} complete.")


def _build_combined_sentiment_report(results: List[dict]) -> dict:
    """Build a combined sentiment landscape from individual results."""
    with_sentiment = [r for r in results if r.get("sentiment", {}).get("overall_score") is not None]
    with_rating    = [r for r in results if r.get("rating")]

    if not with_sentiment:
        return {}

    scores   = [r["sentiment"]["overall_score"] for r in with_sentiment]
    avg_score = round(sum(scores) / len(scores), 3)

    if avg_score > 0.5:   market_label = "Very Positive"
    elif avg_score > 0.2: market_label = "Positive"
    elif avg_score > -0.2:market_label = "Mixed / Neutral"
    elif avg_score > -0.5:market_label = "Negative"
    else:                 market_label = "Very Negative"

    avg_rating = round(sum(r["rating"] for r in with_rating) / len(with_rating), 2) if with_rating else None

    # Sentiment ranking — sorted best to worst
    ranked = sorted(
        with_sentiment,
        key=lambda r: r["sentiment"].get("overall_score", -99),
        reverse=True,
    )

    best  = ranked[0]  if ranked else None
    worst = ranked[-1] if len(ranked) > 1 else None

    # Aggregate keyword themes across all places
    combined_themes = {}
    for r in results:
        for theme, count in r.get("sentiment", {}).get("keyword_themes", {}).items():
            combined_themes[theme] = combined_themes.get(theme, 0) + count

    # Total positive/neutral/negative counts
    total_pos = sum(r["sentiment"].get("positive_count", 0) for r in with_sentiment)
    total_neu = sum(r["sentiment"].get("neutral_count",  0) for r in with_sentiment)
    total_neg = sum(r["sentiment"].get("negative_count", 0) for r in with_sentiment)
    total_all = total_pos + total_neu + total_neg or 1

    # Sentiment distribution across places
    positive_places = sum(1 for r in with_sentiment if r["sentiment"].get("overall_score", 0) > 0.2)
    neutral_places  = sum(1 for r in with_sentiment if -0.2 <= r["sentiment"].get("overall_score", 0) <= 0.2)
    negative_places = sum(1 for r in with_sentiment if r["sentiment"].get("overall_score", 0) < -0.2)

    # Insights
    insights = []
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
    insights.append(f"Analysis based on {total_scraped:,} reviews scraped across {len(results)} hotels over the selected period.")

    return {
        "total_analysed":       len(results),
        "with_sentiment":       len(with_sentiment),
        "avg_sentiment_score":  avg_score,
        "market_label":         market_label,
        "avg_rating":           avg_rating,
        "sentiment_ranking":    [{"name": r["name"], "score": r["sentiment"].get("overall_score"), "label": r["sentiment"].get("overall_label"), "rating": r.get("rating")} for r in ranked],
        "best_sentiment":       {"name": best["name"], "score": best["sentiment"].get("overall_score")} if best else None,
        "worst_sentiment":      {"name": worst["name"], "score": worst["sentiment"].get("overall_score")} if worst else None,
        "total_positive":       total_pos,
        "total_neutral":        total_neu,
        "total_negative":       total_neg,
        "positive_pct":         round(total_pos / total_all * 100, 1),
        "neutral_pct":          round(total_neu / total_all * 100, 1),
        "negative_pct":         round(total_neg / total_all * 100, 1),
        "positive_places":      positive_places,
        "neutral_places":       neutral_places,
        "negative_places":      negative_places,
        "combined_themes":      dict(sorted(combined_themes.items(), key=lambda x: x[1], reverse=True)),
        "insights":             insights,
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/search")
async def hotel_search(request: HotelSearchRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    hotel_sentiment_tasks[task_id] = {
        "status": "searching", "progress": 0,
        "status_message": f"Searching for Luxury Hotels near {request.city}...",
        "places": [], "error": None, "city": request.city,
        "days_back": request.days_back if hasattr(request, 'days_back') else 30,
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
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "status":          task["status"],
        "progress":        task["progress"],
        "status_message":  task["status_message"],
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
        raise HTTPException(status_code=404, detail="Task not found")

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
    """Generate and stream a professional PDF sentiment report."""
    task = hotel_sentiment_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["status"] != "complete":
        raise HTTPException(status_code=400, detail="Analysis not complete yet")
    try:
        import io, datetime
        pdf_bytes = _generate_sentiment_pdf(task)
        combined  = task.get("combined_report", {})
        city      = task.get("city", "")
        filename  = f"hotel-sentiment-{city.replace(' ','-')}-{datetime.date.today()}.pdf"
        from fastapi.responses import StreamingResponse
        return StreamingResponse(
            io.BytesIO(pdf_bytes), media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error(f"[HOTEL SENTIMENT] PDF generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")


def _generate_sentiment_pdf(task: dict) -> bytes:
    import io, datetime, math
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, PageBreak, KeepTogether,
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

    results  = task.get("results", [])
    combined = task.get("combined_report", {})
    days_back = task.get("days_back", 30)

    # ── Colours ──────────────────────────────────────────────────────────────
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

    # ── Cover ─────────────────────────────────────────────────────────────────
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

    # ── KPI tiles ─────────────────────────────────────────────────────────────
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

    # ── Sentiment breakdown ───────────────────────────────────────────────────
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

    # ── Sentiment ranking ─────────────────────────────────────────────────────
    ranking = combined.get("sentiment_ranking", [])
    if ranking:
        story.append(Paragraph("Sentiment Ranking", style_section))
        story.append(HRFlowable(width=W, thickness=1, color=PURPLE_LITE))
        story.append(Spacer(1, 0.2*cm))
        rank_rows = [["#","Hotel","Sentiment","Score","Rating"]]
        for i, r in enumerate(ranking):
            sc = r.get("score")
            sc_color = "#059669" if sc and sc>0.2 else ("#DC2626" if sc and sc<-0.2 else "#B45309")
            rank_rows.append([
                str(i+1),
                Paragraph(r.get("name",""),style_body),
                Paragraph(f'<font color="{sc_color}">{r.get("label","")}</font>',style_body),
                Paragraph(f'<font color="{sc_color}">{f"{sc:+.3f}" if sc is not None else "—"}</font>',style_body_bold),
                f"★ {r['rating']}" if r.get("rating") else "—",
            ])
        rt = Table(rank_rows, colWidths=[W*0.06,W*0.38,W*0.25,W*0.15,W*0.16])
        rt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),PURPLE_DARK),("TEXTCOLOR",(0,0),(-1,0),WHITE),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),8),("ALIGN",(0,0),(0,-1),"CENTER"),("ALIGN",(3,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("ROWBACKGROUNDS",(0,1),(-1,-1),[WHITE,SLATE_LITE]),("INNERGRID",(0,0),(-1,-1),0.3,colors.HexColor("#E2E8F0")),("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#CBD5E1")),("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7),("LEFTPADDING",(0,0),(-1,-1),8)]))
        story.append(rt)

    # ── Topic frequency ───────────────────────────────────────────────────────
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

    # ── Market insights ───────────────────────────────────────────────────────
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

    # ── Individual hotel summaries ────────────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("Individual Hotel Sentiment", style_section))
    story.append(HRFlowable(width=W, thickness=1, color=PURPLE_LITE))
    story.append(Spacer(1, 0.2*cm))

    for i, r in enumerate(results):
        s = r.get("sentiment", {})
        sc = s.get("overall_score")
        sc_color = GREEN if sc and sc>0.2 else (RED if sc and sc<-0.2 else AMBER)
        pos = s.get("positive_count",0); neu = s.get("neutral_count",0); neg = s.get("negative_count",0); total = pos+neu+neg or 1

        header = Table([[
            Paragraph(f"{'★ ' if r.get('is_user_establishment') else ''}{r.get('name','')}", ParagraphStyle("HN",fontSize=10,leading=14,textColor=WHITE if not r.get('is_user_establishment') else AMBER,fontName="Helvetica-Bold")),
            Paragraph(f"{s.get('overall_label','No Data')} · {f'{sc:+.3f}' if sc is not None else '—'}" + (f" · ★ {r['rating']}" if r.get('rating') else ""), ParagraphStyle("HS",fontSize=8,leading=12,textColor=PURPLE_LITE,fontName="Helvetica",alignment=TA_RIGHT)),
        ]], colWidths=[W*0.6, W*0.4])
        header.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),PURPLE_DARK),("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8),("LEFTPADDING",(0,0),(-1,-1),12),("RIGHTPADDING",(0,0),(-1,-1),12),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
        story.append(header)

        if r.get("scraped_review_count",0) == 0:
            story.append(Table([[Paragraph("No reviews scraped for this period.",style_small)]],colWidths=[W],style=TableStyle([("BACKGROUND",(0,0),(-1,-1),SLATE_LITE),("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),("LEFTPADDING",(0,0),(-1,-1),12)])))
        else:
            body_rows = [
                [Paragraph(f"Reviews scraped: {r.get('scraped_review_count',0)}  ·  Positive: {pos} ({pos/total*100:.0f}%)  ·  Neutral: {neu} ({neu/total*100:.0f}%)  ·  Negative: {neg} ({neg/total*100:.0f}%)", style_small)],
            ]
            # Top positive snippet
            if s.get("top_positive_phrases"):
                p0 = s["top_positive_phrases"][0]
                body_rows.append([Paragraph(f'<font color="#059669">✓ {p0.get("author","")} ({p0.get("date","")}):</font> "{p0.get("text","")}"', style_italic)])
            # Top negative snippet
            if s.get("top_negative_phrases"):
                n0 = s["top_negative_phrases"][0]
                body_rows.append([Paragraph(f'<font color="#DC2626">✗ {n0.get("author","")} ({n0.get("date","")}):</font> "{n0.get("text","")}"', style_italic)])

            body = Table(body_rows, colWidths=[W])
            body.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),WHITE),("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),5),("LEFTPADDING",(0,0),(-1,-1),12),("RIGHTPADDING",(0,0),(-1,-1),12),("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#E2E8F0"))]))
            story.append(body)

        story.append(Spacer(1, 0.3*cm))

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.4*cm))
    story.append(HRFlowable(width=W, thickness=0.5, color=colors.HexColor("#E2E8F0")))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(f"Generated by DoWell Samanta Scraper  ·  {datetime.date.today().strftime('%d %B %Y')}  ·  Data source: Google Maps Reviews  ·  Analysis period: last {days_back} days", style_caption))

    doc.build(story)
    return buf.getvalue()