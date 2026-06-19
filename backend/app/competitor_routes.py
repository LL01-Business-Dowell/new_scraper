"""
competitor_routes.py
---------------------
FastAPI routes for competitor search, approval, and SWOT analysis.
Integrates google_maps_scraper.py and swot_analyzer.py
"""

import uuid
import logging
from typing import Optional, List
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
import requests

import datetime
import os

from .google_maps_scraper import search_google_maps_competitors
from .swot_analyzer import analyze_batch_swot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/competitors", tags=["competitors"])

# In-memory task store for competitor analysis
competitor_tasks = {}

CRUD_BASE_URL = os.getenv("CRUD_BASE_URL", "https://datacube.uxlivinglab.online/api/v2")
CRUD_API_KEY = os.getenv("CRUD_API_KEY", "")
SAMANTA_DATABASE_ID = os.getenv("SAMANTA_DATABASE_ID", "")
SEARCH_COLLECTION = "competitor_searches"

def _save_competitor_search(task_id, keyword, city, country, radius_km, establishment_name, places_found):
    """Save competitor search input to Datacube v2. Never raises — failure never blocks the search."""
    if not CRUD_API_KEY or not SAMANTA_DATABASE_ID:
        logger.warning("[COMPETITOR] Datacube credentials not set — skipping save.")
        return
    try:
        resp = requests.post(
            f"{CRUD_BASE_URL.rstrip('/')}/crud/",
            json={
                "database_id":     SAMANTA_DATABASE_ID,
                "collection_name": SEARCH_COLLECTION,
                "documents": [{
                    "task_id":            task_id,
                    "keyword":            keyword,
                    "city":               city,
                    "country":            country,
                    "radius_km":          radius_km,
                    "establishment_name": establishment_name,
                    "places_found":       places_found,
                    "created_at":         datetime.datetime.utcnow().isoformat() + "Z",
                }],
            },
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Api-Key {CRUD_API_KEY}",
            },
            timeout=10,
        )
        if resp.status_code in (200, 201):
            logger.info(f"[COMPETITOR] Search saved to Datacube — task_id={task_id} keyword={keyword} city={city}")
        else:
            logger.warning(f"[COMPETITOR] Datacube save failed {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        logger.error(f"[COMPETITOR] Datacube save error: {e}")

class SearchRequest(BaseModel):
    """Request to search for competitors on Google Maps."""
    keyword: str
    city: str
    country: str
    establishment_name: str
    location_hint: str = ""
    radius_km: float = 5.0
    limit: int = 100
    origin_lat: float = None
    origin_lng: float = None


class ApproveListRequest(BaseModel):
    """Request to approve/edit the competitor list and start analysis."""
    task_id: str
    approved_places: List[dict]  # List of place dicts with "selected": True/False


@router.post("/search")
async def search_competitors(request: SearchRequest, background_tasks: BackgroundTasks):
    """
    Search Google Maps for competitors matching keyword in city + radius.
    
    Returns immediately with task_id.
    Frontend polls GET /competitors/progress/{task_id} to get results.
    """
    task_id = str(uuid.uuid4())
    
    logger.info(
        f"[COMPETITOR SEARCH] task_id={task_id} "
        f"keyword={request.keyword} city={request.city} radius={request.radius_km}km"
    )
    
    # Store task
    competitor_tasks[task_id] = {
        "status": "searching",
        "progress": 0,
        "status_message": "Initializing Google Maps search...",
        "places": [],
        "error": None,
    }
    
    # Run search in background
    background_tasks.add_task(
        _search_worker,
        task_id=task_id,
        keyword=request.keyword,
        city=request.city,
        country=request.country,
        location_hint=request.location_hint,
        radius_km=request.radius_km,
        limit=request.limit,
        establishment_name=request.establishment_name,
        origin_lat=request.origin_lat,
        origin_lng=request.origin_lng,
    )
    
    return {"task_id": task_id}


def _search_worker(task_id: str, keyword: str, city: str, country: str, location_hint: str, radius_km: float, limit: int, origin_lat: float, origin_lng:float, establishment_name: str):
    """Background worker to search for competitors."""
    try:
        def progress_callback(current, total, status_text):
            competitor_tasks[task_id]["progress"] = int((current / total) * 90)
            competitor_tasks[task_id]["status_message"] = status_text
        
        places = search_google_maps_competitors(
            keyword=keyword,
            city=location_hint or city,
            establishment_name=establishment_name,
            radius_km=radius_km,
            limit=limit,
            origin_lat=origin_lat,
            origin_lng=origin_lng,
            progress_callback=progress_callback,
        )
        
        # Add the establishment itself as the first entry
        establishment = {
            "name": establishment_name,
            "address": f"{city}, {keyword} area",
            "rating": None,
            "reviews": 0,
            "url": "",
            "selected": True,
            "is_user_establishment": True,
        }
        places.insert(0, establishment)
        
        competitor_tasks[task_id]["places"] = places
        competitor_tasks[task_id]["status"] = "ready_for_approval"
        competitor_tasks[task_id]["progress"] = 100
        competitor_tasks[task_id]["status_message"] = f"Found {len(places)} places. Please review and approve."
        
        logger.info(f"[COMPETITOR SEARCH] task_id={task_id} completed. Found {len(places)} places.")

        _save_competitor_search(
            task_id=task_id,
            keyword=keyword,
            city=city,
            country=country,          
            radius_km=radius_km,
            establishment_name=establishment_name,
            places_found=len(places),
        )
        
    except Exception as e:
        logger.error(f"[COMPETITOR SEARCH] task_id={task_id} failed: {str(e)}")
        competitor_tasks[task_id]["status"] = "error"
        competitor_tasks[task_id]["error"] = str(e)
        competitor_tasks[task_id]["progress"] = 100


@router.get("/progress/{task_id}")
async def get_progress(task_id: str):
    """
    Poll the progress of a competitor search or analysis task.
    """
    if task_id not in competitor_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = competitor_tasks[task_id]
    
    return {
        "task_id": task_id,
        "status": task["status"],
        "progress": task["progress"],
        "status_message": task.get("status_message", ""),
        "places": task.get("places", []),
        "error": task.get("error"),
        "swot_results": task.get("swot_results"),
        "competitive_analysis": task.get("competitive_analysis"),
    }


@router.post("/approve-and-analyze")
async def approve_and_analyze(request: ApproveListRequest, background_tasks: BackgroundTasks):
    """
    User approves/edits the competitor list and kicks off SWOT analysis.
    
    Returns immediately with task_id.
    Frontend polls GET /competitors/progress/{task_id} for results.
    """
    if request.task_id not in competitor_tasks:
        raise HTTPException(status_code=404, detail="Original search task not found")
    
    task = competitor_tasks[request.task_id]
    task["status"] = "analyzing"
    task["progress"] = 0
    task["status_message"] = "Starting SWOT analysis..."
    task["approved_places"] = request.approved_places
    
    logger.info(
        f"[COMPETITOR ANALYSIS] task_id={request.task_id} "
        f"analyzing {len([p for p in request.approved_places if p.get('selected')])} places"
    )
    
    # Run analysis in background
    background_tasks.add_task(
        _analysis_worker,
        task_id=request.task_id,
        places=request.approved_places,
    )
    
    return {"task_id": request.task_id, "status": "analyzing"}


def _analysis_worker(task_id: str, places: List[dict]):
    """Background worker to run SWOT analysis on approved places."""
    try:
        def progress_callback(current, total, status_text):
            competitor_tasks[task_id]["progress"] = int((current / total) * 100)
            competitor_tasks[task_id]["status_message"] = status_text
        
        # Run batch SWOT analysis
        analysis_results = analyze_batch_swot(places, progress_callback=progress_callback)
        
        competitor_tasks[task_id]["swot_results"] = analysis_results["individual_analyses"]
        competitor_tasks[task_id]["competitive_analysis"] = analysis_results["competitive_analysis"]
        competitor_tasks[task_id]["status"] = "complete"
        competitor_tasks[task_id]["progress"] = 100
        competitor_tasks[task_id]["status_message"] = "Analysis complete!"
        
        logger.info(
            f"[COMPETITOR ANALYSIS] task_id={task_id} completed. "
            f"Analyzed {len(analysis_results['individual_analyses'])} places."
        )
        
    except Exception as e:
        logger.error(f"[COMPETITOR ANALYSIS] task_id={task_id} failed: {str(e)}")
        competitor_tasks[task_id]["status"] = "error"
        competitor_tasks[task_id]["error"] = str(e)
        competitor_tasks[task_id]["progress"] = 100

@router.get("/dashboard")
async def get_dashboard_data():
    """
    Returns all saved competitor searches from Datacube for the dashboard.
    """
    if not CRUD_API_KEY or not SAMANTA_DATABASE_ID:
        raise HTTPException(status_code=503, detail="Datacube credentials not configured")
    try:
        resp = requests.get(
            f"{CRUD_BASE_URL.rstrip('/')}/crud/",
            params={
                "database_id":     SAMANTA_DATABASE_ID,
                "collection_name": SEARCH_COLLECTION,
                "filters":         "{}",
                "page":            1,
                "page_size":       500,
            },
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Api-Key {CRUD_API_KEY}",
            },
            timeout=15,
        )
        if resp.status_code == 200:
            body = resp.json()
            return {"searches": body.get("data", [])}
        else:
            logger.warning(f"[DASHBOARD] Datacube query failed {resp.status_code}: {resp.text[:200]}")
            raise HTTPException(status_code=502, detail="Failed to fetch from Datacube")
    except requests.RequestException as e:
        logger.error(f"[DASHBOARD] Datacube error: {e}")
        raise HTTPException(status_code=502, detail=str(e))
    

@router.get("/download-results/{task_id}")
async def download_results(task_id: str, format: str = "json"):
    """
    Download the analysis results as JSON or CSV.
    """
    if task_id not in competitor_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = competitor_tasks[task_id]
    
    if task["status"] != "complete":
        raise HTTPException(status_code=400, detail="Analysis not yet complete")
    
    if format == "json":
        return {
            "individual_analyses": task.get("swot_results", []),
            "competitive_analysis": task.get("competitive_analysis", {}),
        }
    
    elif format == "csv":
        import csv
        from io import StringIO
        from fastapi.responses import StreamingResponse
        
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            "Place Name",
            "Rating",
            "Review Count",
            "Sentiment Score",
            "Strength 1",
            "Strength 2",
            "Strength 3",
            "Weakness 1",
            "Weakness 2",
            "Weakness 3",
            "Opportunity 1",
            "Opportunity 2",
            "Opportunity 3",
            "Threat 1",
            "Threat 2",
            "Threat 3",
        ])
        
        # Write data rows
        for analysis in task.get("swot_results", []):
            swot = analysis.get("swot", {})
            writer.writerow([
                analysis.get("name", ""),
                analysis.get("rating", ""),
                analysis.get("review_count", ""),
                analysis.get("sentiment_score", ""),
                swot.get("strengths", [""])[0],
                swot.get("strengths", ["", ""])[1],
                swot.get("strengths", ["", "", ""])[2],
                swot.get("weaknesses", [""])[0],
                swot.get("weaknesses", ["", ""])[1],
                swot.get("weaknesses", ["", "", ""])[2],
                swot.get("opportunities", [""])[0],
                swot.get("opportunities", ["", ""])[1],
                swot.get("opportunities", ["", "", ""])[2],
                swot.get("threats", [""])[0],
                swot.get("threats", ["", ""])[1],
                swot.get("threats", ["", "", ""])[2],
            ])
        
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=competitor_analysis.csv"}
        )
    
    else:
        raise HTTPException(status_code=400, detail="Unsupported format")


# ── Scrape-all endpoint ────────────────────────────────────────────────────

class ScrapeAllRequest(BaseModel):
    task_id: str
    approved_places: List[dict]


@router.post("/scrape-and-analyze")
async def scrape_and_analyze_all(request: ScrapeAllRequest, background_tasks: BackgroundTasks):
    """
    Takes the approved competitor list, scrapes reviews for each place,
    runs VADER SWOT on real reviews, then produces a combined report.

    Frontend polls GET /competitors/progress/{task_id} — same as before.
    Status flow: searching → scraping → complete
    """
    if request.task_id not in competitor_tasks:
        raise HTTPException(status_code=404, detail="Original search task not found")

    task = competitor_tasks[request.task_id]
    task["status"]         = "scraping"
    task["progress"]       = 0
    task["status_message"] = "Starting review scraping..."
    task["approved_places"] = request.approved_places

    background_tasks.add_task(
        _scrape_all_worker,
        task_id=request.task_id,
        places=request.approved_places,
    )

    return {"task_id": request.task_id, "status": "scraping"}


def _scrape_all_worker(task_id: str, places: List[dict]):
    """
    For each selected place:
      1. Scrape Google Maps reviews using review_scraper.py
      2. Run VADER SWOT on the real reviews
    Then generate combined competitive analysis.
    """
    from .review_scraper import scrape_place_reviews
    from .swot_analyzer import analyze_place_swot, generate_competitive_analysis

    selected = [p for p in places if p.get("selected", True)]
    total    = len(selected)

    logger.info(f"[SCRAPE ALL] task_id={task_id} scraping {total} places")

    individual_results = []
    errors             = []

    for i, place in enumerate(selected):
        place_name = place.get("name", f"Place {i+1}")
        url        = place.get("url", "")

        competitor_tasks[task_id]["status_message"] = (
            f"Scraping {place_name} ({i+1}/{total})..."
        )
        competitor_tasks[task_id]["progress"] = int((i / total) * 90)

        if not url:
            # No URL — use rating-only SWOT
            logger.info(f"[SCRAPE ALL] No URL for {place_name}, using rating-only SWOT")
            swot_result = analyze_place_swot({
                **place,
                "scraped_reviews": [],
            })
            individual_results.append(swot_result)
            continue

        try:
            scraped = scrape_place_reviews(
                url=url,
                max_reviews=50,   # 50 per place keeps total time reasonable
                days_back=30,
            )

            # Merge scraped business details with the Maps listing data
            biz = scraped.get("business_details", {})
            merged_place = {
                **place,
                "name":            biz.get("name") or place.get("name"),
                "address":         biz.get("address") or place.get("address"),
                "rating":          biz.get("rating") or place.get("rating"),
                "scraped_reviews": scraped.get("reviews", []),
            }

            swot_result = analyze_place_swot(merged_place)
            swot_result["scraped_review_count"] = len(scraped.get("reviews", []))
            individual_results.append(swot_result)

            logger.info(
                f"[SCRAPE ALL] {place_name} — "
                f"{len(scraped.get('reviews', []))} reviews scraped, "
                f"sentiment={swot_result.get('sentiment_score')}"
            )

        except Exception as e:
            logger.error(f"[SCRAPE ALL] Failed for {place_name}: {e}")
            errors.append({"name": place_name, "error": str(e)})
            # Still add a fallback entry so the place appears in results
            individual_results.append(analyze_place_swot({
                **place,
                "scraped_reviews": [],
            }))

    # Combined competitive analysis
    competitive = generate_competitive_analysis(individual_results)

    competitor_tasks[task_id]["swot_results"]         = individual_results
    competitor_tasks[task_id]["competitive_analysis"] = competitive
    competitor_tasks[task_id]["scrape_errors"]        = errors
    competitor_tasks[task_id]["status"]               = "complete"
    competitor_tasks[task_id]["progress"]             = 100
    competitor_tasks[task_id]["status_message"]       = (
        f"Done! Analysed {len(individual_results)} places "
        f"({len(errors)} errors)."
    )

    logger.info(
        f"[SCRAPE ALL] task_id={task_id} complete — "
        f"{len(individual_results)} analysed, {len(errors)} errors"
    )